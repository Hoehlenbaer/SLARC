# brain/run_decision_suite.py
# Version 0.2 (07.11.2026) – Entscheidungs-Testsuite für den Modellvergleich.
# V0.2: --gpu-layers für den PC (Latenzen dann nicht mit dem Pi vergleichbar).
# V0.3: Statusmeldungen beim Laden/Aufwärmen, --verbose (Ausgabe von llama.cpp).
#
# Aufruf aus src_dev/ai:
#   python -m brain.run_decision_suite --mock
#   python -m brain.run_decision_suite --model Qwen3-4B-Instruct-2507-Q4_K_M.gguf --repeat 3
#   python -m brain.run_decision_suite --model a.gguf --model b.gguf --threads 4 --out ergebnis.json
#
# Misst je Modell: Trefferquote (Wahl in "expected"), ungültige Antworten,
# Latenz (Median, Maximum) mit gecachtem Systemprompt, Tokens.
# Standard: Menü-Reihenfolge gemischt. Sonst steht die Code-Wahl immer auf
# Platz 1, und ein Modell, das nur "1" antwortet, sähe gut aus.
# --sorted: Reihenfolge wie im Betrieb (nach Code-Nutzen).
# Vergleichsbasis "Code": wie oft die beste Code-Option schon richtig wäre.
# Das LLM lohnt sich nur, wenn es das übertrifft (v. a. in semantik_*-Szenarien).

from __future__ import annotations

import argparse
import json
import random
import statistics
import time

from .behaviors import build_options
from .llm import LlamaBrain, MockBrain
from .prompt import state_text
from .safety import check
from .scenarios import SCENARIOS, prepare


def build(sc, shuffle_rng=None):
    mem, nm, needs = prepare(sc)
    menu = build_options(sc.obs, needs, mem, check(sc.obs))
    code_best = menu[0] if menu else None       # vor dem Mischen: höchster Code-Nutzen
    if shuffle_rng is not None:
        shuffle_rng.shuffle(menu)
    return needs, menu, state_text(sc.obs, needs, menu, sc.triggers), code_best


def run(brain, repeat: int, shuffle: bool, show: bool, only: list[str]) -> dict:
    rng = random.Random(42)
    rows = []
    print("Wärme Systemprompt und Few-Shot auf …", flush=True)
    t_warm = brain.warmup()
    print(f"Aufgewärmt in {t_warm:.1f} s", flush=True)
    for sc in SCENARIOS:
        if only and sc.name not in only:
            continue
        for k in range(repeat):
            needs, menu, state, code_best = build(sc, rng if shuffle else None)
            in_menu = {o.behavior for o in menu}
            if not sc.expected & in_menu:
                rows.append({"szenario": sc.name, "lauf": k, "setup_fehler": True,
                             "menue": [o.key for o in menu]})
                print(f"[SETUP] {sc.name}: erwartetes Verhalten nicht im Menü: {sorted(in_menu)}")
                break
            if show and k == 0:
                print("-" * 60 + f"\n{sc.name}\n{state}")
            res = brain.decide(state, len(menu))
            chosen = menu[res.choice - 1] if res.choice else None
            ok = chosen is not None and chosen.behavior in sc.expected
            rows.append({
                "szenario": sc.name, "lauf": k, "ok": ok,
                "code_ok": code_best is not None and code_best.behavior in sc.expected,
                "wahl": chosen.key if chosen else None, "position": res.choice,
                "erwartet": sorted(sc.expected), "begruendung": res.reason, "stimmung": res.mood,
                "latenz_s": round(res.latency_s, 2), "tokens_in": res.tokens_in,
                "tokens_out": res.tokens_out, "fehler": res.error, "roh": res.raw,
            })
            mark = "ok " if ok else "FALSCH" if res.choice else "UNGÜLTIG"
            print(f"{mark:8} {sc.name:30} -> {chosen.key if chosen else '-':32} "
                  f"{res.latency_s:5.1f} s  {res.reason}", flush=True)
    valid = [r for r in rows if not r.get("setup_fehler")]
    lat = [r["latenz_s"] for r in valid if r["position"]]
    summary = {
        "modell": brain.name,
        "shuffle": shuffle,
        "laeufe": len(valid),
        "treffer": sum(r["ok"] for r in valid),
        "code_treffer": sum(r["code_ok"] for r in valid),
        "ungueltig": sum(1 for r in valid if not r["position"]),
        "setup_fehler": sum(1 for r in rows if r.get("setup_fehler")),
        "position_1_anteil": round(sum(1 for r in valid if r["position"] == 1) / max(1, len(valid)), 2),
        "latenz_median_s": round(statistics.median(lat), 2) if lat else None,
        "latenz_max_s": round(max(lat), 2) if lat else None,
        "warmup_s": round(t_warm, 2),
    }
    return {"summary": summary, "rows": rows}


def main() -> None:
    ap = argparse.ArgumentParser(description="SLARC Brain: Entscheidungs-Testsuite")
    ap.add_argument("--model", action="append", default=[], help="GGUF-Datei oder Name (mehrfach möglich)")
    ap.add_argument("--mock", action="store_true", help="ohne Modell, regelbasiert")
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--sorted", action="store_true", help="Menü nach Code-Nutzen sortiert lassen (wie im Betrieb)")
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--verbose", action="store_true", help="Ausgabe von llama.cpp zeigen (Laden, GPU-Schichten)")
    ap.add_argument("--gpu-layers", type=int, default=0, help="-1 = alle Schichten auf die GPU (nur PC)")
    ap.add_argument("--temperature", type=float, default=0.3)
    ap.add_argument("--show", action="store_true", help="Zustandstext je Szenario ausgeben")
    ap.add_argument("--only", action="append", default=[], help="nur dieses Szenario")
    ap.add_argument("--out", default=None, help="Ergebnisse als JSON speichern")
    a = ap.parse_args()

    brains = []
    if a.mock or not a.model:
        brains.append(lambda: MockBrain())
    for m in a.model:
        brains.append(lambda m=m: LlamaBrain(m, n_threads=a.threads, temperature=a.temperature,
                                                     n_gpu_layers=a.gpu_layers, verbose=a.verbose))

    results = []
    for make in brains:
        t0 = time.perf_counter()
        print("Lade Modell … (von /mnt/… unter WSL sehr langsam, besser ~/.models)", flush=True)
        b = make()
        print(f"=== {b.name} (geladen in {time.perf_counter() - t0:.1f} s) ===")
        r = run(b, a.repeat, not a.sorted, a.show, a.only)
        results.append(r)
        s = r["summary"]
        print(f"--> {s['modell']}: {s['treffer']}/{s['laeufe']} richtig (Code allein: {s['code_treffer']}), "
              f"{s['ungueltig']} ungültig, "
              f"Position 1: {s['position_1_anteil']:.0%}, Latenz Median {s['latenz_median_s']} s, "
              f"max {s['latenz_max_s']} s")
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=1)
        print(f"gespeichert: {a.out}")


if __name__ == "__main__":
    main()
