# brain/vision/compare_vlm.py
# Version 0.2 (08.11.2026) – Kleine Vision-Sprachmodelle gegeneinander und gegen COCO.
# V0.2: Ohne Pillow wird abgebrochen statt still das Originalbild zu senden (--max-side 320
#       und 448 lieferten am 08.11. auf dem PC deshalb dieselben Zahlen wie 640).
#
# Frage: Kann Qwen3.5-4B mit Bildeingabe (mmproj) Bilder brauchbar deuten? Als
# Vergleich dient ein größeres Modell (z. B. Qwen3.5-9B), beide über llama-server.
# Der YOLO-Head ist kein Vergleich: er liefert Boxen, das VLM Antworten auf Fragen.
#
# Teil A – COCO als Wahrheit: Welche der 40 Roboter-Klassen sind im Bild?
#   Antwort per JSON-Schema auf die 40 Namen begrenzt. Kennzahlen je Modell:
#   Precision, Recall, F1 (Bild-Klasse-Paare), Recall nur für nicht kleine Objekte
#   (Fläche >= 32x32 px), häufigste übersehene und erfundene Klassen, Zeit je Bild.
#   Dazu je Bild eine freie Kurzbeschreibung zum Lesen (--describe).
# Teil B – eigene Fotos mit Fragen, die die Detektion nicht beantworten kann
#   (--questions, Vorlage questions_template.json).
#
# Je Modell ein llama-server, z. B.
#   llama-server -m ~/.models/Qwen3.5-4B-Q4_K_M.gguf --mmproj ~/.models/mmproj-Qwen3.5-4B-f16.gguf -ngl 99 -c 8192 --port 8080
#   llama-server -m ~/.models/Qwen3.5-9B-Q4_K_M.gguf --mmproj ~/.models/mmproj-Qwen3.5-9B-f16.gguf -ngl 99 -c 8192 --port 8081
# (beide gleichzeitig nur, wenn der VRAM reicht; sonst nacheinander mit je einem --server)
# Aufruf aus src_dev/ai:
#   python -m brain.vision.compare_vlm --server 4B=http://127.0.0.1:8080 --server 9B=http://127.0.0.1:8081 \
#          --coco-ann /pfad/instances_val2017.json --coco-img /pfad/val2017 -n 100 --indoor --describe 10
#   python -m brain.vision.compare_vlm --server 4B=http://127.0.0.1:8080 --questions fotos/fragen.json
# Latenzen auf dem PC sagen nichts über den Pi.

from __future__ import annotations

import argparse
import base64
import io
import json
import os
import random
import statistics
import time
import urllib.request
from collections import Counter, defaultdict

from ..perception_classes import DET_CLASSES, ITEM, LANDMARK

ROBOT = [c for c in DET_CLASSES if c.coco_id is not None]         # 40 Klassen ohne "unbekannt"
COCO2EN = {c.coco_id: c.en for c in ROBOT}
NAMES = [c.en for c in ROBOT]
INDOOR_EN = {c.en for c in ROBOT if c.kind in (LANDMARK, ITEM)}
SMALL_AREA = 32 * 32

PROMPT_A = ("Which of these objects are visible in the image? Only list objects you can clearly see. "
            "Allowed names: " + ", ".join(NAMES) + ". "
            'Answer as JSON: {"objects": [...]}')


# ---------------------------------------------------------------- Server
def _image_b64(path: str, max_side: int) -> str:
    with open(path, "rb") as f:
        data = f.read()
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(data)).convert("RGB")
        if max(im.size) > max_side:
            im.thumbnail((max_side, max_side))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=90)
        data = buf.getvalue()
    except OSError as e:          # Pillow kann die Datei nicht lesen: unverändert senden, aber sagen
        print(f"   Hinweis: {path} nicht verkleinert ({e})")
    return base64.b64encode(data).decode()


def ask(url: str, image_path: str, prompt: str, schema: dict, max_side: int, timeout: float = 300.0):
    body = {
        "messages": [{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + _image_b64(image_path, max_side)}},
            {"type": "text", "text": prompt}]}],
        "temperature": 0.0,
        "max_tokens": 300,
        "response_format": {"type": "json_schema", "json_schema": {"name": "antwort", "schema": schema}},
        "chat_template_kwargs": {"enable_thinking": False},
    }
    req = urllib.request.Request(url.rstrip("/") + "/v1/chat/completions", json.dumps(body).encode(),
                                 {"Content-Type": "application/json"})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        out = json.loads(r.read())
    lat = time.perf_counter() - t0
    text = out["choices"][0]["message"]["content"]
    try:
        return json.loads(text), lat, text
    except json.JSONDecodeError:
        return None, lat, text


def check_server(url: str) -> None:
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/health", timeout=5) as r:
            r.read()
    except Exception as e:
        raise SystemExit(f"llama-server unter {url} nicht erreichbar ({e}). Start siehe Kopf dieser Datei.")


# ---------------------------------------------------------------- COCO
def load_coco(ann_path: str):
    with open(ann_path, encoding="utf-8") as f:
        d = json.load(f)
    files = {im["id"]: im["file_name"] for im in d["images"]}
    gt_all: dict[int, set] = defaultdict(set)
    gt_big: dict[int, set] = defaultdict(set)
    for a in d["annotations"]:
        en = COCO2EN.get(a["category_id"])
        if en is None:
            continue
        gt_all[a["image_id"]].add(en)
        if a.get("area", 0) >= SMALL_AREA:
            gt_big[a["image_id"]].add(en)
    return files, gt_all, gt_big


def pick_images(gt_all, n: int, indoor: bool, seed: int) -> list[int]:
    ids = sorted(i for i, s in gt_all.items() if s and (not indoor or s & INDOOR_EN))
    random.Random(seed).shuffle(ids)
    return ids[:n]


def metrics(pred: dict[int, set], gt_all, gt_big, ids) -> dict:
    tp = fp = fn = big_tp = big_n = 0
    missed, invented = Counter(), Counter()
    for i in ids:
        p, g, gb = pred.get(i, set()), gt_all.get(i, set()), gt_big.get(i, set())
        tp += len(p & g)
        fp += len(p - g)
        fn += len(g - p)
        big_tp += len(p & gb)
        big_n += len(gb)
        missed.update(g - p)
        invented.update(p - g)
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    return {"precision": round(prec, 3), "recall": round(rec, 3),
            "f1": round(2 * prec * rec / (prec + rec), 3) if prec + rec else 0.0,
            "recall_nicht_klein": round(big_tp / big_n, 3) if big_n else None,
            "uebersehen": missed.most_common(8), "erfunden": invented.most_common(8)}


# ---------------------------------------------------------------- Bericht
PROMPT_DESC = "Describe in one short German sentence what you see in this image, as a small robot in the room would."
DESC_SCHEMA = {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}


def out_paths(stem: str):
    d = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ergebnisse",
                     time.strftime("%Y-%m-%d"))
    os.makedirs(d, exist_ok=True)
    base = os.path.join(d, f"{stem}_{time.strftime('%H%M')}")
    return base + ".md", base + ".json"


def run_coco(a, servers: dict[str, str]) -> None:
    files, gt_all, gt_big = load_coco(a.coco_ann)
    ids = pick_images(gt_all, a.n, a.indoor, a.seed)
    print(f"{len(ids)} Bilder ({'nur mit Innenraum-Klassen' if a.indoor else 'alle'}), Seed {a.seed}")
    schema = {"type": "object", "properties": {"objects": {"type": "array", "items": {"type": "string", "enum": NAMES}}},
              "required": ["objects"]}
    res = {"bilder": len(ids), "seed": a.seed, "indoor": a.indoor, "max_side": a.max_side, "modelle": {}}
    rows = {i: {"image_id": i, "file": files[i], "gt": sorted(gt_all[i])} for i in ids}
    for name, url in servers.items():
        pred, lats, invalid = {}, [], 0
        for k, i in enumerate(ids, 1):
            ans, lat, raw = ask(url, os.path.join(a.coco_img, files[i]), PROMPT_A, schema, a.max_side)
            lats.append(lat)
            if ans is None:
                invalid += 1
                ans = {"objects": []}
            pred[i] = set(ans.get("objects", []))
            rows[i][name] = sorted(pred[i])
            print(f"[{name} {k}/{len(ids)}] {files[i]}  GT {sorted(gt_all[i])}  -> {sorted(pred[i])}  {lat:.1f} s", flush=True)
            if k <= a.describe:
                d, _, _ = ask(url, os.path.join(a.coco_img, files[i]), PROMPT_DESC, DESC_SCHEMA, a.max_side)
                rows[i][name + "_text"] = d.get("text", "") if d else ""
        res["modelle"][name] = {**metrics(pred, gt_all, gt_big, ids), "ungueltig": invalid,
                                "latenz_median_s": round(statistics.median(lats), 2) if lats else None}
    res["rows"] = list(rows.values())
    md, js = out_paths("vision_coco")
    lines = [f"# Vision-Sprachmodelle auf COCO ({time.strftime('%d.%m.%Y %H:%M')})", "",
             f"{len(ids)} Bilder, Seed {a.seed}, {'nur Innenraum' if a.indoor else 'alle'}, Bild max. {a.max_side} px. "
             "Bild-Ebene: Ist die Klasse im Bild? Recall „nicht klein“: nur Objekte ab 32×32 px.", "",
             "| Modell | Precision | Recall | F1 | Recall nicht klein | ungültig | Zeit/Bild (PC) |",
             "|---|---|---|---|---|---|---|"]
    for name, m in res["modelle"].items():
        lines.append(f"| {name} | {m['precision']} | {m['recall']} | {m['f1']} | {m['recall_nicht_klein']} | "
                     f"{m['ungueltig']} | {m['latenz_median_s']} s |")
    for name, m in res["modelle"].items():
        lines += ["", f"**{name} übersieht am häufigsten:** " + ", ".join(f"{c} ({n})" for c, n in m["uebersehen"]),
                  f"**{name} erfindet am häufigsten:** " + ", ".join(f"{c} ({n})" for c, n in m["erfunden"])]
    descs = [r for r in res["rows"] if any(k.endswith("_text") for k in r)]
    if descs:
        lines += ["", "**Beschreibungen zum Lesen**", ""]
        for r in descs:
            lines.append(f"- {r['file']} (COCO: {', '.join(r['gt'])})")
            for name in servers:
                if name + "_text" in r:
                    lines.append(f"  - {name}: {r[name + '_text']}")
    with open(md, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    with open(js, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    print("\n" + "\n".join(lines[4:4 + 2 + len(servers)]) + f"\n\nBericht: {md}")


def run_questions(a, servers: dict[str, str]) -> None:
    with open(a.questions, encoding="utf-8") as f:
        qs = json.load(f)
    base = os.path.dirname(os.path.abspath(a.questions))
    rows = [dict(q) for q in qs]
    score = {}
    for name, url in servers.items():
        ok_n = 0
        for k, (q, r) in enumerate(zip(qs, rows), 1):
            path = q["bild"] if os.path.isabs(q["bild"]) else os.path.join(base, q["bild"])
            schema = {"type": "object", "properties": {"antwort": {"type": "string", "enum": q["antworten"]}},
                      "required": ["antwort"]}
            prompt = q["frage"] + " Antworte nur mit einer dieser Möglichkeiten: " + ", ".join(q["antworten"]) + \
                '. Als JSON: {"antwort": "..."}'
            ans, lat, raw = ask(url, path, prompt, schema, a.max_side)
            got = ans.get("antwort") if ans else None
            ok_n += got == q["richtig"]
            r[name] = got
            print(f"[{name} {k}/{len(qs)}] {'ok ' if got == q['richtig'] else 'FALSCH'} {q['bild']}: {q['frage']} -> {got} "
                  f"(richtig: {q['richtig']}) {lat:.1f} s", flush=True)
        score[name] = ok_n
    md, js = out_paths("vision_fragen")
    lines = [f"# Vision-Fragen an eigene Fotos ({time.strftime('%d.%m.%Y %H:%M')})", ""]
    lines += [f"- {name}: {n}/{len(qs)} richtig" for name, n in score.items()] + [""]
    for r in rows:
        lines.append(f"- {r['bild']} – {r['frage']} (richtig: {r['richtig']}): "
                     + ", ".join(f"{n} → {r.get(n)}" for n in servers))
    with open(md, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    with open(js, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)
    print("\n" + "\n".join(lines[2:2 + len(servers)]) + f"\nBericht: {md}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Vision-Sprachmodelle gegeneinander (COCO und eigene Fotos)")
    ap.add_argument("--server", action="append", default=[], help="NAME=URL, mehrfach, z. B. 4B=http://127.0.0.1:8080")
    ap.add_argument("--coco-ann", help="instances_val2017.json")
    ap.add_argument("--coco-img", help="Ordner mit den val2017-Bildern")
    ap.add_argument("-n", type=int, default=100)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--indoor", action="store_true", help="nur Bilder mit mindestens einer Innenraum-Klasse")
    ap.add_argument("--describe", type=int, default=10, help="für die ersten N Bilder zusätzlich eine Beschreibung")
    ap.add_argument("--max-side", type=int, default=640, help="Bild aufs Modell auf diese Kantenlänge verkleinern")
    ap.add_argument("--questions", help="eigene Fotos mit Fragen (Vorlage questions_template.json)")
    a = ap.parse_args()
    try:                                                       # [V0.2] ohne Pillow keine Verkleinerung
        import PIL  # noqa: F401
    except ImportError:
        raise SystemExit("Pillow fehlt (conda install -c conda-forge pillow), sonst gilt --max-side nicht.")
    servers = dict(x.split("=", 1) for x in (a.server or ["4B=http://127.0.0.1:8080"]))
    for url in servers.values():
        check_server(url)
    if a.questions:
        run_questions(a, servers)
    elif a.coco_ann and a.coco_img:
        run_coco(a, servers)
    else:
        raise SystemExit("Entweder --coco-ann und --coco-img oder --questions angeben.")


if __name__ == "__main__":
    main()
