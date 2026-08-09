#!/usr/bin/env python3
"""
SLARC – CMA-ES Optimierung der KLETTER-Konstanten (headless, PyBullet DIRECT)
=============================================================================
Optimiert NUR die skalaren Kletter-Parameter der analytischen Regelung
(R1/R2/R3 bleiben fix – die tragen und sind ESP32-portabel). Kein Deep-RL:
für ~8 Skalare ist CMA-ES das richtige Werkzeug (konvergiert in einigen
hundert Headless-Läufen, CPU, keine Gradienten).

Robustheit: es wird gegen MEHRERE Stufenhöhen gleichzeitig optimiert
(sonst tunt es sich auf eine Treppe fest).

Aufruf:
    pip install cma
    python3 slarc_cma_climb.py                 # volle Optimierung
    python3 slarc_cma_climb.py --eval           # nur die Default-Parameter bewerten (Baseline)
    python3 slarc_cma_climb.py --gens 40 --pop 12
Ergebnis: bester Parametervektor wird laufend nach slarc_cma_best.txt geschrieben.
"""
import argparse
import math
import sys
import numpy as np
import pybullet as p
import slarc_sim_V10 as sim

# ── Zu optimierende Kletter-Konstanten:  name, (lo, hi), default ──────────
PARAMS = [
    ("G_CLIMB_REAR_FWD", 0.00, 0.18, 0.120),   # Hinterbein-Vorgriff auf die Stufe
    ("G_COM_SHIFT",      0.00, 0.10, 0.040),   # CoM-Wippe Amplitude
    ("G_COM_RAMP",     0.0003, 0.0025, 0.0008), # CoM-Wippe Rampe
    ("G_CLIMB_CLEAR",    0.02, 0.12, 0.050),   # Rumpfhöhe beim Klettern
    ("G_CLIMB_LIFT",     0.02, 0.14, 0.050),   # Fuß-Welt-Hub beim Schwung
    ("G_CLIMB_H_KP",    0.002, 0.025, 0.008),  # R3-Gain beim Klettern
    ("G_H_LOW_LP",      0.002, 0.030, 0.005),  # Referenz-Tiefpass
    ("G_CLIMB_DIR_DB",   0.02, 0.10, 0.050),   # Richtungs-Hysterese
]
NAMES = [q[0] for q in PARAMS]
LO = np.array([q[1] for q in PARAMS])
HI = np.array([q[2] for q in PARAMS])
DEFAULT = np.array([q[3] for q in PARAMS])

RISES = (0.08, 0.12, 0.17)     # Stufenhöhen, gegen die robust optimiert wird
STAIR_RUN = 0.25
STAIR_X = 0.60
SETTLE = 240
MAX_S = 22.0                    # max. Sim-Dauer je Lauf [s]


def _unit_to_real(u):
    """CMA arbeitet in [0,1]^n (einheitlich skaliert) -> echte Werte."""
    return LO + np.clip(u, 0.0, 1.0) * (HI - LO)


def run_climb(real, rise):
    """Ein headless Kletterlauf. Gibt Metriken zurück. Regler-Kern bleibt fix."""
    sim.STAIR_RISE = rise
    sim.STAIR_RUN = STAIR_RUN
    sim.STAIR_X = STAIR_X
    robot = None
    try:
        robot = sim.SlarcController()
        robot.init_pybullet(gui=False, build_stairs=True, spawn_can=False,
                            terrain='stairs')
        robot.auto_balance = True
        robot.G_FOOTHOLD = True
        robot.G_FREEZE_ENABLE = False           # --no-freeze (sonst Deadlock)
        robot.gait_name = 'placemove'
        robot._enter_gait()
        # Kletter-Parameter setzen (nur diese; alles andere bleibt Default)
        for name, v in zip(NAMES, real):
            setattr(robot, name, float(v))

        for _ in range(SETTLE):                 # ruhig einschwingen
            robot.cmd_vel_x = 0.0
            robot.update_gait(); p.stepSimulation()

        z0 = p.getBasePositionAndOrientation(robot.robot_id)[0][2]
        bz_hist = []
        tipped = False
        n = int(MAX_S * 240)
        robot.cmd_vel_x = 1.0
        for i in range(n):
            robot.cmd_vel_x = 1.0
            robot.update_gait(); p.stepSimulation()
            pos, orn = p.getBasePositionAndOrientation(robot.robot_id)
            roll, pitch, yaw = p.getEulerFromQuaternion(orn)
            bz = pos[2]
            if math.isnan(bz) or math.isnan(pitch) or abs(roll) > 0.6 or pitch > 0.55:
                tipped = True                    # umgekippt / nach hinten weg
                break
            bz_hist.append(bz)

        bz = np.array(bz_hist) if bz_hist else np.array([z0])
        climbed = float(bz.max() - z0)           # erreichter Höhengewinn
        # lokaler Bounce (peak-to-peak über 0.5s-Fenster) = Sicherheitsmaß
        bounce = 0.0
        if len(bz) > 40:
            w = 30
            pps = [bz[k:k+w].max() - bz[k:k+w].min() for k in range(0, len(bz)-w, 15)]
            bounce = float(np.mean(pps))
        return dict(climbed=climbed, steps=climbed / rise,
                    bounce=bounce, tipped=tipped)
    except Exception as e:
        return dict(climbed=0.0, steps=0.0, bounce=1.0, tipped=True, err=str(e))
    finally:
        try:
            p.disconnect()
        except Exception:
            pass


def score_one(real, rise):
    r = run_climb(real, rise)
    s = r["steps"]                               # Hauptbelohnung: erreichte Stufen
    if r["tipped"]:
        s -= 6.0                                 # harte Strafe fürs Kippen (sicherheitskritisch)
    s -= 25.0 * r["bounce"]                       # Bounce-Strafe (kein Hoch/Runter)
    return s, r


def fitness(u):
    """CMA MINIMIERT -> wir geben den negativen Gesamtscore zurück."""
    real = _unit_to_real(np.asarray(u))
    total = 0.0
    for rise in RISES:
        s, _ = score_one(real, rise)
        total += s
    return -total


def _report(real, tag=""):
    print(f"\n  {tag} Parameter:")
    for name, v in zip(NAMES, real):
        print(f"    {name:20s} = {v:.5f}")
    line = []
    for rise in RISES:
        s, r = score_one(real, rise)
        st = "KIPP" if r["tipped"] else f"{r['steps']:.2f} Stufen"
        line.append(f"rise {rise:.2f}: {st}, bounce {r['bounce']*1000:.0f}mm")
    print("   -> " + " | ".join(line))
    return real


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gens", type=int, default=50, help="max. CMA-Generationen")
    ap.add_argument("--pop", type=int, default=12, help="Population je Generation")
    ap.add_argument("--sigma", type=float, default=0.25, help="Start-Streuung (Einheitsraum)")
    ap.add_argument("--eval", action="store_true", help="nur Default-Parameter bewerten")
    args = ap.parse_args()

    if args.eval:
        _report(DEFAULT, tag="[DEFAULT]")
        return

    try:
        import cma
    except ImportError:
        print("Bitte 'pip install cma'."); sys.exit(1)

    # Start = aktuelle Defaults, in den Einheitsraum abgebildet
    u0 = np.clip((DEFAULT - LO) / (HI - LO), 0.0, 1.0)
    print("=== CMA-ES: Kletter-Konstanten optimieren ===")
    print(f"    {len(PARAMS)} Parameter | Rises {RISES} | pop {args.pop} | max {args.gens} Gen")
    _report(DEFAULT, tag="[Baseline/Default]")

    es = cma.CMAEvolutionStrategy(
        list(u0), args.sigma,
        {"bounds": [0.0, 1.0], "popsize": args.pop, "maxiter": args.gens, "seed": 1})

    gen = 0
    best_f = float("inf"); best_u = u0
    while not es.stop():
        sols = es.ask()
        fits = [fitness(u) for u in sols]
        es.tell(sols, fits)
        gen += 1
        i = int(np.argmin(fits))
        if fits[i] < best_f:
            best_f = fits[i]; best_u = sols[i]
            real = _unit_to_real(best_u)
            with open("slarc_cma_best.txt", "w") as fh:
                fh.write(f"# Gesamtscore {-best_f:.3f}  (Gen {gen})\n")
                for name, v in zip(NAMES, real):
                    fh.write(f"self.{name} = {v:.5f}\n")
        print(f"  Gen {gen:3d} | bester Score {-min(fits):.3f} | global {-best_f:.3f}")

    print("\n=== FERTIG ===")
    _report(_unit_to_real(best_u), tag="[BESTER]")
    print("  -> slarc_cma_best.txt (direkt in __init__ einsetzbar)")


if __name__ == "__main__":
    main()
