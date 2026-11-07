# brain/compare_models.py
# Version 0.1 (07.11.2026) – Alle Modelle mit beiden Testsuiten gegeneinander.
#
# Aufruf aus src_dev/ai:
#   python -m brain.compare_models --gpu-layers -1                 # alle *.gguf in ~/.models
#   python -m brain.compare_models --model a.gguf --model b.gguf --repeat 3 --gpu-layers -1
#   python -m brain.compare_models --mock                          # nur Kette prüfen
#
# Je Modell, nacheinander (immer nur eines im Speicher):
#   1. Zielwahl, volles Menü gemischt   (run_decision_suite)
#   2. Zielwahl, nur knappe Fälle       (run_decision_suite --close, so läuft es im Betrieb)
#   3. Chat deuten, Objekte, Suchorte   (run_open_suite)
# Ausgabe: Vergleichstabelle in der Konsole, Bericht modellvergleich.md mit den
# häufigsten Fehlern und Beispiel-Antworten zum Lesen, Rohdaten als JSON.
# Latenzen auf dem PC sagen nichts über den Pi.

from __future__ import annotations

import argparse
import gc
import glob
import json
import os
import time
from collections import Counter

from . import run_decision_suite as DS
from . import run_open_suite as OS
from . import semantic as S
from .llm import LlamaBrain, MockBrain

SMALLTALK_SAMPLES = ["Wie geht's dir?", "Hast du heute was Spannendes erlebt?", "Ich geh jetzt schlafen, gute Nacht."]


def _free(b) -> None:
    llm = getattr(b, "llm", None)
    if llm is not None and hasattr(llm, "close"):
        llm.close()
    pool = getattr(b, "_pool", None)
    if pool is not None:
        pool.shutdown(wait=False)
    del b
    gc.collect()


def evaluate(make, repeat: int) -> dict:
    t0 = time.perf_counter()
    try:
        b = make()
    except Exception as e:  # z. B. Architektur von dieser llama.cpp-Version nicht unterstützt
        return {"modell": getattr(make, "label", "?"), "fehler": f"nicht ladbar: {e}"}
    load_s = time.perf_counter() - t0
    print(f"=== {b.name}: geladen in {load_s:.1f} s", flush=True)

    t = time.perf_counter()
    full = DS.run(b, repeat, shuffle=True, show=False, only=[], close=False, rows_out=False)
    print(f"    Zielwahl voll:   {full['summary']['treffer']}/{full['summary']['laeufe']} "
          f"({time.perf_counter() - t:.0f} s)", flush=True)
    t = time.perf_counter()
    close = DS.run(b, repeat, shuffle=True, show=False, only=[], close=True, rows_out=False)
    print(f"    Zielwahl knapp:  {close['summary']['treffer']}/{close['summary']['laeufe']} "
          f"({time.perf_counter() - t:.0f} s)", flush=True)
    t = time.perf_counter()
    open_ = OS.run(b, repeat, rows_out=False)
    s = open_["summary"]
    print(f"    Chat {s['chat']['treffer']}/{s['chat']['laeufe']}, Objekt {s['objekt']['treffer']}/"
          f"{s['objekt']['laeufe']}, Suchen {s['suchen']['treffer']}/{s['suchen']['laeufe']} "
          f"({time.perf_counter() - t:.0f} s)", flush=True)
    talk = [(q, S.interpret_chat(b, q).reply) for q in SMALLTALK_SAMPLES]
    name = b.name
    path = getattr(getattr(b, "llm", None), "model_path", None)
    size_gb = os.path.getsize(path) / 1e9 if path and os.path.exists(path) else None
    _free(b)
    return {"modell": name, "laden_s": round(load_s, 1), "groesse_gb": round(size_gb, 2) if size_gb else None,
            "voll": full, "knapp": close, "offen": open_, "smalltalk": talk}


def _rate(s: dict) -> str:
    return f"{s['treffer']}/{s['laeufe']}"


def _lat(*vals) -> str:
    v = [x for x in vals if x is not None]
    return f"{sum(v) / len(v):.2f}" if v else "-"


def table(results: list[dict]) -> list[str]:
    head = ("| Modell | GB | Laden s | Zielwahl voll (Code) | knapp | ungültig | Chat | Objekt | Suchen | Latenz s |\n"
            "|---|---|---|---|---|---|---|---|---|---|")
    lines = [head]
    for r in results:
        if "fehler" in r:
            lines.append(f"| {r['modell']} | | | {r['fehler']} | | | | | | |")
            continue
        f, k, o = r["voll"]["summary"], r["knapp"]["summary"], r["offen"]["summary"]
        inval = f["ungueltig"] + k["ungueltig"] + sum(o[t]["ungueltig"] for t in ("chat", "objekt", "suchen"))
        lines.append(
            f"| {r['modell']} | {r['groesse_gb'] or '-'} | {r['laden_s']} | {_rate(f)} ({f['code_treffer']}) | "
            f"{_rate(k)} | {inval} | {_rate(o['chat'])} | {_rate(o['objekt'])} | {_rate(o['suchen'])} | "
            f"{_lat(f['latenz_median_s'], o['chat']['latenz_median_s'], o['objekt']['latenz_median_s'])} |")
    return lines


def report(results: list[dict], repeat: int) -> str:
    out = [f"# Modellvergleich Brain ({time.strftime('%d.%m.%Y %H:%M')}, {repeat} Wiederholungen)", "",
           "Latenzen auf dem PC, nicht auf den Pi übertragbar. „Zielwahl voll“: alle Optionen, gemischt; "
           "in Klammern, wie oft der Code allein richtig läge. „knapp“: nur knappe Fälle, so wie im Betrieb.", ""]
    out += table(results)
    for r in results:
        if "fehler" in r:
            continue
        out += ["", f"## {r['modell']}", "", "**Häufigste Fehler**", ""]
        errs = Counter()
        for part in ("voll", "knapp"):
            for row in r[part]["rows"]:
                if not row.get("ok") and not row.get("setup_fehler"):
                    errs[f"Zielwahl {part}: {row['szenario']} -> {row.get('wahl')}"] += 1
        for row in r["offen"]["rows"]:
            if not row["ok"]:
                errs[f"{row['aufgabe']}: {row['fall']} -> {row['ausgabe']}"] += 1
        out += [f"- {n}× {e}" for e, n in errs.most_common(12)] or ["- keine"]
        out += ["", "**Antworten zum Lesen**", ""]
        out += [f"- „{q}“ → „{a}“" for q, a in r["smalltalk"]]
        out += ["", f"Tagebuch: {r['offen']['summary'].get('tagebuch') or '-'}"]
    return "\n".join(out) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description="SLARC Brain: Modellvergleich mit beiden Testsuiten")
    ap.add_argument("--model", action="append", default=[], help="GGUF (mehrfach); ohne Angabe alle in ~/.models")
    ap.add_argument("--mock", action="store_true")
    ap.add_argument("--repeat", type=int, default=3)
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--gpu-layers", type=int, default=0)
    ap.add_argument("--report", default="modellvergleich.md")
    ap.add_argument("--out", default="modellvergleich.json")
    a = ap.parse_args()

    makers = []
    if a.mock:
        def mk():
            return MockBrain(responder=OS.mock_responder)
        mk.label = "mock"
        makers.append(mk)
    else:
        models = a.model or sorted(glob.glob(os.path.expanduser("~/.models/*.gguf")))
        if not models:
            raise SystemExit("Keine Modelle gefunden (~/.models/*.gguf oder --model).")
        print("Modelle:\n  " + "\n  ".join(models), flush=True)
        for m in models:
            def mk(m=m):
                return LlamaBrain(m, n_threads=a.threads, n_gpu_layers=a.gpu_layers)
            mk.label = os.path.basename(m)
            makers.append(mk)

    results = []
    for mk in makers:
        results.append(evaluate(mk, a.repeat))
        with open(a.out, "w", encoding="utf-8") as f:     # nach jedem Modell sichern
            json.dump(results, f, ensure_ascii=False, indent=1)
    rep = report(results, a.repeat)
    with open(a.report, "w", encoding="utf-8") as f:
        f.write(rep)
    print("\n" + "\n".join(table(results)))
    print(f"\nBericht: {a.report}, Rohdaten: {a.out}")


if __name__ == "__main__":
    main()
