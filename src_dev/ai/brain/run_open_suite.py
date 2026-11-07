# brain/run_open_suite.py
# Version 0.1 (07.11.2026) – Testsuite für die semantischen Aufgaben (semantic.py).
#
# Aufruf aus src_dev/ai:
#   python -m brain.run_open_suite --mock
#   python -m brain.run_open_suite --model Qwen3-4B-Instruct-2507-Q4_K_M.gguf --gpu-layers -1 --repeat 3 --out offen.json
#
# Je Aufgabe: Trefferquote, ungültige Antworten, Latenz. Am Ende ein
# Tagebuch-Beispiel zum Lesen (nicht bewertet).

from __future__ import annotations

import argparse
import json
import statistics
import time

from . import semantic as S
from .llm import LlamaBrain, MockBrain
from .open_scenarios import CHAT_CASES, DIARY_SAMPLE, OBJECT_CASES, SEARCH_CASES


def mock_responder(msgs, gbnf):
    """Gültige, aber dumme Antworten: prüft nur die Kette."""
    task = msgs[0]["content"].split("\n", 1)[0]
    if task == "AUFGABE: chat":
        return '{"dienst": "smalltalk", "gegenstand": "", "antwort": "Mock."}'
    if task == "AUFGABE: objekt":
        return '{"grund": "Mock.", "interesse": "mittel", "melden": "nein"}'
    if task == "AUFGABE: suchen":
        first = gbnf.split('ort ::= "\\"', 1)[1].split('\\"', 1)[0]
        return '{"grund": "Mock.", "orte": ["' + first + '"]}'
    return '{"text": "Mock."}'


def _item_ok(item: str, wanted: set[str]) -> bool:
    return not wanted or any(w in item for w in wanted)


def run(b, repeat: int) -> dict:
    rows = []

    def row(task, case, ok, valid, lat, out, reason=""):
        rows.append({"aufgabe": task, "fall": case, "ok": ok, "gueltig": valid,
                     "latenz_s": round(lat, 2), "ausgabe": out, "grund": reason})
        mark = "ok " if ok else "FALSCH" if valid else "UNGÜLTIG"
        print(f"{mark:8} {task:7} {case[:44]:44} -> {out}", flush=True)

    for k in range(repeat):
        for c in CHAT_CASES:
            r = S.interpret_chat(b, c.text)
            ok = r.service in c.services and _item_ok(r.item, c.item_any)
            row("chat", c.text, ok, r.service is not None, r.latency_s,
                f"{r.service}({r.item}) „{r.reply}“")
        for c in OBJECT_CASES:
            r = S.assess_object(b, c.cls, c.place, c.context)
            ok = r.report == c.report and r.interest in c.interest
            row("objekt", f"{c.cls} / {c.place}", ok, r.interest is not None, r.latency_s,
                f"melden={'ja' if r.report else 'nein'}, interesse={r.interest}", r.reason)
        for c in SEARCH_CASES:
            r = S.search_places(b, c.item, c.places)
            ok = bool(r.places) and r.places[0] in c.first_any
            row("suchen", c.item, ok, bool(r.places), r.latency_s, ", ".join(r.places), r.reason)

    text, lat, err = S.narrate(b, DIARY_SAMPLE)
    print("\nTagebuch-Beispiel:\n" + (text or f"(Fehler: {err})") + f"\n({lat:.1f} s)")

    summary = {"modell": b.name}
    for task in ("chat", "objekt", "suchen"):
        rs = [r for r in rows if r["aufgabe"] == task]
        lats = [r["latenz_s"] for r in rs if r["gueltig"]]
        summary[task] = {
            "laeufe": len(rs), "treffer": sum(r["ok"] for r in rs),
            "ungueltig": sum(not r["gueltig"] for r in rs),
            "latenz_median_s": round(statistics.median(lats), 2) if lats else None,
        }
    summary["tagebuch"] = text
    return {"summary": summary, "rows": rows}


def main() -> None:
    ap = argparse.ArgumentParser(description="SLARC Brain: Testsuite für semantische Aufgaben")
    ap.add_argument("--model", action="append", default=[])
    ap.add_argument("--mock", action="store_true")
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--gpu-layers", type=int, default=0)
    ap.add_argument("--ram-cache-mb", type=int, default=0, help="RAM-Cache für mehrere Systemprompts (Pi: z. B. 1024)")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    makers = []
    if a.mock or not a.model:
        makers.append(lambda: MockBrain(responder=mock_responder))
    for m in a.model:
        makers.append(lambda m=m: LlamaBrain(m, n_threads=a.threads, n_gpu_layers=a.gpu_layers,
                                             verbose=a.verbose, ram_cache_mb=a.ram_cache_mb))
    results = []
    for make in makers:
        t0 = time.perf_counter()
        print("Lade Modell …", flush=True)
        b = make()
        print(f"=== {b.name} (geladen in {time.perf_counter() - t0:.1f} s) ===", flush=True)
        r = run(b, a.repeat)
        results.append(r)
        s = r["summary"]
        for task in ("chat", "objekt", "suchen"):
            t = s[task]
            print(f"--> {task:7}: {t['treffer']}/{t['laeufe']} richtig, {t['ungueltig']} ungültig, "
                  f"Latenz Median {t['latenz_median_s']} s")
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=1)
        print(f"gespeichert: {a.out}")


if __name__ == "__main__":
    main()
