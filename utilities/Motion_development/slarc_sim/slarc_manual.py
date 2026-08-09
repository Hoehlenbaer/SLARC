#!/usr/bin/env python3
"""
SLARC – MANUELLE Teleop + AUFNAHME/REPLAY
=========================================
Fuß-ZIELE fest im Körperframe (Servos halten stur), TASTEN bewegen in WELT-
Richtung. Rot/grüne Kugeln = Bodenkontakt. Aufnahme schreibt mit festem Takt
alles (alle Füße + Körperpose + Kontakt + aktuelle Beinselektion) in eine
JSONL-Datei; 'k' markiert Keyframes mittendrin. Replay fährt die Sequenz nach.

Aufnahme:  python3 slarc_manual.py --rise 0.17
Replay:    python3 slarc_manual.py --rise 0.17 --replay slarc_demo.jsonl

TASTEN (Fenster-Fokus nötig) – Bewegungsrichtung ist WELT:
  1..6        Bein wählen (FR,FL,MR,ML,RR,RL)
  Pfeile L/R  Fuß WELT-x    Pfeile U/D  Fuß WELT-z    n / m  Fuß WELT-y
  w / s       alle Füße WELT-x (Körper fore-aft)      r / f  Körper höher/tiefer
  t / g       Körper-PITCH (Nase hoch/runter)         z / h  Körper-ROLL
  SPACE Bein->Neutral   x Pose->Neutral
  j           AUFNAHME an/aus (schreibt slarc_demo.jsonl)
  k           Keyframe markieren (während der Aufnahme)
  p           Zustand drucken     ESC/q  Ende
  Kontakt: GRÜN = trägt, ROT = in der Luft
"""
import argparse, math, time, json
import pybullet as p
import slarc_sim_V10 as sim

ap = argparse.ArgumentParser()
ap.add_argument("--rise", type=float, default=0.17)
ap.add_argument("--run",  type=float, default=0.25)
ap.add_argument("--stair-x", type=float, default=0.60)
ap.add_argument("--no-stairs", action="store_true")
ap.add_argument("--replay", type=str, default=None, help="JSONL-Sequenz abspielen")
ap.add_argument("--out", type=str, default="slarc_demo.jsonl", help="Aufnahme-Datei")
a = ap.parse_args()

sim.STAIR_RISE = a.rise; sim.STAIR_RUN = a.run; sim.STAIR_X = a.stair_x
robot = sim.SlarcController()
robot.init_pybullet(gui=True, build_stairs=not a.no_stairs, spawn_can=False, terrain='stairs')
robot._g_pitch_eff = 0.0; robot._g_roll_eff = 0.0

LEGS = list(robot.legs); NAMES = [l.name for l in LEGS]
REC_EVERY = 8            # Aufnahme-/Replay-Takt: alle 8 Sim-Schritte ein Sample (~30 Hz)

def neutral(leg):
    nx, ny = robot._gait_neutral(leg, 0.5); return [nx, ny, robot.G_Z]
foot = {l.name: neutral(l) for l in LEGS}

def contact(leg):
    return len(p.getContactPoints(bodyA=robot.robot_id,
                                  linkIndexA=robot._foot_link_idx[leg.name])) > 0

# ─────────────────────────── REPLAY-MODUS ───────────────────────────
if a.replay:
    with open(a.replay) as fh:
        seq = [json.loads(ln) for ln in fh if ln.strip()]
    print("  Replay: %d Samples aus %s" % (len(seq), a.replay))
    for s in seq:
        for name, fx, fy, fz, *_ in s["feet"]:
            foot[name] = [fx, fy, fz]
        cpr = s.get("cpr", [0.0, 0.0])
        robot._g_pitch_eff = cpr[0]; robot._g_roll_eff = cpr[1]
        for _ in range(REC_EVERY):
            for l in LEGS:
                f = foot[l.name]; robot._set_leg(l, f[0], f[1], f[2])
            p.stepSimulation(); time.sleep(1.0/240.0)
    print("  Replay fertig."); 
    while True: p.stepSimulation(); time.sleep(1.0/240.0)

# ─────────────────────────── AUFNAHME/TELEOP ────────────────────────
sel = 0; STEP = 0.0015; APOS = 0.004; mark = {l.name: -1 for l in LEGS}
pitch = 0.0; roll = 0.0     # manueller Körper-Pitch/Roll (via _g_pitch_eff/_roll_eff, stur)
recording = False; rec_fh = None; pending_kf = False; n_samples = 0

def sample(frame, kf):
    bpos, born = p.getBasePositionAndOrientation(robot.robot_id)
    roll, pitch, yaw = p.getEulerFromQuaternion(born)
    feet = []
    for l in LEGS:
        fx, fy, fz = foot[l.name]
        wp = p.getLinkState(robot.robot_id, robot._foot_link_idx[l.name])[0]
        feet.append([l.name, round(fx,4), round(fy,4), round(fz,4),
                     round(wp[0],4), round(wp[1],4), round(wp[2],4), int(contact(l))])
    return {"f": frame, "sel": sel, "leg": NAMES[sel], "kf": kf,
            "cpr": [round(globals()['pitch'],4), round(globals()['roll'],4)],  # kommandiert
            "body": [round(bpos[0],4), round(bpos[1],4), round(bpos[2],4),
                     round(pitch,4), round(roll,4), round(yaw,4)],
            "feet": feet}

def world_to_body_delta(dw):
    if dw == (0.0, 0.0, 0.0): return (0.0, 0.0, 0.0)
    m = p.getMatrixFromQuaternion(p.getBasePositionAndOrientation(robot.robot_id)[1])
    return (m[0]*dw[0]+m[3]*dw[1]+m[6]*dw[2],
            m[1]*dw[0]+m[4]*dw[1]+m[7]*dw[2],
            m[2]*dw[0]+m[5]*dw[1]+m[8]*dw[2])

print(__doc__); print("  Ausgewählt: %s" % NAMES[sel])
DOWN = p.KEY_IS_DOWN; frame = 0
while True:
    keys = p.getKeyboardEvents()
    for k, st in keys.items():
        if not (st & p.KEY_WAS_TRIGGERED): continue
        if ord('1') <= k <= ord('6'):
            sel = k - ord('1'); print("  Ausgewählt: %s" % NAMES[sel])
        elif k == ord(' '): foot[NAMES[sel]] = neutral(LEGS[sel]); print("  %s->Neutral"%NAMES[sel])
        elif k == ord('x'):
            for l in LEGS: foot[l.name] = neutral(l)
            pitch = 0.0; roll = 0.0
            print("  Pose->Neutral")
        elif k == ord('j'):
            if not recording:
                rec_fh = open(a.out, "w"); recording = True; n_samples = 0
                print("  ● AUFNAHME an -> %s" % a.out)
            else:
                recording = False; rec_fh.close()
                print("  ■ AUFNAHME aus (%d Samples in %s)" % (n_samples, a.out))
        elif k == ord('k'):
            if recording: pending_kf = True; print("  ◆ Keyframe (Bein %s)" % NAMES[sel])
            else: print("  (k: nur während Aufnahme)")
        elif k == ord('p'):
            bpos = p.getBasePositionAndOrientation(robot.robot_id)[0]
            print("  Körper=(%.3f,%.3f,%.3f) | %s"%(bpos[0],bpos[1],bpos[2],
                  " ".join("%s:%s"%(l.name[:2],"G" if contact(l) else "r") for l in LEGS)))
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
        robot._set_leg(l, f[0], f[1], f[2])

    frame += 1
    if recording and frame % REC_EVERY == 0:
        rec_fh.write(json.dumps(sample(frame, pending_kf)) + "\n"); n_samples += 1
        pending_kf = False
    if frame % 4 == 0:
        for l in LEGS:
            wp = p.getLinkState(robot.robot_id, robot._foot_link_idx[l.name])[0]
            col = [0,1,0] if contact(l) else [1,0,0]
            mark[l.name] = p.addUserDebugText("●", [wp[0],wp[1],wp[2]+0.02],
                            textColorRGB=col, textSize=1.6, replaceItemUniqueId=mark[l.name])
    p.stepSimulation(); time.sleep(1.0/240.0)
