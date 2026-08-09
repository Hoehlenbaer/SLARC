#!/usr/bin/env python3
"""
SLARC Simulation V8 - Unified omnidirektionaler Gait-Kern
=========================================================
Radikaler Neuaufbau auf einem EINZIGEN Motion-Kern (statt Mode 1..8 + _fh/_m7/_v2/_ug).

Architektur & HW-Grenze (für späteren Port gekennzeichnet)
---------------------------------------------------------
  [PI]    deliberativ, ~15 Hz : Perception -> Gait-Wahl, cmd_vel(vx,vy,omega),
                                Körperhöhe/Pose-Sollwerte, Pitch-Sollwert aus
                                Fußebene (FK über 6 Present-Positions), Mission.
  [ESP32] reaktiv, 100-240 Hz : der Motion-Kern - Phase, Schwung-Trajektorie aus
                                cmd_vel, Workspace-Clamp, IK, Kontakt stoppt Fuß,
                                Coxa-Block -> höher tasten, Balancer.
  [SIM]   nur PC              : PyBullet-Welt, Kamera, Logger, Tastatur.

Ein Gait = Konfiguration (GAITS): Schwinggruppen, Vortriebsmodus, Splay.
Bewegung ist omnidirektional: cmd_vel = (vx, vy, omega) deckt vorwärts/rückwärts/
seitwärts/Rotation in EINEM Modell ab (kein Sonderfall je Richtung).

Übernommene, getestete Infrastruktur aus V7 (1:1): URDF, Welt/Treppe, Stereo,
HexapodKinematics, BalanceController, StallGuard, StairModel, HexapodLeg, Logger.
"""

import pybullet as p          # SIM ONLY (PC)
import pybullet_data          # SIM ONLY (PC)
import time                   # SIM ONLY (PC)
import math                   # PORTABLE (ESP32 hat math)
import numpy as np            # SIM ONLY (PC) - nur Stereo/Perzeption
from enum import IntEnum      # SIM ONLY (PC) - StairClimber-Skript


# ==========================================
# 0. URDF GENERATOR
# ==========================================
# Gemeinsame Körper-Geometrie: hier ÄNDERN, dann passen URDF UND Controller.
# Länge auf 200mm verkürzt (war 250): Hinterbein-Coxa/Femur saßen sonst auf
# der 17cm-Stufenkante auf. Elektronik passt (LiPo ZEEE 9000mAh = 166mm).
# Breiter (150mm statt 120) -> seitlich stabiler.
BODY_L = 0.400; BODY_W = 0.150; BODY_H = 0.040
MID_Y_OFFSET = 0.040

def generate_hexapod_urdf(filename="slarc_primitives.urdf"):
    body_l = BODY_L; body_w = BODY_W; body_h = BODY_H
    coxa_l = 0.060; femur_l = 0.175; tibia_l = 0.150
    foot_radius = 0.015
    mid_y_offset = MID_Y_OFFSET

    legs = [
        ("front_right",  body_l/2, -body_w/2, -math.radians(30)),
        ("front_left",   body_l/2,  body_w/2,  math.radians(30)),
        ("mid_right",    0,        -(body_w/2 + mid_y_offset), -math.radians(90)),
        ("mid_left",     0,         (body_w/2 + mid_y_offset),  math.radians(90)),
        ("rear_right",  -body_l/2, -body_w/2, -math.radians(150)),
        ("rear_left",   -body_l/2,  body_w/2,  math.radians(150))
    ]

    # Massenverteilung (realistisch, Gesamt 2.58 kg):
    # base_link  = Chassis(0.40)+Elektronik(0.30)+Akku(0.20)+6×Hüftservo(0.39) = 1.29 kg
    # coxa link  = Coxasegment(0.015)+Femurservo(0.065) = 0.080 kg
    # femur link = Femursegment(0.030)+Tibiaservo(0.065) = 0.095 kg
    # tibia link = Tibiasegment(0.025) = 0.025 kg
    # foot link  = TPU-Fuß = 0.015 kg
    urdf = f"""<?xml version="1.0"?>
<robot name="slarc">
    <link name="base_link">
        <visual><geometry><box size="{body_l} {body_w} {body_h}"/></geometry><material name="grey"><color rgba="0.5 0.5 0.5 1"/></material></visual>
        <collision><geometry><box size="{body_l} {body_w} {body_h}"/></geometry></collision>
        <inertial><mass value="1.29"/><inertia ixx="0.015" ixy="0" ixz="0" iyy="0.015" iyz="0" izz="0.015"/></inertial>
    </link>"""
    for name, x, y, yaw in legs:
        urdf += f"""
    <joint name="{name}_coxa_joint" type="revolute">
        <parent link="base_link"/><child link="{name}_coxa"/>
        <origin xyz="{x} {y} 0" rpy="0 0 {yaw}"/><axis xyz="0 0 1"/>
        <limit lower="-3.14" upper="3.14" effort="3.0" velocity="3.14"/>
    </joint>
    <link name="{name}_coxa">
        <visual><origin xyz="{coxa_l/2} 0 0"/><geometry><box size="{coxa_l} 0.02 0.02"/></geometry><material name="red"><color rgba="0.8 0.2 0.2 1"/></material></visual>
        <collision><origin xyz="{coxa_l/2} 0 0"/><geometry><box size="{coxa_l} 0.02 0.02"/></geometry></collision>
        <inertial><mass value="0.080"/><inertia ixx="0.0002" ixy="0" ixz="0" iyy="0.0002" iyz="0" izz="0.0002"/></inertial>
    </link>
    <joint name="{name}_femur_joint" type="revolute">
        <parent link="{name}_coxa"/><child link="{name}_femur"/>
        <origin xyz="{coxa_l} 0 0" rpy="0 0 0"/><axis xyz="0 1 0"/>
        <limit lower="-3.14" upper="3.14" effort="3.0" velocity="3.14"/>
    </joint>
    <link name="{name}_femur">
        <visual><origin xyz="{femur_l/2} 0 0"/><geometry><box size="{femur_l} 0.02 0.02"/></geometry><material name="green"><color rgba="0.2 0.8 0.2 1"/></material></visual>
        <collision><origin xyz="{femur_l/2} 0 0"/><geometry><box size="{femur_l} 0.02 0.02"/></geometry></collision>
        <inertial><mass value="0.095"/><inertia ixx="0.0003" ixy="0" ixz="0" iyy="0.0003" iyz="0" izz="0.0003"/></inertial>
    </link>
    <joint name="{name}_tibia_joint" type="revolute">
        <parent link="{name}_femur"/><child link="{name}_tibia"/>
        <origin xyz="{femur_l} 0 0" rpy="0 0 0"/><axis xyz="0 1 0"/>
        <limit lower="-3.14" upper="3.14" effort="3.0" velocity="3.14"/>
    </joint>
    <link name="{name}_tibia">
        <visual><origin xyz="{tibia_l/2} 0 0"/><geometry><box size="{tibia_l} 0.015 0.015"/></geometry><material name="blue"><color rgba="0.2 0.2 0.8 1"/></material></visual>
        <collision><origin xyz="{tibia_l/2} 0 0"/><geometry><box size="{tibia_l} 0.015 0.015"/></geometry></collision>
        <inertial><mass value="0.025"/><inertia ixx="0.0001" ixy="0" ixz="0" iyy="0.0001" iyz="0" izz="0.0001"/></inertial>
    </link>
    <joint name="{name}_foot_joint" type="fixed">
        <parent link="{name}_tibia"/><child link="{name}_foot"/>
        <origin xyz="{tibia_l} 0 0" rpy="0 0 0"/>
    </joint>
    <link name="{name}_foot">
        <visual><geometry><sphere radius="{foot_radius}"/></geometry><material name="black"><color rgba="0 0 0 1"/></material></visual>
        <collision><geometry><sphere radius="{foot_radius}"/></geometry></collision>
        <inertial><mass value="0.015"/><inertia ixx="0.00002" ixy="0" ixz="0" iyy="0.00002" iyz="0" izz="0.00002"/></inertial>
    </link>"""
    urdf += "</robot>"
    with open(filename, "w") as f: f.write(urdf)


# ==========================================
# TREPPE
# ==========================================
# Gemeinsame Treppen-Geometrie: hier ÄNDERN, dann passen Sim-Treppe UND der
# FIXED-Anstellwinkel automatisch zusammen. (Für 100-mm-Test: STAIR_RISE=0.10)
SLARC_VERSION = "V10.16-rear-fwd"   # V10.16: Hinterbein-Ziel beim Klettern nach VORN (statt G_REAR_REACH
                                    # zurück) -> Coxa schwenkt vor auf die Stufe; CoM-Wippe trägt die Stabilität.
STAIR_RISE = 0.05      # Stufenhöhe [m] (5-cm-Einstiegstest; 10-cm später: 0.10)
STAIR_RUN  = 0.250     # Stufentiefe [m]
STAIR_X    = 0.60      # x-Start der Treppe [m] (näher an Slarc = kürzere Anlaufzeit)

# ST3215 Stall-Drehmoment ~30 kg·cm ≈ 2.94 Nm. Dient als realer Motor-force
# (Sättigung) UND als 100%-Bezug der Drehmomentanzeige - eine Quelle, konsistent.
SERVO_STALL_NM = 2.94

# Positions-Regelsteifigkeit des Servos (PyBullet Kp). 0.05 war für ein
# realistisch "weiches" Bein gedacht, ist aber so nachgiebig, dass der Servo
# (a) den Fuß kaum zügig auf Coxa-Höhe hebt und (b) den Stand-Sweep nicht in
# Körpervortrieb überträgt -> Rutschen + Kriechtempo. Der echte ST3215 ist
# deutlich steifer; das Stall-Drehmoment (force) bleibt die Sättigungsgrenze,
# die Drehmomentanzeige also weiter ≤100%. Bei Oszillation Wert senken.
SERVO_POS_GAIN = 0.030    # weich, hardware-nah (ST3215-Getriebeelastizität + Spiel + TPU-Fuß
                          # federn Aufsetz-Impulse ab). Vorher 0.30 = zu steif -> Rückstoß/Hüpfen.

def create_staircase():
    step_ids = []
    step_h = STAIR_RISE; step_d = STAIR_RUN; step_w = 1.200
    x_start = STAIR_X; n_up = 5

    for i in range(n_up):
        h_total = step_h * (i + 1)
        cx = x_start + i * step_d + step_d / 2
        col = p.createCollisionShape(p.GEOM_BOX,
                halfExtents=[step_d/2, step_w/2, h_total/2])
        vis = p.createVisualShape(p.GEOM_BOX,
                halfExtents=[step_d/2, step_w/2, h_total/2],
                rgbaColor=[0.75, 0.75, 0.70, 1])
        sid = p.createMultiBody(0, col, vis,
                                basePosition=[cx, 0, h_total/2])
        _set_contact(sid)
        step_ids.append(sid)

    top_h = step_h * n_up
    x_top = x_start + n_up * step_d

    # Plateau
    plateau_len = 1.00
    col_pl = p.createCollisionShape(p.GEOM_BOX,
                halfExtents=[plateau_len/2, step_w/2, top_h/2])
    vis_pl = p.createVisualShape(p.GEOM_BOX,
                halfExtents=[plateau_len/2, step_w/2, top_h/2],
                rgbaColor=[0.60, 0.80, 0.60, 1])
    pl_id = p.createMultiBody(0, col_pl, vis_pl,
                               basePosition=[x_top + plateau_len/2, 0, top_h/2])
    _set_contact(pl_id)
    step_ids.append(pl_id)

    # 5 Stufen abwärts
    small_h = 0.170; small_d = 0.250
    x_down = x_top + plateau_len; n_down = 5

    for i in range(n_down):
        h_total = top_h - small_h * (i + 1)
        if h_total <= 0: h_total = 0.005
        cx = x_down + i * small_d + small_d / 2
        col = p.createCollisionShape(p.GEOM_BOX,
                halfExtents=[small_d/2, step_w/2, h_total/2])
        vis = p.createVisualShape(p.GEOM_BOX,
                halfExtents=[small_d/2, step_w/2, h_total/2],
                rgbaColor=[0.70, 0.70, 0.80, 1])
        sid = p.createMultiBody(0, col, vis, basePosition=[cx, 0, h_total/2])
        _set_contact(sid)
        step_ids.append(sid)

    print(f"  Treppenkomplex: {len(step_ids)} Objekte")
    print(f"  5 Stufen aufwärts  (x=1.0-2.25m, +{top_h*100:.0f}cm)")
    print(f"  Plateau            (x=2.25-3.25m)")
    print(f"  5 Stufen abwärts   (x=3.25-4.5m)")
    return step_ids


def create_hills(x_start=1.0, n=6, width=1.20, seed=0, style='scatter', length=2.5):
    """[V9] Hügelstrecke, zwei Stile:
      style='ridges'  : Querzylinder über die volle Breite -> lateral UNIFORM, nur Pitch-Störung.
      style='scatter' : Feld halb vergrabener KUGELKAPPEN an zufälligen (x,y), breit+flach ->
                        jedes Bein trifft eine andere Höhe -> Roll + Pitch + Per-Bein-Störung,
                        näher am echten Trail. Testet R2-Roll und FK-Median-R3 richtig.
    Reproduzierbar via seed. Kappe der Höhe h ragt aus vergrabener Kugel/Zylinder (Mittelpunkt z=h-r)."""
    import random as _rnd
    rng = _rnd.Random(seed)
    ids = []
    if style == 'ridges':
        x = x_start
        for i in range(n):
            r = rng.uniform(0.15, 0.30); h = min(rng.uniform(0.03, 0.08), 0.5*r); cx = x + r
            orn = p.getQuaternionFromEuler([math.pi/2, 0, 0])
            col = p.createCollisionShape(p.GEOM_CYLINDER, radius=r, height=width)
            vis = p.createVisualShape(p.GEOM_CYLINDER, radius=r, length=width, rgbaColor=[0.55,0.62,0.45,1])
            sid = p.createMultiBody(0, col, vis, basePosition=[cx, 0, h-r], baseOrientation=orn)
            _set_contact(sid); ids.append(sid)
            hs = math.sqrt(max(1e-4, 2*r*h - h*h)); x = cx + hs + rng.uniform(0.03, 0.12)
        print("  Hügelstrecke [ridges]: %d Kuppen (x=%.2f..%.2f m, seed=%d)" % (len(ids), x_start, x, seed))
        return ids
    # scatter: Kugelkappen-Feld
    x_end = x_start + length
    n_dome = n if n >= 20 else 40                # dichtes Feld -> quasi-kontinuierlicher Lump-Boden
    for _ in range(n_dome):
        r = rng.uniform(0.12, 0.26)             # groß -> breite, flache (begehbare) Kappe
        h = min(rng.uniform(0.02, 0.08), 0.6*r)
        px = rng.uniform(x_start, x_end)
        py = rng.uniform(-width/2, width/2)
        col = p.createCollisionShape(p.GEOM_SPHERE, radius=r)
        vis = p.createVisualShape(p.GEOM_SPHERE, radius=r, rgbaColor=[0.55, 0.62, 0.45, 1])
        sid = p.createMultiBody(0, col, vis, basePosition=[px, py, h-r])   # Kappe ragt h heraus
        _set_contact(sid); ids.append(sid)
    print("  Hügelstrecke [scatter]: %d Kuppeln (x=%.2f..%.2f m, b=±%.2f, seed=%d)"
          % (len(ids), x_start, x_end, width/2, seed))
    return ids


def create_single_step(x_at=0.8, height=0.06, run=1.5, width=1.2):
    """[V9.4] Eine EINZELNE Stufe (scharfe Kante) zum Isolieren von Klettern + Freeze bei
    placemove. Box mit Oberkante bei z=height, beginnt bei x_at. Hier SOLL der Freeze feuern
    (ein Stützbein erreicht die höhere Fläche nicht) - anders als auf flach, wo er spurios war.
    Sauberer Diagnose-Fall, ein Ereignis statt eines ganzen Treppenkomplexes."""
    h2 = height/2.0; cx = x_at + run/2.0
    col = p.createCollisionShape(p.GEOM_BOX, halfExtents=[run/2.0, width/2.0, h2])
    vis = p.createVisualShape(p.GEOM_BOX, halfExtents=[run/2.0, width/2.0, h2], rgbaColor=[0.60, 0.55, 0.50, 1])
    sid = p.createMultiBody(0, col, vis, basePosition=[cx, 0, h2])   # Unterkante 0, Oberkante height
    _set_contact(sid)
    print("  Einzelstufe: h=%.0fmm ab x=%.2f m (Lauffläche %.1f m)" % (height*1000, x_at, run))
    return [sid]


# ==========================================
# STEREO-KAMERAS
# ==========================================
class StereoCameras:
    """
    IMX296: 1456×1088px, 3.45µm Pixelpitch, f=2.8mm
    Scaling auf 640×480 - FOV bleibt identisch (83.8°H × 67.7°V)
    fx = 811.6 × (640/1456) = 357 px
    fy = 811.6 × (480/1088) = 358 px
    """
    IMG_W = 640; IMG_H = 480
    NEAR  = 0.01; FAR   = 10.0
    FX = 357.0; FY = 358.0
    BASELINE = 0.050
    FOV_V = math.degrees(2 * math.atan(IMG_H / 2 / FY))  # 67.7°

    def __init__(self):
        self._proj = p.computeProjectionMatrixFOV(
            fov=self.FOV_V, aspect=self.IMG_W / self.IMG_H,
            nearVal=self.NEAR, farVal=self.FAR)
        print(f"  Stereo-Kameras: Baseline={self.BASELINE*1000:.0f}mm  "
              f"f=2.8mm  fx={self.FX:.0f}px  FOV={self.FOV_V:.1f}°V")

    def get_images(self, robot_id):
        pos, orn = p.getBasePositionAndOrientation(robot_id)
        rot = p.getMatrixFromQuaternion(orn)
        fwd = [rot[0], rot[3], rot[6]]
        up  = [rot[2], rot[5], rot[8]]
        rgt = [-rot[1], -rot[4], -rot[7]]
        cam_base = [pos[0]+fwd[0]*0.10+up[0]*0.05,
                    pos[1]+fwd[1]*0.10+up[1]*0.05,
                    pos[2]+fwd[2]*0.10+up[2]*0.05]
        target = [cam_base[0]+fwd[0], cam_base[1]+fwd[1], cam_base[2]+fwd[2]]

        def render(sign):
            eye = [cam_base[0]+rgt[0]*self.BASELINE*sign,
                   cam_base[1]+rgt[1]*self.BASELINE*sign,
                   cam_base[2]+rgt[2]*self.BASELINE*sign]
            view = p.computeViewMatrix(eye, target, up)
            _, _, rgb, depth_buf, _ = p.getCameraImage(
                self.IMG_W, self.IMG_H, view, self._proj,
                renderer=p.ER_TINY_RENDERER)
            depth = self.FAR * self.NEAR / (
                self.FAR - (self.FAR - self.NEAR) * np.array(depth_buf))
            return np.array(rgb, dtype=np.uint8).reshape(
                self.IMG_H, self.IMG_W, 4), depth.astype(np.float32)

        rgb_l, depth_l = render(-0.5)
        rgb_r, _       = render( 0.5)
        return rgb_l, rgb_r, depth_l

    def depth_to_disparity(self, depth_m):
        disp = np.zeros_like(depth_m)
        valid = depth_m > self.NEAR
        disp[valid] = self.FX * self.BASELINE / depth_m[valid]
        return disp


# ==========================================
# 1. IK + LEG
# ==========================================
# >>> PORTABLE CORE (ESP32) >>>
# Ab hier bis zum nächsten Marker: NUR `math`. Keine numpy/pybullet/enum.
# Direkt nach MicroPython/C++ übertragbar.

def _clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


# ── Best-Practice-Kontaktparameter für einen ~3-kg-Hexapod in PyBullet ──
# Begründung (Maschinenbau-Sicht):
#  • frictionAnchor=1: verankert den Kontaktpunkt -> belastete Füße KRIECHEN nicht
#    mehr unter Tangentiallast (behebt das Rückwärtsrutschen). Ohne Anchor löst
#    PyBullets Solver den Reibkegel iterativ und lässt Rest-Schlupf zu.
#  • restitution=0: kein Rückprall (ein 3-kg-Roboter mit Gummifüßen prallt nicht).
#  • contactStiffness/Damping: weiche, GEDÄMPFTE Kontaktfeder statt der steifen
#    Default-ERP-Feder -> der Fuß federt nicht (kein Hüpfen). k=15000 N/m: statische
#    Fußlast ~5 N -> Eindrücken 0.3 mm (realistisch fest). Dämpfung c=1500 ist ggü.
#    dem kritischen c=2·√(k·m)≈420 (m≈3 kg) leicht überdämpft -> kein Nachschwingen,
#    aber WEICH genug, dass ein aufsetzender Fuß nicht abprallt (Aufprall ~ c·v).
#  • spinning/rollingFriction klein: etwas Dreh-/Rollwiderstand gegen Zappeln.
FOOT_FRICTION   = 0.9      # TPU-Fuß: realer Trocken-COF von TPU ~0.4-0.7 (Lit.), Gummi/Beton
GROUND_FRICTION = 0.7      # 0.7-0.9. FOOT*GROUND=0.63 -> hardware-nah statt vorher 1.6*1.6=2.56
CONTACT_K       = 30000.0  # angepasst an weiche Servo-Nachgiebigkeit (Marco-Test)
CONTACT_C       = 800.0

def _set_contact(body_id, link=-1, friction=GROUND_FRICTION):
    p.changeDynamics(body_id, link,
                     lateralFriction=friction,
                     spinningFriction=0.01, rollingFriction=0.01,
                     restitution=0.0, frictionAnchor=1,
                     contactStiffness=CONTACT_K, contactDamping=CONTACT_C)


class HexapodKinematics:
    """
    3-DOF-Beinkinematik (Coxa/Femur/Tibia) mit:
      - kinematisch hergeleiteten Betriebsgrenzen (Schritthöhe, Körperhöhe),
      - Reichweiten-Clamping (Workspace),
      - Gelenklimits (Servo- + Selbstkollisions-Schutz),
      - Coxa-Stetigkeit (kein 360°-Umklappen).

    Konvention:
      Coxa-Achse +z (Yaw), Femur/Tibia-Achse +y. Positiver Femurwinkel
      senkt die Beinspitze (down-positiv) -> negativer Femurwinkel = aufwärts.
    """
    # Segmentlängen [m]
    L_C = 0.060
    L_F = 0.175
    L_T = 0.150

    # --- Req 1: maximale Schritthöhe ----------------------------------
    # Extrempose: Femur 90° aufwärts, Knie-Innenwinkel ~160°.
    # Die Tibia weicht um (180°-160°)=20° von der Femur-Verlängerung ab,
    # zeigt also unter 90°-20° = 70° Elevation. Fußhöhe ÜBER dem Hüftgelenk:
    #   foot_z = L_F*sin(90°) + L_T*sin(70°)  ≈ 0.316 m
    KNEE_TUCK_DEG = 160.0
    _TIBIA_ELEV = 90.0 - (180.0 - KNEE_TUCK_DEG)          # = 70°
    FOOT_Z_MAX = L_F + L_T * math.sin(math.radians(_TIBIA_ELEV))

    STEP_H_MIN = 0.010

    # --- Req 2: Körperhöhe --------------------------------------------
    BODY_H_MIN = 0.000          # Bauchlage (Fuß auf Hüfthöhe)
    BODY_H_NOM = 0.190          # Nennstand
    L_REACH_STAND = 0.120       # horizontale Reichweite im Stand (Stabilität)
    # max. Standhöhe = vertikale Komponente bei fast gestrecktem Bein:
    BODY_H_MAX = math.sqrt((L_F + L_T) ** 2 - L_REACH_STAND ** 2)  # ≈ 0.302 m

    # --- Gelenklimits [rad] ------------------------------------------
    # Die ST3215 drehen kontinuierlich, mechanische Anschläge ergeben sich
    # erst aus der Beinkonstruktion und sind aktuell KEINE harte Grenze.
    # Daher bewusst WEIT gesetzt, damit die Limits die gewünschten Tuck-/
    # Streck-Posen nicht künstlich abschneiden. Die EINZIGE echte Grenze ist
    # die Beinreichweite D ∈ [|L_F-L_T|, L_F+L_T] = [25 mm, 325 mm].
    # Werte später an die reale Beinkonstruktion anpassen (Selbstkollision).
    COXA_MIN, COXA_MAX = -math.radians(110), math.radians(110)
    FEMUR_MIN, FEMUR_MAX = -math.radians(160), math.radians(130)  # neg = auf
    TIBIA_MIN, TIBIA_MAX = -math.radians(20), math.radians(175)

    def femur_torque(self, r, F_leg):
        """Statisches Femur-Moment [Nm] bei horizontalem Fußabstand r vom Hüftgelenk
        unter vertikaler Beinlast F_leg. Hebelarm = (r − L_C)."""
        return F_leg * max(0.0, r - self.L_C)

    def torque_limited_reach(self, F_leg, tau_servo, sf=1.5):
        """Größter horizontaler Fußabstand vom Hüftgelenk [m], bei dem das Femur-Servo
        die Last F_leg noch hält (Dynamik-Sicherheitsfaktor sf):
            F_leg·(r − L_C) ≤ tau_servo/sf  ->  r ≤ L_C + (tau_servo/sf)/F_leg
        Hängt NUR von Last und Servo ab, nicht von der Beinlänge."""
        return self.L_C + (tau_servo / sf) / F_leg

    def max_leg_length(self, F_leg, tau_servo, z, sf=1.5):
        """Längste sinnvolle (L_F+L_T) für ein Ziel-z: dort, wo die geometrische
        Reichweite gerade die drehmoment-sichere erreicht. Länger gibt nur Raum,
        den das Servo nicht tragen kann.
            L_C + sqrt((L_F+L_T)² − z²) = L_C + (tau_servo/sf)/F_leg
            -> L_F+L_T = sqrt(a² + z²),  a = (tau_servo/sf)/F_leg
        """
        a = (tau_servo / sf) / F_leg
        return math.sqrt(a*a + z*z)

    def max_reach(self, z, margin=0.015):
        """
        Maximaler horizontaler Fußabstand vom Hüftgelenk [m] bei Fußhöhe z
        (z < 0 = Fuß unter der Hüfte). Reine Funktion der Segmentlängen:

            r_max(z) = L_C + sqrt((L_F + L_T)² − z²)

        Herleitung: Die Coxa (L_C) liegt horizontal und legt die Azimutrichtung
        fest; Femur+Tibia arbeiten in der dadurch aufgespannten Vertikalebene und
        erreichen voll gestreckt einen Punkt im Abstand (L_F+L_T) vom Femurgelenk.
        Dessen horizontale Projektion bei Höhe z ist sqrt((L_F+L_T)² − z²).
        `margin` hält Abstand zu Gelenk-/Singularitätsgrenzen (echte IK ~1-2 cm enger).
        Skaliert automatisch mit L_C/L_F/L_T -> Beinlänge frei wählbar.
        """
        span = self.L_F + self.L_T
        if abs(z) >= span:
            return self.L_C
        return self.L_C + math.sqrt(span*span - z*z) - margin

    def min_reach(self, z, margin=0.010):
        """
        Minimaler horizontaler Fußabstand vom Hüftgelenk [m] bei Fußhöhe z.
        Voll gefaltete Kette erreicht innen den Abstand |L_F − L_T| vom Femurgelenk:

            r_min(z) = L_C + sqrt(max(0, (L_F − L_T)² − z²)) + margin
        """
        fold = abs(self.L_F - self.L_T)
        inner = math.sqrt(max(0.0, fold*fold - z*z))
        return self.L_C + inner + margin

    def step_h_max(self, stance_z):
        """
        Maximale Schritt-Hubhöhe relativ zur Standfußhöhe `stance_z`
        (stance_z < 0). Fußspitze darf FOOT_Z_MAX über Hüfte nicht
        überschreiten -> max. Hub = FOOT_Z_MAX - stance_z.
        """
        return self.FOOT_Z_MAX - stance_z

    def solve(self, x, y, z):
        """
        Liefert (theta_c, theta_f, theta_t, ok).
        `ok` = False, wenn Ziel außerhalb Workspace oder Gelenklimits
        lag und geclampt werden musste (für Logging/Sicherheit).
        Eingabe: Fuß im Hüft-Koordinatensystem des Beins (nach mount_yaw).
        """
        ok = True

        # Hinweis: kein künstlicher Höhen-Cap mehr. Die physikalische Grenze
        # ist allein die Reichweite D (unten geclampt). Der Fuß darf also bis
        # nahe an die volle Streckung (325 mm) in JEDE Richtung - inkl. weit
        # über Schulterhöhe (Mittelbein-Tuck) und tief abgesenkt (Greifer).

        # --- Coxa (Yaw) ---
        theta_c = math.atan2(y, x)

        # --- horizontale Reichweite ab Femurgelenk ---
        L = math.sqrt(x * x + y * y) - self.L_C
        if L < 0.02:
            L = 0.02
            ok = False

        # --- Geradlinige Distanz Femurgelenk->Fuß, auf Reichweite clampen ---
        D = math.sqrt(L * L + z * z)
        reach_max = self.L_F + self.L_T - 0.002
        reach_min = abs(self.L_F - self.L_T) + 0.002
        if D > reach_max:
            D = reach_max
            ok = False
        if D < reach_min:
            D = reach_min
            ok = False

        # --- Femur/Tibia (Kosinussatz, einheitlicher stetiger Ast) ---
        # phi = Elevationswinkel der Fußrichtung (z<0 ⇒ phi<0)
        phi = math.atan2(z, L)
        val_f = _clamp((self.L_F * self.L_F + D * D - self.L_T * self.L_T)
                       / (2 * self.L_F * D), -1.0, 1.0)
        alpha = math.acos(val_f)
        # down-positiv ⇒ theta_f = -(phi + alpha)  (Knie-oben-Lösung)
        theta_f = -(phi + alpha)

        val_t = _clamp((self.L_F * self.L_F + self.L_T * self.L_T - D * D)
                       / (2 * self.L_F * self.L_T), -1.0, 1.0)
        theta_t = math.pi - math.acos(val_t)

        # --- Gelenklimits anwenden (Servo-/Kollisionsschutz) ---
        tc = _clamp(theta_c, self.COXA_MIN, self.COXA_MAX)
        tf = _clamp(theta_f, self.FEMUR_MIN, self.FEMUR_MAX)
        tt = _clamp(theta_t, self.TIBIA_MIN, self.TIBIA_MAX)
        if (tc != theta_c) or (tf != theta_f) or (tt != theta_t):
            ok = False
        return tc, tf, tt, ok

    def forward(self, theta_c, theta_f, theta_t):
        """FK - Umkehrung von solve(). Aus den drei Servowinkeln den Fuß im
        Hüft-Frame (vor mount_yaw). REIN aus Winkeln -> 1:1 auf ESP32 portierbar
        (Present-Position der ST3215 einsetzen). Verifiziert gegen solve():
        forward(solve(x,y,z)) == (x,y,z).
        Konvention (wie solve): down-positiv, Knie-oben-Ast.
          beta_f = -theta_f                 (geom. Femur-Aufwärtswinkel gg. L-Achse)
          beta_t = -theta_f - theta_t       (geom. Tibia-Winkel gg. L-Achse)"""
        beta_f = -theta_f
        beta_t = -theta_f - theta_t
        L = self.L_C + self.L_F*math.cos(beta_f) + self.L_T*math.cos(beta_t)
        z = self.L_F*math.sin(beta_f) + self.L_T*math.sin(beta_t)
        x = L*math.cos(theta_c)
        y = L*math.sin(theta_c)
        return x, y, z


        tc, tf, tt, _ = self.solve(x, y, z)
        return tc, tf, tt


class BalanceController:
    """
    PD-Regler, der die Körpernormale zur Schwerkraft ausrichtet
    (Roll/Pitch -> 0). Gibt additive Roll/Pitch-KORREKTUREN zurück, die
    über die Gang-IK gelegt werden ("IK-Balance-Überlagerung").

    Negatives Feedback: gemessener Nase-hoch-Pitch ⇒ Kommando senkt die
    Nase. Vorzeichen hängt von der Lage-Konvention ab -> über
    PITCH_SIGN/ROLL_SIGN an Sim bzw. IMU anpassbar.

    Reine math-Logik: auf dem ESP32 mit IMU-Winkeln (rad) speisen.
    """
    # Die kommandierte Lage-Rotation der Fußziele ist invers zur gemessenen
    # Euler-Lage (kommandierter Pitch>0 -> Nase HOCH -> Euler-Pitch wird negativ).
    # Daher +1.0, damit der Regler die gemessene Neigung gegen 0 fährt
    # (statt sie zu verstärken - vorher kippte der Körper nach vorne).
    PITCH_SIGN = +1.0     # bei Vorzeichenfehler auf -1.0 drehen
    ROLL_SIGN = +1.0

    def __init__(self, kp=0.9, kd=0.04, max_corr=0.45, lp=0.15, slew=0.10):
        self.kp = kp; self.kd = kd
        self.max_corr = max_corr
        self.lp = lp; self.slew = slew
        self._r_f = 0.0; self._p_f = 0.0      # tiefpassgefilterte Messung
        self._r_prev = 0.0; self._p_prev = 0.0
        self.r_out = 0.0; self.p_out = 0.0

    def reset(self):
        self._r_f = self._p_f = 0.0
        self._r_prev = self._p_prev = 0.0
        self.r_out = self.p_out = 0.0

    def update(self, roll_meas, pitch_meas, dt, pitch_sp=0.0, roll_sp=0.0):
        # IMU-Tiefpass (gegen Rauschen/Schritt-Impulse)
        self._r_f += (roll_meas - self._r_f) * self.lp
        self._p_f += (pitch_meas - self._p_f) * self.lp
        d_r = (self._r_f - self._r_prev) / dt if dt > 1e-6 else 0.0
        d_p = (self._p_f - self._p_prev) / dt if dt > 1e-6 else 0.0
        self._r_prev = self._r_f; self._p_prev = self._p_f

        # Fehler gegen SOLLWERT (0 = waagerecht; beim Treppensteigen = Fußebene-
        # Neigung, damit der Körper parallel zur schiefen Ebene steht statt am
        # Bein-Reichweiten-Limit zu kämpfen).
        r_cmd = self.ROLL_SIGN * (self.kp * (self._r_f - roll_sp) + self.kd * d_r)
        p_cmd = self.PITCH_SIGN * (self.kp * (self._p_f - pitch_sp) + self.kd * d_p)
        r_cmd = _clamp(r_cmd, -self.max_corr, self.max_corr)
        p_cmd = _clamp(p_cmd, -self.max_corr, self.max_corr)

        # sanftes Nachführen (kein Sprung)
        self.r_out += (r_cmd - self.r_out) * self.slew
        self.p_out += (p_cmd - self.p_out) * self.slew
        return self.r_out, self.p_out

    def decay(self):
        """Korrekturen sanft gegen 0 abklingen lassen, wenn der Balancer
        inaktiv ist (Auto-Balance aus / Treppen-Climber aktiv). Hält die
        Messzustände konsistent, damit das Wiedereinschalten ruckfrei ist."""
        self.r_out += (0.0 - self.r_out) * self.slew
        self.p_out += (0.0 - self.p_out) * self.slew
        # gefilterte Messung mitziehen, damit update() später nicht springt
        self._r_prev = self._r_f
        self._p_prev = self._p_f
        return self.r_out, self.p_out


class StallGuard:
    """
    Portable Stall-Erkennung pro Bein (ESP32-tauglich: nur Vergleiche und
    Integer-Zähler, keine Bibliotheken).

    Eingaben je Zyklus:
      pos_err   = |Soll-Winkel − Ist-Winkel| des Coxa-Gelenks [rad]
                  (Hardware: kommandierte Position vs. Present-Position-Register;
                   Sim: kommandierter Winkel vs. getJointState[0])
      load_frac = Gelenklast 0..1 bezogen auf Stall
                  (Hardware: Present-Load/Strom-Register; Sim: |tau|/Stall)

    Stall, wenn der Soll-Ist-Fehler GROSS bleibt UND die Last HOCH ist (Bein
    drückt gegen ein Hindernis, kommt aber nicht weiter) - über mehrere Zyklen
    entprellt. Danach läuft ein Recovery-Timer; solange er > 0 ist, soll der
    Aufrufer das Bein anheben & den Vorschub zurücknehmen.
    """
    POS_ERR = 0.10      # rad bleibende Abweichung (~6°)
    LOAD_TH = 0.80      # Last-Anteil vom Stall
    TRIP    = 10        # Zyklen, die beide Bedingungen halten müssen
    RECOVER = 90        # Zyklen Recovery-Dauer (~0.4 s @ 240 Hz)

    def __init__(self):
        self.trip = 0
        self.recover = 0
        self.events = 0     # Zähler erkannter Stalls (Diagnose)

    def update(self, pos_err, load_frac):
        if self.recover > 0:
            self.recover -= 1
            return True
        if pos_err > self.POS_ERR and load_frac > self.LOAD_TH:
            self.trip += 1
            if self.trip >= self.TRIP:
                self.trip = 0
                self.recover = self.RECOVER
                self.events += 1
                return True
        elif self.trip > 0:
            self.trip -= 1
        return False

    def reset(self):
        self.trip = 0; self.recover = 0


class StairModel:
    """
    Perception-Abstraktion (portabel). In der Sim mit der bekannten
    Treppengeometrie gefuettert; auf der echten Hardware liefert das
    Perception-Modul (Hailo-8) dieselben Abfragen aus der Hoehenkarte:
      height_at(x)      -> Welt-Hoehe der Stuetzflaeche an Laengsposition x
      tread_center(x)   -> x auf Tritt-Mitte schieben (weg von Kanten/Risern)
      slope_at(x)       -> lokale Steigung [rad] (fuer Auto-Pitch)
    Nur einfache Arithmetik, kein numpy.
    """
    def __init__(self, rise, run, x_start=1.0, n_up=5, plateau_len=1.0):
        self.rise = rise; self.run = run
        self.x0 = x_start; self.n = n_up
        self.top = rise * n_up
        self.x_plat_end = x_start + n_up * run + plateau_len
        self.x_down0 = self.x_plat_end

    def height_at(self, x):
        if x < self.x0:
            return 0.0
        if x < self.x0 + self.n * self.run:
            i = int((x - self.x0) // self.run)
            return (i + 1) * self.rise
        if x < self.x_plat_end:
            return self.top
        xd = x - self.x_down0
        if xd < self.n * self.run:
            i = int(xd // self.run)
            return self.top - (i + 1) * self.rise
        return 0.0

    def tread_center(self, x):
        if x < self.x0:
            return x
        if x < self.x0 + self.n * self.run:
            i = int((x - self.x0) // self.run)
            return self.x0 + i * self.run + self.run * 0.55
        if x < self.x_plat_end:
            return x
        xd = x - self.x_down0
        if xd < self.n * self.run:
            i = int(xd // self.run)
            return self.x_down0 + i * self.run + self.run * 0.55
        return x

    def slope_at(self, x):
        if self.x0 - 0.30 < x < self.x0 + self.n * self.run + 0.10:
            return math.atan2(self.rise, self.run)
        if self.x_down0 - 0.10 < x < self.x_down0 + self.n * self.run + 0.30:
            return -math.atan2(self.rise, self.run)
        return 0.0

    def _tread_bounds(self, x):
        """[x_lo, x_hi] der Trittfläche, auf der x liegt (Welt-x)."""
        if x < self.x0:
            return (self.x0 - 2.0, self.x0)                       # Boden vor Treppe
        if x < self.x0 + self.n * self.run:
            i = int((x - self.x0) // self.run)
            return (self.x0 + i * self.run, self.x0 + (i + 1) * self.run)
        if x < self.x_plat_end:
            return (self.x0 + self.n * self.run, self.x_plat_end) # Plateau
        xd = x - self.x_down0
        if xd < self.n * self.run:
            i = int(xd // self.run)
            return (self.x_down0 + i * self.run, self.x_down0 + (i + 1) * self.run)
        return (self.x_down0 + self.n * self.run, self.x_down0 + self.n * self.run + 2.0)

    def foothold(self, x, margin=0.06):
        """Foothold-Planung (Ground-Truth-Ersatz für die Perzeptions-Elevation-Map).
        Zu einem gewünschten Fuß-Welt-x: sicherer Aufsetzpunkt auf der nächsten
        Trittfläche, weg von Risern/Kanten.
        Rückgabe (x_safe, z, valid):
          x_safe - Welt-x, auf margin zur Vorder-/Hinterkante geclampt
          z      - Trittflächenhöhe
          valid  - Trittfläche breit genug für einen Fuß (sonst nur Riser/Kante)
        """
        x_lo, x_hi = self._tread_bounds(x)
        z = self.height_at(0.5 * (x_lo + x_hi))                  # Höhe der Trittfläche (kantenrobust)
        width = x_hi - x_lo
        valid = width > 2.0 * margin
        lo, hi = x_lo + margin, x_hi - margin
        x_safe = lo if x < lo else (hi if x > hi else x)
        return (x_safe, z, valid)


# <<< PORTABLE CORE (ESP32) <<<


class HexapodLeg:
    def __init__(self, name, m_x, m_y, m_yaw):
        self.name = name
        self.mount_x = m_x; self.mount_y = m_y; self.mount_yaw = m_yaw
        def_x = 0.22; def_y = 0.00; def_z = -HexapodKinematics.BODY_H_NOM
        self.base_x = m_x + def_x * math.cos(m_yaw) - def_y * math.sin(m_yaw)
        self.base_y = m_y + def_x * math.sin(m_yaw) + def_y * math.cos(m_yaw)
        self.base_z = def_z
        self.default_z = def_z   # Referenz für Stair-Reset
        # Reichweite vom Hüftgelenk (für Schrittlängen-Kollisionsgrenze)
        self.reach_xy = math.hypot(def_x, def_y)


# ============================================================================
#  TUNER-STUB - manueller Bein-Override (im V8-Fundament als No-Op).
#    Der IK-Output fragt get_override_angles ab; hier immer None.
# ============================================================================
class _TunerStub:
    def __init__(self, ctrl): self.ctrl = ctrl
    def init_sliders(self): pass
    def get_override_angles(self, leg_name): return None
    def toggle(self): pass


# ============================================================================
#  STANCE-CONTROLLER (V9, portabler Kern) - die drei entkoppelten Regler,
#  STÜTZMENGEN-AGNOSTISCH: läuft über eine beliebige Stützmenge S (6 beim Stand,
#  3-5 im Gait, 4 beim Zentaur). Der Median-über-S macht R3 stützmengen-robust,
#  ohne Sonderpfade. Eingänge NUR µ-Switch, IMU, FK -> exakt der ESP32-Kern.
#    R1 (command_leg, pro Bein): µ-Switch offen -> nachsenken; zu -> einrasten.
#       ZWEI-WEGE: Rumpf über Soll (R3-gated) -> gesenktes Bein zurückholen (Anti-Ratschet).
#    R2 (update_attitude, global): IMU-Balancer, rotiert die Fußebene (in _set_leg).
#    R3 (update_height): FK-Median der Fuß-z über S -> body_height_offset (bump-robust).
#  Kommandiert NUR die Stance-Beine; die xy-Sollpose liefert der Aufrufer (Stand=Neutral,
#  Gait=geplanter Trittpunkt) -> der Kern bleibt gait-agnostisch.
# ============================================================================
class StanceController:
    def __init__(self, robot):
        self.r = robot

    def update_attitude(self, pitch_sp=0.0):
        """R2 (global): Balancer auf Sollwert (pitch_sp != 0 fürs Klettern). Setzt _g_*_eff,
        die _set_leg als Fußebenen-Rotation anwendet. EINMAL pro Frame, vor den Beinen."""
        r = self.r
        roll_m, pitch_m = r._read_body_attitude()
        r._g_pitch_meas = pitch_m
        r._g_roll_meas  = roll_m
        if r.auto_balance:
            r.roll_bal, r.pitch_bal = r.balance.update(roll_m, pitch_m, 1/240., pitch_sp=pitch_sp)
        else:
            r.roll_bal, r.pitch_bal = r.balance.decay()
        r._g_pitch_eff = r.pitch_bal
        r._g_roll_eff  = r.roll_bal

    def proj_height(self, stance):
        """[V9.5-DIAG] Pitch/Roll-projizierte VERTIKALE Körperhöhe über den tragenden Beinen.
        Dreht den körper-relativen FK-Fußvektor (fx,fy,fz) mit den IMU-Winkeln in die Welt und
        nimmt die z-Komponente -> echte vertikale Höhe, auch bei nase-hoch/nase-runter. Wird
        NUR geloggt (regelt noch nicht) -> Vorzeichen an echten Kletterdaten prüfen, dann erst
        R3 darauf umstellen. z_welt = -sin(t)*fx + cos(t)*sin(f)*fy + cos(t)*cos(f)*fz."""
        r = self.r
        th = getattr(r, '_g_pitch_meas', 0.0); ph = getattr(r, '_g_roll_meas', 0.0)
        ct, st = math.cos(th), math.sin(th); cf, sf = math.cos(ph), math.sin(ph)
        zs = []
        for name in stance:
            leg = r._legmap[name]
            if not r._foot_touch_down(leg):
                continue
            ci = r.joint_map.get(f"{name}_coxa_joint")
            fi = r.joint_map.get(f"{name}_femur_joint")
            ti = r.joint_map.get(f"{name}_tibia_joint")
            if None in (ci, fi, ti):
                continue
            tc = p.getJointState(r.robot_id, ci)[0]
            tf = p.getJointState(r.robot_id, fi)[0]
            tt = p.getJointState(r.robot_id, ti)[0]
            fx, fy, fz = r.ik.forward(tc, tf, tt)
            zs.append(-st*fx + ct*sf*fy + ct*cf*fz)          # Welt-z-Komponente (vertikaler Fall)
        r._g_r3_n = len(zs)                                  # tragende Beine, die R3 sieht
        if len(zs) >= 3:
            zs.sort()
            r._g_h_proj = -zs[len(zs)//2]                     # Median (flach von R3 genutzt)
            r._g_h_low  = -zs[0]                              # über dem TIEFSTEN Bein (roh; springt bei Fuß-Wechsel)
            r._g_h_high = -zs[-1]                             # über dem HÖCHSTEN Bein
            # [V10.1] tiefpassgefiltert -> R3 folgt der MITTLEREN Untergrundhöhe, nicht jedem
            # sprunghaften Wechsel des tiefsten Beins (sonst reißt es den Rumpf ±10cm hoch/runter).
            r._g_h_low_f = r._g_h_low_f + r.G_H_LOW_LP * (r._g_h_low - r._g_h_low_f)
        # <3: letzten Wert halten (kein Update)
        return getattr(r, '_g_h_proj', abs(r.G_Z))

    def update_height(self, stance):
        """R3: Körperhöhe halten. FLACH -> robuster roher FK-Median (unverändert V9.6, kein
        Flach-Risiko). KLETTERN (climbing) -> Höhe über dem TIEFSTEN tragenden Bein (est_h_low,
        projiziert = echte Vertikale über der unteren Stütze). Sollwert dabei |G_Z| + Kletter-Hub
        + G_CLIMB_CLEAR (Bauch-Freiheit) -> R3 kämpft NICHT gegen den Hub, dämpft aber den Hop.
        Läuft in beiden Fällen (kein Einfrieren mehr). proj_height hat _g_h_low/_g_r3_n gesetzt."""
        r = self.r
        if getattr(r, '_g_climbing', False):
            if r._g_r3_n < 3:
                return 0.0
            sp = abs(r.G_Z) + r.G_CLIMB_CLEAR                # Soll: Rumpf G_CLIMB_CLEAR über der Referenz
            # [V10.5] PAAR-ANKER: Richtung über Pitch. Nase-hoch (pitch<0) = Aufstieg -> Hinterpaar
            # (untere, gefährdete Stütze); nase-runter = Abstieg -> Vorderpaar. FK der Referenz-
            # STANCE-Beine (Schwungbeine raus) projiziert -> ein dangelndes Referenzbein liest tief
            # und zieht den Rumpf runter (kein blinder Fleck). Gefiltert für glatte Nachführung.
            # [V10.7] Richtung mit HYSTERESE: nur umschalten, wenn Pitch KLAR nase-hoch/-runter ist,
            # nicht bei jedem Nulldurchgang -> sonst flippt das Referenzpaar auf Pitch-Rauschen und
            # der Bezug springt (sporadischer Bounce). Dazwischen: letzte Richtung halten.
            thp = getattr(r, '_g_pitch_meas', 0.0)
            if thp < -r.G_CLIMB_DIR_DB:
                r._g_ascending = True
            elif thp > r.G_CLIMB_DIR_DB:
                r._g_ascending = False
            ascending = getattr(r, '_g_ascending', True)
            ref = r._climb_ref_rear if ascending else r._climb_ref_front
            sw = getattr(r, '_g_swing_set', ())
            zs = []
            for name in ref:
                if name in sw:
                    continue                                  # Schwungbein: nicht als Referenz
                ci = r.joint_map.get(f"{name}_coxa_joint")
                fi = r.joint_map.get(f"{name}_femur_joint")
                ti = r.joint_map.get(f"{name}_tibia_joint")
                if None in (ci, fi, ti):
                    continue
                fz = r.ik.forward(p.getJointState(r.robot_id, ci)[0],
                                  p.getJointState(r.robot_id, fi)[0],
                                  p.getJointState(r.robot_id, ti)[0])[2]
                zs.append(fz)                                 # [V10.6] ROHE Beinstreckung (relativ!) - NICHT
                #  projizierte Welt-Höhe: wir wollen die BEINSTRECKUNG komfortabel halten, nicht die
                #  Welt-Vertikale (die der Pitch aufbläht -> sonst zwingt R3 die Bodenbeine kürzer = abheben).
            if zs:
                zs.sort()
                h_ref = -zs[len(zs)//2]                        # Beinstreckung über dem Referenzpaar (Median)
                r._g_h_ref_f = r._g_h_ref_f + r.G_H_LOW_LP * (h_ref - r._g_h_ref_f)   # gefiltert
                r._g_h_ref_raw = h_ref                         # [Diag] roher Referenzwert
            # Overstretch-Sicherheitsnetz (v.a. Mittelbeine, die nicht im Paar sind)
            over = 0.0
            thr = r.G_Z_FLOOR + r.G_OVERSTRETCH_DB
            for name in stance:
                leg = r._legmap[name]
                if r._foot_touch_down(leg):
                    continue
                ci = r.joint_map.get(f"{name}_coxa_joint")
                fi = r.joint_map.get(f"{name}_femur_joint")
                ti = r.joint_map.get(f"{name}_tibia_joint")
                if None in (ci, fi, ti):
                    continue
                fzf = r.ik.forward(p.getJointState(r.robot_id, ci)[0],
                                   p.getJointState(r.robot_id, fi)[0],
                                   p.getJointState(r.robot_id, ti)[0])[2]
                if fzf < thr:
                    over = max(over, thr - fzf)
            err = (r._g_h_ref_f - sp) + r.G_OVERSTRETCH_K * over
            r._g_climb_err = err; r._g_climb_over = over; r._g_n_ref = len(zs)   # [Diag]
            # [V10.11] KLEINE Kletter-Gain (nicht die flache 0.05): der Integrator verstärkte sonst
            # den kleinen Referenz-Ripple zu einer großen bho-Schwingung (Isolation: eingefroren war
            # glatt). Kleine Gain -> fast eingefroren (glatt) + langsame Drift-/Lift-Korrektur für hohe Stufen.
            r.body_height_offset = _clamp(r.body_height_offset - r.G_CLIMB_H_KP * err, -0.10, 0.15)
            return max(0.0, err - r.HOLD_RETRACT_DB)
        # FLACH: robuster roher FK-Median über die tragenden Beine
        fz = []
        for name in stance:
            leg = r._legmap[name]
            if not r._foot_touch_down(leg):
                continue
            ci = r.joint_map.get(f"{name}_coxa_joint")
            fi = r.joint_map.get(f"{name}_femur_joint")
            ti = r.joint_map.get(f"{name}_tibia_joint")
            if None in (ci, fi, ti):
                continue
            tc = p.getJointState(r.robot_id, ci)[0]
            tf = p.getJointState(r.robot_id, fi)[0]
            tt = p.getJointState(r.robot_id, ti)[0]
            fz.append(r.ik.forward(tc, tf, tt)[2])
        r._g_r3_n = len(fz)
        if len(fz) >= 3:
            fz.sort()
            err = (-fz[len(fz)//2]) - abs(r.G_Z)
            r.body_height_offset = _clamp(r.body_height_offset - r.HOLD_H_KP * err, -0.10, 0.15)
            return max(0.0, err - r.HOLD_RETRACT_DB)
        return 0.0

    def command_leg(self, name, nx, ny, over_height, set_contact=True):
        """R1 (pro Bein, ZWEI-WEGE) + Höhenoffset -> z, dann IK/_set_leg. kein Kontakt ->
        nachsenken; Kontakt UND Rumpf über Soll -> zurückholen (min 0, nie kürzer als Basis).
        set_contact: _g_contact hier setzen (Hold/Anzeige). Im Gait besitzt die Kontakt-
        Hysterese das Flag -> dort False. Gibt die kommandierte z zurück (für _g_foot-Konsistenz)."""
        r = self.r
        leg = r._legmap[name]
        td = r._foot_touch_down(leg)
        if set_contact:
            r._g_contact[name] = td
        if not td:
            r._hold_dz[name] -= r.HOLD_SEEK_V
        elif over_height > 0.0:
            r._hold_dz[name] = min(0.0, r._hold_dz[name] + r.HOLD_SEEK_V)
        z = _clamp(r.G_Z + r._hold_dz[name] - r.body_height_offset, r.G_Z_FLOOR, 0.06)
        r._set_leg(leg, nx, ny, z)
        return z


# ============================================================================
#  SLARC CONTROLLER (V8) - schlank: Setup + Glue + EIN Gait-Kern.
# ============================================================================
class SlarcController:
    def __init__(self):
        # [SIM/PORTABLE] Kinematik, Balance, Roboter-Setup
        self.kin = HexapodKinematics()
        self.ik  = self.kin
        self.balance = BalanceController()
        self.auto_balance = True   # PD-Balancer fährt gemessenen Pitch/Roll auf Sollwert.
                                   # ESSENTIELL für flaches Klettern (climb_pitch=0 wird sonst
                                   # nur passiv gewünscht, nicht durchgesetzt). Taste B togglet.
        self.roll_bal = 0.0; self.pitch_bal = 0.0

        self.robot_id = None
        self.joint_map = {}
        self.cameras = None
        self._foot_link_idx = {}
        self._contact_cache = []
        self._contact_frame = -1
        # V9.4: Kontakt-LATCH (Sim-Entprellung, HW-Gegenstück zur µ-Switch-ms-Entprellung).
        # 1×/Frame in _refresh_contact_cache aktualisiert: schnell TRUE, langsam FALSE.
        # (Die Latch-Dicts werden weiter unten initialisiert, sobald self.legs existiert.)
        self.G_TD_RELEASE = 8      # Frames echten Verlusts, bevor der Latch auf FALSE fällt (~33ms@240Hz)

        body_l = BODY_L; body_w = BODY_W; mid_y_off = MID_Y_OFFSET
        self.legs = [
            HexapodLeg("front_right",  body_l/2, -body_w/2, -math.radians(30)),
            HexapodLeg("front_left",   body_l/2,  body_w/2,  math.radians(30)),
            HexapodLeg("mid_right",    0,        -(body_w/2 + mid_y_off), -math.radians(90)),
            HexapodLeg("mid_left",     0,         (body_w/2 + mid_y_off),  math.radians(90)),
            HexapodLeg("rear_right",  -body_l/2, -body_w/2, -math.radians(150)),
            HexapodLeg("rear_left",   -body_l/2,  body_w/2,  math.radians(150)),
        ]
        leg_names = [l.name for l in self.legs]
        self._legmap = {l.name: l for l in self.legs}   # Name -> Bein (StanceController)
        self._climb_ref_front = [l.name for l in self.legs if l.mount_x > 1e-3]   # Vorderpaar (Abstieg)
        self._climb_ref_rear  = [l.name for l in self.legs if l.mount_x < -1e-3]   # Hinterpaar (Aufstieg)
        self.stance  = StanceController(self)            # V9 portabler Regler-Kern
        self._td_latch = {n: False for n in leg_names}   # V9.4: Kontakt-Latch (entprellt)
        self._td_air   = {n: 0 for n in leg_names}
        self._stall    = {n: StallGuard() for n in leg_names}
        self._cmd_coxa = {n: 0.0 for n in leg_names}
        self.RECOVER_LIFT = 0.10

        # [PI] Bewegungskommando (omnidirektional, Körperframe) + Pose-Sollwerte
        self.cmd_vel_x = 0.0; self.cmd_vel_y = 0.0; self.cmd_yaw = 0.0
        self.pitch = 0.0; self.roll = 0.0
        self.body_height_offset = 0.0
        self.BHO_MIN = self.kin.BODY_H_MIN - self.kin.BODY_H_NOM
        self.BHO_MAX = self.kin.BODY_H_MAX - self.kin.BODY_H_NOM
        self._bho_target = 0.0                    # gerampter Höhen-Sollwert (kein Hüpfen)

        # [PI] Geländemodell (Sim: aus Geometrie; HW: aus Hailo-Höhenkarte)
        self.stairs = StairModel(STAIR_RISE, STAIR_RUN, x_start=STAIR_X, n_up=5, plateau_len=1.0)

        # ── GAIT-KERN-Parameter ──
        self.gait_name = 'tripod'
        self.GAITS = {
            'tripod':    {'groups': [['front_left','mid_right','rear_left'],
                                     ['front_right','mid_left','rear_right']],
                          'advance': 'continuous',   'splay': 0.0},
            'ripple':    {'groups': [['rear_left'],['mid_right'],['front_left'],
                                     ['rear_right'],['mid_left'],['front_right']],
                          'advance': 'continuous',   'splay': 0.0},
            'placemove': {'groups': [['front_right'],['front_left'],
                                     ['mid_right'],['mid_left'],
                                     ['rear_right'],['rear_left']],
                          'advance': 'when_planted', 'splay': 0.5, 'splay_rear': 0.0},
        }
        # Kern-Konstanten (ESP32-reaktiv)
        self.G_RADIUS   = 0.229    # Neutral-Radius vom Hüftgelenk [m]
        self.G_CLIMB_RADIUS_SCALE = 1.0    # [V10.13 zurückgenommen] Narrow zog Hinterfüße nach innen/unter
        self.G_REAR_REACH = 0.13   # Hinterbein-Offset nach hinten pro rad Nase-hoch-Pitch [m/rad] (flach-nah)
        self.G_CLIMB_REAR_FWD = 0.06   # [V10.16] Klettern: Hinterbein-Trittpunkt nach VORN Richtung Stufe [m]
        self.G_COM_SHIFT = 0.04    # [V10.14] CoM-Wippe: max fore-aft Rumpfverschiebung beim Klettern [m]
        self.G_COM_RAMP  = 0.0008  # [V10.14] Rampe der CoM-Verschiebung [m/Frame] (sanft)
        self.G_HOLD_SPLAY = 0.0    # Halte-Standpose: 0.0 = Füße in Mount-Richtung (Spider, tiefe
                                   # Stützbasis vorn/hinten), 1.0 = alle seitlich (flach fore-aft).
                                   # Kleiner Splay -> mehr Schwerpunkt-Reserve gegen Nick-Kipp.
        self.G_Z        = -0.12    # Neutral-Standhöhe (Fuß unter Hüfte) [m]
        self.G_STEP     = 0.06     # Schrittlänge (halber Hub vor/zurück) [m]  (Taste 7)
        self.G_STEP_OPTS= [0.04, 0.06, 0.09, 0.12]
        self.G_LIFT     = 0.05     # Schwung-Hubhöhe [m]
        self.G_CLIMB_LIFT = 0.05   # beim Klettern: Fuß ÜBER KÖRPERHÖHE heben (Femur nach oben,                                   # Tibia eingezogen -> Fußpunkt über der Hüfte), BEVOR er vor-
                                   # schwingt. So kann er an keiner Stufe < Körper+5cm hängen
                                   # bleiben. Der ST3215-Femur hat keinen Anschlag, die IK erlaubt
                                   # bis ~0.32 über Hüfte -> nur diese kommandierte Höhe zählt.
        self.G_LIFT_MAX = 0.20     # max Schwung-Hubhöhe [m] (top bis +0.08 rel Hüfte -> Stufen bis ~20cm)
        self.G_CLIMB_RAISE = 0.0   # [V10.2] V8-Kletter-Hub STILLGELEGT - der Tiefstes-Bein-Anker
                                   # übernimmt seine Funktion (Rumpf steigt automatisch mit der Stufe).
                                   # Kein doppeltes Heben mehr -> Bodenbeine nicht überstreckt.
        self._g_climb_raise = 0.0  # gerampter Ist-Wert (bleibt 0, da G_CLIMB_RAISE=0)
        self.G_PHASE_V  = 0.020    # Phasenfortschritt/Frame
        # Freeze-Interrupt (quasi-statisch): verliert ein tragendes Bein den Boden,
        # hält die GESAMTE Bewegung an (Phase+Vortrieb+Schwung), bis der Kontakt
        # wieder da ist. HW = µ-Switch-Flankeninterrupt (MCP23017).
        self.G_FREEZE_DEB     = 2      # Entprellung [Frames]: so viele Frames Kontaktverlust, bevor Freeze greift
        self.G_FREEZE_TIMEOUT = 480    # findet ein Bein in so vielen Frames keinen Boden -> stuck (Replanner)
        self.G_SEEK_V_FREEZE  = 0.004  # schnelle Boden-Suche während Freeze [m/Frame] (~6.7× normale SEEK)
        self.G_FREEZE_ENABLE  = False  # Taste K togglet. STANDARD AUS - Isolationstest
                                       # (test_layers.py) belegt: Freeze war HAUPT-Hüpfer-
                                       # Erzeuger (−56% vz, Kontakt 2.0->3.6, wenn AUS). Die
                                       # schnelle Freeze-SEEK rammt die Beine in den Boden.
                                       # Konzept bleibt, braucht aber sanfte statt rammende Boden-Suche. Taste K togglet.
        self.G_BODY_V   = 0.0010   # Körper-Vortrieb/Frame bei vollem cmd [m]
        self.G_YAW_V    = 0.004    # Körper-Rotation/Frame bei vollem cmd [rad]
        self.G_LAND_F   = 3.0      # Aufsetz-Last [N]
        self.G_LAND_PH  = 0.55     # Last erst ab dieser Phase werten
        self.G_TOUCH_D  = 0.002    # Berührungs-Distanz [m]
        self.G_DOWN_NZ  = 0.7      # waagerechte Fläche: Normale_z darüber
        self.G_BLOCK_C  = 1.3      # Coxa-Anschlag-Schwelle [Nm] (über Schwung-Baseline max 1.2, unter Stall 2.94)
        self.G_BLOCK_ENABLE = True   # Coxa-Block: nur wenn Fuß KEINEN Bodenkontakt hat (sonst Trag-Artefakte
                                     # bis Stall). _foot_touch_down=False bei seitlichem Kantenanschlag -> fängt genau den.
        self.G_STEP_H_UP= 0.020; self.G_STEP_H_DN = 0.008
        self.G_BODY_H_KP= 0.02; self.G_FEMUR_TGT = -0.172; self.G_OFFSET_LIM = 0.10
        self.G_SEEK_V   = 0.0006; self.G_Z_FLOOR = -0.30
        self.G_SEEK_BHO_DB = 0.035   # Seek-Gate: Nachsenken nur wenn bho > -diese. Schwelle liegt
                                     # ZWISCHEN Tripods normalem Wippen (bho ~ -0.016..-0.028) und
                                     # placemoves echtem Windup (~-0.049) -> Tripod frei, placemove gegated.
        self.G_CLIMB_CLEAR = 0.050   # [V10.15] TUNING-Knopf Rumpfhöhe beim Klettern: Rumpf = |G_Z|+diese
                                     # über den Hinterfüßen. Tiefer -> Mittelbeine berühren Boden, Vorder-Femur
                                     # zeigt hoch. Rear-Reichweite macht jetzt die CoM-Wippe, nicht ein hoher Rumpf.
        self.G_H_LOW_LP = 0.005      # [V10.9] Tiefpass auf die Kletter-Höhenreferenz (Hinterbein-Streckung).
                                     # 0.02->0.005 (tau ~0.8s): die Referenz ist im stetigen Klettern konstant
                                     # (~0.19), springt nur kurz bei Bein-/Stufenwechsel; hart filtern -> R3
                                     # regelt nur den langsamen Mittelwert -> kein Bounce (Isolation: R3 war die Quelle).
        self._g_h_low_f = abs(self.G_Z)   # gefilterter Anker (Startwert = Standhöhe)
        self._g_h_ref_f = abs(self.G_Z)   # [V10.5] gefilterte Höhe über dem Referenzpaar (Klettern)
        self.G_OVERSTRETCH_DB = 0.03  # [V10.4] Band ab G_Z_FLOOR: fz darunter + kein Kontakt = überstreckt
        self.G_OVERSTRETCH_K  = 3.0   # [V10.4] Verstärkung des Overstretch-Abwärtsterms in R3 (Klettern)
        self.G_CLIMB_DIR_DB = 0.05    # [V10.7] Pitch-Hysterese für Auf/Ab-Richtung (Referenzpaar-Flip)
        self._g_ascending = True      # gelatchte Kletter-Richtung (Start: Aufstieg)
        # [HALTE-MODUS] isolierter Stand-Regelkreis (kein Gait). Zwei entkoppelte Regler.
        self.HOLD_SEEK_V = 0.0010  # Regler 1: Nachsenk-Rate für kontaktlose Füße [m/Frame]
        self.HOLD_H_KP   = 0.05    # Regler 3: Höhen-Regler-Verstärkung (Körperhöhe über Boden) - FLACH
        self.G_CLIMB_H_KP = 0.008  # [V10.11] R3-Gain beim KLETTERN: klein -> Integrator verstärkt den
                                   # Referenz-Ripple nicht zum Bounce; nur langsame Lift-/Drift-Korrektur.
        self.HOLD_RETRACT_DB = 0.005  # Regler 1 Zwei-Wege: Rumpf-Überhöhe-Totband [m]; oberhalb
                                      # holt R1 gesenkte Beine bei Kontakt zurück (R3-gated) ->
                                      # verhindert Einweg-Ratschet-Drift des dz (Common-Mode-Hub)
        self._hold_dz = {}         # pro-Bein z-Korrektur (Nachsenkung), init in start_hold()
        self.G_AIR_FR   = 3; self.G_HEAD_KP = 0.06; self.G_YAW_MAX = 0.006
        self.G_RECENT_DEAD = 0.05; self.G_RECENT_GAIN = 1.0
        self.G_SLOPE_DEAD  = 0.05; self.G_PITCH_LP = 0.08; self.G_PITCH_LIM = 0.22
        self.G_CLIMB_HOLD  = 60    # [V10.10] Frames climbing-Halten nach letztem on_stairs=True (Entprellung)
        self._g_climb_hold = 0
        self.G_PROG_WIN = 360; self.G_PROG_MIN = 0.030   # Fortschritts-Fenster [Frames] / Mindeststrecke [m]
        self.stuck = False; self.stuck_reason = ''
        self.G_FOOTHOLD = True     # Foothold-Planung (Trittflächen-Ziel) bei placemove - Taste F togglet
        self.G_STEP_DETECT = 0.025; self.G_BHO_RAMP = 0.004   # W/S-Rampe [m/Frame]
        # [PI] EINSTIEGS-BOOST (Option A): steht der Rumpf mit den Vorderbeinen auf der
        # Stufe (tragende Vorderbeine deutlich höher als Hinterbeine), wird der Schwerpunkt
        # per REINEM VORWÄRTSSCHUB über die Kante geschoben — placemove fehlt an der Kante
        # der Schwung, den Tripod ballistisch mitbringt. KEIN Anheben (dzb), das nur die
        # Vorderbeine von der Stufe löst. Universell (skaliert mit gemessener Stufenhöhe,
        # nicht auf 15 cm zugeschnitten). Portabel: FK-Höhen + µ-Switch. Taste Z togglet.
        self.G_ENTRY_BOOST = True
        self.G_ENTRY_THRESH   = 0.06   # Fußebenen-Höhendiff front-rear ab der Einstieg gilt [m]
        self.G_ENTRY_STEP_REF = 0.12   # Referenz-Stufenhöhe zur Normierung des Boost-Anteils [m]
        self.G_ENTRY_DX = 1.0          # extra Vortrieb an der Kante (× normaler Frame-Vortrieb).
                                       # Moderat: starker Schub überdehnt die Hinterbeine. Die
                                       # Vortriebs-Bremse (G_BRAKE_BAND) fängt Überdehnung ohnehin ab.
        self._g_entry = 0.0
        self._g_pitch_meas = 0.0   # gemessener Körper-Pitch (IMU), für Kletter-Hub-Erkennung
        # [PI] VORTRIEBS-BREMSE: der Rumpf-Vortrieb wird gedrosselt, je näher das am weitesten
        # gestreckte tragende Bein an seine Reichweitengrenze kommt (bis Stopp am Anschlag).
        # Verhindert, dass der Körper davonfährt und die nachziehenden Beine überdehnt.
        # Universell (ebener Boden wie Kante), portabel (Reichweite aus FK / max_reach).
        self.G_BRAKE_BAND = 0.04       # Reserve-Band [m]: >Band volle Fahrt, 0 = Stopp
        self._g_brake = 1.0
        self._g_ready = False

        self.tuner  = _TunerStub(self)
        self.logger = MotionLogger(self)

    def _foot_force(self, leg):
        """Summe der Normalkraft am Fuß-Link [N] (0 = kein Kontakt)."""
        idx = self._foot_link_idx.get(leg.name, -1)
        if idx < 0:
            return 0.0
        f = 0.0
        for c in self._contact_cache:
            if c[3] == idx:
                f += c[9]
        return f


    def _foot_touch_down(self, leg):
        """Entprellter Kontakt (Latch, 1×/Frame in _refresh_contact_cache aktualisiert): schnell
        TRUE, langsam FALSE. Sim-Gegenstück zur HW-µ-Switch-Entprellung -> kein Flackern. Alle
        Regler/Landung nutzen dieses stabile Signal."""
        return self._td_latch.get(leg.name, False)

    def _foot_touch_down_raw(self, leg):
        """Sensor 1 (ROH, ungefiltert) - BERÜHRUNG VON OBEN: Fuß steht auf einer (annähernd
        waagerechten) Fläche -> Kontaktnormale SENKRECHT (nz > G_DOWN_NZ). Geometrischer Kontakt;
        flackert bei fast lastfreien Füßen -> deshalb über _foot_touch_down entprellt konsumieren."""
        idx = self._foot_link_idx.get(leg.name, -1)
        if idx < 0:
            return False
        for c in self._contact_cache:
            if c[3] == idx and c[8] <= self.G_TOUCH_D and c[7][2] > self.G_DOWN_NZ:
                return True
        return False


    def _coxa_torque(self, leg):
        """|Coxa-Drehmoment| [Nm]. Die COXA macht den Vorschub (theta_c = atan2(y,x)) und ist
        dabei nahezu lastfrei (kein Beingewicht, nur Trägheit bei niedriger Geschw.) ->
        Baseline ~0.05 Nm. Stößt der Fuß im Vorholen an eine Stufenkante, steigt das Moment
        schlagartig (1.3-2.5 Nm gemessen) -> sauberes Blockade-Signal, IMMUN gegen vertikale
        Stöße (die laden Femur/Tibia, nicht die Coxa). Femur/Tibia tragen Gewicht -> als
        Blockade-Signal unbrauchbar (hohe Baseline)."""
        jid = self.joint_map.get(f"{leg.name}_coxa_joint")
        return abs(p.getJointState(self.robot_id, jid)[3]) if jid is not None else 0.0


    # ------------------------------------------------------------------ [SIM]
    def update_contact_display(self):
        """[SIM] Färbt jeden Fuß je Frame: GRÜN = Bodenkontakt, ROT = Luft.
        Nutzt den GEOMETRISCHEN Hysterese-Kontakt (_g_contact, basiert auf
        _foot_touch_down = Berührung mit senkrechter Normale), NICHT die rohe
        Normalkraft. Grund: bei 6 aufliegenden Beinen ist die Lastverteilung
        statisch unbestimmt - PyBullets Solver schiebt die Einzelkräfte
        frame-zu-frame um, einzelne Füße fallen kurz auf 0 N, ohne abzuheben.
        Kraft-basierte Färbung blinkt dadurch. Berührung ist stabil - und das
        ist genau, was der HW-Microswitch (TPU-Stempel) misst: gedrückt/nicht."""
        self._refresh_contact_cache()
        if not hasattr(self, '_contact_col'):
            self._contact_col = {}
        for leg in self.legs:
            idx = self._foot_link_idx.get(leg.name, -1)
            if idx < 0:
                continue
            if self._g_contact.get(leg.name, False):
                col = (0.0, 0.9, 0.0, 1.0)   # grün: Bodenkontakt (berührt)
            else:
                col = (0.9, 0.0, 0.0, 1.0)   # rot: Luft (Schwung)
            if self._contact_col.get(leg.name) != col:
                p.changeVisualShape(self.robot_id, idx, rgbaColor=list(col))
                self._contact_col[leg.name] = col

    def update_torque_display(self):
        """[SIM] Per-Servo-Drehmoment: ein Balken pro Bein am Fuß (Höhe ~ Last,
        Farbe = dominierender Servo-Typ Coxa=cyan/Femur=gelb/Tibia=magenta) plus
        zwei Textzeilen über dem Körper (WORST + max je Typ). Alle 8 Frames."""
        if not hasattr(self, '_torque_init'):
            self._torque_init = True; self._torque_frame = 0
            self._leg_servo_idx = {}
            for i in range(p.getNumJoints(self.robot_id)):
                nm = p.getJointInfo(self.robot_id, i)[1].decode('utf-8')
                if 'foot' in nm:
                    continue
                for leg in self.legs:
                    if nm.startswith(leg.name):
                        d = self._leg_servo_idx.setdefault(leg.name, {})
                        if   'coxa'  in nm: d['coxa']  = i
                        elif 'femur' in nm: d['femur'] = i
                        elif 'tibia' in nm: d['tibia'] = i
                        break
            self._bar_ids = {}; self._txt_id = None; self._txt2_id = None
            self._tau_lp = {}
        self._torque_frame += 1
        if self._torque_frame % 8 != 0:
            return
        TAU_MAX = SERVO_STALL_NM; WARN = 0.50; CRIT = 0.80
        TYPE_COL = {'coxa': [0.1, 0.8, 0.9], 'femur': [1.0, 0.8, 0.0],
                    'tibia': [0.9, 0.2, 0.9]}
        def col(r):
            return ([0.1, 0.9, 0.1] if r < WARN else
                    [1.0, 0.75, 0.0] if r < CRIT else [1.0, 0.1, 0.1])
        type_max = {'coxa': 0.0, 'femur': 0.0, 'tibia': 0.0}
        worst = 0.0; worst_type = ''; worst_leg = ''
        for leg in self.legs:
            servos = self._leg_servo_idx.get(leg.name, {})
            if not servos:
                continue
            leg_max = 0.0; leg_dom = 'femur'
            for typ, idx in servos.items():
                raw = abs(p.getJointState(self.robot_id, idx)[3]) / TAU_MAX
                key = (leg.name, typ); lp = self._tau_lp.get(key, raw)
                lp += (raw - lp) * 0.20; self._tau_lp[key] = lp
                r = min(lp, 1.0)
                if r > type_max[typ]: type_max[typ] = r
                if r > leg_max: leg_max = r; leg_dom = typ
                if r > worst: worst = r; worst_type = typ; worst_leg = leg.name
            fidx = self._foot_link_idx.get(leg.name, -1)
            if fidx < 0:
                continue
            fp = p.getLinkState(self.robot_id, fidx)[0]
            base = [fp[0], fp[1], fp[2] + 0.02]
            top  = [fp[0], fp[1], fp[2] + 0.08 + leg_max * 0.32]
            c = TYPE_COL[leg_dom]
            if leg.name in self._bar_ids:
                self._bar_ids[leg.name] = p.addUserDebugLine(base, top, lineColorRGB=c,
                    lineWidth=14, replaceItemUniqueId=self._bar_ids[leg.name])
            else:
                self._bar_ids[leg.name] = p.addUserDebugLine(base, top, lineColorRGB=c, lineWidth=14)
        pos, _ = p.getBasePositionAndOrientation(self.robot_id)
        line1 = f"WORST: {worst_type.upper()} {worst*100:.0f}%  [{worst_leg.replace('_',' ')}]"
        line2 = (f"max  Coxa {type_max['coxa']*100:.0f}% | Femur {type_max['femur']*100:.0f}% | "
                 f"Tibia {type_max['tibia']*100:.0f}%")
        c = col(worst)
        t1 = [pos[0], pos[1], pos[2] + 0.60]; t2 = [pos[0], pos[1], pos[2] + 0.50]
        if self._txt_id is not None:
            self._txt_id = p.addUserDebugText(line1, t1, textColorRGB=c, textSize=2.4,
                                              replaceItemUniqueId=self._txt_id)
        else:
            self._txt_id = p.addUserDebugText(line1, t1, textColorRGB=c, textSize=2.4)
        if self._txt2_id is not None:
            self._txt2_id = p.addUserDebugText(line2, t2, textColorRGB=[0.85,0.85,0.85],
                                               textSize=1.8, replaceItemUniqueId=self._txt2_id)
        else:
            self._txt2_id = p.addUserDebugText(line2, t2, textColorRGB=[0.85,0.85,0.85], textSize=1.8)


    def _read_body_attitude(self):
        """
        Liefert (roll, pitch) der Körperlage gegenüber der Schwerkraft [rad].
        SIM: aus der Basis-Orientierung. ESP32: hier IMU-Treiber einsetzen
        (MPU6050/BNO055 -> roll/pitch). Yaw wird für die Balance nicht benötigt.
        """
        if self.robot_id is None:
            return 0.0, 0.0
        _, orn = p.getBasePositionAndOrientation(self.robot_id)
        roll, pitch, _ = p.getEulerFromQuaternion(orn)
        return roll, pitch


    def _read_body_z(self):
        """Körperhöhe [m] (Welt-z der Basis). SIM: Basis-Position.
        ESP32: aus Odometrie/IMU-Höhe bzw. FK über die Standbeine. Für die
        WELT-referenzierte Körperhöhen-Regelung in Modus 7."""
        if self.robot_id is None:
            return 0.0
        pos, _ = p.getBasePositionAndOrientation(self.robot_id)
        return pos[2]


    def _read_body_yaw(self):
        """Körper-Gierwinkel [rad] (Kurs). SIM: aus der Basis-Orientierung.
        ESP32: IMU-Yaw (BNO055 liefert ihn fusioniert; MPU6050 per Magnetometer/
        Gyro-Integration). Nur für die Kurshaltung in Modus 7 nötig."""
        if self.robot_id is None:
            return 0.0
        _, orn = p.getBasePositionAndOrientation(self.robot_id)
        _, _, yaw = p.getEulerFromQuaternion(orn)
        return yaw

    def _body_to_world(self, fx, fy, fz):
        """[PERCEPTION] Punkt im Körper-Frame -> Welt. SIM: Basis-Transform.
        HW: aus der Roboter-Pose (visuelle Odometrie / IMU). Für Foothold-Planung."""
        if self.robot_id is None:
            return (fx, fy, fz)
        pos, orn = p.getBasePositionAndOrientation(self.robot_id)
        wp, _ = p.multiplyTransforms(pos, orn, (fx, fy, fz), (0, 0, 0, 1))
        return wp

    def _world_to_body(self, wx, wy, wz):
        """[PERCEPTION] Welt-Punkt -> Körper-Frame (Umkehrung von _body_to_world)."""
        if self.robot_id is None:
            return (wx, wy, wz)
        pos, orn = p.getBasePositionAndOrientation(self.robot_id)
        ipos, iorn = p.invertTransform(pos, orn)
        bp, _ = p.multiplyTransforms(ipos, iorn, (wx, wy, wz), (0, 0, 0, 1))
        return bp



    # ── [SIM] PyBullet-Welt + Roboter ──
    def init_pybullet(self, gui=True, build_stairs=True, spawn_can=True, spawn_x=0.0,
                      terrain='stairs', hills_n=6, hills_seed=0, hills_style='scatter',
                      hills_len=2.5, step_h=0.06):
        generate_hexapod_urdf("slarc_primitives.urdf")
        p.connect(p.GUI if gui else p.DIRECT)
        if gui:
            p.configureDebugVisualizer(p.COV_ENABLE_KEYBOARD_SHORTCUTS, 0)
        p.setAdditionalSearchPath(pybullet_data.getDataPath())
        p.setGravity(0, 0, -9.81)
        # Split Impulse: entkoppelt Penetrations-Korrektur (Position) von der
        # Geschwindigkeit -> der Fuß sinkt nicht in die Stufenkante ein und wird
        # NICHT im Folgeschritt herausgeschnellt (= der "Pop", Hauptquelle der
        # Mikrohüpfer). Etabliertes Mittel gegen LCP-Jitter bei Laufrobotern.
        p.setPhysicsEngineParameter(fixedTimeStep=1./240., numSolverIterations=150, numSubSteps=2,
                                    useSplitImpulse=1, splitImpulsePenetrationThreshold=-0.02)
        planeId = p.loadURDF("plane.urdf"); _set_contact(planeId)
        self.robot_id = p.loadURDF("slarc_primitives.urdf", [spawn_x, 0, 0.20])
        for i in range(p.getNumJoints(self.robot_id)):
            info = p.getJointInfo(self.robot_id, i)
            jn = info[1].decode('utf-8'); self.joint_map[jn] = i
            if "foot" in jn:
                _set_contact(self.robot_id, i, FOOT_FRICTION)
                self._foot_link_idx[jn.replace('_foot_joint','')] = i
        if spawn_can:
            col = p.createCollisionShape(p.GEOM_CYLINDER, radius=0.033, height=0.115)
            vis = p.createVisualShape(p.GEOM_CYLINDER, radius=0.033, length=0.115, rgbaColor=[0.8,0.1,0.1,1])
            self.can_id = p.createMultiBody(0.350, col, vis, basePosition=[0.37,0,0.06])
            p.changeDynamics(self.can_id, -1, lateralFriction=2.0, spinningFriction=0.1, rollingFriction=0.1)
        else:
            self.can_id = None
        if terrain == 'hills':
            print("\n  Erzeuge Hügelstrecke..."); create_hills(n=hills_n, seed=hills_seed,
                                                               style=hills_style, length=hills_len)
        elif terrain == 'step':
            print("\n  Erzeuge Einzelstufe..."); create_single_step(height=step_h)
        elif build_stairs and terrain == 'stairs':
            print("\n  Erzeuge Treppenkomplex..."); create_staircase()
        self.cameras = StereoCameras() if gui else None
        for _ in range(120): p.stepSimulation()
        for i in range(p.getNumJoints(self.robot_id)):
            p.changeDynamics(self.robot_id, i, jointDamping=0.05)
        for _ in range(120): self.update_gait(); p.stepSimulation()
        if gui: self.tuner.init_sliders()

    # ── [ESP32] Servo-Ausgabe ──
    def set_servo(self, joint_name, angle_rad):
        if joint_name in self.joint_map:
            p.setJointMotorControl2(self.robot_id, self.joint_map[joint_name],
                p.POSITION_CONTROL, targetPosition=angle_rad,
                force=SERVO_STALL_NM, maxVelocity=4.0, positionGain=SERVO_POS_GAIN, velocityGain=1.0)

    def _refresh_contact_cache(self):
        self._contact_cache = p.getContactPoints(bodyA=self.robot_id) or []
        self._contact_frame += 1
        # Kontakt-Latch pro Frame aktualisieren (Sim-Entprellung): schnell TRUE bei Erstkontakt
        # (für Swing-Lande-Erkennung), FALSE erst nach G_TD_RELEASE Frames echtem Verlust ->
        # kein Flackern bei fast lastfreien Füßen. µ-Switch-getreu: berührt = geschlossen.
        for leg in self.legs:
            if self._foot_touch_down_raw(leg):
                self._td_latch[leg.name] = True; self._td_air[leg.name] = 0
            else:
                self._td_air[leg.name] += 1
                if self._td_air[leg.name] >= self.G_TD_RELEASE:
                    self._td_latch[leg.name] = False

    # ── [ESP32] Körperframe-Fußziel -> Balancer-Rotation -> IK -> Servos ──
    def _set_leg(self, leg, fx, fy, fz):
        cidx = self.joint_map.get(f"{leg.name}_coxa_joint")
        if cidx is not None:
            js = p.getJointState(self.robot_id, cidx)
            pe_ = abs(self._cmd_coxa[leg.name] - js[0]); lf_ = abs(js[3]) / SERVO_STALL_NM
            if self._stall[leg.name].update(pe_, lf_): fz += self.RECOVER_LIFT
        pe = self._g_pitch_eff; re = self._g_roll_eff
        cy = math.cos(pe); sy = math.sin(pe); cx = math.cos(re); sx = math.sin(re)
        rx = fx*cy + fz*sy; rz = -fx*sy + fz*cy
        ry_new = fy*cx - rz*sx; rz_new = fy*sx + rz*cx
        dx = rx - leg.mount_x; dy = ry_new - leg.mount_y
        lx = dx*math.cos(-leg.mount_yaw) - dy*math.sin(-leg.mount_yaw)
        ly = dx*math.sin(-leg.mount_yaw) + dy*math.cos(-leg.mount_yaw)
        tc, tf, tt, _ok = self.ik.solve(lx, ly, rz_new)
        ov = self.tuner.get_override_angles(leg.name)
        if ov: tc, tf, tt = ov
        self.set_servo(f"{leg.name}_coxa_joint",  tc)
        self.set_servo(f"{leg.name}_femur_joint", tf)
        self.set_servo(f"{leg.name}_tibia_joint", tt)
        self._cmd_coxa[leg.name] = tc

    # ── [ESP32/PORTABLE] Kern-Helfer ──
    def _gait_neutral(self, leg, splay):
        lat = math.copysign(math.pi/2.0, leg.mount_y)
        yaw = leg.mount_yaw + (lat - leg.mount_yaw) * splay
        # [V10.13] Schmalere Stellung beim Klettern: Radius x Faktor -> kleinerer Horizontalabstand
        # -> mehr Vertikal-Reach (0.278->~0.30). Für die hinten zeigenden Hinterbeine holt das den
        # Fuß zugleich nach vorn (Richtung Stufe). Workspace-Clamp fängt Überstreckung ab.
        rad = self.G_RADIUS * (self.G_CLIMB_RADIUS_SCALE if getattr(self, '_g_climbing', False) else 1.0)
        nx = leg.mount_x + rad*math.cos(yaw)
        ny = leg.mount_y + rad*math.sin(yaw)
        # [climb] Bei Nase-hoch-Pitch Hinterbeine weiter nach hinten -> Stützbasis erhalten,
        # CoM bleibt im Stützpolygon. Workspace-Clamp fängt Überstreckung ab.
        # [V10.16] Beim Klettern: Hinterbein-Ziel nach VORN (Richtung Stufe), damit die Coxa vorschwenkt
        # statt nur zu heben. Die CoM-Wippe (V10.14) übernimmt die Stabilität, die vorher G_REAR_REACH
        # (Rückstellung) geben sollte. Ohne climbing: alte Rückstellung für die Stützbasis.
        if leg.mount_x < -1e-3:                          # nur Hinterbeine
            if getattr(self, '_g_climbing', False):
                nx += self.G_CLIMB_REAR_FWD              # Klettern: nach vorn Richtung Stufe
            else:
                nx -= self.G_REAR_REACH * max(0.0, -self._g_climb_pitch)
        return (nx, ny)

    def _leg_splay(self, leg, cfg):
        # Hinterbeine bekommen reduzierten Splay (splay_rear) -> mehr Stützweite nach hinten
        # statt seitlich. Vorne/Mitte behalten den Gait-Splay (Kantenkollision-Schutz).
        if leg.mount_x < -1e-3:
            return cfg.get('splay_rear', cfg['splay'])
        return cfg['splay']

    def _arc_z(self, ph, start_z, top, land):
        if ph <= 0.5:
            a = ph/0.5; a = a*a*(3-2*a); return start_z + (top-start_z)*a
        a = (ph-0.5)/0.5; a = a*a*(3-2*a); return top + (land-top)*a

    def _step_vector(self, nx, ny, vx, vy, om):
        # Schrittvektor (Körperframe): Translation in Bewegungsrichtung + Rotations-Tangente
        sx = self.G_STEP * vx + (-ny) * om * self.G_STEP * 4.0
        sy = self.G_STEP * vy + ( nx) * om * self.G_STEP * 4.0
        return sx, sy

    def _clamp_workspace(self, leg, tx, ty, z=None):
        # [ESP32] Bug-3-Fix: Fußziel auf erreichbaren XY-Radius vom Hüftgelenk begrenzen.
        #   Grenzen sind analytische Funktionen der Segmentlängen (kin.max/min_reach),
        #   skalieren also automatisch mit, wenn L_C/L_F/L_T geändert werden.
        if z is None: z = self.G_Z
        dx = tx - leg.mount_x; dy = ty - leg.mount_y
        r = math.hypot(dx, dy)
        r_max = self.ik.max_reach(z)
        r_min = self.ik.min_reach(z)
        if r > r_max: s = r_max/r; return leg.mount_x + dx*s, leg.mount_y + dy*s
        if 1e-6 < r < r_min: s = r_min/r; return leg.mount_x + dx*s, leg.mount_y + dy*s
        return tx, ty

    def _foot_plane_pitch(self):
        # [PI] Neigung der Fußebene aus FK (6 Present-Positions), kontaktgefiltert.
        front = ('front_right','front_left'); rear = ('rear_right','rear_left')
        def avg(group):
            pts = []
            for n in group:
                if not self._g_contact.get(n, False): continue
                idx = self._foot_link_idx.get(n, -1)
                if idx < 0: continue
                wp = p.getLinkState(self.robot_id, idx)[0]; pts.append((wp[0], wp[2]))
            if not pts: return None
            return (sum(x for x,_ in pts)/len(pts), sum(z for _,z in pts)/len(pts))
        fa, ra = avg(front), avg(rear)
        if fa is None or ra is None: return None
        dz = fa[1]-ra[1]
        if abs(dz) < self.G_STEP_DETECT: return None   # flach -> kein Pitch (Anti-Mitkopplung)
        dx = fa[0]-ra[0]
        if abs(dx) < 1e-4: return None
        return math.atan2(dz, dx)

    def estimate_pose(self):
        """[PI/PORTABLE] Schätzt die Körperpose pro Frame REIN aus IMU + Gelenkwinkeln
        (FK) + Kontakt - keine Sim-Welt-Koordinaten, 1:1 ESP32-fähig. Liefert:
          roll/pitch (IMU), yaw (integriert), height = Höhe über lokalem Boden via
          Leg-Odometry (vertikale Distanz Körper->Stance-Füße, pitch/roll-korrigiert),
          angles = 18 Servowinkel, feet = 6 Fußpunkte im Körper-Frame (aus FK).
        Zweck u.a. Perception-Entzerrung: Stufen-Normalen erscheinen im Körper-Frame
        um die Körperlage gekippt; mit roll/pitch lassen sie sich in die Welt drehen."""
        roll, pitch = self._read_body_attitude()          # IMU (ESP32: BNO055)
        yaw = self._read_body_yaw()                        # integriert
        angles = {}; feet = {}
        for leg in self.legs:
            tc = p.getJointState(self.robot_id, self.joint_map[f"{leg.name}_coxa_joint"])[0]
            tf = p.getJointState(self.robot_id, self.joint_map[f"{leg.name}_femur_joint"])[0]
            tt = p.getJointState(self.robot_id, self.joint_map[f"{leg.name}_tibia_joint"])[0]
            angles[leg.name] = (tc, tf, tt)
            lx, ly, lz = self.ik.forward(tc, tf, tt)       # Hüft-Frame (vor mount_yaw)
            cyaw = math.cos(leg.mount_yaw); syaw = math.sin(leg.mount_yaw)
            rx = leg.mount_x + lx*cyaw - ly*syaw           # -> Körper-Frame
            ry = leg.mount_y + lx*syaw + ly*cyaw
            feet[leg.name] = (rx, ry, lz)
        # Höhe über Boden: Fuß-z im Körper-Frame in die Welt-Vertikale drehen (roll/pitch),
        # Mittel über die tragenden Beine. Portierbar (nur FK + IMU + Kontakt-Flags).
        cp = math.cos(pitch); sp = math.sin(pitch); cr = math.cos(roll); sr = math.sin(roll)
        hs = []
        for n, (rx, ry, rz) in feet.items():
            if not self._g_contact.get(n, False):
                continue
            z_w = -rx*sp + ry*cp*sr + rz*cp*cr             # Welt-z-Anteil rel Körper
            hs.append(-z_w)
        height = sum(hs)/len(hs) if hs else float('nan')
        return {'roll': roll, 'pitch': pitch, 'yaw': yaw, 'height': height,
                'angles': angles, 'feet': feet}

    def _foothold(self, fx_body, fy_body, fz_body):
        # [PI] Plant den Aufsetzpunkt auf der nächsten Trittfläche.
        # Sim (Stufe A): Ground-Truth via StairModel. Pi (Stufe B): Perzeptions-Elevation-Map.
        # Input: gewünschtes Fußziel im Körper-Frame. Output: (tx, ty, land, valid) im Körper-Frame,
        # land = Trittflächenhöhe relativ Körper. valid=False -> keine Trittfläche (Riser/Kante).
        if self.stairs is None:
            return fx_body, fy_body, None, False
        wx, wy, wz = self._body_to_world(fx_body, fy_body, fz_body)   # volle Pose (inkl. Pitch)
        wx_safe, wz_tread, valid = self.stairs.foothold(wx)
        tx, ty, land = self._world_to_body(wx_safe, wy, wz_tread)     # korrigiertes Ziel zurück
        return tx, ty, land, valid

    def _update_progress(self):
        # [PI] Fortschritts-Monitor - diagnostiziert Festhängen OHNE absolute Höhe.
        # Vergleicht die TATSÄCHLICHE Körperbewegung (hier bx/bz aus der Sim; auf dem
        # Roboter: visuelle Odometrie / IMU) mit der vom Gait KOMMANDIERTEN Strecke.
        # Verhältnis-basiert -> skaliert mit der Gangart (placemove langsam ≠ stuck).
        # Setzt self.stuck -> Auslöser für Fail-and-Replan auf dem Pi.
        pos = p.getBasePositionAndOrientation(self.robot_id)[0]
        bx, bz = pos[0], pos[2]
        if not hasattr(self, '_prog_x0'):
            self._prog_x0 = bx; self._prog_z0 = bz; self._prog_t = 0
            self._prog_exp = 0.0; self._prog_lift = 0.0
        self._prog_t += 1
        self._prog_exp += getattr(self, '_cmd_adv', 0.0)          # erwartete Strecke (kommandiert)
        mh = max(self._g_step_h.values()) if self._g_step_h else 0.0
        self._prog_lift = max(self._prog_lift, mh)
        if self._prog_t >= self.G_PROG_WIN:
            moved = math.hypot(bx - self._prog_x0, bz - self._prog_z0)   # vor + hoch zählt beides
            lift_sat = self._prog_lift >= self.G_LIFT_MAX - 1e-4
            # stuck nur, wenn nennenswert kommandiert UND weniger als 30% davon erreicht
            if self._prog_exp > self.G_PROG_MIN and moved < 0.30 * self._prog_exp:
                self.stuck = True
                self.stuck_reason = 'Stufe zu hoch (Schritthöhe ausgereizt)' if lift_sat else 'Schlupf/kein Vortrieb'
            else:
                self.stuck = False; self.stuck_reason = ''
            self._prog_x0 = bx; self._prog_z0 = bz; self._prog_t = 0
            self._prog_exp = 0.0; self._prog_lift = 0.0
        if not hasattr(self, '_stuck_txt'): self._stuck_txt = None
        if self.stuck:
            tpos = [bx, pos[1], bz + 0.45]
            if self._stuck_txt is not None:
                self._stuck_txt = p.addUserDebugText('STUCK: ' + self.stuck_reason, tpos,
                    textColorRGB=[1,0.2,0.2], textSize=2.2, replaceItemUniqueId=self._stuck_txt)
            else:
                self._stuck_txt = p.addUserDebugText('STUCK: ' + self.stuck_reason, tpos,
                    textColorRGB=[1,0.2,0.2], textSize=2.2)
        elif self._stuck_txt is not None:
            p.removeUserDebugItem(self._stuck_txt); self._stuck_txt = None

        # FREEZE-Overlay (quasi-statischer Kontakt-Wächter aktiv)
        if not hasattr(self, '_freeze_txt'): self._freeze_txt = None
        if getattr(self, '_g_frozen', False) and not self.stuck:
            tpos = [bx, pos[1], bz + 0.40]
            if self._freeze_txt is not None:
                self._freeze_txt = p.addUserDebugText('FREEZE: Bodenkontakt suchen', tpos,
                    textColorRGB=[0.3,0.6,1.0], textSize=2.0, replaceItemUniqueId=self._freeze_txt)
            else:
                self._freeze_txt = p.addUserDebugText('FREEZE: Bodenkontakt suchen', tpos,
                    textColorRGB=[0.3,0.6,1.0], textSize=2.0)
        elif self._freeze_txt is not None:
            p.removeUserDebugItem(self._freeze_txt); self._freeze_txt = None

    def _advance_group(self, cfg):
        self._g_group = (self._g_group + 1) % len(cfg['groups'])
        self._g_phase = 0.0; self._g_sub = 'SWING'
        if self._g_group == 0:
            if not self._g_blocked_cycle:
                for n in self._g_step_h:
                    self._g_step_h[n] = max(self._g_step_h[n] - self.G_STEP_H_DN, self.G_LIFT)
            self._g_blocked_cycle = False
        legmap = {l.name: l for l in self.legs}
        for name in cfg['groups'][self._g_group]:
            self._g_landed[name] = False
            self._g_start[name] = list(self._g_foot[name])
            # [climb] Anti-Block-Schritthöhe von weiter vorn stehenden Beinen erben -
            # die haben dieselbe Stufe schon erklommen und kennen die nötige Höhe.
            lx = legmap[name].mount_x
            ahead = [self._g_step_h[l.name] for l in self.legs if l.mount_x > lx + 1e-3]
            if ahead:
                self._g_step_h[name] = max(self._g_step_h[name], max(ahead))

    def _enter_gait(self):
        cfg = self.GAITS[self.gait_name]
        self._g_climb_pitch = 0.0
        self._g_foot = {}; self._g_base_z = {}
        for leg in self.legs:
            nx, ny = self._gait_neutral(leg, self._leg_splay(leg, cfg))
            self._g_foot[leg.name] = [nx, ny, self.G_Z]
            self._g_base_z[leg.name] = self.G_Z
        self._g_group = 0; self._g_phase = 0.0; self._g_sub = 'SWING'; self._g_shifted = 0.0
        self._g_landed = {l.name: False for l in self.legs}
        self._g_start  = {l.name: list(self._g_foot[l.name]) for l in self.legs}
        self._g_step_h = {l.name: self.G_LIFT for l in self.legs}
        self._g_contact = {l.name: True for l in self.legs}
        self._hold_dz  = {l.name: 0.0 for l in self.legs}   # V9.2: R1-Zustand (StanceController) im Gait
        self._g_settled = {l.name: True for l in self.legs}  # V9.4: hatte das Bein seit dem Schwung Kontakt?
        self._g_com_fwd = 0.0; self._g_com_prev = 0.0        # V10.14: CoM-Wippe fore-aft-Offset
        self._g_air = {l.name: 0 for l in self.legs}
        self._g_offset = 0.0; self._g_climb_pitch = 0.0; self._g_blocked_cycle = False
        self._g_freeze_cnt = 0; self._g_frozen = False
        self._g_settle = 240
        self._g_pitch_eff = 0.0; self._g_roll_eff = 0.0
        _, orn = p.getBasePositionAndOrientation(self.robot_id)
        self._g_yaw_hold = p.getEulerFromQuaternion(orn)[2]
        self._g_ready = True
        print("[V8] Gait '%s' (%s, splay %.1f). Pfeile=Bewegung, Q/E=Drehen, W/S=Hoehe, 7=Schrittlaenge, 8=Gait."
              % (self.gait_name, cfg['advance'], cfg['splay']))

    # ════════════════════════════════════════════════════════════════════
    #  [ESP32] GAIT-KERN - ein Frame. Omnidirektional (vx,vy,omega).
    # ════════════════════════════════════════════════════════════════════
    def _step_gait(self):
        if not self._g_ready:
            self._enter_gait()
        self._refresh_contact_cache()
        cfg = self.GAITS[self.gait_name]
        legmap = {l.name: l for l in self.legs}

        # R2 (global) über den portablen Kern; Sollwert = Kletter-Pitch (flach 0). update_attitude
        # setzt _g_pitch_meas + _g_*_eff. Manuelle Pose-Offsets (self.pitch/roll) danach addieren.
        self.stance.update_attitude(pitch_sp=(0.0 if getattr(self, 'G_CLIMB_PITCH_OFF', False)
                                              else self._g_climb_pitch))   # R2; Isolation: Pitch-Folgen aus
        self._g_pitch_eff += self.pitch
        self._g_roll_eff  += self.roll

        # V9.2: R3 (StanceController) besitzt jetzt body_height_offset (Höhen-Halt, Sollwert |G_Z|).
        # Manuelle W/S-Höhe + Kletter-Hub kommen erst beim Klettern (V9.4) als separate Adds dazu;
        # flach sind beide 0, daher hier keine W/S-Rampe mehr.
        # Kletter-Anhebung rampen: nase-hoch (IMU) -> Rumpf steigt, damit die Vorderkante über
        # die nächste Stufe kommt. Gerampt wie die W/S-Höhe. Kontaktunabhängig (nur Pitch).
        _craise_tgt = self.G_CLIMB_RAISE if self._g_pitch_meas < -self.G_SLOPE_DEAD else 0.0
        self._g_climb_raise += _clamp(_craise_tgt - self._g_climb_raise, -self.G_BHO_RAMP, self.G_BHO_RAMP)

        # Settle (Eintritt): Füße auf feste Standhöhe, Körper sinkt durch Schwerkraft drauf
        if self._g_settle > 0:
            self._g_settle -= 1
            self._g_pitch_eff = 0.0; self._g_roll_eff = 0.0
            for leg in self.legs:
                f = self._g_foot[leg.name]
                f[2] = self.G_Z
                self._g_base_z[leg.name] = self.G_Z
                self._set_leg(leg, f[0], f[1], f[2])
            return

        # Kontakt-Hysterese
        for leg in self.legs:
            if self._foot_touch_down(leg):
                self._g_contact[leg.name] = True; self._g_air[leg.name] = 0
                self._g_settled[leg.name] = True         # V9.4: hat getragen -> ab jetzt zählt Verlust als echt
            else:
                self._g_air[leg.name] += 1
                if self._g_air[leg.name] >= self.G_AIR_FR:
                    self._g_contact[leg.name] = False

        # [PI] Pitch-Sollwert = Fußebenen-Neigung: der Körper soll PARALLEL zur Treppe
        # stehen (nase-hoch beim Steigen), nicht flach. Der Balancer stabilisiert dann noch
        # Roll und Störungen, kämpft aber nicht mehr gegen die natürliche Kletterpose — das
        # verkürzte sonst die Vorderbeine so stark, dass sie von der Stufe abhoben (Kontakt-
        # verlust) und die Hinterbeine dagegendrückten (Rückwärtshüpfen). Früher: mit Foothold
        # sp=0 (flach) erzwungen; das ist die eigentliche Ursache des Hüpfens gewesen.
        slope = self._foot_plane_pitch()
        on_stairs = slope is not None and abs(slope) > self.G_SLOPE_DEAD
        sp = -slope if on_stairs else 0.0
        self._g_climb_pitch += (sp - self._g_climb_pitch) * self.G_PITCH_LP
        self._g_climb_pitch = _clamp(self._g_climb_pitch, -self.G_PITCH_LIM, self.G_PITCH_LIM)
        # [V10.10] climbing ENTPRELLT: on_stairs (slope-basiert) flackerte 134x -> R3 fiel in den
        # flachen 6er-Median-Zweig (Bypass um den Paar-Anker). Nach dem letzten on_stairs=True noch
        # G_CLIMB_HOLD Frames als klettern halten -> kein Flicker, R3 bleibt im Kletter-Zweig.
        if on_stairs:
            self._g_climb_hold = self.G_CLIMB_HOLD
        elif self._g_climb_hold > 0:
            self._g_climb_hold -= 1
        climbing = on_stairs or self._g_climb_hold > 0   # entprellt

        # V9.2: P2 (Femur-Ziel-Höhenregler) entfällt - R3 (FK-Median über die Stützmenge) hält
        # die Höhe. _g_offset bleibt 0 (nur noch als neutraler Term in der Swing-Landehöhe).

        vx, vy, om = self.cmd_vel_x, self.cmd_vel_y, self.cmd_yaw
        moving = (abs(vx) > 1e-4 or abs(vy) > 1e-4 or abs(om) > 1e-4)
        grp = cfg['groups'][self._g_group]
        swing_set = set(grp) if (moving and self._g_sub == 'SWING') else set()
        for n in swing_set:
            self._g_settled[n] = False               # V9.4: in der Luft -> baut Erstkontakt neu auf
        body_adv = 0.0

        # [PI] FREEZE-INTERRUPT (quasi-statisch). Ein tragendes Bein (alles außer
        # aktivem Schwungbein) hat den GEOMETRISCHEN Kontakt verloren -> gesamte
        # Bewegung anhalten (Phase, Vortrieb UND Schwung), bis alle tragenden Beine
        # den Boden wiederfinden. Bricht die Aufschaukelung abheben->Schwingung->abheben.
        # NUR bei placemove (quasi-statisch, 5 tragen/1 schwingt). Beim dynamischen
        # Tripod/Ripple ist kurzes Abheben normal -> dort AUS, sonst Dauer-Freeze.
        # HW: µ-Switch-Flankeninterrupt (MCP23017) liefert exakt dieses Signal.
        quasi_static = (cfg['advance'] == 'when_planted')
        stance_now = [l.name for l in self.legs
                      if not (l.name in swing_set and not self._g_landed[l.name])]
        stance_lost = [n for n in stance_now if self._g_settled[n] and not self._g_contact[n]]
        self._g_stance_lost_n = len(stance_lost)              # [Diag] SETTLED Stützbeine ohne Kontakt
        # V9.4.1: Freeze ist ein KLETTER-Feature (bricht das Aufschaukeln an einer Stufe). Auf
        # flachem Boden hat er nichts zu suchen -> nur bei erkannter Steigung (climbing). Sonst
        # feuerte er auf flach spurios und löste den Seek/R3-Ratschet aus.
        if self.G_FREEZE_ENABLE and quasi_static and moving and climbing and stance_lost:
            self._g_freeze_cnt += 1
        else:
            self._g_freeze_cnt = 0
        self._g_frozen = self._g_freeze_cnt > self.G_FREEZE_DEB
        if self._g_freeze_cnt > self.G_FREEZE_TIMEOUT:   # findet keinen Boden -> Replanner-Andockpunkt
            self.stuck = True
            self.stuck_reason = 'Stance-Bein findet keinen Boden (Freeze-Timeout)'
        frozen = self._g_frozen

        # SCHWUNG der aktiven Gruppe
        if moving and self._g_sub == 'SWING':
            if not frozen:                                  # FREEZE: Phase hält -> Schwungbein steht still
                self._g_phase = min(1.0, self._g_phase + self.G_PHASE_V)
            ph = self._g_phase; all_done = True
            for name in grp:
                leg = legmap[name]; f = self._g_foot[name]
                if self._g_landed[name]: continue
                nx, ny = self._gait_neutral(leg, self._leg_splay(leg, cfg))
                ox, oy = self._step_vector(nx, ny, vx, vy, om)
                land = _clamp(self._g_base_z[name] + self._g_offset - self.body_height_offset
                              - self._g_climb_raise, self.G_Z_FLOOR, -0.10)
                tgt_x, tgt_y = nx + ox, ny + oy
                # Foothold-Planung: Schwung-Ziel auf nächste Trittfläche legen (statt blind nach vorn)
                if self.G_FOOTHOLD and cfg['advance'] == 'when_planted':
                    ftx, fty, fland, fvalid = self._foothold(tgt_x, tgt_y, land)
                    if fvalid and fland is not None:
                        tgt_x, tgt_y = ftx, fty
                        land = _clamp(fland, self.G_Z_FLOOR, 0.10)    # Trittfläche rel Körper; +: Hochgreifen erlaubt
                tx, ty = self._clamp_workspace(leg, tgt_x, tgt_y, land)
                sx, sy, sz = self._g_start[name]
                if (self.G_BLOCK_ENABLE and ph > 0.15 and not self._foot_touch_down(leg)
                        and self._coxa_torque(leg) > self.G_BLOCK_C):
                    self._g_step_h[name] = min(self._g_step_h[name] + self.G_STEP_H_UP, self.G_LIFT_MAX)
                    self._g_phase = 0.0; ph = 0.0          # Schwung komplett abbrechen, vom Start höher neu
                    self._g_blocked_cycle = True
                top  = land + self._g_step_h[name]
                # KLETTER-HUB an IMU-PITCH gekoppelt, NICHT an on_stairs (das braucht tragende
                # Beine vorne+hinten, die beim Klettern fehlen -> Henne-Ei). Der Pitch ist immer
                # verfügbar (BNO055), unabhängig vom Kontakt. Nase-hoch (pitch < -Totband) = am
                # Steigen -> Welt-Hub. tx*tan(pitch) hebt Hinterbeine (tx<0) höher, Vorderbeine
                # niedriger, sodass der Fuß in der WELT G_CLIMB_LIFT über der Hüftebene erreicht.
                if self._g_pitch_meas < -self.G_SLOPE_DEAD:
                    world_lift = self.G_CLIMB_LIFT + tx * math.tan(self._g_pitch_meas)
                    top = max(top, world_lift)
                # LIFT->REACH->PLANT: erst senkrecht heben, dann vorschwingen, dann absetzen.
                # Entkoppelt x von z -> Fuß ist beim Erreichen der Stufe schon auf voller Höhe,
                # statt diagonal hineinzulaufen. Kritisch für hohe/nahe Stufen.
                if ph < 0.30:                                   # LIFT: x hält hinten, z hoch
                    a = ph/0.30; a = a*a*(3.0-2.0*a)
                    f[0] = sx; f[1] = sy; f[2] = sz + (top-sz)*a
                elif ph < 0.70:                                 # REACH: vorschwingen auf top-Höhe
                    a = (ph-0.30)/0.40; a = a*a*(3.0-2.0*a)
                    f[0] = sx + (tx-sx)*a; f[1] = sy + (ty-sy)*a; f[2] = top
                else:                                           # PLANT: absenken aufs Ziel
                    a = (ph-0.70)/0.30; a = a*a*(3.0-2.0*a)
                    z_plan = top + (land-top)*a
                    # KONTAKT-STOPP (µ-Switch): meldet der Fußschalter beim Absenken Boden,
                    # NICHT weiter Richtung land drücken. Sonst presst der Fuß gegen eine früh
                    # erreichte (höhere) Stufe und hebt den Körper -> Rückwärtshüpfen. Höhe auf
                    # dem Kontaktpunkt halten. Portabel: reiner µ-Switch-Flankentrigger.
                    if self._foot_touch_down(leg) and z_plan < f[2]:
                        z_plan = f[2]
                    f[0] = tx; f[1] = ty; f[2] = z_plan
                if ph >= self.G_LAND_PH and (self._foot_force(leg) > self.G_LAND_F
                                             or self._foot_touch_down(leg)):
                    self._g_landed[name] = True
                    self._g_base_z[name] = f[2] + self.body_height_offset + self._g_climb_raise - self._g_offset
                self._set_leg(leg, f[0], f[1], f[2])
                if not self._g_landed[name]: all_done = False
            if not frozen and (all_done or self._g_phase >= 1.0):
                if cfg['advance'] == 'when_planted':
                    self._g_sub = 'SHIFT'; self._g_shifted = 0.0
                else:
                    self._advance_group(cfg)
        elif moving and self._g_sub == 'SHIFT':
            if not frozen:                                  # FREEZE: Vortrieb-Shift hält an
                shift_tgt = self.G_STEP / 3.0
                self._g_shifted += 2.0 * self.G_STEP * self.G_PHASE_V / max(1, len(cfg['groups']) - 1)
                body_adv = 1.0
                if self._g_shifted >= shift_tgt:
                    self._advance_group(cfg)

        if cfg['advance'] == 'continuous' and moving and not frozen:
            body_adv = 1.0

        # Stance-Beine: omnidirektionaler Körpervortrieb (Translation + Rotation) + Höhe
        pe = self._g_pitch_eff
        body_v = 2.0 * self.G_STEP * self.G_PHASE_V   # Vortrieb an Schrittlänge gekoppelt -> Fuß pendelt ±G_STEP um Neutral
        gait_speed = 1.0 / max(1, len(cfg['groups']) - 1)   # Stance-Wanderung über Gaits konstant
        adv_fwd = body_adv * body_v * gait_speed * vx
        dxb = adv_fwd * (math.cos(pe) if climbing else 1.0)
        dzb = adv_fwd * math.sin(pe) if climbing else 0.0
        dyb = body_adv * body_v * gait_speed * vy
        # ---- EINSTIEGS-BOOST (Option A): Schwerpunkt aktiv über die Kante ----
        # Tragende Vorderbeine deutlich höher als tragende Hinterbeine -> Rumpf steht mit
        # den Vorderbeinen auf der Stufe. Dann Körper zusätzlich nach vorn (dxb) UND aktiv
        # anheben (dzb), skaliert mit der gemessenen Stufenhöhe. Rein aus Soll-Fußhöhen im
        # Körper-Frame + µ-Switch - ESP32-portabel, keine Weltkoordinaten.
        self._g_entry = 0.0
        if self.G_ENTRY_BOOST and climbing and moving and abs(vx) > 1e-4 and not frozen:
            fz = [self._g_foot[l.name][2] for l in self.legs
                  if l.name.startswith('front') and self._g_contact[l.name]]
            rz = [self._g_foot[l.name][2] for l in self.legs
                  if l.name.startswith('rear') and self._g_contact[l.name]]
            if fz and rz:
                dz_step = sum(fz)/len(fz) - sum(rz)/len(rz)      # >0: Vorderbeine höher
                if dz_step > self.G_ENTRY_THRESH:
                    frac = _clamp(dz_step / self.G_ENTRY_STEP_REF, 0.0, 1.0)
                    extra = body_v * gait_speed * frac
                    # REINER VORWÄRTSSCHUB: an der Kante fehlt placemove der Schwung, den
                    # Tripod ballistisch mitbringt (dort vx~0.8 m/s über die Kante, hier ~0).
                    # Wir schieben den Schwerpunkt statisch nach VORN — kein Anheben (dzb),
                    # das nur die Vorderbeine von der Stufe löst. Portabel: FK-Höhe + µ-Switch.
                    dxb += self.G_ENTRY_DX * extra * (1.0 if vx > 0 else -1.0)
                    self._g_entry = frac
        # ---- VORTRIEBS-BREMSE: dxb drosseln, sobald ein tragendes Bein HINTER seiner Hüfte
        # die Reichweite ausreizt. Bricht den Teufelskreis "Rumpf fährt vor -> Hinterbein
        # überdehnt sich -> hängt am Anschlag/Riser". Der Rumpf hält, das Bein zieht in den
        # Arbeitsraum nach, dann geht es weiter. Universell (kein Stufen-Sonderfall), gilt auch
        # eben. Portabel: Reichweite aus Fußziel (Körper-Frame, FK) + analytische max_reach.
        self._g_brake = 1.0
        if dxb > 1e-6:                                       # nur Vorwärts-Vortrieb bremsen
            min_res = 999.0
            for l in self.legs:
                if l.name in swing_set and not self._g_landed[l.name]:
                    continue                                # nur tragende Beine
                ff = self._g_foot[l.name]
                ddx = ff[0] - l.mount_x
                if ddx >= 0.0:
                    continue                                # Fuß vor der Hüfte -> Vortrieb entlastet ihn
                r = math.hypot(ddx, ff[1] - l.mount_y)
                min_res = min(min_res, self.ik.max_reach(ff[2]) - r)
            if min_res < self.G_BRAKE_BAND:
                self._g_brake = _clamp(min_res / self.G_BRAKE_BAND, 0.0, 1.0)
                dxb *= self._g_brake
        self._cmd_adv = math.hypot(dxb, dyb) + abs(dzb)   # kommandierte Strecke/Frame (für Stuck-Monitor)
        self._g_dxb = dxb                                 # [V9.2-Diag] Vorwärts-Schritt (nach Bremse) fürs Log
        yaw_now = self._read_body_yaw()
        if frozen:                                          # FREEZE: auch Heading-Korrektur ruht
            dyaw = 0.0
        elif abs(om) > 1e-4:
            self._g_yaw_hold = yaw_now; dyaw = body_adv * om * self.G_YAW_V * gait_speed
        else:
            yerr = math.atan2(math.sin(yaw_now-self._g_yaw_hold), math.cos(yaw_now-self._g_yaw_hold))
            dyaw = _clamp(-self.G_HEAD_KP*yerr, -self.G_YAW_MAX, self.G_YAW_MAX)
        cz = math.cos(-dyaw); sz2 = math.sin(-dyaw); yawing = abs(dyaw) > 1e-6
        # V9.3: Stance-HÖHE global über R3 (FK-Median -> body_height_offset), Lage über R2
        # (update_attitude). Die per-Bein Stance-z bleibt aber die geplante TRITTPUNKT-Höhe
        # (_g_base_z + Sweep, bewährter V8-Weg) - NICHT R1s Seek: im Gait stellt der SCHWUNG
        # den Kontakt her, nicht R1. R1/command_leg ist Hold-only. Der Recovery-Seek für ein
        # ECHT (debounced _g_contact) verlorenes Stance-Bein bleibt, läuft aber NICHT auf rohem
        # µ-Switch -> kurzes dynamisches Flackern ratscht die Beine nicht mehr länger.
        stance = [l.name for l in self.legs
                  if not (l.name in swing_set and not self._g_landed[l.name])]   # tragende Menge (post-Swing)
        self._g_climbing = climbing                          # R3-Modus: flach=Median, Klettern=Paar-Anker
        self._g_swing_set = swing_set                        # für Paar-Anker: Schwungbeine ausschließen
        self.stance.proj_height(stance)                      # setzt _g_h_low/_g_h_proj/_g_r3_n
        if not (getattr(self, 'G_FREEZE_CLIMB_H', False) and climbing):
            self.stance.update_height(stance)                # R3 (flach Median, Klettern Paar-Anker)
        # [Isolation] --freeze-climb-height: bho beim Klettern halten -> zeigt, ob der Bounce aus
        # R3 (dann weg) oder aus Gait/Aufsetzen (dann bleibt) kommt.
        seek_v = self.G_SEEK_V_FREEZE if frozen else self.G_SEEK_V
        # [V10.14] CoM-Wippe beim Klettern: Rumpf fore-aft WEG vom Bein der aktuellen Gruppe
        # (entlastet es vor dem Schwung). Hinterbein-Gruppe -> CoM VOR (Rumpf über Vorder+Mitte,
        # Hinterbeine frei zum Nachziehen); Vorderbein-Gruppe -> CoM ZURÜCK (Vorderbeine frei zum
        # Vorgreifen). Mitte -> neutral. Gerampt, als gleichmäßiger fore-aft-Offset aller Stützfüße.
        com_tgt = 0.0
        if climbing and moving:
            mx = sum(self._legmap[n].mount_x for n in grp) / len(grp)
            if mx < -1e-3:   com_tgt =  self.G_COM_SHIFT      # Hinterbein schwingt -> CoM vor
            elif mx > 1e-3:  com_tgt = -self.G_COM_SHIFT      # Vorderbein schwingt -> CoM zurück
        self._g_com_fwd += _clamp(com_tgt - self._g_com_fwd, -self.G_COM_RAMP, self.G_COM_RAMP)
        d_com = self._g_com_fwd - self._g_com_prev            # Frame-Delta (einmalige Verschiebung)
        self._g_com_prev = self._g_com_fwd
        for leg in self.legs:
            if leg.name in swing_set and not self._g_landed[leg.name]: continue
            f = self._g_foot[leg.name]
            f[0] -= dxb + d_com; f[1] -= dyb                  # xy-Sweep + CoM-Wippe (fore-aft)
            self._g_base_z[leg.name] += dzb
            if yawing:
                f[0], f[1] = f[0]*cz - f[1]*sz2, f[0]*sz2 + f[1]*cz
            if not self._g_contact[leg.name] and (climbing or self.body_height_offset > -self.G_SEEK_BHO_DB):
                # Seek-Gate gilt nur flach (Anti-Windup). Beim Klettern IMMER nachsenken dürfen -
                # sonst blockiert der gegated Seek (bho am Clamp) die Stufen-Recovery -> Dauer-Freeze.
                self._g_base_z[leg.name] -= dzb               # Anheben zurücknehmen
                self._g_base_z[leg.name] = max(self._g_base_z[leg.name] - seek_v, self.G_Z - 0.13)
            f[2] = _clamp(self._g_base_z[leg.name] - self.body_height_offset - self._g_climb_raise,
                          self.G_Z_FLOOR, -0.10)              # R3-Offset global, Trittpunkt per Bein
            f[0], f[1] = self._clamp_workspace(leg, f[0], f[1], f[2])
            self._set_leg(leg, f[0], f[1], f[2])

        # Bein-Zustand fürs Logging
        self._g_state = {l.name: ('SWING' if (l.name in swing_set and not self._g_landed[l.name])
                                  else ('SHIFT' if self._g_sub == 'SHIFT' else 'STANCE'))
                         for l in self.legs}

        # Re-Zentrierung (Anti-Drift der per-Bein Trittpunkt-Höhen; der eigentliche Gait-Stabilisator).
        bzs = [self._g_base_z[l.name] for l in self.legs if self._g_contact[l.name]]
        if bzs:
            dev = sum(bzs)/len(bzs) - self.G_Z
            if abs(dev) > self.G_RECENT_DEAD:
                corr = (dev - math.copysign(self.G_RECENT_DEAD, dev)) * self.G_RECENT_GAIN
                for l in self.legs:
                    if self._g_contact[l.name]: self._g_base_z[l.name] -= corr

    def start_hold(self):
        """Halte-Modus initialisieren: pro-Bein z-Korrektur auf 0."""
        self._hold_dz = {l.name: 0.0 for l in self.legs}
        self._g_contact = {l.name: False for l in self.legs}  # Kontakt-Flag (Anzeige/Logger):
                                                              # erst messen, dann grün -> kein Stale-True

    def hold_update(self):
        """[HALTE-MODUS] V9.1: reiner Stand über den StanceController, Stützmenge = alle 6 Beine.
        Delegiert 1:1 an den portablen Kern (R2 Attitude, R3 Höhe, R1 pro Bein) und reproduziert
        damit das bekannte gute Hold-Verhalten -> Regression für die neue Engine.
        xy-Sollpose = neutrale Spider-Standpose. Alles portabel: µ-Switch + IMU + FK."""
        self._refresh_contact_cache()
        self.stance.update_attitude(pitch_sp=0.0)                 # R2 (global)
        stance = [l.name for l in self.legs]                     # Stand: volle 6er-Stützmenge
        self.stance.proj_height(stance)                          # projizierte vertikale Höhe (R3-Messung)
        over = self.stance.update_height(stance)                  # R3 -> body_height_offset, over_height
        for leg in self.legs:                                     # R1 pro Bein + IK
            nx, ny = self._gait_neutral(leg, self.G_HOLD_SPLAY)
            self.stance.command_leg(leg.name, nx, ny, over)

    def spawn_bump(self, leg_name, height, size=0.05, ramp_frames=0, osc_amp=0.0, osc_period=0):
        """[TEST] Erhebung (Block) unter einen Fuß setzen -> Störung für den Halte-Regler.
        ramp_frames>0: Block wächst über so viele Frames aus dem Boden (sanfte Störung).
        osc_amp>0: nach der Rampe schwingt die Oberkante ±osc_amp um 'height' mit Periode
        osc_period [Frames] (rein nach oben, wenn height>=osc_amp). Block ist ein vergrabener
        Pfeiler -> Unterkante bleibt immer unter dem Boden, nur die Oberkante stört den Fuß.
        Nur Test-Werkzeug (Weltkoordinaten, nicht Teil der Regelung)."""
        idx = self._foot_link_idx.get(leg_name, -1)
        if idx < 0:
            print("  [BUMP] Bein %s unbekannt" % leg_name); return None
        fp = p.getLinkState(self.robot_id, idx)[0]
        box_h = height + max(0.0, osc_amp) + 0.05    # Pfeiler: Unterkante bleibt vergraben
        h2 = box_h/2.0; s2 = size/2.0
        col = p.createCollisionShape(p.GEOM_BOX, halfExtents=[s2, s2, h2])
        vis = p.createVisualShape(p.GEOM_BOX, halfExtents=[s2, s2, h2], rgbaColor=[1,0.5,0,1])
        top0 = 0.0 if ramp_frames > 0 else height    # Oberkante bei Start
        bid = p.createMultiBody(0, col, vis, basePosition=[fp[0], fp[1], top0 - h2])
        p.changeDynamics(bid, -1, lateralFriction=GROUND_FRICTION)
        self._bump_id = bid; self._bump_xy = [fp[0], fp[1]]; self._bump_h = height
        self._bump_h2 = h2; self._bump_ramp = ramp_frames; self._bump_i = 0
        self._bump_osc_amp = max(0.0, osc_amp); self._bump_osc_period = max(0, int(osc_period))
        print("  [BUMP] +%.0fmm unter %s%s%s" % (height*1000, leg_name,
              (" (Rampe %d)" % ramp_frames) if ramp_frames > 0 else "",
              (" +Osz +/-%.0fmm/%dF" % (osc_amp*1000, osc_period)) if osc_amp > 0 else ""))
        return bid

    def ramp_bump(self):
        """Einzel-Bump pro Frame nachführen: Rampe 0->height, danach optionale Oszillation."""
        if getattr(self, '_bump_id', None) is None: return
        self._bump_i += 1
        i = self._bump_i
        if self._bump_ramp > 0 and i < self._bump_ramp:
            top = (i / self._bump_ramp) * self._bump_h
        elif self._bump_osc_amp > 0.0 and self._bump_osc_period > 0:
            ph = 2.0*math.pi*(i - self._bump_ramp) / self._bump_osc_period
            top = self._bump_h + self._bump_osc_amp*math.sin(ph)
        else:
            top = self._bump_h
        p.resetBasePositionAndOrientation(
            self._bump_id, [self._bump_xy[0], self._bump_xy[1], top - self._bump_h2], [0,0,0,1])

    def spawn_random_bumps(self, amp_max, period_nom, seed=0, ramp_frames=240):
        """[TEST] Unter JEDEM Fuß einen oszillierenden Bumper mit zufälliger Amplitude/Periode/
        Phase (reproduzierbar via seed). amp in [0.4,1.0]*amp_max, Periode in [0.66,1.33]*
        period_nom, Phase in [0,2pi). Oberkante schwingt 0..amp (nie unter Boden). ramp_frames>0:
        Amplituden-Einhüllende wächst 0->1 über so viele Frames -> kein Sprung beim Spawn (sonst
        wirft die Zufallsphase den Fuß weg). Nur Test-Werkzeug (Weltkoords, nicht Teil der Regelung)."""
        import random as _rnd
        rng = _rnd.Random(seed)
        self._rand_bumps = []; self._rand_i = 0; self._rand_ramp = max(0, int(ramp_frames))
        for leg in self.legs:
            idx = self._foot_link_idx.get(leg.name, -1)
            if idx < 0: continue
            fp = p.getLinkState(self.robot_id, idx)[0]
            amp = rng.uniform(0.4, 1.0) * amp_max
            period = max(1.0, rng.uniform(0.66, 1.33) * period_nom)
            phase = rng.uniform(0.0, 2.0*math.pi)
            box_h = amp + 0.05; h2 = box_h/2.0; s2 = 0.05/2.0
            col = p.createCollisionShape(p.GEOM_BOX, halfExtents=[s2, s2, h2])
            vis = p.createVisualShape(p.GEOM_BOX, halfExtents=[s2, s2, h2], rgbaColor=[1,0.5,0,1])
            bid = p.createMultiBody(0, col, vis, basePosition=[fp[0], fp[1], -h2])  # Oberkante 0
            p.changeDynamics(bid, -1, lateralFriction=GROUND_FRICTION)
            self._rand_bumps.append({'id': bid, 'xy': [fp[0], fp[1]], 'amp': amp,
                                     'period': period, 'phase': phase, 'h2': h2})
        print("  [BUMP] %d Zufalls-Bumper (amp<=%.0fmm, T~%dF, Rampe %dF, seed=%d)"
              % (len(self._rand_bumps), amp_max*1000, int(period_nom), self._rand_ramp, seed))

    def update_bumps(self):
        """Zufalls-Bumper pro Frame nachführen (falls aktiv). Oberkante = env*amp*(1+sin)/2,
        env = Einhüllende 0..1 (Spawn-Rampe) -> Start bei 0, egal welche Phase."""
        rb = getattr(self, '_rand_bumps', None)
        if not rb: return
        self._rand_i += 1
        env = min(1.0, self._rand_i / self._rand_ramp) if self._rand_ramp > 0 else 1.0
        for b in rb:
            top = env * 0.5*b['amp']*(1.0 + math.sin(2.0*math.pi*self._rand_i/b['period'] + b['phase']))
            p.resetBasePositionAndOrientation(
                b['id'], [b['xy'][0], b['xy'][1], top - b['h2']], [0,0,0,1])

    def update_gait(self):
        self._step_gait()

    # ── [SIM] Tastatur ──
    def process_keyboard(self):
        keys = p.getKeyboardEvents()
        self.cmd_vel_x = 0.0; self.cmd_vel_y = 0.0; self.cmd_yaw = 0.0
        up, dn, lf, rt = p.B3G_UP_ARROW, p.B3G_DOWN_ARROW, p.B3G_LEFT_ARROW, p.B3G_RIGHT_ARROW
        def held(k): return k in keys and (keys[k] & p.KEY_IS_DOWN)
        if held(up): self.cmd_vel_x =  1.0
        if held(dn): self.cmd_vel_x = -1.0
        if held(lf): self.cmd_vel_y =  1.0
        if held(rt): self.cmd_vel_y = -1.0
        for key, st in keys.items():
            down = bool(st & p.KEY_IS_DOWN)
            trig = bool(st & p.KEY_WAS_TRIGGERED)
            if down:                                  # gehaltene Tasten
                if key == ord('q'): self.cmd_yaw =  1.0
                if key == ord('e'): self.cmd_yaw = -1.0
                if key == ord('w'): self._bho_target = min(self._bho_target + self.G_BHO_RAMP, self.BHO_MAX)
                if key == ord('s'): self._bho_target = max(self._bho_target - self.G_BHO_RAMP, self.BHO_MIN)
            if trig:                                  # einmalig getriggert
                if key == ord('7'):
                    opts = self.G_STEP_OPTS
                    self.G_STEP = min((o for o in opts if o > self.G_STEP + 1e-6), default=opts[0])
                    print("Schrittlaenge: %.0f cm" % (self.G_STEP*100))
                if key == ord('8'):
                    names = list(self.GAITS.keys())
                    self.gait_name = names[(names.index(self.gait_name)+1) % len(names)]
                    self._g_ready = False
                    for g in self._stall.values(): g.reset()
                if key == ord('b'):
                    self.auto_balance = not self.auto_balance
                    print("Auto-Balance:", "AN" if self.auto_balance else "AUS")
                if key == ord('f'):
                    self.G_FOOTHOLD = not self.G_FOOTHOLD
                    print("Foothold-Planung:", "AN" if self.G_FOOTHOLD else "AUS")
                if key == ord('k'):
                    self.G_FREEZE_ENABLE = not self.G_FREEZE_ENABLE
                    print("Freeze-Interrupt:", "AN" if self.G_FREEZE_ENABLE else "AUS")
                if key == ord('z'):
                    self.G_ENTRY_BOOST = not self.G_ENTRY_BOOST
                    print("Einstiegs-Boost:", "AN" if self.G_ENTRY_BOOST else "AUS")
                if key == ord('v'):
                    self.logger.toggle()
                if key == ord('r'):
                    self.pitch = 0.0; self.roll = 0.0; self._bho_target = 0.0
                    self.balance.reset(); self.roll_bal = 0.0; self.pitch_bal = 0.0
                    self._g_ready = False

    def set_gait_from_perception(self, seg_dominant, normal_variance):
        # [PI] Perception -> Gait-Wahl (Stub, wie V7)
        FLOOR=0; STEP=1; TERRAIN=5
        if seg_dominant == FLOOR: self.gait_name = 'tripod'
        elif seg_dominant == STEP: self.gait_name = 'placemove'
        elif seg_dominant == TERRAIN and normal_variance < 0.08: self.gait_name = 'ripple'
        else: self.gait_name = 'placemove'


def main():
    import argparse
    global STAIR_RISE, STAIR_RUN, STAIR_X
    ap = argparse.ArgumentParser(description="SLARC V8 - omnidirektionaler Gait-Kern")
    ap.add_argument('--no-gui',    action='store_true', help="headless (ohne GUI-Fenster)")
    ap.add_argument('--no-stairs', action='store_true', help="ohne Treppenkomplex")
    ap.add_argument('--can',       action='store_true', help="Dose auf den Rücken setzen")
    ap.add_argument('--rise', type=float, default=0.10,  help="Stufenhöhe [m] (Default 0.10)")
    ap.add_argument('--run',  type=float, default=0.250, help="Stufentiefe [m] (Default 0.250)")
    ap.add_argument('--stair-x', type=float, default=0.60, help="x-Start der Treppe [m] (näher = kürzere Anlaufzeit)")
    ap.add_argument('--start-x', type=float, default=0.0,
                    help="Spawn-x [m]: Roboter näher an die Treppe (x=1.0) setzen, z.B. 0.7")
    # --- Isolations-/Testmodus ---
    ap.add_argument('--no-balance',  action='store_true', help="Balancer aus")
    ap.add_argument('--no-foothold', action='store_true', help="Foothold-Planung aus")
    ap.add_argument('--no-freeze',   action='store_true', help="Freeze-Interrupt aus")
    ap.add_argument('--climb-pitch-off', action='store_true', help="[Isolation] Pitch-Folgen beim Klettern aus (R2 flach)")
    ap.add_argument('--freeze-climb-height', action='store_true', help="[Isolation] R3-Höhe beim Klettern einfrieren (bho halten)")
    ap.add_argument('--no-entry',    action='store_true', help="Einstiegs-Boost aus")
    ap.add_argument('--gait', choices=['tripod','ripple','placemove'], default=None,
                    help="Gangart fest vorgeben (überschreibt Default tripod)")
    ap.add_argument('--auto', type=int, default=0,
                    help="Auto-Fahrmodus: so viele Frames geradeaus fahren, dann beenden (0=manuell)")
    # --- Halte-Modus (isolierter Stand-Regeltest, kein Gait) ---
    ap.add_argument('--hold', type=int, default=0,
                    help="Halte-Modus: so viele Frames stehen (nur Kontaktregler), dann beenden")
    ap.add_argument('--bump-at', type=int, default=0, help="Bei diesem Frame Erhebung spawnen")
    ap.add_argument('--bump-leg', default='front_right', help="Bein für die Erhebung")
    ap.add_argument('--bump-h', type=float, default=0.03, help="Höhe der Erhebung [m]")
    ap.add_argument('--bump-ramp', type=int, default=0,
                    help="Bump wächst über so viele Frames aus dem Boden (0=sofort)")
    ap.add_argument('--bump-osc-amp', type=float, default=0.0,
                    help="Einzel-Bump: Oszillations-Amplitude um bump-h [m] (0=aus)")
    ap.add_argument('--bump-osc-period', type=int, default=360,
                    help="Oszillations-Periode [Frames] (240=1s, 360=1.5s, 480=2s @240Hz)")
    ap.add_argument('--bump-random', action='store_true',
                    help="Oszillierender Zufalls-Bumper unter JEDEM Bein (Härtetest)")
    ap.add_argument('--bump-rand-amp-max', type=float, default=0.03,
                    help="Max. Amplitude der Zufalls-Bumper [m] (Default 30mm)")
    ap.add_argument('--bump-rand-seed', type=int, default=0,
                    help="Seed für reproduzierbare Zufalls-Bumper (Single-Lever)")
    ap.add_argument('--bump-rand-ramp', type=int, default=240,
                    help="Zufalls-Bumper: Einhüllende wächst 0->1 über so viele Frames (Anti-Sprung)")
    ap.add_argument('--settle', type=int, default=240,
                    help="Frames ruhig stehen vor dem Fahren (Default 240 = 1 s)")
    ap.add_argument('--drive-vx', type=float, default=1.0, help="Fahrbefehl vx im Auto-Modus")
    # --- Terrain (V9): Hügelstrecke statt Treppe ---
    ap.add_argument('--hills', action='store_true',
                    help="Hügelstrecke (runde Kuppen) statt Treppe bauen")
    ap.add_argument('--hills-n', type=int, default=6, help="Anzahl Kuppen (ridges) bzw. Kuppeln (scatter, min 40)")
    ap.add_argument('--hills-seed', type=int, default=0, help="Seed der Hügelstrecke (reproduzierbar)")
    ap.add_argument('--hills-style', choices=['scatter', 'ridges'], default='scatter',
                    help="scatter = verstreute Kuppeln (Roll+Pitch+Per-Bein), ridges = Querzylinder (nur Pitch)")
    ap.add_argument('--hills-len', type=float, default=2.5, help="Streckenlänge des Kuppelfelds (scatter) [m]")
    # --- Einzelstufe (V9.4): Klettern/Freeze isolieren ---
    ap.add_argument('--step', action='store_true', help="Einzelne Stufe statt Treppe/Hügel")
    ap.add_argument('--step-h', type=float, default=0.06, help="Höhe der Einzelstufe [m] (Default 60mm)")
    ap.add_argument('--tag', default='', help="Kürzel im Log-Dateinamen (z.B. balance_off)")
    # --- Servo-Stellwinkel-Grenzen [Grad] zum Live-Testen des IK-Pfads ---
    # Default = None -> Klassenwert der IK behalten. Femur: neg = auf.
    ap.add_argument('--coxa-min',  type=float, default=None, help="Coxa min [deg]  (Default -110)")
    ap.add_argument('--coxa-max',  type=float, default=None, help="Coxa max [deg]  (Default +110)")
    ap.add_argument('--femur-min', type=float, default=None, help="Femur min [deg] neg=auf (Default -160)")
    ap.add_argument('--femur-max', type=float, default=None, help="Femur max [deg] (Default +130)")
    ap.add_argument('--tibia-min', type=float, default=None, help="Tibia min [deg] (Default -20)")
    ap.add_argument('--tibia-max', type=float, default=None, help="Tibia max [deg] (Default +175)")
    args = ap.parse_args()
    STAIR_RISE = args.rise; STAIR_RUN = args.run; STAIR_X = args.stair_x
    print("  Treppe: rise=%.0fmm run=%.0fmm | GUI=%s Treppe=%s Dose=%s"
          % (STAIR_RISE*1000, STAIR_RUN*1000, not args.no_gui, not args.no_stairs, args.can))
    robot = SlarcController()
    robot.init_pybullet(gui=not args.no_gui, build_stairs=not args.no_stairs,
                        spawn_can=args.can, spawn_x=args.start_x,
                        terrain=('step' if args.step else ('hills' if args.hills else 'stairs')),
                        hills_n=args.hills_n, hills_seed=args.hills_seed,
                        hills_style=args.hills_style, hills_len=args.hills_len, step_h=args.step_h)

    # Servo-Stellwinkel-Grenzen überschreiben (nur die gesetzten), IK-Pfad live testen
    _lim = [('coxa_min','COXA_MIN'),('coxa_max','COXA_MAX'),('femur_min','FEMUR_MIN'),
            ('femur_max','FEMUR_MAX'),('tibia_min','TIBIA_MIN'),('tibia_max','TIBIA_MAX')]
    _changed = False
    for _arg, _attr in _lim:
        _v = getattr(args, _arg)
        if _v is not None:
            setattr(robot.ik, _attr, math.radians(_v)); _changed = True
    if _changed:
        print("  [SERVO-LIMITS] Coxa [%.0f,%.0f] Femur [%.0f,%.0f] Tibia [%.0f,%.0f] deg (neg Femur=auf)"
              % (math.degrees(robot.ik.COXA_MIN), math.degrees(robot.ik.COXA_MAX),
                 math.degrees(robot.ik.FEMUR_MIN), math.degrees(robot.ik.FEMUR_MAX),
                 math.degrees(robot.ik.TIBIA_MIN), math.degrees(robot.ik.TIBIA_MAX)))

    # Layer-Konfiguration (für Isolations-Tests)
    robot.auto_balance    = not args.no_balance
    robot.G_FOOTHOLD      = not args.no_foothold
    robot.G_FREEZE_ENABLE = not args.no_freeze
    robot.G_CLIMB_PITCH_OFF = args.climb_pitch_off   # [Isolation] R2 flach beim Klettern
    robot.G_FREEZE_CLIMB_H  = args.freeze_climb_height   # [Isolation] bho beim Klettern halten
    robot.G_ENTRY_BOOST   = not args.no_entry
    if args.gait:
        robot.gait_name = args.gait; robot._enter_gait()

    # ---------- HALTE-MODUS (isolierter Stand-Regeltest) ----------
    if args.hold > 0:
        robot.start_hold()
        robot.logger.tag = args.tag or 'hold'
        print("  [HOLD] balance=%s | %d Frames stehen%s"
              % ("AN" if robot.auto_balance else "AUS", args.hold,
                 (" | Bump +%.0fmm unter %s @f%d" % (args.bump_h*1000, args.bump_leg, args.bump_at))
                 if args.bump_at > 0 else ""))
        robot.logger.start()
        legs = list(robot.legs)
        _rand_spawn = args.bump_at if args.bump_at > 0 else 60   # Zufalls-Bumper brauchen Settle-Rand
        for i in range(args.hold):
            robot.hold_update(); p.stepSimulation()
            if args.bump_random:
                if i == _rand_spawn:
                    robot.spawn_random_bumps(args.bump_rand_amp_max, args.bump_osc_period,
                                             seed=args.bump_rand_seed, ramp_frames=args.bump_rand_ramp)
                robot.update_bumps()
            else:
                if args.bump_at > 0 and i == args.bump_at:
                    robot.spawn_bump(args.bump_leg, args.bump_h, ramp_frames=args.bump_ramp,
                                     osc_amp=args.bump_osc_amp, osc_period=args.bump_osc_period)
                robot.ramp_bump()
            if not args.no_gui:
                robot.update_contact_display()
            robot.logger.tick()
            if not args.no_gui: time.sleep(1./240.)
        robot.logger.stop()
        # Metrik: Kontaktzahl-Stabilität, vz-Ruhe, Pitch
        print("  [HOLD] fertig -> %s" % robot.logger.path)
        return

    # ---------- AUTO-FAHRMODUS (reproduzierbare Isolations-Läufe) ----------
    if args.auto > 0:
        robot.logger.tag = args.tag
        print("  [AUTO] balance=%s foothold=%s freeze=%s entry=%s gait=%s | settle=%d drive=%d vx=%.2f"
              % ("AN" if robot.auto_balance else "AUS",
                 "AN" if robot.G_FOOTHOLD else "AUS",
                 "AN" if robot.G_FREEZE_ENABLE else "AUS",
                 "AN" if robot.G_ENTRY_BOOST else "AUS",
                 robot.gait_name, args.settle, args.auto, args.drive_vx))
        robot.logger.start()
        for _ in range(args.settle):                 # erst ruhig stehen (Baseline)
            robot.update_gait(); p.stepSimulation()
            robot.logger.tick()
            if not args.no_gui: time.sleep(1./240.)
        robot.cmd_vel_x = args.drive_vx              # dann geradeaus fahren
        for _ in range(args.auto):
            robot.update_gait(); p.stepSimulation()
            if not args.no_gui:
                robot.update_contact_display(); robot.update_torque_display()
            robot._update_progress(); robot.logger.tick()
            if not args.no_gui: time.sleep(1./240.)
        robot.logger.stop()
        print("  [AUTO] Lauf fertig -> %s" % robot.logger.path)
        return

    print("\n=== SLARC V8 - Unified omnidirektionaler Gait-Kern ===")
    print("Pfeile: vor/zurueck/seitwaerts | Q/E: drehen | W/S: Koerperhoehe")
    print("7: Schrittlaenge | 8: Gait (tripod/ripple/placemove) | B: Balance | K: Freeze | V: Log | R: Reset\n")
    while True:
        robot.process_keyboard()
        robot.update_gait()
        p.stepSimulation()
        robot.update_contact_display()
        robot.update_torque_display()
        robot._update_progress()
        if robot.logger: robot.logger.tick()
        time.sleep(1./240.)


class MotionLogger:
    """
    Schreibt pro N Frames eine CSV-Zeile mit dem REALEN Closed-Loop-Zustand:
      Körperpose (x/y/z, roll/pitch/yaw), Körpergeschwindigkeit (lin/ang),
      Balancer (roll_bal/pitch_bal), Fahrbefehl (cmd_vx/cmd_yaw) und je Bein
      Fuß-Weltposition, Bodenkontakt, die drei Servo-Drehmomente sowie den
      Mode-7-Tastzustand.
    Zweck: Test live laufen lassen -> CSV hochladen -> Verhalten an Messdaten
    analysieren (z.B. wann/warum Pitch wegkippt, welche Füße dann Kontakt
    haben, welche Servos sättigen, ob der Balancer greift).
    Taste V startet/stoppt. Datei landet im Arbeitsverzeichnis.
    """
    LEG_ORDER = ['front_right', 'front_left', 'mid_right',
                 'mid_left', 'rear_right', 'rear_left']

    def __init__(self, ctrl, decimate=4):
        self.ctrl = ctrl
        self.decimate = max(1, int(decimate))   # 240 Hz / 4 = 60 Hz
        self.active = False
        self.f = None
        self.path = None
        self.frame = 0
        self.rows = 0
        self.t0 = None

    def _legs(self):
        names = {l.name for l in self.ctrl.legs}
        return [n for n in self.LEG_ORDER if n in names]

    def _header(self):
        cols = ["t", "frame", "mode", "bx", "by", "bz",
                "roll", "pitch", "yaw", "vx", "vy", "vz",
                "wx", "wy", "wz", "cmd_vx", "cmd_yaw",
                "roll_bal", "pitch_bal",
                # [PORTABLE] Pose-Schätzung (IMU + Leg-Odometry, ESP32-fähig) + Freeze-Status
                "est_roll", "est_pitch", "est_yaw", "est_height", "frozen",
                # [V9.2-Diag] Vortriebs-Bremse: kommandierter Vorwärts-Schritt dxb, Bremsfaktor
                # brake (1=frei, 0=voll gebremst), tatsächlich kommandierte Strecke/Frame cmd_adv
                "dxb", "brake", "cmd_adv",
                # [V9.3-Diag] R3-Gate: r3n = tragende Beine die R3 sieht (<3 -> R3 hält/aus),
                # bho = body_height_offset (R3-Output), lost = Stützbeine ohne Kontakt (Freeze-Treiber)
                "r3n", "bho", "lost",
                # [V9.4-Diag] Klettern/Freeze: climb_pitch = R2-Sollwert (nase-hoch beim Steigen),
                # freeze_cnt = Freeze-Debounce-Zähler (>DEB -> frozen; zeigt spurios vs. echt)
                "climb_pitch", "freeze_cnt",
                # [V9.5-Diag] est_h_proj = pitch/roll-projizierte VERTIKALE Höhe (Vergleich zur
                # rohen est_height: sollte beim Klettern flach ~0.12 bleiben, wenn Vorzeichen stimmt)
                "est_h_proj",
                # [V10-Diag] Anker-Kandidaten (projiziert): est_h_low = Höhe über tiefstem tragenden
                # Bein (V10-Anker), est_h_high = über höchstem. Vergleich zum Median est_h_proj.
                "est_h_low", "est_h_high",
                # [V10.9-Diag] R3-Kletter-Innenleben: h_ref_raw/h_ref_f (roh/gefiltert), climb_err,
                # climb_over (Overstretch-Term), n_ref (Referenzbeine), climbing (0/1)
                "h_ref_raw", "h_ref_f", "climb_err", "climb_over", "n_ref", "climbing",
                "com_fwd"]   # [V10.14] CoM-Wippe fore-aft-Offset
        for n in self._legs():
            cols += [f"{n}_fx", f"{n}_fy", f"{n}_fz", f"{n}_contact", f"{n}_force",
                     f"{n}_tau_coxa", f"{n}_tau_femur", f"{n}_tau_tibia",
                     f"{n}_state",
                     # Servowinkel (rad) + Fußpunkt im Körper-Frame (FK, portierbar)
                     f"{n}_th_c", f"{n}_th_f", f"{n}_th_t",
                     f"{n}_rfx", f"{n}_rfy", f"{n}_rfz"]
        return cols

    def toggle(self):
        self.stop() if self.active else self.start()

    def start(self):
        import os, time, csv
        if self.ctrl.robot_id is None:
            print("[Logger] Roboter noch nicht bereit."); return
        ts = time.strftime("%Y%m%d_%H%M%S")
        tag = getattr(self, 'tag', '')
        suffix = f"_{tag}" if tag else ""
        self.path = os.path.join(os.getcwd(), f"slarc_log_{ts}{suffix}.csv")
        self.f = open(self.path, "w", newline="")
        self.writer = csv.writer(self.f)
        c = self.ctrl
        self.f.write("# SLARC %s | rise=%.3f run=%.3f | balance=%s foothold=%s freeze=%s entry=%s | G_Z=%.3f G_STEP=%.3f\n" % (
            SLARC_VERSION, STAIR_RISE, STAIR_RUN,
            "AN" if c.auto_balance else "AUS",
            "AN" if c.G_FOOTHOLD else "AUS",
            "AN" if c.G_FREEZE_ENABLE else "AUS",
            "AN" if c.G_ENTRY_BOOST else "AUS", c.G_Z, c.G_STEP))
        self.writer.writerow(self._header())
        self.active = True; self.frame = 0; self.rows = 0; self.t0 = None
        print(f"[Logger] AUFNAHME gestartet -> {self.path}  (Taste V stoppt)")

    def stop(self):
        if not self.active: return
        self.active = False
        try:
            self.f.flush(); self.f.close()
        except Exception:
            pass
        print(f"[Logger] gestoppt. {self.rows} Zeilen -> {self.path}")

    def tick(self):
        if not self.active or self.ctrl.robot_id is None:
            return
        self.frame += 1
        if self.frame % self.decimate != 0:
            return
        import time
        c = self.ctrl; rid = c.robot_id
        if self.t0 is None:
            self.t0 = time.time()
        t = time.time() - self.t0
        pos, orn = p.getBasePositionAndOrientation(rid)
        roll, pitch, yaw = p.getEulerFromQuaternion(orn)
        lin, ang = p.getBaseVelocity(rid)
        # Rohkraft je Fuß-Link sammeln (informativ - Last/Drehmoment).
        # Der Kontakt-FLAG kommt NICHT aus der Kraft (flackert durch Solver-
        # Lastumverteilung), sondern aus dem geometrischen Hysterese-Kontakt
        # _g_contact (= µ-Switch-Äquivalent: berührt/berührt nicht).
        forces = {}
        for ct in (p.getContactPoints(bodyA=rid) or []):
            forces[ct[3]] = forces.get(ct[3], 0.0) + ct[9]
        # [PORTABLE] Pose-Schätzung einmal pro Tick (IMU + FK + Leg-Odometry)
        try:
            est = c.estimate_pose()
        except Exception:
            est = {'roll': 0.0, 'pitch': 0.0, 'yaw': 0.0, 'height': float('nan'),
                   'angles': {}, 'feet': {}}
        frozen = 1 if getattr(c, '_g_frozen', False) else 0
        row = [f"{t:.3f}", self.frame, getattr(c,'gait_name','?'),
               f"{pos[0]:.4f}", f"{pos[1]:.4f}", f"{pos[2]:.4f}",
               f"{roll:.4f}", f"{pitch:.4f}", f"{yaw:.4f}",
               f"{lin[0]:.4f}", f"{lin[1]:.4f}", f"{lin[2]:.4f}",
               f"{ang[0]:.4f}", f"{ang[1]:.4f}", f"{ang[2]:.4f}",
               f"{c.cmd_vel_x:.3f}", f"{getattr(c,'cmd_yaw',0.0):.3f}",
               f"{getattr(c,'roll_bal',0.0):.4f}",
               f"{getattr(c,'pitch_bal',0.0):.4f}",
               f"{est['roll']:.4f}", f"{est['pitch']:.4f}", f"{est['yaw']:.4f}",
               f"{est['height']:.4f}", frozen,
               f"{getattr(c,'_g_dxb',0.0):.5f}", f"{getattr(c,'_g_brake',1.0):.3f}",
               f"{getattr(c,'_cmd_adv',0.0):.5f}",
               getattr(c,'_g_r3_n',0), f"{getattr(c,'body_height_offset',0.0):.4f}",
               getattr(c,'_g_stance_lost_n',0),
               f"{getattr(c,'_g_climb_pitch',0.0):.4f}", getattr(c,'_g_freeze_cnt',0),
               f"{getattr(c,'_g_h_proj',abs(c.G_Z)):.4f}",
               f"{getattr(c,'_g_h_low',abs(c.G_Z)):.4f}", f"{getattr(c,'_g_h_high',abs(c.G_Z)):.4f}",
               f"{getattr(c,'_g_h_ref_raw',0.0):.4f}", f"{getattr(c,'_g_h_ref_f',0.0):.4f}",
               f"{getattr(c,'_g_climb_err',0.0):.4f}", f"{getattr(c,'_g_climb_over',0.0):.4f}",
               getattr(c,'_g_n_ref',0), int(getattr(c,'_g_climbing',False)),
               f"{getattr(c,'_g_com_fwd',0.0):.4f}"]
        for n in self._legs():
            fidx = c._foot_link_idx.get(n, -1)
            if fidx >= 0:
                fp = p.getLinkState(rid, fidx)[0]
                fx, fy, fz = fp[0], fp[1], fp[2]
                con = 1 if c._g_contact.get(n, False) else 0
                frc = forces.get(fidx, 0.0)
            else:
                fx = fy = fz = 0.0; con = 0; frc = 0.0
            taus = []
            for j in ('coxa', 'femur', 'tibia'):
                jidx = c.joint_map.get(f"{n}_{j}_joint")
                taus.append(abs(p.getJointState(rid, jidx)[3])
                            if jidx is not None else 0.0)
            state = getattr(c, '_g_state', {}).get(n, '')
            thc, thf, tht = est['angles'].get(n, (0.0, 0.0, 0.0))
            rfx, rfy, rfz = est['feet'].get(n, (0.0, 0.0, 0.0))
            row += [f"{fx:.4f}", f"{fy:.4f}", f"{fz:.4f}", con, f"{frc:.2f}",
                    f"{taus[0]:.3f}", f"{taus[1]:.3f}", f"{taus[2]:.3f}", state,
                    f"{thc:.4f}", f"{thf:.4f}", f"{tht:.4f}",
                    f"{rfx:.4f}", f"{rfy:.4f}", f"{rfz:.4f}"]
        self.writer.writerow(row)
        self.rows += 1
        if self.rows % 120 == 0:      # ~alle 2 s sichern
            self.f.flush()


# ==========================================


if __name__ == "__main__":
    main()
