#!/usr/bin/env python3
"""
SLARC – MANUELLE Teleop + AUFNAHME/REPLAY   (slarc_manual V3, 07.11.2026)
=========================================================================
Zwei Modi:
  FUSS-Modus   Fuß-ZIELE fest im Körperframe (Servos halten stur), Tasten bewegen
               die Ziele in WELT-Richtung, die IK rechnet die Servowinkel.
  GELENK-Modus jeder Servo direkt (z. B. Zurückrollen aus der Rückenlage).
Aufnahme schreibt mit festem Takt alles (Fußziele, kommandierte Servowinkel,
Fußpositionen, Kontakt, Fußlast, Gelenkwinkel, Momente, Körperpose, Auswahl,
Modus, Tripod-Verlagerung) in eine JSONL-Datei; 'k' markiert Keyframes.
Replay fährt die kommandierten Servowinkel nach (V1/V2-Dateien: Fußziele).

V3: Tripod-Verlagerung (u/i/o), Gruppen-Auswahl (7/8/9/0/b), Gelenkmodus (e).
V2: CAD-URDF-Prüfung, Kontakt als Fußfarbe, Last-/Momenttabelle, a/d.

Aufnahme:  python3 slarc_manual.py --rise 0.17
Replay:    python3 slarc_manual.py --rise 0.17 --replay slarc_demo.jsonl

TASTEN (Fenster-Fokus nötig)
 Auswahl (beide Modi):
  1..6   ein Bein (FR,FL,MR,ML,RR,RL)
  7      Tripod A (FR, ML, RR)       8  Tripod B (FL, MR, RL)
  9      linke Seite (FL, ML, RL)    0  rechte Seite (FR, MR, RR)      b  alle
 FUSS-Modus (Richtung = WELT, gilt für alle ausgewählten Füße):
  Pfeile L/R  Fuß x    Pfeile U/D  Fuß z    n / m  Fuß y
  w / s  Körper vor/zurück   a / d  Körper links/rechts   r / f  Körper höher/tiefer
  t / g  Pitch (Nase hoch/runter)   z / h  Roll
  u      Gewicht auf Tripod A (FR, ML, RR werden länger -> FL, MR, RL heben ab)
  i      Gewicht auf Tripod B (FL, MR, RL werden länger -> FR, ML, RR heben ab)
  o      Verlagerung zurück auf 0 (läuft selbst)
 GELENK-Modus (gilt für alle ausgewählten Beine, ±1 je Seite gespiegelt):
  Pfeile L/R  Coxa zurück/vor    Pfeile U/D  Femur hoch/runter    n / m  Tibia ein/aus
 Beide:
  e      Gelenkmodus an/aus (zurück: Fußziele aus den Servowinkeln, Verlagerung 0)
  SPACE  Auswahl -> Neutral    x  alles -> Neutral (auch Pitch/Roll/Verlagerung)
  j      AUFNAHME an/aus       k  Keyframe     v  Spitzenwerte ausgeben/zurücksetzen
  p      Zustand ins Log       ESC/q  Ende

ANZEIGE
  Fußfarbe:  GRÜN = Mikroschalter gedrückt (Auflage von oben, entprellt wie HW)
             ORANGE = Berührung nur seitlich (z. B. Stufenkante), Schalter offen
             ROT = Luft
  Label am Fuß: Bein, höchstbelasteter Servo (C/F/T) und % vom Stall-Moment.
             Farbe nur nach Auslastung: grün < 50 %, gelb 50–80 %, rot >= 80 %.
  Terminal:  Tabelle aller 18 Servos (% Stall und Nm), Fußlast in N und % vom
             Gewicht, Kontakt, Gelenkgrenzen-Treffer (LIM). '>' = ausgewählt.
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
ap.add_argument("--tri-pair", type=float, default=0.030,
                help="Verlagerung voll: Vorder-/Hinterbein des tragenden Tripods länger um [m] (negativ = kürzer)")
ap.add_argument("--tri-mid", type=float, default=0.030,
                help="Verlagerung voll: Mittelbein des tragenden Tripods länger um [m]")
ap.add_argument("--no-hud", action="store_true", help="keine Terminal-Tabelle (nur Log-Zeilen)")
ap.add_argument("--no-gui", action="store_true", help="[Test] ohne Fenster")
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
if GUI:   # [V2] Startkamera nah am Roboter; Maus ändert sie wie gewohnt
    p.resetDebugVisualizerCamera(cameraDistance=1.1, cameraYaw=40, cameraPitch=-30,
                                 cameraTargetPosition=list(p.getBasePositionAndOrientation(robot.robot_id)[0]))

LEGS = list(robot.legs); NAMES = [l.name for l in LEGS]; LEG = {l.name: l for l in LEGS}
SHORT = {"front_right": "FR", "front_left": "FL", "mid_right": "MR",
         "mid_left": "ML", "rear_right": "RR", "rear_left": "RL"}
TYPES = ("coxa", "femur", "tibia")
REC_EVERY = 8            # Aufnahme-/Replay-Takt: alle 8 Sim-Schritte ein Sample (~30 Hz)
TAU_MAX = sim.SERVO_STALL_NM
WARN, CRIT = 0.50, 0.80
JIDX = {n: [robot.joint_map[f"{n}_{t}_joint"] for t in TYPES] for n in NAMES}
IK = robot.ik
QMIN = (IK.COXA_MIN, IK.FEMUR_MIN, IK.TIBIA_MIN); QMAX = (IK.COXA_MAX, IK.FEMUR_MAX, IK.TIBIA_MAX)

# [V3] Gruppen. Tripod A = FR, ML, RR; Tripod B = FL, MR, RL
TRI_A = ["front_right", "mid_left", "rear_right"]; TRI_B = ["front_left", "mid_right", "rear_left"]
GROUPS = {ord(str(i + 1)): (SHORT[n], [n]) for i, n in enumerate(NAMES)}
GROUPS.update({ord('7'): ("Tripod A", TRI_A), ord('8'): ("Tripod B", TRI_B),
               ord('9'): ("links", [n for n in NAMES if LEG[n].mount_y > 0]),
               ord('0'): ("rechts", [n for n in NAMES if LEG[n].mount_y < 0]),
               ord('b'): ("alle", list(NAMES))})
SIDE = {n: (1.0 if LEG[n].mount_y < 0 else -1.0) for n in NAMES}   # Coxa +: rechts vor, links zurück

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

# ─────────────────────── [V3] KINEMATIK (wie _set_leg, ohne StallGuard) ───────────────────────
def body_to_q(n, f):
    """Fußziel im Körperframe -> kommandierte Servowinkel (Pitch/Roll-Rotation wie _set_leg)."""
    l = LEG[n]; fx, fy, fz = f
    pe = robot._g_pitch_eff; re = robot._g_roll_eff
    cy = math.cos(pe); sy = math.sin(pe); cx = math.cos(re); sx = math.sin(re)
    rx = fx*cy + fz*sy; rz = -fx*sy + fz*cy
    ry = fy*cx - rz*sx; rz2 = fy*sx + rz*cx
    dx = rx - l.mount_x; dy = ry - l.mount_y
    lx = dx*math.cos(-l.mount_yaw) - dy*math.sin(-l.mount_yaw)
    ly = dx*math.sin(-l.mount_yaw) + dy*math.cos(-l.mount_yaw)
    h0 = sim.HexapodKinematics.lim_hits
    tc, tf, tt, _ = IK.solve(lx, ly, rz2)
    return [tc, tf, tt], sim.HexapodKinematics.lim_hits > h0

def q_to_body(n, q):
    """Umkehrung von body_to_q (FK + inverse Pitch/Roll-Rotation)."""
    l = LEG[n]
    lx, ly, z = IK.forward(*q)
    c, s = math.cos(l.mount_yaw), math.sin(l.mount_yaw)
    rx = l.mount_x + lx*c - ly*s; ry = l.mount_y + lx*s + ly*c
    pe = robot._g_pitch_eff; re = robot._g_roll_eff
    cy = math.cos(pe); sy = math.sin(pe); cx = math.cos(re); sx = math.sin(re)
    fy = ry*cx + z*sx; rz = -ry*sx + z*cx
    fx = rx*cy - rz*sy; fz = rx*sy + rz*cy
    return [fx, fy, fz]

def neutral(n):
    nx, ny = robot._gait_neutral(LEG[n], 0.5); return [nx, ny, robot.G_Z]

foot = {n: neutral(n) for n in NAMES}
qcmd = {n: body_to_q(n, foot[n])[0] for n in NAMES}
mode = "foot"
tri_s = 0.0; tri_auto0 = False          # +1 = Tripod A trägt voll, -1 = Tripod B
TRI_RATE = 1.0 / 180                    # 0 -> voll in 0,75 s

def tri_offset(n):
    """[V3] z-Versatz im Körperframe (- = Bein länger) für das tragende Tripod.
    Ein freier Fuß hebt um die Summe der Verlängerungen ab, gewichtet mit seinen baryzentrischen
    Koordinaten im Stützdreieck (Summe 1). Gleich lange Verlängerung -> alle freien Füße heben
    genau um diesen Betrag ab, unabhängig von der Geometrie (auch auf der Treppe).
    Nur Paar kürzer + Mittelbein länger (Rollen um die Paarlinie) drückt das freie Mittelbein der
    Paarseite auf den Boden: es liegt außerhalb des Dreiecks (gemessen: trägt weiter ~19 N)."""
    if tri_s > 0:
        carry = TRI_A; s = tri_s
    elif tri_s < 0:
        carry = TRI_B; s = -tri_s
    else:
        return 0.0
    if n not in carry: return 0.0
    return -(a.tri_mid if n.startswith("mid") else a.tri_pair) * s

def eff_target(n):
    f = foot[n]; return [f[0], f[1], f[2] + tri_offset(n)]

# ─────────────────────────── MESSUNG ───────────────────────────
tau_lp = {(n, t): 0.0 for n in NAMES for t in TYPES}   # gefilterte Momente [Nm]
force_lp = {n: 0.0 for n in NAMES}                      # gefilterte Fußlast [N]
peak = {}                                               # (n, t) -> Nm, seit 'v'
lim_cnt = {n: 0 for n in NAMES}                         # IK-Zielrücknahmen je Bein, seit 'v'
lim_now = {n: False for n in NAMES}

def contact_state(n):
    """2 = Schalter gedrückt (entprellt, Normale nach oben), 1 = nur seitlich, 0 = Luft."""
    l = LEG[n]
    if robot._foot_touch_down(l): return 2
    idx = robot._foot_link_idx[n]
    return 1 if any(c[3] == idx for c in robot._contact_cache) else 0

def measure():
    """Einmal je Frame: Kontakt-Cache/Latch, Momente und Fußlast (Tiefpass 0.2 wie V10)."""
    robot._refresh_contact_cache()
    for n in NAMES:
        for t, j in zip(TYPES, JIDX[n]):
            raw = abs(p.getJointState(robot.robot_id, j)[3])
            k = (n, t); tau_lp[k] += (raw - tau_lp[k]) * 0.2
            if tau_lp[k] > peak.get(k, 0.0): peak[k] = tau_lp[k]
        force_lp[n] += (robot._foot_force(LEG[n]) * NSUB - force_lp[n]) * 0.2

def command(n):
    """[V3] Fußmodus: Ziel -> IK -> qcmd. Gelenkmodus: qcmd direkt. Dann Servos."""
    if mode == "foot":
        qcmd[n], lim = body_to_q(n, eff_target(n))
        lim_now[n] = lim
        if lim: lim_cnt[n] += 1
    else:
        lim_now[n] = False
    for t, q in zip(TYPES, qcmd[n]):
        robot.set_servo(f"{n}_{t}_joint", q)

def leg_worst(n):
    t = max(TYPES, key=lambda t: tau_lp[(n, t)]); return t, tau_lp[(n, t)] / TAU_MAX

# ─────────────────────────── ANZEIGE ───────────────────────────
FOOT_COL = {2: [0.0, 0.85, 0.0, 1], 1: [1.0, 0.55, 0.0, 1], 0: [0.9, 0.0, 0.0, 1]}
foot_col = {}; label_id = {}

def sev_rgb(r):
    return [0.1, 0.9, 0.1] if r < WARN else [1.0, 0.8, 0.0] if r < CRIT else [1.0, 0.1, 0.1]

def update_gui(sel):
    if not GUI: return
    bp = p.getBasePositionAndOrientation(robot.robot_id)[0]
    for n in NAMES:
        cs = contact_state(n); idx = robot._foot_link_idx[n]
        if foot_col.get(n) != cs:
            p.changeVisualShape(robot.robot_id, idx, rgbaColor=FOOT_COL[cs]); foot_col[n] = cs
        t, r = leg_worst(n)
        txt = "%s%s %s%d%%%s" % (">" if n in sel else "", SHORT[n], t[0].upper(),
                                 round(r * 100), " LIM" if lim_now[n] else "")
        wp = p.getLinkState(robot.robot_id, idx)[0]
        dx, dy = wp[0] - bp[0], wp[1] - bp[1]; dn = math.hypot(dx, dy) or 1.0
        pos = [wp[0] + 0.08 * dx / dn, wp[1] + 0.08 * dy / dn, wp[2] + 0.10]   # außen über dem Fuß
        kw = dict(textColorRGB=sev_rgb(r), textSize=1.3)
        if n in label_id: kw["replaceItemUniqueId"] = label_id[n]
        label_id[n] = p.addUserDebugText(txt, pos, **kw)

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

def tri_text():
    if tri_s == 0: return "Verlagerung 0"
    return "Tripod %s trägt %d%%" % ("A" if tri_s > 0 else "B", round(abs(tri_s) * 100))

hud_n = 0
def hud(gname, sel, rec, n_samples):
    """Feste Tabelle im Terminal, überschreibt sich selbst (ANSI)."""
    global hud_n
    if not ANSI: return
    bpos, born = p.getBasePositionAndOrientation(robot.robot_id)
    rl, pt, _ = p.getEulerFromQuaternion(born)
    L = []
    L.append("SLARC manuell V3 | %s | Auswahl %s | %s | %s"
             % ("GELENK" if mode == "joint" else "FUSS", gname, tri_text(),
                ("AUFNAHME %d" % n_samples) if rec else "keine Aufnahme"))
    L.append("   Körper z %.3f m  Roll %+.1f°  Pitch %+.1f°" % (bpos[2], math.degrees(rl), math.degrees(pt)))
    L.append("   Bein Kontakt  Fußlast       Coxa          Femur         Tibia         Soll C/F/T")
    tot = 0.0
    for n in NAMES:
        cs = contact_state(n); f = force_lp[n]; tot += f
        cells = []
        for t in TYPES:
            r = tau_lp[(n, t)] / TAU_MAX
            cells.append(c_sev(r, "%3d%% %4.2fNm" % (round(r * 100), tau_lp[(n, t)])))
        qs = []
        for i, v in enumerate(qcmd[n]):
            s = "%+4.0f" % math.degrees(v)
            if v > QMAX[i] - math.radians(5) or v < QMIN[i] + math.radians(5): s = c_sev(1.0, s)
            qs.append(s)
        L.append(" %s %-3s %-7s %5.1fN %3d%%   %s  %s  %s   %s%s"
                 % (">" if n in sel else " ", SHORT[n], ("TRÄGT", "SEITE", "Luft")[2 - cs],
                    f, round(100 * f / WEIGHT), cells[0], cells[1], cells[2], "/".join(qs),
                    c_sev(1.0, "  LIM") if lim_now[n] else ""))
    L.append("   Summe Fußlast %.1f N = %d %% des Gewichts (%.1f N; Rest trägt Rumpf/Kante)"
             % (tot, round(100 * tot / WEIGHT), WEIGHT))
    L.append("   Log: " + (log_lines[-1] if log_lines else ""))
    for s in log_lines[-4:-1][::-1]: L.append("        " + s)
    while len(L) < 14: L.append("")
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
def sample(frame, kf, gname, sel, pitch_c, roll_c):
    bpos, born = p.getBasePositionAndOrientation(robot.robot_id)
    rl, pt, yw = p.getEulerFromQuaternion(born)
    feet = []
    for n in NAMES:
        fx, fy, fz = eff_target(n) if mode == "foot" else q_to_body(n, qcmd[n])
        wp = p.getLinkState(robot.robot_id, robot._foot_link_idx[n])[0]
        q = [p.getJointState(robot.robot_id, j)[0] for j in JIDX[n]]
        feet.append([n, round(fx,4), round(fy,4), round(fz,4),
                     round(wp[0],4), round(wp[1],4), round(wp[2],4),
                     int(contact_state(n) == 2),                      # 1 = Schalter gedrückt
                     round(force_lp[n], 2),                           # [V2] Fußlast N
                     [round(v, 4) for v in q],                         # [V2] Gelenkwinkel Ist rad
                     [round(tau_lp[(n, t)], 3) for t in TYPES],        # [V2] Momente Nm (Tiefpass)
                     int(lim_now[n]),                                  # [V2] IK-Grenze getroffen
                     [round(v, 5) for v in qcmd[n]]])                  # [V3] Servowinkel Soll rad
    return {"f": frame, "sel": sel, "grp": gname, "kf": kf, "mode": mode, "tri": round(tri_s, 3),
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
    mode = "joint"            # [V3] Servowinkel direkt; ältere Dateien: Fußziele -> IK
    frame = 0
    for s in seq:
        cpr = s.get("cpr", [0.0, 0.0])
        robot._g_pitch_eff = cpr[0]; robot._g_roll_eff = cpr[1]
        for e in s["feet"]:
            qcmd[e[0]] = e[12] if len(e) > 12 else body_to_q(e[0], [e[1], e[2], e[3]])[0]
        sel = s.get("sel", 0); sel = [NAMES[sel]] if isinstance(sel, int) else sel
        tri_s = s.get("tri", 0.0)
        for _ in range(REC_EVERY):
            for n in NAMES: command(n)
            step_sim(); measure(); frame += 1
            if frame % 8 == 0: update_gui(sel)
            if frame % 24 == 0: hud(s.get("grp", "-"), sel, False, 0)
        if s.get("kf"): msg("Keyframe bei Sample-Frame %d" % s["f"])
    msg("Replay fertig.")
    for ln in peak_report(): msg(ln) if not ANSI else print(ln)
    while GUI:
        step_sim(); measure()
    raise SystemExit

# ─────────────────────────── AUFNAHME/TELEOP ────────────────────────
gname, sel = GROUPS[ord('1')]
STEP = 0.0015; APOS = 0.004; QSTEP = math.radians(0.25)   # 0,25°/Frame = 60°/s
pitch = 0.0; roll = 0.0     # manueller Körper-Pitch/Roll (via _g_pitch_eff/_roll_eff, stur)
recording = False; rec_fh = None; pending_kf = False; n_samples = 0

def world_to_body_delta(dw):
    if dw == (0.0, 0.0, 0.0): return (0.0, 0.0, 0.0)
    m = p.getMatrixFromQuaternion(p.getBasePositionAndOrientation(robot.robot_id)[1])
    return (m[0]*dw[0]+m[3]*dw[1]+m[6]*dw[2],
            m[1]*dw[0]+m[4]*dw[1]+m[7]*dw[2],
            m[2]*dw[0]+m[5]*dw[1]+m[8]*dw[2])

def to_neutral(names):
    for n in names:
        foot[n] = neutral(n)
        if mode == "joint": qcmd[n] = body_to_q(n, foot[n])[0]

print(__doc__)
msg("Auswahl: %s | Fußmodus" % gname)
DOWN = p.KEY_IS_DOWN; frame = 0
while True:
    keys = p.getKeyboardEvents()
    for k, st in keys.items():
        if not (st & p.KEY_WAS_TRIGGERED): continue
        if k in GROUPS:
            gname, sel = GROUPS[k]; msg("Auswahl: %s" % gname)
        elif k == ord(' '): to_neutral(sel); msg("%s -> Neutral" % gname)
        elif k == ord('x'):
            pitch = 0.0; roll = 0.0; tri_s = 0.0; tri_auto0 = False
            robot._g_pitch_eff = 0.0; robot._g_roll_eff = 0.0
            to_neutral(NAMES); msg("Pose -> Neutral")
        elif k == ord('e'):
            if mode == "foot":
                mode = "joint"; msg("GELENK-Modus (Pfeile L/R Coxa, U/D Femur, n/m Tibia)")
            else:
                for n in NAMES: foot[n] = q_to_body(n, qcmd[n])
                tri_s = 0.0; tri_auto0 = False; mode = "foot"
                msg("FUSS-Modus (Fußziele aus Servowinkeln übernommen, Verlagerung 0)")
        elif k == ord('o'):
            tri_auto0 = True; msg("Verlagerung -> 0")
        elif k == ord('j'):
            if not recording:
                rec_fh = open(a.out, "w"); recording = True; n_samples = 0
                msg("AUFNAHME an -> %s" % a.out)
            else:
                recording = False; rec_fh.close()
                msg("AUFNAHME aus (%d Samples in %s)" % (n_samples, a.out))
        elif k == ord('k'):
            if recording: pending_kf = True; msg("Keyframe (%s)" % gname)
            else: msg("k: nur während der Aufnahme")
        elif k == ord('v'):
            for ln in peak_report(): msg(ln)
            peak.clear(); lim_cnt.update({n: 0 for n in NAMES})
            msg("Spitzen zurückgesetzt" + (" (im Log nur letzte Zeilen; vollständig mit --no-hud)" if ANSI else ""))
        elif k == ord('p'):
            bpos = p.getBasePositionAndOrientation(robot.robot_id)[0]
            msg("Körper=(%.3f,%.3f,%.3f) | %s" % (bpos[0], bpos[1], bpos[2],
                " ".join("%s:%s" % (SHORT[n], "GSL"[2 - contact_state(n)]) for n in NAMES)))
        elif k in (27, ord('q')):
            if rec_fh and not rec_fh.closed: rec_fh.close()
            p.disconnect(); raise SystemExit

    down = lambda c: keys.get(c, 0) & DOWN
    if mode == "joint":
        # [V3] Einzelgelenke: Coxa gespiegelt je Seite (→ = vor), Femur/Tibia gleiche Bedeutung
        dq = [0.0, 0.0, 0.0]
        if down(p.B3G_RIGHT_ARROW): dq[0] += QSTEP
        if down(p.B3G_LEFT_ARROW):  dq[0] -= QSTEP
        if down(p.B3G_UP_ARROW):    dq[1] -= QSTEP        # Femur + = runter
        if down(p.B3G_DOWN_ARROW):  dq[1] += QSTEP
        if down(ord('n')): dq[2] += QSTEP                 # Tibia einklappen
        if down(ord('m')): dq[2] -= QSTEP                 # Tibia strecken
        if dq != [0.0, 0.0, 0.0]:
            for n in sel:
                d = [dq[0] * SIDE[n], dq[1], dq[2]]
                qcmd[n] = [min(QMAX[i], max(QMIN[i], qcmd[n][i] + d[i])) for i in range(3)]
    else:
        dsel=[0.,0.,0.]; dall=[0.,0.,0.]
        if down(p.B3G_RIGHT_ARROW): dsel[0]+=STEP
        if down(p.B3G_LEFT_ARROW):  dsel[0]-=STEP
        if down(p.B3G_UP_ARROW):    dsel[2]+=STEP
        if down(p.B3G_DOWN_ARROW):  dsel[2]-=STEP
        if down(ord('m')): dsel[1]+=STEP
        if down(ord('n')): dsel[1]-=STEP
        if down(ord('w')): dall[0]+=STEP
        if down(ord('s')): dall[0]-=STEP
        if down(ord('a')): dall[1]-=STEP      # [V2] Füße nach rechts = Körper nach links
        if down(ord('d')): dall[1]+=STEP      # [V2] Körper nach rechts
        if down(ord('r')): dall[2]-=STEP
        if down(ord('f')): dall[2]+=STEP
        if down(ord('t')): pitch -= APOS      # Nase HOCH (neg = nose high, Konvention)
        if down(ord('g')): pitch += APOS      # Nase runter
        if down(ord('z')): roll  -= APOS
        if down(ord('h')): roll  += APOS
        if down(ord('u')): tri_s = min(1.0, tri_s + TRI_RATE); tri_auto0 = False   # [V3] A trägt
        if down(ord('i')): tri_s = max(-1.0, tri_s - TRI_RATE); tri_auto0 = False  # [V3] B trägt
        if tri_auto0:
            tri_s = 0.0 if abs(tri_s) <= TRI_RATE else tri_s - math.copysign(TRI_RATE, tri_s)
            if tri_s == 0.0: tri_auto0 = False
        robot._g_pitch_eff = pitch; robot._g_roll_eff = roll   # stur, nur bei Tastendruck geändert
        bsel=world_to_body_delta(tuple(dsel)); ball=world_to_body_delta(tuple(dall))
        for n in NAMES:
            d = (bsel[0]+ball[0], bsel[1]+ball[1], bsel[2]+ball[2]) if n in sel else ball
            f = foot[n]; f[0]+=d[0]; f[1]+=d[1]; f[2]+=d[2]
    for n in NAMES: command(n)

    step_sim(); measure(); frame += 1
    if recording and frame % REC_EVERY == 0:
        rec_fh.write(json.dumps(sample(frame, pending_kf, gname, sel, pitch, roll)) + "\n"); n_samples += 1
        pending_kf = False
    if frame % 8 == 0: update_gui(sel)
    if frame % 24 == 0: hud(gname, sel, recording, n_samples)
    if a.frames and frame >= a.frames:
        if not ANSI:
            for ln in peak_report(): print("  " + ln)
        p.disconnect(); raise SystemExit
