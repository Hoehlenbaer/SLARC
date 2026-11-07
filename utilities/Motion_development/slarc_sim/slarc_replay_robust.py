#!/usr/bin/env python3
"""
SLARC – Robustheitstest für Aufnahmen aus slarc_manual (V4, 07.11.2026)
=======================================================================
Spielt eine Aufnahme headless mehrfach ab: einmal exakt von der aufgezeichneten
Startpose, dann mit variierter Startpose (Drehung um die Hochachse, Kippen um die
Längsachse, Verschieben). Läuft parallel, eine Zeile je Lauf, am Ende die Quote.

Erfolg (Standard):
  aufrecht   up_z > --up-min (Körper-Hochachse zeigt nach oben; 1 = waagerecht)
  Höhe       |z_Ende - z_Ende_Aufnahme| < --dz-max  (z. B. dieselbe Stufe erreicht)
Mit --goal back: Erfolg = auf dem Rücken (up_z < -up_min), z. B. für Gegenproben.

  python3 slarc_replay_robust.py slarc_roll.jsonl
  python3 slarc_replay_robust.py slarc_stairs.jsonl --yaw 0 10 20 --tilt 0 --shift 0 0.03
"""
import argparse, itertools, json, os, subprocess, sys
from concurrent.futures import ThreadPoolExecutor

ap = argparse.ArgumentParser()
ap.add_argument("file")
ap.add_argument("--yaw", type=float, nargs="+", default=[0, -20, 20], help="Gier-Varianten [°] (± wird gespiegelt)")
ap.add_argument("--tilt", type=float, nargs="+", default=[0, -10, 10], help="Kipp-Varianten [°]")
ap.add_argument("--shift", type=float, nargs="+", default=[0, 0.05], help="Verschiebung [m] in x und y (je ±)")
ap.add_argument("--up-min", type=float, default=0.9)
ap.add_argument("--dz-max", type=float, default=0.03)
ap.add_argument("--goal", choices=("upright", "back"), default="upright")
ap.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 1))
a = ap.parse_args()

HERE = os.path.dirname(os.path.abspath(__file__))
shifts = sorted({(0.0, 0.0)} | {(sx * d, sy * d) for d in a.shift if d for sx, sy in ((1, 0), (-1, 0), (0, 1), (0, -1))})
cases = [(0.0, 0.0, 0.0, 0.0)]
for yaw, tilt, (dx, dy) in itertools.product(a.yaw, a.tilt, shifts):
    c = (float(yaw), float(tilt), dx, dy)
    if c not in cases: cases.append(c)

def run(c):
    yaw, tilt, dx, dy = c
    cmd = [sys.executable, os.path.join(HERE, "slarc_manual.py"), "--no-gui", "--no-hud",
           "--replay", os.path.abspath(a.file), "--start-yaw=%g" % yaw, "--start-tilt=%g" % tilt,
           "--start-dx=%g" % dx, "--start-dy=%g" % dy]
    out = subprocess.run(cmd, cwd=HERE, capture_output=True, text=True).stdout
    line = next((l for l in out.splitlines() if l.startswith("RESULT ")), None)
    return c, (json.loads(line[7:]) if line else None), out[-400:]

print("Aufnahme: %s | %d Läufe | %d parallel" % (a.file, len(cases), a.jobs))
print("  Gier°  Kipp°    dx     dy  |  up_z   dz_mm  Ende x/y/z [m]          Spitze        LIM  Ergebnis")
ok_n = 0; base_end = None
with ThreadPoolExecutor(a.jobs) as ex:
    for c, r, tail in ex.map(run, cases):
        if r is None:
            print("  %+5.0f  %+5.0f  %+5.2f  %+5.2f  |  FEHLER\n%s" % (c + (tail,))); continue
        rec_z = r["rec_end_body"][2] if r["rec_end_body"] else r["end_pos"][2]
        dz = r["end_pos"][2] - rec_z
        if a.goal == "upright":
            ok = r["up_z"] > a.up_min and abs(dz) < a.dz_max
        else:
            ok = r["up_z"] < -a.up_min
        ok_n += ok
        if c == (0.0, 0.0, 0.0, 0.0): base_end = r["end_pos"]
        print("  %+5.0f  %+5.0f  %+5.2f  %+5.2f  | %+5.2f  %+6.0f  %+6.3f %+6.3f %+6.3f   %3d%% %-8s %3d  %s"
              % (c[0], c[1], c[2], c[3], r["up_z"], 1000 * dz, *r["end_pos"], r["peak_pct"], r["peak_at"],
                 r["lim"], "OK" if ok else "--"))
print("Erfolg: %d/%d" % (ok_n, len(cases)))
if base_end:
    print("Referenzlauf (ohne Variation) endet bei x %.3f y %.3f z %.3f" % tuple(base_end))
