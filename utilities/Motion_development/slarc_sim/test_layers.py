#!/usr/bin/env python3
"""
SLARC Layer-Isolation - reproduzierbarer Hüpfer-Test
====================================================
Fährt DIESELBE Strecke (ebener Boden, placemove) mehrfach, jeweils mit einer
abgeschalteten Regelungsschicht, und vergleicht die vertikale Körperunruhe (vz).
Ziel: herausfinden, WELCHE Schicht die Mikrohüpfer erzeugt.

Prinzip: Beim Stehen ist vz=0 (Physik stabil). Steigt vz erst beim Gehen, kommt
die Unruhe aus der Steuerung. Die Konfiguration mit dem NIEDRIGSTEN drive_vz ist
diejenige, deren fehlende Schicht die Hüpfer verursacht hat.

Aufruf:   python test_layers.py
          python test_layers.py --rise 0.15 --run 0.28 --stairs   # mit Treppe
          python test_layers.py --auto 2000 --gait placemove

Voraussetzung: slarc_sim_V8.py im selben Verzeichnis.
"""
import subprocess, csv, glob, os, sys, statistics, argparse, time

SIM = "slarc_sim_V8.py"
LEGS = ['front_right','front_left','mid_right','mid_left','rear_right','rear_left']

# Test-Matrix: (tag, zusätzliche Flags). Reihenfolge = Ausgabereihenfolge.
TESTS = [
    ("baseline",    []),                                   # alle Schichten AN
    ("no_balance",  ["--no-balance"]),                     # Balancer AUS
    ("no_foothold", ["--no-foothold"]),                    # Foothold AUS
    ("no_freeze",   ["--no-freeze"]),                      # Freeze AUS
    ("bare",        ["--no-balance","--no-foothold","--no-freeze"]),           # nackt + Einstiegs-Boost
    ("bare_no_entry",["--no-balance","--no-foothold","--no-freeze","--no-entry"]),  # nackt OHNE Boost
]


def g(r, k):
    try: return float(r[k])
    except Exception: return 0.0


def run_one(tag, extra, common, gui=False):
    """Führt einen Sim-Lauf aus, gibt den Log-Pfad zurück."""
    for old in glob.glob(f"slarc_log_*_{tag}.csv"):
        try: os.remove(old)
        except OSError: pass
    cmd = [sys.executable, SIM] + common + ["--tag", tag] + extra
    label = " ".join(extra) if extra else "(alle Schichten AN)"
    print(f"  -> {tag:12s} {label}")
    # UTF-8 für die Subprozess-Pipe erzwingen (Windows-Konsole ist oft cp1252 und
    # crasht sonst an Sonderzeichen), errors='replace' als zusätzliches Netz.
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
    try:
        if gui:
            # GUI sichtbar: keine Ausgabe abfangen, damit Fenster + Konsole live sind
            subprocess.run(cmd, env=env, timeout=600)
        else:
            subprocess.run(cmd, check=True, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", env=env, timeout=600)
    except subprocess.CalledProcessError as e:
        print(f"    FEHLER: {e.stderr[-300:] if e.stderr else e}")
        return None
    except subprocess.TimeoutExpired:
        print("    TIMEOUT"); return None
    logs = sorted(glob.glob(f"slarc_log_*_{tag}.csv"))
    return logs[-1] if logs else None


def analyze(path):
    f = open(path); meta = f.readline()
    rows = list(csv.DictReader(f))
    if not rows: return None
    drive = [r for r in rows if g(r, "cmd_vx") > 0.01]
    still = [r for r in rows if g(r, "cmd_vx") <= 0.01]

    def vz(rs):
        v = [abs(g(r, "vz")) for r in rs]
        return (statistics.mean(v), max(v)) if v else (0.0, 0.0)

    dmean, dmax = vz(drive)
    _, smax = vz(still)
    ncon = [sum(int(g(r, lg + "_contact")) for lg in LEGS) for r in drive]
    frozen = [int(g(r, "frozen")) for r in drive]
    bx = [g(r, "bx") for r in drive]
    bz = [g(r, "bz") for r in drive]
    bx_end = bx[-1] if bx else 0.0
    # Endhöhe robust: Median der letzten 15 % der Fahrt (nicht Peak -> keine Hüpfer/Anstöße)
    tail = bz[int(len(bz) * 0.85):] if bz else [0.0]
    bz_end = statistics.median(tail) if tail else 0.0
    return dict(
        still_vzmax=smax,
        drive_vzmean=dmean, drive_vzmax=dmax,
        contact=statistics.mean(ncon) if ncon else 0.0,
        frozen=100 * sum(frozen) / len(frozen) if frozen else 0.0,
        progress=(bx[-1] - bx[0]) if bx else 0.0,
        bx_end=bx_end, bz_max=max(bz) if bz else 0.0, bz_end=bz_end,
        rows=len(rows),
    )


def main():
    # Eigene Ausgabe (Tabelle mit Ø) UTF-8-sicher machen, falls Konsole cp1252 ist.
    try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception: pass
    ap = argparse.ArgumentParser(description="SLARC Layer-Isolation")
    ap.add_argument("--auto", type=int, default=1400, help="Fahr-Frames (Default 1400 ca. 6 s)")
    ap.add_argument("--settle", type=int, default=240, help="Ruhe-Frames vor Fahrt")
    ap.add_argument("--gait", default="placemove", choices=["tripod","ripple","placemove"])
    ap.add_argument("--stairs", action="store_true", help="MIT Treppe (Default: ohne)")
    ap.add_argument("--rise", type=float, default=0.15)
    ap.add_argument("--run",  type=float, default=0.28)
    ap.add_argument("--drive-vx", type=float, default=1.0)
    ap.add_argument("--start-x", type=float, default=0.0,
                    help="Spawn-x: Roboter vor die Treppe setzen (Treppe bei x=1.0), z.B. 0.7")
    ap.add_argument("--gui", action="store_true",
                    help="Läufe mit GUI-Fenster zeigen (Echtzeit, 1 Fenster pro Lauf, langsamer)")
    args = ap.parse_args()

    common = ["--auto", str(args.auto), "--settle", str(args.settle),
              "--gait", args.gait, "--drive-vx", str(args.drive_vx),
              "--rise", str(args.rise), "--run", str(args.run),
              "--start-x", str(args.start_x)]
    if not args.gui:
        common.insert(0, "--no-gui")
    if not args.stairs:
        common.append("--no-stairs")

    print("=" * 68)
    print(f"SLARC Layer-Isolation | gait={args.gait} | Treppe={'AN' if args.stairs else 'AUS'} "
          f"| start-x={args.start_x} | {args.auto} Fahr-Frames")
    print("=" * 68)

    t0 = time.time()
    results = {}
    for tag, extra in TESTS:
        path = run_one(tag, extra, common, gui=args.gui)
        if path:
            r = analyze(path)
            if r: results[tag] = r

    print("\n" + "=" * 88)
    print("ERGEBNIS - vz = vertikale Körperunruhe (niedriger = ruhiger). Treppe beginnt bei x=1.0")
    print("=" * 88)
    hdr = (f"{'Konfiguration':<13}{'drive_vzØ':>11}{'Kontakt':>9}{'frozen%':>8}"
           f"{'bx_end':>8}{'bz_end':>8}{'Stufe':>7}")
    print(hdr)
    print("-" * 88)
    base = results.get("baseline", {}).get("drive_vzmean", None)
    for tag, _ in TESTS:
        if tag not in results: continue
        r = results[tag]
        # Ehrlicher Fortschritt: auf welcher Stufe steht der Körper? Stufe 1 = Kante x=1.0
        # überschritten, Stufe 2 = eine run weiter. <1.0 = noch vor der Treppe (Stufe 0).
        if r["bx_end"] > 1.0:
            step = int((r["bx_end"] - 1.0) / max(args.run, 1e-3)) + 1
        else:
            step = 0
        print(f"{tag:<13}{r['drive_vzmean']:>11.4f}{r['contact']:>9.1f}{r['frozen']:>8.0f}"
              f"{r['bx_end']:>8.3f}{r['bz_end']:>8.3f}{step:>7}")
    print("-" * 88)
    print("Lesart: Stufe = wie weit die Treppe hinauf (0 = noch davor, 1 = ueber erste Kante,")
    print("        2 = eine Stufe hoeher). bx_end ist der ehrliche Fortschritt, nicht bz_end.")
    print(f"\nGesamtzeit: {time.time()-t0:.0f} s")


if __name__ == "__main__":
    main()
