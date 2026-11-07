#!/usr/bin/env python3
"""
SLARC – MANUELLE Teleop + AUFNAHME/REPLAY   (slarc_manual V2, 07.11.2026)
=========================================================================
Fuß-ZIELE fest im Körperframe (Servos halten stur), TASTEN bewegen in WELT-
Richtung. Aufnahme schreibt mit festem Takt alles (Fußziele, Fußpositionen,
Kontakt, Fußlast, Gelenkwinkel, Servomomente, Körperpose, Beinselektion) in
eine JSONL-Datei; 'k' markiert Keyframes. Replay fährt die Sequenz nach.

V2: Modell = CAD-URDF (wird beim Start geprüft), Kontakt als Fußfarbe,
    Last-/Momentanzeige als Tabelle im Terminal + Label je Fuß im 3D-Fenster,
    Körper seitlich verschieben (a/d), StallGuard im Handbetrieb aus.

Aufnahme:  python3 slarc_manual.py --rise 0.17
Replay:    python3 slarc_manual.py --rise 0.17 --replay slarc_demo.jsonl

TASTEN (Fenster-Fokus nötig) – Bewegungsrichtung ist WELT:
  1..6        Bein wählen (FR,FL,MR,ML,RR,RL)
  Pfeile L/R  Fuß WELT-x    Pfeile U/D  Fuß WELT-z    n / m  Fuß WELT-y
  w / s       alle Füße WELT-x (Körper vor/zurück)   a / d  Körper links/rechts
  r / f       Körper höher/tiefer
  t / g       Körper-PITCH (Nase hoch/runter)         z / h  Körper-ROLL
  SPACE Bein->Neutral   x Pose->Neutral
  j           AUFNAHME an/aus (schreibt --out)
  k           Keyframe markieren (während der Aufnahme)
  v           Spitzenwerte ausgeben und zurücksetzen
  p           Zustand ins Log     ESC/q  Ende

ANZEIGE
  Fußfarbe:  GRÜN = Mikroschalter gedrückt (Auflage von oben, entprellt wie HW)
             ORANGE = Berührung nur seitlich (z. B. Stufenkante), Schalter offen
             ROT = Luft
  Label am Fuß: Bein, höchstbelasteter Servo (C/F/T) und % vom Stall-Moment.
             Farbe nur nach Auslastung: grün < 50 %, gelb 50–80 %, rot >= 80 %.
  Terminal:  Tabelle aller 18 Servos (% Stall und Nm), Fußlast in N und % vom
             Gewicht, Kontakt, Gelenkgrenzen-Treffer (LIM). '>' = gewähltes Bein.
"""
import argparse, math, time, json, sys
import pybullet as p
import slarc_sim_V10 as sim

ap = argparse.ArgumentParser()
ap.add_argument("--rise", type=float, default=0.17)
ap.add_argument("--run",  type=float, default=0.25)
ap.add_argument("--stair-x", type=float, default=0.60)
ap.add_argument("--no-stairs", action="store_true")
ap.add_argument("--replay", type=str, default=None, help="JSONL-Sequenz abspielen")
ap.add_argument("--out", type=str, default="slarc_demo.jsonl", help="Aufnahme-Datei")
ap.add_argument("--stallguard", action="store_true",
                help="StallGuard aktiv lassen (hebt ein blockiertes Bein selbst 10 cm an)")
ap.add_argument("--no-hud", action="store_true", help="keine Terminal-Tabelle (nur Log-Zeilen)")
ap.add_argument("--no-gui", action="store_true", help="[Test] ohne Fenster, ohne Tasten")
ap.add_argument("--frames", type=int, default=0, help="[Test] nach N Frames beenden")
a = ap.parse_args()

# [V2] CAD-URDF erzwingen: ohne sie keine Aussage über reale Lasten
if not (sim.USE_CAD_URDF and sim._os.path.isfile(sim.CAD_URDF)):
    sys.exit("  FEHLER: CAD-URDF fehlt: %s (meshes/ daneben nötig)" % sim.CAD_URDF)

sim.STAIR_RISE = a.rise; sim.STAIR_RUN = a.run; sim.STAIR_X = a.stair_x
GUI = not a.no_gui
robot = sim.SlarcController()
robot.init_pybullet(gui=GUI, build_stairs=not a.no_stairs, spawn_can=False, terrain='stairs')
robot._g_pitch_eff = 0.0; robot._g_roll_eff = 0.0
if GUI:   # [V2] Startkamera nah am Roboter (vorher 5 m -> Labels unlesbar); Maus ändert sie wie gewohnt
    p.resetDebugVisualizerCamera(cameraDistance=1.1, cameraYaw=40, cameraPitch=-30,
                                 cameraTargetPosition=list(p.getBasePositionAndOrientation(robot.robot_id)[0]))
if not a.stallguard:
    robot.RECOVER_LIFT = 0.0     # [V2] Handbetrieb: kein selbständiges Anheben

LEGS = list(robot.legs); NAMES = [l.name for l in LEGS]
SHORT = {"front_right": "FR", "front_left": "FL", "mid_right": "MR",
         "mid_left": "ML", "rear_right": "RR", "rear_left": "RL"}
TYPES = ("coxa", "femur", "tibia")
REC_EVERY = 8            # Aufnahme-/Replay-Takt: alle 8 Sim-Schritte ein Sample (~30 Hz)
TAU_MAX = sim.SERVO_STALL_NM
WARN, CRIT = 0.50, 0.80
JIDX = {l.name: [robot.joint_map[f"{l.name}_{t}_joint"] for t in TYPES] for l in LEGS}
JLIM = {t: lim for t, lim in zip(TYPES, (robot.ik.COXA_MAX, robot.ik.FEMUR_MAX, robot.ik.TIBIA_MAX))}

# [V2] Modellprüfung: Masse aus der geladenen URDF
MASS = sum(p.getDynamicsInfo(robot.robot_id, i)[0] for i in range(-1, p.getNumJoints(robot.robot_id)))
WEIGHT = MASS * 9.81
print("  Modell: %s | Masse %.3f kg | Gewicht %.1f N | Stall %.2f Nm"
      % (sim._os.path.basename(sim.CAD_URDF), MASS, WEIGHT, TAU_MAX))
if abs(MASS - 3.79) > 0.15:
    print("  WARNUNG: Masse weicht von der CAD-URDF (3.79 kg) ab")

# [V2] PyBullet meldet die Normalkraft geteilt durch numSubSteps (gemessen: Summe 50 % bei 2,
# 25 % bei 4, 100 % bei 1). Korrekturfaktor, damit die Fußlast in N stimmt.
NSUB = int(p.getPhysicsEngineParameters().get("numSubSteps", 1)) or 1

def neutral(leg):
    nx, ny = robot._gait_neutral(leg, 0.5); return [nx, ny, robot.G_Z]
foot = {l.name: neutral(l) for l in LEGS}

# ─────────────────────────── MESSUNG ───────────────────────────
tau_lp = {(n, t): 0.0 for n in NAMES for t in TYPES}   # gefilterte Momente [Nm]
force_lp = {n: 0.0 for n in NAMES}                      # gefilterte Fußlast [N]
peak = {}                                               # (n, t) -> Nm, seit 'v'
lim_cnt = {n: 0 for n in NAMES}                         # IK-Zielrücknahmen je Bein, seit 'v'
lim_now = {n: False for n in NAMES}

def contact_state(leg):
    """2 = Schalter gedrückt (entprellt, Normale nach oben), 1 = nur seitlich, 0 = Luft."""
    if robot._foot_touch_down(leg): return 2
    idx = robot._foot_link_idx[leg.name]
    return 1 if any(c[3] == idx for c in robot._contact_cache) else 0

def measure():
    """Einmal je Frame: Kontakt-Cache/Latch, Momente und Fußlast (Tiefpass 0.2 wie V10)."""
    robot._refresh_contact_cache()
    for l in LEGS:
        for t, j in zip(TYPES, JIDX[l.name]):
            raw = abs(p.getJointState(robot.robot_id, j)[3])
            k = (l.name, t); tau_lp[k] += (raw - tau_lp[k]) * 0.2
            if tau_lp[k] > peak.get(k, 0.0): peak[k] = tau_lp[k]
        force_lp[l.name] += (robot._foot_force(l) * NSUB - force_lp[l.name]) * 0.2

def set_leg(l, f):
    h0 = sim.HexapodKinematics.lim_hits
    robot._set_leg(l, f[0], f[1], f[2])
    lim_now[l.name] = sim.HexapodKinematics.lim_hits > h0
    if lim_now[l.name]: lim_cnt[l.name] += 1

def leg_worst(n):
    t = max(TYPES, key=lambda t: tau_lp[(n, t)]); return t, tau_lp[(n, t)] / TAU_MAX

# ─────────────────────────── ANZEIGE ───────────────────────────
FOOT_COL = {2: [0.0, 0.85, 0.0, 1], 1: [1.0, 0.55, 0.0, 1], 0: [0.9, 0.0, 0.0, 1]}
foot_col = {}; label_id = {}

def sev_rgb(r):
    return [0.1, 0.9, 0.1] if r < WARN else [1.0, 0.8, 0.0] if r < CRIT else [1.0, 0.1, 0.1]

def update_gui(sel):
    if not GUI: return
    for i, l in enumerate(LEGS):
        cs = contact_state(l); idx = robot._foot_link_idx[l.name]
        if foot_col.get(l.name) != cs:
            p.changeVisualShape(robot.robot_id, idx, rgbaColor=FOOT_COL[cs]); foot_col[l.name] = cs
        t, r = leg_worst(l.name)
        txt = "%s%s %s%d%%%s" % (">" if i == sel else "", SHORT[l.name], t[0].upper(),
                                 round(r * 100), " LIM" if lim_now[l.name] else "")
        wp = p.getLinkState(robot.robot_id, idx)[0]
        bp = p.getBasePositionAndOrientation(robot.robot_id)[0]
        dx, dy = wp[0] - bp[0], wp[1] - bp[1]; dn = math.hypot(dx, dy) or 1.0
        pos = [wp[0] + 0.08 * dx / dn, wp[1] + 0.08 * dy / dn, wp[2] + 0.10]   # außen über dem Fuß
        kw = dict(textColorRGB=sev_rgb(r), textSize=1.3)
        if l.name in label_id: kw["replaceItemUniqueId"] = label_id[l.name]
        label_id[l.name] = p.addUserDebugText(txt, pos, **kw)

ANSI = sys.stdout.isatty() and not a.no_hud
def c_sev(r, s):
    if not ANSI: return s
    return ("\033[32m" if r < WARN else "\033[33m" if r < CRIT else "\033[31;1m") + s + "\033[0m"

log_lines = []
def msg(s):
    if ANSI:
        log_lines.append(s); del log_lines[:-4]
    else:
        print("  " + s)

hud_n = 0
def hud(sel, rec, n_samples):
    """Feste Tabelle im Terminal, überschreibt sich selbst (ANSI)."""
    global hud_n
    if not ANSI: return
    bpos, born = p.getBasePositionAndOrientation(robot.robot_id)
    rl, pt, _ = p.getEulerFromQuaternion(born)
    L = []
    L.append("SLARC manuell V2 | Bein %s | %s | Körper z %.3f m  Roll %+.1f°  Pitch %+.1f°"
             % (SHORT[NAMES[sel]], ("AUFNAHME %d" % n_samples) if rec else "keine Aufnahme",
                bpos[2], math.degrees(rl), math.degrees(pt)))
    L.append("   Bein Kontakt  Fußlast       Coxa          Femur         Tibia         Gelenkwinkel C/F/T")
    tot = 0.0
    for i, l in enumerate(LEGS):
        n = l.name; cs = contact_state(l); f = force_lp[n]; tot += f
        cells = []
        for t in TYPES:
            r = tau_lp[(n, t)] / TAU_MAX
            cells.append(c_sev(r, "%3d%% %4.2fNm" % (round(r * 100), tau_lp[(n, t)])))
        q = [math.degrees(p.getJointState(robot.robot_id, j)[0]) for j in JIDX[n]]
        qs = []
        for t, v in zip(TYPES, q):
            s = "%+4.0f" % v
            if abs(math.radians(v)) > JLIM[t] - math.radians(5): s = c_sev(1.0, s)   # < 5° vor Grenze
            qs.append(s)
        L.append(" %s %-3s %-7s %5.1fN %3d%%   %s  %s  %s   %s%s"
                 % (">" if i == sel else " ", SHORT[n], ("TRÄGT", "SEITE", "Luft")[2 - cs],
                    f, round(100 * f / WEIGHT), cells[0], cells[1], cells[2], "/".join(qs),
                    c_sev(1.0, "  LIM") if lim_now[n] else ""))
    L.append("   Summe Fußlast %.1f N = %d %% des Gewichts (%.1f N; Rest trägt Rumpf/Kante)"
             % (tot, round(100 * tot / WEIGHT), WEIGHT))
    L.append("   Log: " + (log_lines[-1] if log_lines else ""))
    for s in log_lines[-4:-1][::-1]: L.append("        " + s)
    while len(L) < 13: L.append("")
    out = ("\033[%dF" % hud_n) if hud_n else ""
    out += "".join("\033[K" + s + "\n" for s in L)
    sys.stdout.write(out); sys.stdout.flush(); hud_n = len(L)

def peak_report():
    lines = ["Spitzen seit Start/letztem 'v' (Tiefpass, % Stall):"]
    for n in NAMES:
        lines.append("  %s  " % SHORT[n] + "  ".join("%s %3d%%" % (t[0].upper(), round(100 * peak.get((n, t), 0) / TAU_MAX))
                                                    for t in TYPES) + "  LIM %d" % lim_cnt[n])
    k = max(peak, key=peak.get) if peak else None
    if k: lines.append("  Max: %s %s %d%% (%.2f Nm)" % (SHORT[k[0]], k[1], round(100 * peak[k] / TAU_MAX), peak[k]))
    return lines

# ─────────────────────────── AUFNAHME-SAMPLE ───────────────────────────
def sample(frame, kf, sel, pitch_c, roll_c):
    bpos, born = p.getBasePositionAndOrientation(robot.robot_id)
    rl, pt, yw = p.getEulerFromQuaternion(born)
    feet = []
    for l in LEGS:
        fx, fy, fz = foot[l.name]
        wp = p.getLinkState(robot.robot_id, robot._foot_link_idx[l.name])[0]
        q = [p.getJointState(robot.robot_id, j)[0] for j in JIDX[l.name]]
        feet.append([l.name, round(fx,4), round(fy,4), round(fz,4),
                     round(wp[0],4), round(wp[1],4), round(wp[2],4),
                     int(contact_state(l) == 2),                      # wie V1: 1 = Schalter gedrückt
                     round(force_lp[l.name], 2),                      # [V2] Fußlast N
                     [round(v, 4) for v in q],                         # [V2] Gelenkwinkel rad
                     [round(tau_lp[(l.name, t)], 3) for t in TYPES],   # [V2] Momente Nm (Tiefpass)
                     int(lim_now[l.name])])                            # [V2] IK-Grenze getroffen
    return {"f": frame, "sel": sel, "leg": NAMES[sel], "kf": kf,
            "cpr": [round(pitch_c,4), round(roll_c,4)],  # kommandiert
            "body": [round(bpos[0],4), round(bpos[1],4), round(bpos[2],4),
                     round(pt,4), round(rl,4), round(yw,4)],
            "feet": feet}

def step_sim():
    p.stepSimulation()
    if GUI: time.sleep(1.0/240.0)

# ─────────────────────────── REPLAY-MODUS ───────────────────────────
if a.replay:
    with open(a.replay) as fh:
        seq = [json.loads(ln) for ln in fh if ln.strip()]
    print("  Replay: %d Samples aus %s" % (len(seq), a.replay))
    frame = 0
    for s in seq:
        for e in s["feet"]:
            foot[e[0]] = [e[1], e[2], e[3]]
        cpr = s.get("cpr", [0.0, 0.0])
        robot._g_pitch_eff = cpr[0]; robot._g_roll_eff = cpr[1]
        for _ in range(REC_EVERY):
            for l in LEGS: set_leg(l, foot[l.name])
            step_sim(); measure(); frame += 1
            if frame % 8 == 0: update_gui(s.get("sel", 0))
            if frame % 24 == 0: hud(s.get("sel", 0), False, 0)
        if s.get("kf"): msg("Keyframe bei Sample-Frame %d" % s["f"])
    msg("Replay fertig.")
    for ln in peak_report(): msg(ln) if not ANSI else print(ln)
    while GUI:
        step_sim(); measure()
    raise SystemExit

# ─────────────────────────── AUFNAHME/TELEOP ────────────────────────
sel = 0; STEP = 0.0015; APOS = 0.004
pitch = 0.0; roll = 0.0     # manueller Körper-Pitch/Roll (via _g_pitch_eff/_roll_eff, stur)
recording = False; rec_fh = None; pending_kf = False; n_samples = 0

def world_to_body_delta(dw):
    if dw == (0.0, 0.0, 0.0): return (0.0, 0.0, 0.0)
    m = p.getMatrixFromQuaternion(p.getBasePositionAndOrientation(robot.robot_id)[1])
    return (m[0]*dw[0]+m[3]*dw[1]+m[6]*dw[2],
            m[1]*dw[0]+m[4]*dw[1]+m[7]*dw[2],
            m[2]*dw[0]+m[5]*dw[1]+m[8]*dw[2])

print(__doc__)
msg("Ausgewählt: %s" % SHORT[NAMES[sel]] + ("" if a.stallguard else " | StallGuard aus"))
DOWN = p.KEY_IS_DOWN; frame = 0
while True:
    keys = p.getKeyboardEvents()
    for k, st in keys.items():
        if not (st & p.KEY_WAS_TRIGGERED): continue
        if ord('1') <= k <= ord('6'):
            sel = k - ord('1'); msg("Ausgewählt: %s" % SHORT[NAMES[sel]])
        elif k == ord(' '): foot[NAMES[sel]] = neutral(LEGS[sel]); msg("%s -> Neutral" % SHORT[NAMES[sel]])
        elif k == ord('x'):
            for l in LEGS: foot[l.name] = neutral(l)
            pitch = 0.0; roll = 0.0
            msg("Pose -> Neutral")
        elif k == ord('j'):
            if not recording:
                rec_fh = open(a.out, "w"); recording = True; n_samples = 0
                msg("AUFNAHME an -> %s" % a.out)
            else:
                recording = False; rec_fh.close()
                msg("AUFNAHME aus (%d Samples in %s)" % (n_samples, a.out))
        elif k == ord('k'):
            if recording: pending_kf = True; msg("Keyframe (Bein %s)" % SHORT[NAMES[sel]])
            else: msg("k: nur während der Aufnahme")
        elif k == ord('v'):
            for ln in peak_report(): msg(ln)
            peak.clear(); lim_cnt.update({n: 0 for n in NAMES})
            msg("Spitzen zurückgesetzt" + (" (Tabelle oben im Log nur letzte Zeilen; Details mit --no-hud)" if ANSI else ""))
        elif k == ord('p'):
            bpos = p.getBasePositionAndOrientation(robot.robot_id)[0]
            msg("Körper=(%.3f,%.3f,%.3f) | %s" % (bpos[0], bpos[1], bpos[2],
                " ".join("%s:%s" % (SHORT[l.name], "GSL"[2 - contact_state(l)]) for l in LEGS)))
        elif k in (27, ord('q')):
            if rec_fh and not rec_fh.closed: rec_fh.close()
            p.disconnect(); raise SystemExit

    dsel=[0.,0.,0.]; dall=[0.,0.,0.]
    if keys.get(p.B3G_RIGHT_ARROW,0)&DOWN: dsel[0]+=STEP
    if keys.get(p.B3G_LEFT_ARROW,0)&DOWN:  dsel[0]-=STEP
    if keys.get(p.B3G_UP_ARROW,0)&DOWN:    dsel[2]+=STEP
    if keys.get(p.B3G_DOWN_ARROW,0)&DOWN:  dsel[2]-=STEP
    if keys.get(ord('m'),0)&DOWN: dsel[1]+=STEP
    if keys.get(ord('n'),0)&DOWN: dsel[1]-=STEP
    if keys.get(ord('w'),0)&DOWN: dall[0]+=STEP
    if keys.get(ord('s'),0)&DOWN: dall[0]-=STEP
    if keys.get(ord('a'),0)&DOWN: dall[1]-=STEP      # [V2] Füße nach rechts = Körper nach links
    if keys.get(ord('d'),0)&DOWN: dall[1]+=STEP      # [V2] Körper nach rechts
    if keys.get(ord('r'),0)&DOWN: dall[2]-=STEP
    if keys.get(ord('f'),0)&DOWN: dall[2]+=STEP
    if keys.get(ord('t'),0)&DOWN: pitch -= APOS      # Nase HOCH (neg = nose high, Konvention)
    if keys.get(ord('g'),0)&DOWN: pitch += APOS      # Nase runter
    if keys.get(ord('z'),0)&DOWN: roll  -= APOS
    if keys.get(ord('h'),0)&DOWN: roll  += APOS
    robot._g_pitch_eff = pitch; robot._g_roll_eff = roll   # stur, nur bei Tastendruck geändert
    bsel=world_to_body_delta(tuple(dsel)); ball=world_to_body_delta(tuple(dall))
    for l in LEGS:
        d = ball if l.name!=NAMES[sel] else (bsel[0]+ball[0],bsel[1]+ball[1],bsel[2]+ball[2])
        f=foot[l.name]; f[0]+=d[0]; f[1]+=d[1]; f[2]+=d[2]
        set_leg(l, f)

    step_sim(); measure(); frame += 1
    if recording and frame % REC_EVERY == 0:
        rec_fh.write(json.dumps(sample(frame, pending_kf, sel, pitch, roll)) + "\n"); n_samples += 1
        pending_kf = False
    if frame % 8 == 0: update_gui(sel)
    if frame % 24 == 0: hud(sel, recording, n_samples)
    if a.frames and frame >= a.frames:
        if not ANSI:
            for ln in peak_report(): print("  " + ln)
        p.disconnect(); raise SystemExit
