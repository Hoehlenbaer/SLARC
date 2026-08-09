#!/usr/bin/env python3
"""
SLARC Leg Tuner
===============
Manuelle Gelenk-Steuerung für IK-Positions-Kalibrierung.

Sliders steuern Coxa/Femur/Tibia des ausgewählten Beins.
SPACE   → aktuelle Pose loggen
L       → alle 6 Beine loggen
S       → Positionen in leg_positions.json speichern
R       → ausgewähltes Bein auf Default zurücksetzen
1–6     → Bein auswählen

Ausgabe: leg_positions.json
  {
    "front_right": {"angles_deg": [c, f, t],
                    "foot_world": [x, y, z],
                    "foot_body":  [x, y, z],   ← base_x/y/z Äquivalent
                    "base_z":     z},
    ...
  }
"""

import pybullet as p
import pybullet_data
import math, time, json, os
import numpy as np

# ── URDF (aus slarc_sim_V4 kopiert) ──────────────────────────────────
def generate_urdf(filename="slarc_tuner.urdf"):
    body_l=0.250; body_w=0.120; body_h=0.040
    coxa_l=0.060; femur_l=0.175; tibia_l=0.150; fr=0.015
    mid_y=0.040
    legs=[
        ("front_right", body_l/2,-body_w/2,-math.radians(30)),
        ("front_left",  body_l/2, body_w/2, math.radians(30)),
        ("mid_right",   0,       -(body_w/2+mid_y),-math.radians(90)),
        ("mid_left",    0,        (body_w/2+mid_y), math.radians(90)),
        ("rear_right", -body_l/2,-body_w/2,-math.radians(150)),
        ("rear_left",  -body_l/2, body_w/2, math.radians(150))
    ]
    u = f"""<?xml version="1.0"?><robot name="slarc">
<link name="base_link">
  <visual><geometry><box size="{body_l} {body_w} {body_h}"/></geometry>
  <material name="g"><color rgba="0.5 0.5 0.5 1"/></material></visual>
  <collision><geometry><box size="{body_l} {body_w} {body_h}"/></geometry></collision>
  <inertial><mass value="1.29"/><inertia ixx="0.015" ixy="0" ixz="0" iyy="0.015" iyz="0" izz="0.015"/></inertial>
</link>"""
    for nm,x,y,yaw in legs:
        u += f"""
<joint name="{nm}_coxa_joint" type="revolute">
  <parent link="base_link"/><child link="{nm}_coxa"/>
  <origin xyz="{x} {y} 0" rpy="0 0 {yaw}"/><axis xyz="0 0 1"/>
  <limit lower="-3.14" upper="3.14" effort="5" velocity="5"/>
</joint>
<link name="{nm}_coxa">
  <visual><origin xyz="{coxa_l/2} 0 0"/>
  <geometry><box size="{coxa_l} 0.02 0.02"/></geometry>
  <material name="r"><color rgba="0.8 0.2 0.2 1"/></material></visual>
  <inertial><mass value="0.08"/><inertia ixx="2e-4" ixy="0" ixz="0" iyy="2e-4" iyz="0" izz="2e-4"/></inertial>
</link>
<joint name="{nm}_femur_joint" type="revolute">
  <parent link="{nm}_coxa"/><child link="{nm}_femur"/>
  <origin xyz="{coxa_l} 0 0" rpy="0 0 0"/><axis xyz="0 1 0"/>
  <limit lower="-3.14" upper="3.14" effort="5" velocity="5"/>
</joint>
<link name="{nm}_femur">
  <visual><origin xyz="{femur_l/2} 0 0"/>
  <geometry><box size="{femur_l} 0.02 0.02"/></geometry>
  <material name="gg"><color rgba="0.2 0.8 0.2 1"/></material></visual>
  <inertial><mass value="0.095"/><inertia ixx="3e-4" ixy="0" ixz="0" iyy="3e-4" iyz="0" izz="3e-4"/></inertial>
</link>
<joint name="{nm}_tibia_joint" type="revolute">
  <parent link="{nm}_femur"/><child link="{nm}_tibia"/>
  <origin xyz="{femur_l} 0 0" rpy="0 0 0"/><axis xyz="0 1 0"/>
  <limit lower="-3.14" upper="3.14" effort="5" velocity="5"/>
</joint>
<link name="{nm}_tibia">
  <visual><origin xyz="{tibia_l/2} 0 0"/>
  <geometry><box size="{tibia_l} 0.015 0.015"/></geometry>
  <material name="b"><color rgba="0.2 0.2 0.8 1"/></material></visual>
  <inertial><mass value="0.025"/><inertia ixx="1e-4" ixy="0" ixz="0" iyy="1e-4" iyz="0" izz="1e-4"/></inertial>
</link>
<joint name="{nm}_foot_joint" type="fixed">
  <parent link="{nm}_tibia"/><child link="{nm}_foot"/>
  <origin xyz="{tibia_l} 0 0"/>
</joint>
<link name="{nm}_foot">
  <visual><geometry><sphere radius="{fr}"/></geometry>
  <material name="bk"><color rgba="0 0 0 1"/></material></visual>
  <inertial><mass value="0.015"/><inertia ixx="2e-5" ixy="0" ixz="0" iyy="2e-5" iyz="0" izz="2e-5"/></inertial>
</link>"""
    u += "</robot>"
    with open(filename,'w') as f: f.write(u)

# ── Konstanten ────────────────────────────────────────────────────────
LEG_NAMES  = ['front_right','front_left','mid_right',
              'mid_left','rear_right','rear_left']
LEG_KEYS   = [ord('1'),ord('2'),ord('3'),ord('4'),ord('5'),ord('6')]
BODY_H_NOM = 0.190   # Nominale Körperhöhe

# ── Hauptprogramm ──────────────────────────────────────────────────────
def main():
    generate_urdf()
    p.connect(p.GUI)
    p.setAdditionalSearchPath(pybullet_data.getDataPath())
    p.setGravity(0,0,-9.81)
    p.setPhysicsEngineParameter(fixedTimeStep=1/240.)

    p.loadURDF("plane.urdf")
    robot = p.loadURDF("slarc_tuner.urdf", [0,0,BODY_H_NOM])

    # Joint-Map
    jmap  = {}   # "front_right_coxa_joint" → idx
    fmap  = {}   # "front_right" → foot_link_idx
    for i in range(p.getNumJoints(robot)):
        info = p.getJointInfo(robot,i)
        nm   = info[1].decode()
        jmap[nm] = i
        if 'foot' in nm:
            leg = nm.replace('_foot_joint','')
            fmap[leg] = i

    # Standard-Winkel (Initialisierung)
    defaults = {}   # leg_name → [coxa, femur, tibia] in rad
    for leg in LEG_NAMES:
        defaults[leg] = [0.0, -0.3, 0.5]   # leicht gebeugte Startposition

    def set_leg(leg, c, f, t):
        p.setJointMotorControl2(robot, jmap[f'{leg}_coxa_joint'],
            p.POSITION_CONTROL, c, force=5, maxVelocity=5)
        p.setJointMotorControl2(robot, jmap[f'{leg}_femur_joint'],
            p.POSITION_CONTROL, f, force=5, maxVelocity=5)
        p.setJointMotorControl2(robot, jmap[f'{leg}_tibia_joint'],
            p.POSITION_CONTROL, t, force=5, maxVelocity=5)

    def get_angles(leg):
        c = p.getJointState(robot, jmap[f'{leg}_coxa_joint'])[0]
        f = p.getJointState(robot, jmap[f'{leg}_femur_joint'])[0]
        t = p.getJointState(robot, jmap[f'{leg}_tibia_joint'])[0]
        return c, f, t

    def get_foot_pos(leg):
        state = p.getLinkState(robot, fmap[leg])
        return state[0]   # world xyz

    def foot_body_frame(foot_world):
        """Fuß in Körper-Frame (relativ zu base_link Ursprung, Z=0 = body center)."""
        base_pos, base_orn = p.getBasePositionAndOrientation(robot)
        inv_pos, inv_orn   = p.invertTransform(base_pos, base_orn)
        local, _           = p.multiplyTransforms(inv_pos, inv_orn,
                                                   foot_world, [0,0,0,1])
        return local

    # Alle Beine auf Defaults setzen
    for _ in range(120):
        for leg in LEG_NAMES:
            c,f,t = defaults[leg]
            set_leg(leg, c, f, t)
        p.stepSimulation()

    # ── Sliders ────────────────────────────────────────────────────────
    sliders = {}
    sliders['coxa']  = p.addUserDebugParameter("Coxa  [°]", -150, 150, 0)
    sliders['femur'] = p.addUserDebugParameter("Femur [°]", -150, 150, -17)
    sliders['tibia'] = p.addUserDebugParameter("Tibia [°]", -150, 150,  29)
    slider_bh = p.addUserDebugParameter("Körperhöhe [mm]", 100, 400, 190)

    # Auswahl
    sel_idx = 0   # 0 = front_right
    logged  = {}  # geloggte Positionen
    dbg_ids = []  # Debug-Text IDs

    def update_dbg(sel_leg):
        for d in dbg_ids:
            try: p.removeUserDebugItem(d)
            except: pass
        dbg_ids.clear()

        foot_w = get_foot_pos(sel_leg)
        foot_b = foot_body_frame(foot_w)
        c,f,t  = get_angles(sel_leg)

        # Body-height
        bpos,_ = p.getBasePositionAndOrientation(robot)
        bh = bpos[2]

        text = (
            f"Ausgewählt: {sel_leg}\n"
            f"Coxa:  {math.degrees(c):+7.1f}°\n"
            f"Femur: {math.degrees(f):+7.1f}°\n"
            f"Tibia: {math.degrees(t):+7.1f}°\n"
            f"─────────────────\n"
            f"Fuß Welt:  x={foot_w[0]:+.3f} y={foot_w[1]:+.3f} z={foot_w[2]:+.3f}\n"
            f"Fuß Körper: x={foot_b[0]:+.3f} y={foot_b[1]:+.3f} z={foot_b[2]:+.3f}\n"
            f"base_z = {foot_b[2]:.4f}  (für Gait-Loop)\n"
            f"Körperhöhe: {bh*1000:.0f}mm\n"
            f"─────────────────\n"
            f"Geloggt: {list(logged.keys())}"
        )

        lines = text.split('\n')
        y0 = 0.55
        for i, line in enumerate(lines):
            color = [1.0,0.85,0.0] if i==0 else \
                    [0.6,1.0,0.6]  if 'base_z' in line else \
                    [0.9,0.9,0.9]
            did = p.addUserDebugText(
                line,
                [bpos[0]-0.6, bpos[1]-0.1, bpos[2]+y0-i*0.060],
                textColorRGB=color, textSize=1.1, lifeTime=0.15)
            dbg_ids.append(did)

        # Fußpunkt hervorheben
        did = p.addUserDebugText("●",
            list(foot_w), textColorRGB=[1,0.3,0.3],
            textSize=2.0, lifeTime=0.15)
        dbg_ids.append(did)

    def log_leg(leg):
        foot_w = get_foot_pos(leg)
        foot_b = foot_body_frame(foot_w)
        c, f, t= get_angles(leg)
        entry = {
            "angles_deg": [round(math.degrees(c),1),
                           round(math.degrees(f),1),
                           round(math.degrees(t),1)],
            "foot_world": [round(v,4) for v in foot_w],
            "foot_body":  [round(v,4) for v in foot_b],
            "base_z":     round(foot_b[2], 4),
        }
        logged[leg] = entry
        print(f"📍 {leg}: angles={entry['angles_deg']}°  "
              f"foot_body=({entry['foot_body'][0]:.3f}, "
              f"{entry['foot_body'][1]:.3f}, {entry['foot_body'][2]:.3f})  "
              f"base_z={entry['base_z']:.4f}")
        return entry

    def save_positions():
        fname = "leg_positions.json"
        with open(fname,'w') as fh:
            json.dump(logged, fh, indent=2)
        print(f"💾 Gespeichert: {fname}  ({len(logged)} Beine)")

    print("\n=== SLARC Leg Tuner ===")
    print("  1–6    : Bein auswählen")
    print("  SPACE  : aktuelles Bein loggen")
    print("  L      : alle 6 Beine loggen")
    print("  S      : in leg_positions.json speichern")
    print("  R      : ausgewähltes Bein zurücksetzen")
    print("  ESC    : beenden")
    print(f"\n  Aktuell: {LEG_NAMES[sel_idx]}\n")

    frame = 0
    while True:
        frame += 1
        sel_leg = LEG_NAMES[sel_idx]

        # Slider-Werte lesen
        coxa_deg  = p.readUserDebugParameter(sliders['coxa'])
        femur_deg = p.readUserDebugParameter(sliders['femur'])
        tibia_deg = p.readUserDebugParameter(sliders['tibia'])
        bh_mm     = p.readUserDebugParameter(slider_bh)

        # Körperhöhe anpassen (Basis fixiert, nur visuelle Höhe)
        pos, orn = p.getBasePositionAndOrientation(robot)
        p.resetBasePositionAndOrientation(
            robot, [pos[0], pos[1], bh_mm/1000.0], orn)

        # Ausgewähltes Bein mit Slider-Werten steuern
        set_leg(sel_leg,
                math.radians(coxa_deg),
                math.radians(femur_deg),
                math.radians(tibia_deg))

        # Andere Beine auf Default halten
        for leg in LEG_NAMES:
            if leg != sel_leg:
                if leg in logged:
                    # Geloggte Position halten
                    entry = logged[leg]
                    c,f,t = [math.radians(a) for a in entry['angles_deg']]
                    set_leg(leg, c, f, t)
                else:
                    c,f,t = defaults[leg]
                    set_leg(leg, c, f, t)

        # Debug-Anzeige alle 5 Frames
        if frame % 5 == 0:
            update_dbg(sel_leg)

        # Tastatur
        keys = p.getKeyboardEvents()
        for key, state in keys.items():
            if state & p.KEY_WAS_TRIGGERED:
                # Bein-Auswahl
                if key in LEG_KEYS:
                    sel_idx = LEG_KEYS.index(key)
                    sel_leg = LEG_NAMES[sel_idx]
                    # Slider auf aktuelle Winkel setzen (readback)
                    c,f,t = get_angles(sel_leg)
                    print(f"\n  → {sel_leg}  "
                          f"(C={math.degrees(c):.1f}° "
                          f"F={math.degrees(f):.1f}° "
                          f"T={math.degrees(t):.1f}°)")

                elif key == ord(' '):
                    log_leg(sel_leg)

                elif key == ord('l') or key == ord('L'):
                    print("\n📍 Logge alle 6 Beine:")
                    for leg in LEG_NAMES:
                        log_leg(leg)

                elif key == ord('s') or key == ord('S'):
                    save_positions()

                elif key == ord('r') or key == ord('R'):
                    c,f,t = defaults[sel_leg]
                    set_leg(sel_leg, c, f, t)
                    if sel_leg in logged:
                        del logged[sel_leg]
                    print(f"  ↺ {sel_leg} zurückgesetzt")

                elif key == 27:  # ESC
                    if logged:
                        save_positions()
                    p.disconnect()
                    return

        p.stepSimulation()
        time.sleep(1/240.)


if __name__ == '__main__':
    main()
