# brain/vision/bench_pi.py
# Version 0.3 (08.11.2026) – Geschwindigkeit von Qwen3.5-4B (Text und Bild) auf dem Pi 5.
# V0.6: Messung „anderer Inhalt“: gleiche Aufgabe, gleicher fester Teil, anderer Zustand bzw. Satz
#       (zweimal hintereinander). So ist es im Betrieb; „wiederholt“ (identischer Prompt) ist der
#       Bestfall. Wichtig für Qwen3.5 (hybrid/rekurrent): der Server kann den Cache nur über
#       Checkpoints zurücksetzen.
# V0.5: Server-Speicher getrennt: RssAnon (echter Arbeitsspeicher: KV-Cache, Puffer, mmproj)
#       und RssFile (eingeblendete Modelldatei). VmRSS zählte beides zusammen.
# V0.4: --slots N (ein Slot je Aufgabe wie ServerBrain; Server mit -np N): erst alle Aufgaben
#       einmal rechnen, dann misst „nach Wechsel“, ob der Slot-Cache den Wechsel übersteht.
#       Text-Aufgaben mit den echten Grammatiken (GBNF) wie im Betrieb.
# V0.3: --label, Modell und mmproj aus /props im Bericht, Prompt-Rate der Text-Aufgaben,
#       Kennzahlen kompakt im JSON (für run_pi_matrix.sh).
# V0.2: --text-only für Modelle ohne Bildeingabe (Vergleich mit Qwen3-4B).
#
# Frage: Ist die Inferenz auf dem Pi für die Pipeline praktisch nutzbar?
# Gemessen über llama-server (Aufbau und Start: brain/vision/README.md):
#   1. Bildfragen bei mehreren Bildgrößen (--sizes): Zeit je Bild, Bild-Tokens,
#      Prompt- und Erzeugungsgeschwindigkeit. Zwei realistische Fragen:
#      "Welche der 40 Dinge sind zu sehen?" (Liste) und "Ist eine Getränkedose zu sehen?" (ja/nein).
#   2. Die echten Brain-Aufgaben ohne Bild (Zielwahl, Chat, Objekt, Suchorte), jeweils
#      nach einem Aufgabenwechsel (fester Teil muss neu gerechnet werden) und direkt
#      wiederholt (fester Teil im Cache).
#   3. Randbedingungen: Speicher des Servers, freier Speicher, CPU-Temperatur und
#      Drosselung (vcgencmd) vor und nach dem Lauf.
# Messbedingung wie im Denk-Zustand: Perzeption und Motion aus, nur llama-server läuft.
#
# Aufruf auf dem Pi aus src_dev/ai (nur Standardbibliothek + Pillow):
#   python -m brain.vision.bench_pi --images ~/vlm_pi_subset/val2017 -n 10 --sizes 320,448,640
# Ergebnis: brain/ergebnisse/<Datum>/pi_bench_<Uhrzeit>.md und .json

from __future__ import annotations

import argparse
import base64
import io
import json
import os
import platform
import statistics
import subprocess
import time
import urllib.error
import urllib.request

from .. import semantic as S
from ..behaviors import build_options
from ..llm import slot_of
from ..prompt import grammar as decision_grammar
from ..prompt import messages as decision_messages
from ..prompt import state_text
from ..safety import check
from ..scenarios import SCENARIOS, prepare
from .compare_vlm import NAMES, check_server, out_paths

LIST_PROMPT = ("Which of these objects are visible in the image? Only list objects you can clearly see. "
               "Allowed names: " + ", ".join(NAMES) + '. Answer as JSON: {"objects": [...]}')
LIST_SCHEMA = {"type": "object", "properties": {"objects": {"type": "array", "items": {"type": "string", "enum": NAMES}}},
               "required": ["objects"]}
CAN_PROMPT = 'Ist im Bild eine Getränkedose zu sehen? Antworte als JSON: {"antwort": "ja"} oder {"antwort": "nein"}'
CAN_SCHEMA = {"type": "object", "properties": {"antwort": {"type": "string", "enum": ["ja", "nein"]}},
              "required": ["antwort"]}


# ---------------------------------------------------------------- Server
def _jpeg_b64(path: str, side: int) -> tuple[str, tuple]:
    from PIL import Image
    im = Image.open(path).convert("RGB")
    im.thumbnail((side, side))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=90)
    return base64.b64encode(buf.getvalue()).decode(), im.size


def call(url: str, msgs: list, schema: dict | None, max_tokens: int, timeout: float,
         gbnf: str | None = None, slot: int | None = None) -> dict:
    body = {"messages": msgs, "temperature": 0.0, "max_tokens": max_tokens, "cache_prompt": True,
            "chat_template_kwargs": {"enable_thinking": False}}
    if schema:
        body["response_format"] = {"type": "json_schema", "json_schema": {"name": "a", "schema": schema}}
    if gbnf:
        body["grammar"] = gbnf
    if slot is not None:
        body["id_slot"] = slot
    req = urllib.request.Request(url.rstrip("/") + "/v1/chat/completions", json.dumps(body).encode(),
                                 {"Content-Type": "application/json"})
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            out = json.loads(r.read())
    except urllib.error.HTTPError as e:
        if not gbnf or e.code != 400:
            raise
        print(f"   Server lehnt grammar ab ({e.code}), Messung ohne Grammatik", flush=True)
        return call(url, msgs, schema, max_tokens, timeout, None, slot)
    wall = time.perf_counter() - t0
    tm = out.get("timings", {}) or {}
    return {"wall_s": round(wall, 2),
            "prompt_n": tm.get("prompt_n"), "prompt_ms": tm.get("prompt_ms"),
            "cache_n": tm.get("cache_n"), "gen_n": tm.get("predicted_n"), "gen_ms": tm.get("predicted_ms"),
            "text": out["choices"][0]["message"]["content"]}


def server_props(url: str) -> dict:
    """Modell und mmproj, die der Server geladen hat (llama-server /props). [V0.3]"""
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/props", timeout=10) as r:
            p = json.loads(r.read())
    except (OSError, ValueError):
        return {}
    return {"modell": os.path.basename(p.get("model_path") or "") or None,
            "vision": (p.get("modalities") or {}).get("vision")}


def image_msgs(b64: str, prompt: str) -> list:
    return [{"role": "user", "content": [
        {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + b64}},
        {"type": "text", "text": prompt}]}]


# ---------------------------------------------------------------- System
def _read(path: str) -> str | None:
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return None


def system_state() -> dict:
    st = {"zeit": time.strftime("%H:%M:%S")}
    t = _read("/sys/class/thermal/thermal_zone0/temp")
    st["cpu_temp_c"] = round(int(t) / 1000, 1) if t else None
    try:
        st["throttled"] = subprocess.run(["vcgencmd", "get_throttled"], capture_output=True, text=True,
                                         timeout=3).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        st["throttled"] = None
    mem = _read("/proc/meminfo") or ""
    for line in mem.splitlines():
        if line.startswith("MemAvailable:"):
            st["mem_frei_mb"] = int(line.split()[1]) // 1024
    vals = {"VmRSS:": 0, "RssAnon:": 0, "RssFile:": 0}
    for pid in filter(str.isdigit, os.listdir("/proc") if os.path.isdir("/proc") else []):
        if (_read(f"/proc/{pid}/comm") or "").startswith("llama-server"):
            for line in (_read(f"/proc/{pid}/status") or "").splitlines():
                k = line.split(":", 1)[0] + ":"
                if k in vals:
                    vals[k] += int(line.split()[1]) // 1024
    st["server_rss_mb"] = vals["VmRSS:"] or None
    st["server_anon_mb"] = vals["RssAnon:"] or None      # [V0.5]
    st["server_datei_mb"] = vals["RssFile:"] or None
    return st


# ---------------------------------------------------------------- Brain-Aufgaben (ohne Bild)
TASK_KIND = {"zielwahl": "zielwahl", "chat": "chat", "objekt": "objekt", "suchorte": "suchen"}


VARIANTS = [   # (Szenario für die Zielwahl, Chat-Satz, Objekt, Suchgegenstand); [V0.6] 0 = Standard
    (1, "Marco: Wo ist die Fernbedienung?", ("katze", "wohnzimmer"), "tasse"),
    (2, "Laura: Hast du meinen Rucksack gesehen?", ("koffer", "flur"), "handy"),
    (3, "Marco: Komm mal bitte in die Küche.", ("teddy", "küche"), "fernbedienung"),
]


def brain_tasks(variant: int = 0) -> dict:
    """Name -> (Nachrichten, Grammatik, max_tokens). Grammatiken wie im Betrieb (V0.4).
    variant: anderer Zustand/Satz bei gleichem festem Prompt-Teil (V0.6)."""
    sc_i, chat, (obj, ort), item = VARIANTS[variant]
    sc = SCENARIOS[sc_i]
    mem, nm, st = prepare(sc)
    menu = build_options(sc.obs, st, mem, check(sc.obs))
    places = ["flur", "küche", "bad", "wohnzimmer"]
    return {
        "zielwahl": (decision_messages(state_text(sc.obs, st, menu, sc.triggers)), decision_grammar(len(menu)), 120),
        "chat": (S._messages(S.CHAT_SYSTEM, S.CHAT_SHOTS, chat), S.CHAT_GBNF, 100),
        "objekt": (S._messages(S.OBJECT_SYSTEM, S.OBJECT_SHOTS, f"GEGENSTAND: {obj}\nORT: {ort}"),
                   S.OBJECT_GBNF, 100),
        "suchorte": (S._messages(S.SEARCH_SYSTEM, S.SEARCH_SHOTS, f"GEGENSTAND: {item}\nORTE: " + ", ".join(places)),
                     S.search_gbnf(places), 100),
    }


def med(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.median(xs), 2) if xs else None


def rate(n, ms):
    return round(n / (ms / 1000), 1) if n and ms else None


def summarize(paths: list[str]) -> str:
    """Mehrere pi_bench_*.json nebeneinander (für run_pi_matrix.sh). [V0.3]"""
    runs = []
    for p in paths:
        with open(p, encoding="utf-8") as f:
            runs.append(json.load(f))
    sizes = sorted({int(k) for r in runs for k in r.get("bild", {})})
    tasks = ["zielwahl", "chat", "objekt", "suchorte"]
    head = ["Lauf", "Modell", "mmproj", "Slots"] + [f"Dose {s} px" for s in sizes] + \
           [f"{t} Wechsel / wiederholt / anders" for t in tasks] + ["Prompt tok/s (Zielwahl)", "Erzeugung tok/s", "Server anon MB", "Server Datei MB", "frei MB", "°C Ende"]
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for r in runs:
        b, t, en = r.get("bild", {}), r.get("text", {}), r.get("ende", {})
        row = [r.get("label") or "-", r.get("modell") or "?", r.get("mmproj") or "–", str(r.get("slots", 1))]
        row += [f"{b[str(s)]['dose_s']} s" if str(s) in b else "–" for s in sizes]
        for k in tasks:
            x = t.get(k)
            an = "/".join(str(o["wall_s"]) for o in (x or {}).get("anders", [])) or "–"
            row.append(f"{x['wechsel']['wall_s']} / {x['wiederholt']['wall_s']} / {an} s" if x else "–")
        z = t.get("zielwahl") or {}
        row += [str(z.get("prompt_tok_s")), str(z.get("gen_tok_s")), str(en.get("server_anon_mb")),
                str(en.get("server_datei_mb")), str(en.get("mem_frei_mb")), str(en.get("cpu_temp_c"))]
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description="SLARC Brain: VLM- und LLM-Geschwindigkeit auf dem Pi 5")
    ap.add_argument("--url", default="http://127.0.0.1:8080")
    ap.add_argument("--images", help="Ordner mit JPEGs (z. B. ~/vlm_pi_subset/val2017)")
    ap.add_argument("--text-only", action="store_true", help="nur Brain-Aufgaben ohne Bild (Modell ohne mmproj)")
    ap.add_argument("-n", type=int, default=10)
    ap.add_argument("--sizes", default="320,448,640", help="längste Bildkante in px, kommagetrennt")
    ap.add_argument("--no-text", action="store_true", help="Brain-Aufgaben ohne Bild überspringen")
    ap.add_argument("--timeout", type=float, default=600.0)
    ap.add_argument("--slots", type=int, default=1, help="ein Slot je Aufgabe (Server mit -np N)")
    ap.add_argument("--label", default="", help="Name des Laufs in Bericht und Dateiname, z. B. q35-4b-q8")
    ap.add_argument("--mmproj", default="", help="nur für den Bericht: welches mmproj der Server nutzt")
    ap.add_argument("--summarize", nargs="+", metavar="JSON", help="nur Übersicht aus vorhandenen pi_bench-JSONs")
    a = ap.parse_args()
    if a.summarize:
        table = summarize(a.summarize)
        md, _ = out_paths("pi_matrix")
        with open(md, "w", encoding="utf-8") as f:
            f.write(f"# Pi-Messreihe {time.strftime('%d.%m.%Y %H:%M')}\n\n{table}\n")
        print(table + f"\n\nÜbersicht: {md}")
        return
    if a.text_only:
        a.no_text, files, sizes = False, [], []
    else:
        if not a.images:
            raise SystemExit("--images angeben (oder --text-only).")
        try:
            import PIL  # noqa: F401
        except ImportError:
            raise SystemExit("Pillow fehlt: pip install pillow (nötig, damit die Bildgröße wirklich gilt).")
        files = sorted(f for f in os.listdir(os.path.expanduser(a.images)) if f.lower().endswith((".jpg", ".jpeg", ".png")))
        files = [os.path.join(os.path.expanduser(a.images), f) for f in files[:a.n]]
        sizes = [int(x) for x in a.sizes.split(",")]
    check_server(a.url)
    res = {"rechner": platform.node(), "maschine": platform.machine(), "bilder": len(files), "start": system_state(),
           "label": a.label, "mmproj": a.mmproj or None, "slots": a.slots, **server_props(a.url), "bild": {}, "text": {}}
    print(f"Modell: {res.get('modell')}, mmproj: {res['mmproj']}, Label: {a.label or '-'}", flush=True)
    print(f"{len(files)} Bilder, Größen {sizes}. Start: {res['start']}", flush=True)

    # Aufwärmen (Modell in den Speicher, erste Kernel), nicht gewertet
    if files:
        b64, _ = _jpeg_b64(files[0], sizes[0])
        call(a.url, image_msgs(b64, CAN_PROMPT), CAN_SCHEMA, 10, a.timeout)
    else:
        call(a.url, [{"role": "user", "content": "Hallo"}], None, 5, a.timeout)

    img_slot = slot_of("bild", a.slots) if a.slots > 1 else None
    for side in sizes:
        rows = []
        for k, path in enumerate(files, 1):
            b64, wh = _jpeg_b64(path, side)
            r_list = call(a.url, image_msgs(b64, LIST_PROMPT), LIST_SCHEMA, 120, a.timeout, slot=img_slot)
            r_can = call(a.url, image_msgs(b64, CAN_PROMPT), CAN_SCHEMA, 10, a.timeout, slot=img_slot)
            rows.append({"bild": os.path.basename(path), "px": wh, "liste": r_list, "dose": r_can})
            print(f"[{side} px {k}/{len(files)}] {os.path.basename(path)} {wh[0]}x{wh[1]}: "
                  f"Liste {r_list['wall_s']} s ({r_list['prompt_n']} Prompt-Tokens), Dose {r_can['wall_s']} s "
                  f"-> {r_can['text']}", flush=True)
        res["bild"][side] = {
            "liste_s": med([r["liste"]["wall_s"] for r in rows]),
            "dose_s": med([r["dose"]["wall_s"] for r in rows]),
            "prompt_tokens": med([r["dose"]["prompt_n"] for r in rows]),
            "prompt_tok_s": med([rate(r["dose"]["prompt_n"], r["dose"]["prompt_ms"]) for r in rows]),
            "gen_tok_s": med([rate(r["liste"]["gen_n"], r["liste"]["gen_ms"]) for r in rows]),
            "rows": rows,
        }

    if not a.no_text:
        tasks = brain_tasks()
        names = list(tasks)
        slot = {n: (slot_of(TASK_KIND[n], a.slots) if a.slots > 1 else None) for n in names}
        if a.slots > 1:                                                   # jeder Slot kennt seine Aufgabe
            for n in names:
                call(a.url, tasks[n][0], None, 1, a.timeout, slot=slot[n])
        for name in names:
            msgs, gbnf, mt = tasks[name]
            on = names[(names.index(name) + 1) % len(names)]
            call(a.url, tasks[on][0], None, 5, a.timeout, slot=slot[on])  # andere Aufgabe dazwischen
            cold = call(a.url, msgs, None, mt, a.timeout, gbnf, slot[name])   # nach Aufgabenwechsel
            warm = call(a.url, msgs, None, mt, a.timeout, gbnf, slot[name])   # gleicher Prompt direkt wieder
            other = []                                                    # [V0.6] anderer Inhalt, wie im Betrieb
            for v in (1, 2):
                vm, vg, vt = brain_tasks(v)[name]
                other.append(call(a.url, vm, None, vt, a.timeout, vg, slot[name]))
            res["text"][name] = {"wechsel": cold, "wiederholt": warm, "anders": other,
                                 "prompt_tok_s": rate(cold["prompt_n"], cold["prompt_ms"]),
                                 "gen_tok_s": rate(warm["gen_n"], warm["gen_ms"])}
            print(f"[text] {name}: nach Wechsel {cold['wall_s']} s ({cold['prompt_n']} Tokens neu), "
                  f"wiederholt {warm['wall_s']} s ({warm['prompt_n']} Tokens neu), anderer Inhalt "
                  + " / ".join(f"{o['wall_s']} s ({o['prompt_n']})" for o in other), flush=True)
    res["ende"] = system_state()

    md, js = out_paths("pi_bench_" + a.label if a.label else "pi_bench")
    st, en = res["start"], res["ende"]
    lines = [f"# VLM/LLM-Geschwindigkeit auf {res['rechner']} ({res['maschine']}, {time.strftime('%d.%m.%Y %H:%M')})", "",
             f"Modell `{res.get('modell')}`, mmproj `{res['mmproj']}`" + (f", Lauf `{a.label}`" if a.label else "") + ".", "",
             f"{len(files)} Bilder. Temperatur {st['cpu_temp_c']} → {en['cpu_temp_c']} °C, Drosselung "
             f"{st['throttled']} → {en['throttled']}, Server {en['server_rss_mb']} MB (davon Arbeitsspeicher {en.get('server_anon_mb')} MB, Modelldatei {en.get('server_datei_mb')} MB), frei {en['mem_frei_mb']} MB.", "",
             ]
    if res["bild"]:
        lines += ["**Bildfragen** (Median je Bild)", "",
                  "| längste Kante | Bild+Frage Tokens | Prompt tok/s | Erzeugung tok/s | ja/nein (Dose) | Liste (40 Klassen) |",
                  "|---|---|---|---|---|---|"]
    for side, b in res["bild"].items():
        lines.append(f"| {side} px | {b['prompt_tokens']} | {b['prompt_tok_s']} | {b['gen_tok_s']} | "
                     f"{b['dose_s']} s | {b['liste_s']} s |")
    if res["text"]:
        lines += ["", "**Brain-Aufgaben ohne Bild**", "",
                  "| Aufgabe | nach Wechsel | Tokens neu | Prompt tok/s | wiederholt (Cache) | Tokens neu | "
                  "anderer Inhalt 1 / 2 | Tokens neu | Erzeugung tok/s |",
                  "|---|---|---|---|---|---|---|---|---|"]
        for name, t in res["text"].items():
            c, w, o = t["wechsel"], t["wiederholt"], t.get("anders", [])
            lines.append(f"| {name} | {c['wall_s']} s | {c['prompt_n']} | {t['prompt_tok_s']} | {w['wall_s']} s | "
                         f"{w['prompt_n']} | {' / '.join(str(x['wall_s']) + ' s' for x in o)} | "
                         f"{' / '.join(str(x['prompt_n']) for x in o)} | {t['gen_tok_s']} |")
    lines += ["", "„anderer Inhalt“: gleiche Aufgabe, gleicher fester Teil, anderer Zustand/Satz – so wie im Betrieb.",
              "", "Hinweis: „nach Wechsel“ = vorher lief eine andere Aufgabe. Mit einem Slot muss der feste Teil "
              "neu gerechnet werden; mit --slots behält jede Aufgabe ihren Slot" +
              (f" (hier {a.slots} Slots)." if a.slots > 1 else ".")]
    with open(md, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    with open(js, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1, default=str)
    print("\n" + "\n".join(lines) + f"\n\nBericht: {md}")


if __name__ == "__main__":
    main()
