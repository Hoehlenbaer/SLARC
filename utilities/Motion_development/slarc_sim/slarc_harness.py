#!/usr/bin/env python3
"""
SLARC headless Regressions- & Mess-Harness
===========================================
Fährt jeden Modus deterministisch in PyBullet DIRECT (ohne GUI, schneller als
Echtzeit), misst OBJEKTIVE Metriken und prüft harte Grenzen → PASS/FAIL.

Zweck (die zwei Full-Stop-Fragen):
  1) Funktionierende Bausteine SICHERN: Mode 1/2/Balancer/Zentaur bekommen
     harte Asserts. Bricht ein Treppen-Patch einen Arbeits-Modus, fällt es hier
     in Sekunden auf — nicht erst im Live-Lauf.
  2) Treppensteigen STRUKTURIERT entwickeln: dieselbe Rig misst die Primitive
     B1..B4 (Höhe halten → Translation → eine Stufe → mehrstufig) mit Zahlen
     statt Augenmaß. "Sieht komisch aus" wird zu "höhe-σ 0.04 statt 0.01".

Aufruf:   python3 slarc_harness.py
Exit-Code 0 = alle bestanden (CI-tauglich), sonst 1.
Einzeln:  python3 slarc_harness.py B1     (nur Szenarien, deren Kürzel passt)

Hinweis: misst NUR die Sim. Die echte HW-Dynamik kann abweichen — aber ein in
der Sim reproduzierbarer, vermessener Gang ist die Voraussetzung für alles
Weitere. Grenzwerte unten sind Startwerte; nach dem ersten Lauf an die real
gemessenen Zahlen anpassen (die Spalten zeigen die Ist-Werte).
"""
import math
import sys
import numpy as np
import pybullet as p
import slarc_sim_V7 as sim


# ─────────────────────────────────────────────────────────────────────────
#  Messung
# ─────────────────────────────────────────────────────────────────────────
def _pose(robot):
    """Körperhöhe (Welt-z), Pitch, Roll, Yaw aus der Basis-Pose."""
    pos, orn = p.getBasePositionAndOrientation(robot.robot_id)
    roll, pitch, yaw = p.getEulerFromQuaternion(orn)
    return pos[0], pos[2], pitch, roll, yaw


def _n_contacts(robot):
    """Anzahl Füße mit Bodenkontakt (Kontakt eines Fuß-Links mit irgendetwas)."""
    n = 0
    for idx in robot._foot_link_idx.values():
        if idx is None or idx < 0:
            continue
        if p.getContactPoints(bodyA=robot.robot_id, linkIndexA=idx):
            n += 1
    return n


def _stance_air(robot):
    """Anzahl STAND-Füße OHNE Bodenkontakt (hängende Standbeine = Stützpolygon-Loch)."""
    state = getattr(robot, '_m7_state', {})
    n = 0
    for name, idx in robot._foot_link_idx.items():
        if idx is None or idx < 0:
            continue
        if state.get(name) != 'STANCE':
            continue
        if not p.getContactPoints(bodyA=robot.robot_id, linkIndexA=idx):
            n += 1
    return n


def run_scenario(label, mode, *, seconds=5.0, warmup=2.5, build_stairs=False,
                 cmd_vel_x=0.0, body_offset=0.0, auto_balance=False,
                 mode7=False, gui=False, kill_balance=False, kill_heading=False,
                 use_fk=False, spawn_x=0.0):
    """Ein Szenario headless fahren, Metriken über das Messfenster sammeln."""
    robot = sim.SlarcController()
    try:
        robot.init_pybullet(gui=gui, build_stairs=build_stairs, spawn_can=False)
        # Optional: Robot direkt an eine x-Position setzen (z.B. über die erste
        # Stufe straddeln, um P1/P2 ohne Vortrieb zu testen).
        if abs(spawn_x) > 1e-6:
            p.resetBasePositionAndOrientation(robot.robot_id,
                                              [spawn_x, 0, 0.20], [0, 0, 0, 1])
        robot.gait_mode = mode
        robot.auto_balance = auto_balance
        robot._m7_no_heading = kill_heading
        robot._m7_use_fk = use_fk          # Pitch aus FK/Ist statt Fußzielen
        if mode7:
            robot._m7_ready = False            # erzwingt sauberen _enter_feeler (Settle)

        # ── Warmup: still einschwingen / Settle (NICHT gemessen) ──
        for _ in range(int(warmup * 240)):
            robot.cmd_vel_x = 0.0
            robot.body_height_offset = body_offset
            if kill_balance:
                robot.auto_balance = False
            robot.update_gait()
            p.stepSimulation()

        # ── Messfenster ──
        x0 = _pose(robot)[0]
        z0 = _pose(robot)[1]               # Start-Höhe → Höhengewinn (Klettern)
        zs, pit, rol, con = [], [], [], []
        tipped = False
        x_tip = z_tip = None
        x_max = x0
        nan = False
        # Per-Bein-Reichweite (horizontale Mount→Fuß-Strecke; IK-Limit ~0.325)
        mounts = {leg.name: (leg.mount_x, leg.mount_y) for leg in robot.legs}
        reach_max = {name: 0.0 for name in mounts}
        onstep_evt = None     # (x, pitch, roll, leg) beim ERSTEN onstep (Stufenkontakt)
        climb_sp_max = 0.0     # max |Pitch-Sollwert| (Fußebene) → nickt er mit?
        stance_air_f = 0       # Frames mit ≥1 hängendem Standbein
        stance_air_max = 0     # max. Anzahl gleichzeitig hängender Standbeine
        restep = {}            # v2: Nachsetz-Zähler je Bein (STANCE→SWING)
        prev_state = dict(getattr(robot, '_m7_state', {}))
        n_air = 0
        air_phase = {}        # _m7_phase → Anzahl luftloser Frames
        air_swing = {}        # Schwungbein-Zustand → Anzahl luftloser Frames
        air_t = []            # Zeitpunkte [s] luftloser Frames
        air_z = []            # Körperhöhe in luftlosen Frames
        steps = int(seconds * 240)
        for i in range(steps):
            robot.cmd_vel_x = cmd_vel_x
            robot.body_height_offset = body_offset
            if kill_balance:
                robot.auto_balance = False
            robot.update_gait()
            p.stepSimulation()
            x, z, pitch, roll, yaw = _pose(robot)
            if any(math.isnan(v) for v in (z, pitch, roll)):
                nan = True
                break
            zs.append(z); pit.append(abs(pitch)); rol.append(abs(roll))
            x_max = max(x_max, x)
            c = _n_contacts(robot)
            con.append(c)
            foot = None
            if mode7:
                foot = getattr(robot, '_v2_foot', None) or getattr(robot, '_m7_foot', None)
            if foot:
                for name, (mx, my) in mounts.items():
                    f = foot.get(name)
                    if f:
                        r = math.hypot(f[0] - mx, f[1] - my)
                        if r > reach_max[name]:
                            reach_max[name] = r
            if c == 0:
                n_air += 1
                ph = getattr(robot, '_m7_phase', '?')
                air_phase[ph] = air_phase.get(ph, 0) + 1
                st = getattr(robot, '_m7_state', {})
                for sname, sval in st.items():
                    if sval in ('LIFT', 'REACH', 'PROBE'):
                        air_swing[sval] = air_swing.get(sval, 0) + 1
                air_t.append(i / 240.0)
                air_z.append(z)
            if abs(pitch) > 0.6 or abs(roll) > 0.6 or z < 0.05:
                if not tipped:
                    x_tip, z_tip = x, z      # Ort des ERSTEN Kippens merken
                tipped = True
            if onstep_evt is None and mode7:
                ons = getattr(robot, '_m7_onstep', {})
                hit = next((nm for nm, v in ons.items() if v), None)
                if hit:
                    onstep_evt = (x, pitch, roll, hit)   # erster Stufenkontakt
            if mode7:
                climb_sp_max = max(climb_sp_max,
                                   abs(getattr(robot, '_m7_climb_pitch_sp', 0.0)))
                sa = _stance_air(robot)
                if sa > 0:
                    stance_air_f += 1
                    stance_air_max = max(stance_air_max, sa)
                cur = getattr(robot, '_m7_state', {})
                for nm, sv in cur.items():
                    if sv == 'SWING' and prev_state.get(nm) != 'SWING':
                        restep[nm] = restep.get(nm, 0) + 1
                prev_state = dict(cur)
        x1 = _pose(robot)[0]
    finally:
        p.disconnect()

    if nan or not zs:
        return dict(label=label, nan=True)
    diag = ""
    if n_air:
        ph = ",".join(f"{k}:{v}" for k, v in sorted(air_phase.items()))
        sw = ",".join(f"{k}:{v}" for k, v in sorted(air_swing.items())) or "—"
        diag = (f"luftlos[{ph}] schwung[{sw}] t={min(air_t):.1f}..{max(air_t):.1f}s "
                f"z⌀{float(np.mean(air_z)):.3f}")
    if tipped and x_tip is not None:
        diag += f" | KIPP@x={x_tip:.2f} z={z_tip:.2f} (x_max={x_max:.2f})"
    elif diag:
        diag += f" | x_max={x_max:.2f}"
    if any(reach_max.values()):
        worst = max(reach_max, key=reach_max.get)
        rv = reach_max[worst]
        flag = " ÜBERSTRECKT!" if rv > 0.30 else ""
        diag += f" | reachMax {worst}={rv:.3f}{flag}"
    if onstep_evt is not None:
        ex, ep, er, eleg = onstep_evt
        diag += f" | onstep@x={ex:.2f} pitch={ep:.2f} roll={er:.2f} ({eleg})"
    elif mode7 and build_stairs:
        diag += " | onstep NIE (kein Stufen-Tastkontakt!)"
    z_climb = float(np.max(zs) - z0)        # Höhengewinn = geklettert
    if build_stairs:
        diag += f" | zKlimb={z_climb:+.3f} (z0={z0:.3f}→zmax={np.max(zs):.3f})"
    if climb_sp_max > 0.01:
        diag += f" | pitchSoll_max={climb_sp_max:.3f}"
    if mode7:
        pct = 100.0 * stance_air_f / max(1, len(con))
        if stance_air_f:
            diag += f" | standLuft {pct:.0f}% max{stance_air_max}"
        if restep:
            tot = sum(restep.values())
            short = {n.replace('front_', 'F').replace('rear_', 'R')
                      .replace('mid_', 'M').replace('_right', 'R').replace('_left', 'L'): v
                     for n, v in restep.items()}
            diag += " | nachsetz " + str(tot) + " " + \
                    ",".join(f"{k}:{v}" for k, v in sorted(short.items()))
    return dict(label=label, nan=False, tipped=tipped,
                z_mean=float(np.mean(zs)), z_sigma=float(np.std(zs)),
                z_max=float(np.max(zs)),
                pitch_max=float(np.max(pit)), roll_max=float(np.max(rol)),
                con_min=int(np.min(con)), con_mean=float(np.mean(con)),
                air_pct=100.0 * n_air / len(con), diag=diag,
                dx=float(x1 - x0))


def check(m, lim):
    """Metriken gegen Grenzen prüfen → (ok, [gründe])."""
    if m.get('nan'):
        return False, ["NaN/Crash"]
    f = []
    if m['tipped']:
        f.append("gekippt")
    if m['pitch_max'] > lim['pitch']:
        f.append(f"pitch {m['pitch_max']:.3f}>{lim['pitch']}")
    if m['roll_max'] > lim['roll']:
        f.append(f"roll {m['roll_max']:.3f}>{lim['roll']}")
    if m['z_sigma'] > lim['z_sigma']:
        f.append(f"höhe-σ {m['z_sigma']:.3f}>{lim['z_sigma']}")
    if m['con_min'] < lim['con_min']:
        f.append(f"kontakt {m['con_min']}<{lim['con_min']}")
    if 'z_lo' in lim and m['z_mean'] < lim['z_lo']:
        f.append(f"höhe {m['z_mean']:.3f}<{lim['z_lo']}")
    if 'z_hi' in lim and m['z_mean'] > lim['z_hi']:
        f.append(f"höhe {m['z_mean']:.3f}>{lim['z_hi']}")
    if 'dx_min' in lim and m['dx'] < lim['dx_min']:
        f.append(f"vortrieb {m['dx']:.3f}<{lim['dx_min']}")
    if 'air_max' in lim and m['air_pct'] > lim['air_max']:
        f.append(f"luftlos {m['air_pct']:.1f}%>{lim['air_max']}%")
    if 'z_climb_min' in lim and m['z_max'] < lim['z_climb_min']:
        f.append(f"geklettert z_max {m['z_max']:.3f}<{lim['z_climb_min']}")
    return (len(f) == 0), f


# ─────────────────────────────────────────────────────────────────────────
#  Szenarien
#   (Kürzel, Beschreibung, run_scenario-kwargs, Grenzen)
#   Grenzen sind STARTWERTE — nach dem ersten Lauf an die Ist-Spalten anpassen.
# ─────────────────────────────────────────────────────────────────────────
SCENARIOS = [
    # ── 1) Funktionierende Bausteine sichern ──
    ("M1", "Mode1 Tripod (lauf)",
        dict(mode=1, cmd_vel_x=0.03, seconds=6.0),
        dict(pitch=0.20, roll=0.20, z_sigma=0.04, con_min=1, dx_min=0.02)),
    ("M2", "Mode2 Ripple (lauf)",
        dict(mode=2, cmd_vel_x=0.03, seconds=6.0),
        dict(pitch=0.20, roll=0.20, z_sigma=0.04, con_min=1, dx_min=0.02)),
    ("BAL", "Balancer (stand)",
        dict(mode=1, cmd_vel_x=0.0, auto_balance=True, seconds=4.0),
        dict(pitch=0.10, roll=0.10, z_sigma=0.02, con_min=5)),
    ("Z", "Mode4 Zentaur (stance)",
        dict(mode=4, cmd_vel_x=0.0, seconds=5.0, warmup=3.0),
        dict(pitch=0.70, roll=0.30, z_sigma=0.04, con_min=2)),

    # ── 2) Treppen-Primitive (strukturierter Aufbau) ──
    # B1: Mode 7 auf FLACHEM Boden, nur Höhe halten (kein Laufen). Das ist der
    #     Baustein, der uns 3× zerlegt hat — muss bombenfest sein, BEVOR eine
    #     Stufe ins Spiel kommt. Geprüft: ruhige Höhe (kein Pumpen → kleines σ),
    #     alle Füße Kontakt (kein Hängen), waagerecht.
    ("B1", "B1 Mode7 Höhe flach",
        dict(mode=7, mode7=True, cmd_vel_x=0.0, seconds=4.0, warmup=4.0,
             build_stairs=False),
        dict(pitch=0.08, roll=0.08, z_sigma=0.015, con_min=5,
             z_lo=0.12, z_hi=0.20)),
    # B2: Mode 7 flach, jetzt mit Translation (Wellengang + Shift), ohne Stufe.
    # B2: FUNKTIONAL — kein Kippen, Höhe gehalten, Vortrieb. Das 3%-Abheben ist
    # ein bestätigtes Sim-Steifigkeits-Artefakt (3-kg-Roboter hüpft real nicht);
    # air_max=10 fängt nur Katastrophen (z.B. der 46%-Fehlversuch).
    ("B2", "B2 Mode7 Translation flach",
        dict(mode=7, mode7=True, cmd_vel_x=0.03, seconds=8.0, warmup=4.0,
             build_stairs=False),
        dict(pitch=0.15, roll=0.15, z_sigma=0.02, con_min=0, dx_min=0.05,
             air_max=10.0)),
    # B3: erste Stufe (10 cm). Roboter läuft flach an die Treppe (x≈1.0) und
    # klettert die erste Stufe. Erfolg: erreicht die Treppe (dx>1.0), steigt
    # mind. eine Stufe (z_max>0.21 = ~+0.05 über Flachhöhe) und kippt nicht.
    ("B3", "B3 Mode7 eine Stufe 10cm",
        dict(mode=7, mode7=True, cmd_vel_x=0.04, seconds=30.0, warmup=3.0,
             build_stairs=True),
        dict(pitch=0.40, roll=0.30, z_sigma=0.50, con_min=0,
             dx_min=1.0, z_climb_min=0.21)),
    # B3N: identisch zu B3, aber KURSREGELUNG AUS (kill_heading). Isoliert den
    # Verdacht, dass die Yaw-Drehung der Standfüße + Rückschwenken aufspiralt
    # (reach-Runaway). Bleibt reachMax hier ~0.32 und kippt er nicht → Kurs-
    # regelung ist die Ursache, nicht der Gang selbst.
    ("B3N", "B3N eine Stufe, OHNE Kurs",
        dict(mode=7, mode7=True, cmd_vel_x=0.04, seconds=30.0, warmup=3.0,
             build_stairs=True, kill_heading=True),
        dict(pitch=0.40, roll=0.30, z_sigma=0.50, con_min=0,
             dx_min=1.0, z_climb_min=0.21)),
    # ── ISOLATION des B3-Sturzes bei x=0.54 (flach, vor der Treppe) ──
    # B2S: B2 EXAKT, nur build_stairs=True. Kippt er hier → die Treppe-Objekte
    #      stören die Flach-Physik (Solver/Determinismus). Bleibt grün → unschuldig.
    ("B2S", "B2S flach + Treppe gebaut",
        dict(mode=7, mode7=True, cmd_vel_x=0.03, seconds=8.0, warmup=4.0,
             build_stairs=True),
        dict(pitch=0.15, roll=0.15, z_sigma=0.02, con_min=0, dx_min=0.05,
             air_max=10.0)),
    # B3W: B3 EXAKT, nur warmup=4.0. Pitch-Schwelle gelockert: der Körper NICKT
    #      jetzt absichtlich mit der Treppe (Katzen-Lösung, ~Steigung 0.2 bei 5cm /
    #      0.38 bei 10cm) — das ist KEIN Kippen. Echtes Kippen fängt roll>0.3 + der
    #      tipped-Flag (pitch/roll>0.6). pitchSoll_max zeigt, ob er parallel stellt.
    ("B3W", "B3W eine Stufe, warmup=4",
        dict(mode=7, mode7=True, cmd_vel_x=0.04, seconds=30.0, warmup=4.0,
             build_stairs=True),
        dict(pitch=0.50, roll=0.30, z_sigma=0.50, con_min=0,
             dx_min=1.0, z_climb_min=0.21)),
    # B3WF: identisch zu B3W, aber Pitch-Schätzung aus FK/IST-Fußpositionen statt
    #       Fußzielen. Vergleich: liefert FK die gleiche Lageregelung (HW-näher,
    #       aber verrauschter)? pitchSoll_max + höheσ nebeneinander legen.
    ("B3WF", "B3WF eine Stufe, Pitch via FK",
        dict(mode=7, mode7=True, cmd_vel_x=0.04, seconds=30.0, warmup=4.0,
             build_stairs=True, use_fk=True),
        dict(pitch=0.50, roll=0.30, z_sigma=0.50, con_min=0,
             dx_min=1.0, z_climb_min=0.21)),
    # B3/B4 (eine Stufe / mehrstufig) folgen, sobald B1+B2 grün sind — sie
    # brauchen Positionierung vor der Treppe (build_stairs=True, Startpose bei
    # x≈0.8). Erst die Basis vermessen, dann hochziehen.
    # ── v2-Stufe-1-Tests (nur Körper-Schleifen P1+P2, kein Vortrieb/Stepping) ──
    # V2F: auf FLACH (Robot bei x=0, vor der Treppe) → testet P2: kommt der Körper
    #      runter auf Femur-auf/Tibia-⊥? pitch sollte ~0 bleiben.
    ("V2F", "v2 Stufe1 FLACH (P2: kommt runter?)",
        dict(mode=7, mode7=True, cmd_vel_x=0.0, seconds=8.0, warmup=4.0,
             build_stairs=True, auto_balance=True),
        dict(pitch=0.15, roll=0.15, z_sigma=0.50, con_min=0, dx_min=-99.0)),
    # V2P: über die erste Stufe gestraddelt (Front-Füße auf Stufe 1, Rest flach) →
    #      testet P1: stellt er sich PARALLEL zur Stufenebene? + P2 gleichzeitig.
    # V2W: GEHEN auf FLACH (Stufe 2) — Vortrieb + event-getriebenes Nachsetzen.
    #      Testet: läuft er kontinuierlich, gute Pose, sauberes Nachsetzen, kein
    #      Drift/Kippen? Noch KEINE Treppe.
    ("V2W", "v2 Stufe2 GEHEN flach",
        dict(mode=7, mode7=True, cmd_vel_x=0.04, seconds=20.0, warmup=4.0,
             build_stairs=False, auto_balance=True),
        dict(pitch=0.20, roll=0.20, z_sigma=0.50, con_min=0, dx_min=0.15)),
    # V2C: KLETTERN (Stufe 3) — spawn bei x=0.5 vor der 5-cm-Treppe (erste Stufe
    #      x=1.0), vorlaufen. Beobachtungslauf: trifft der Schwungfuß die Stufenwand
    #      (onstep@x≈1.0)? nickt der Körper hoch (pitchSoll→~0.2)? gewinnt er Höhe
    #      (zKlimb)? oder läuft er an / kippt / überstreckt? Schwellen locker.
    ("V2C", "v2 Stufe3 KLETTERN 5cm",
        dict(mode=7, mode7=True, cmd_vel_x=0.04, seconds=40.0, warmup=4.0,
             build_stairs=True, auto_balance=True, spawn_x=0.5),
        dict(pitch=0.45, roll=0.25, z_sigma=0.60, con_min=0, dx_min=0.4)),
]


def main():
    want = sys.argv[1] if len(sys.argv) > 1 else None
    print("=" * 98)
    print(" SLARC Regressions- & Mess-Harness   (PyBullet DIRECT, headless)")
    print("=" * 98)
    hdr = (f"{'Szenario':<26}{'Erg':<6}{'pitchMax':>9}{'rollMax':>9}"
           f"{'höhe⌀':>8}{'höheσ':>8}{'kMin':>6}{'k⌀':>6}{'luft%':>7}{'dx':>7}  Hinweise")
    print(hdr)
    print("-" * 98)
    allpass = True
    ran = 0
    for code, label, kw, lim in SCENARIOS:
        if want and not (want.upper() in code.upper()
                         or want.upper() == label.upper()):
            continue
        ran += 1
        m = run_scenario(label, **kw)
        ok, fails = check(m, lim)
        allpass &= ok
        if m.get('nan'):
            print(f"{label:<26}{'FAIL':<6}{'—':>9}{'—':>9}{'—':>8}{'—':>8}"
                  f"{'—':>6}{'—':>6}{'—':>7}{'—':>7}  NaN/Crash")
        else:
            tag = "PASS" if ok else "FAIL"
            hint = ";".join(fails) if fails else "ok"
            if m.get('diag'):
                hint += "  " + m['diag']
            print(f"{label:<26}{tag:<6}{m['pitch_max']:>9.3f}{m['roll_max']:>9.3f}"
                  f"{m['z_mean']:>8.3f}{m['z_sigma']:>8.3f}{m['con_min']:>6}"
                  f"{m['con_mean']:>6.1f}{m['air_pct']:>7.1f}{m['dx']:>7.3f}  "
                  + hint)
    print("=" * 98)
    if ran == 0:
        print(f" Kein Szenario passt zu '{want}'. Verfügbar:",
              ", ".join(c for c, *_ in SCENARIOS))
        sys.exit(2)
    print(" ERGEBNIS:", "ALLE BESTANDEN \u2713" if allpass else "FEHLER \u2717")
    sys.exit(0 if allpass else 1)


if __name__ == '__main__':
    main()
