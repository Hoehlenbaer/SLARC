#!/usr/bin/env python3
"""
SLARC Halte-Modus-Test — isolierter Stand-Regelkreis
====================================================
Testet die zwei entkoppelten Kontaktregler OHNE Gehen/Klettern, mit eskalierenden
Störungen. Metrik ist hart: Kontaktzahl konstant 6, vz ~ 0, Pitch am Soll (~0).

  Szenario 1 (eben):       flacher Boden. Halten alle 6 Füße? vz=0?
  Szenario 2 (bump_fruh):  Erhebung unter 1 Fuß gleich zu Beginn. Balancer gleicht aus?
  Szenario 3 (bump_spaet): Erhebung erscheint WÄHREND des Stands. Nachsenkung führt nach?

Aufruf:  python test_hold.py
         python test_hold.py --gui        (zusehen)
         python test_hold.py --frames 1200 --bump-h 0.04

Voraussetzung: slarc_sim_V8.py im selben Verzeichnis.
"""
import subprocess, csv, glob, os, sys, statistics, argparse, time

SIM = "slarc_sim_V8.py"
LEGS = ['front_right','front_left','mid_right','mid_left','rear_right','rear_left']


def g(r, k):
    try: return float(r[k])
    except Exception: return 0.0


def run_one(tag, extra, common, gui=False):
    for old in glob.glob(f"slarc_log_*_{tag}.csv"):
        try: os.remove(old)
        except OSError: pass
    cmd = [sys.executable, SIM] + common + ["--tag", tag] + extra
    print(f"  -> {tag}")
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
    try:
        if gui:
            subprocess.run(cmd, env=env, timeout=600)
        else:
            subprocess.run(cmd, check=True, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", env=env, timeout=600)
    except subprocess.CalledProcessError as e:
        print(f"    FEHLER: {e.stderr[-300:] if e.stderr else e}"); return None
    except subprocess.TimeoutExpired:
        print("    TIMEOUT"); return None
    logs = sorted(glob.glob(f"slarc_log_*_{tag}.csv"))
    return logs[-1] if logs else None


def analyze(path, settle_frac=0.5):
    f = open(path); f.readline()
    rows = list(csv.DictReader(f))
    if not rows: return None
    # zweite Hälfte = eingeschwungener Zustand (nach Bump + Nachregeln)
    tail = rows[int(len(rows) * settle_frac):]
    ncon = [sum(int(g(r, l + "_contact")) for l in LEGS) for r in tail]
    vz = [abs(g(r, "vz")) for r in tail]
    pitch = [abs(g(r, "pitch")) for r in tail]
    # Kontakt-Stabilität: wie oft sind alle 6 in Kontakt?
    all6 = 100 * sum(1 for n in ncon if n >= 6) / len(ncon) if ncon else 0
    return dict(
        con_mean=statistics.mean(ncon) if ncon else 0,
        con_min=min(ncon) if ncon else 0,
        all6=all6,
        vz_mean=statistics.mean(vz) if vz else 0,
        vz_max=max(vz) if vz else 0,
        pitch_max=max(pitch) if pitch else 0,
    )


def main():
    try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception: pass
    ap = argparse.ArgumentParser(description="SLARC Halte-Modus-Test")
    ap.add_argument("--frames", type=int, default=1200, help="Halte-Frames pro Szenario")
    ap.add_argument("--bump-h", type=float, default=0.03, help="Höhe der Erhebung [m]")
    ap.add_argument("--bump-leg", default="front_right")
    ap.add_argument("--bump-ramp", type=int, default=0, help="Bump-Höhenrampe [Frames] (0=sofort)")
    ap.add_argument("--gui", action="store_true")
    args = ap.parse_args()

    common = ["--no-stairs", "--hold", str(args.frames)]
    if args.bump_ramp > 0:
        common += ["--bump-ramp", str(args.bump_ramp)]
    if not args.gui:
        common.insert(0, "--no-gui")

    tests = [
        ("eben",       []),
        ("bump_fruh",  ["--bump-at", "60", "--bump-leg", args.bump_leg, "--bump-h", str(args.bump_h)]),
        ("bump_spaet", ["--bump-at", str(args.frames // 2), "--bump-leg", args.bump_leg,
                        "--bump-h", str(args.bump_h)]),
    ]

    print("=" * 74)
    print(f"SLARC Halte-Modus-Test | {args.frames} Frames | Bump +{args.bump_h*1000:.0f}mm unter {args.bump_leg}")
    print("=" * 74)
    t0 = time.time()
    results = {}
    for tag, extra in tests:
        path = run_one(tag, extra, common, gui=args.gui)
        if path:
            r = analyze(path)
            if r: results[tag] = r

    print("\n" + "=" * 74)
    print("ERGEBNIS — Ziel: Kontakt=6 konstant, vz~0, Pitch~0 (eingeschwungene 2. Hälfte)")
    print("=" * 74)
    print(f"{'Szenario':<13}{'Kontakt Ø':>10}{'min':>5}{'alle6 %':>9}{'vz Ø':>9}{'vz max':>9}{'pitch max':>11}")
    print("-" * 74)
    for tag, _ in tests:
        if tag not in results: continue
        r = results[tag]
        print(f"{tag:<13}{r['con_mean']:>10.1f}{r['con_min']:>5d}{r['all6']:>9.0f}"
              f"{r['vz_mean']:>9.4f}{r['vz_max']:>9.3f}{r['pitch_max']:>11.3f}")
    print("-" * 74)
    print("Lesart: 'alle6 %' nahe 100 = sechs Füße halten stabil. vz max klein = kein Oszillieren.")
    print("        pitch max klein = Balancer haelt den Rumpf eben trotz Erhebung.")
    print(f"\nGesamtzeit: {time.time()-t0:.0f} s")


if __name__ == "__main__":
    main()
