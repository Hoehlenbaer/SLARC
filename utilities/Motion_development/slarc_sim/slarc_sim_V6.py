#!/usr/bin/env python3
"""
SLARC Simulation V6
===================
V5 + portable Stall-Erkennung/Auto-Recovery (StallGuard) und ein
deterministischer Foothold-Tripod-Treppengang (Modus 6).

Neuerungen gegenüber V5
-----------------------
1. StallGuard        : Portable Coxa-Stall-Erkennung (Positionsfehler +
                       Last über Schwelle, entprellt) mit Auto-Recovery
                       (Bein anheben/entlasten). Pro Bein, im PORTABLE CORE.
2. StairModel        : Perception-Abstraktion (height_at/tread_center/
                       slope_at). In der Sim aus der bekannten Geometrie,
                       auf der HW aus der Hailo-Höhenkarte. PORTABLE CORE.
3. Modus 6 — Foothold-Tripod-Treppengang (Taste 6):
                       Statt periodischem "Wackeln" werden die Fußaufsatz-
                       punkte deterministisch in WELTkoordinaten auf Tritt-
                       Mitten geplant. Ein Tripod schwingt zu seinen neuen
                       Footholds, während der andere stützt. Der Körper rückt
                       je Halbzyklus nur so weit vor, dass die Standbeine
                       erreichbar bleiben (whole-body coordination); Pitch
                       nähert sich der Stufensteigung an. Diskrete Planung je
                       Halbzyklus + Frame-Interpolation fürs flüssige Rendern.
                       Offline verifiziert: volle Treppe (auf+Plateau+ab) bei
                       4/8/12/17 cm; 0 % Standbein-Fehler bis 12 cm, ~3-4 %
                       winzige Clamps bei extremen 17 cm. Modus 5 (Ripple-
                       Treppe) bleibt erprobter Fallback.
   WICHTIG/EHRLICH   : Der kinematische Planer (Footholds, Erreichbarkeit,
                       Klettern der ganzen Treppe) ist offline gründlich
                       geprüft. NICHT offline prüfbar war die PyBullet-
                       Closed-Loop-Dynamik (folgt der reale Körper den
                       Standfüßen? Stabilität?) — das bestätigt erst ein
                       Live-Run. Bei Problemen Modus 5 nutzen.

Aus V5 übernommen
-----------------
- Vollflexibler IK-Kern mit kinematisch hergeleiteten Grenzen,
  Gelenklimits/Anti-Kollision, aktive Balance-Überlagerung (Taste B).
- Schritthöhe 1 cm … kinematisches Max; Körperhöhe 0 … gestreckt.
- Modus 5: Ripple-Treppengang + Auto-Pitch (FIXED/ADAPTIV).

ESP32-Portabilität
------------------
Alles zwischen den Markern
    # >>> PORTABLE CORE (ESP32) >>>
    # <<< PORTABLE CORE (ESP32) <<<
ist reine `math`-Logik und nach MicroPython/C++ übertragbar (inkl.
HexapodKinematics, BalanceController, StallGuard, StairModel). Der
Foothold-Planer selbst ist ebenfalls reine Mathematik; nur die virtuelle
Körperpose (Sim: Integration; HW: Odometrie) und set_servo sind plattform-
spezifisch. Auf dem ESP32 reaktive Schicht (IK+Servo+StallGuard, 200 Hz+),
auf RPi5+Hailo deliberativ (Perception + Foothold-Planung, 5-20 Hz).

Tastenbelegung (Ergänzungen)
  B : Auto-Balance an/aus
  N : Treppensteige-Sequenz starten / abbrechen
  5 : Modus 5 Ripple-Treppe (erneut = FIXED/ADAPTIV)
  6 : Modus 6 deterministischer Foothold-Tripod-Treppengang
"""

import pybullet as p          # SIM ONLY (PC)
import pybullet_data          # SIM ONLY (PC)
import time                   # SIM ONLY (PC)
import math                   # PORTABLE (ESP32 hat math)
import numpy as np            # SIM ONLY (PC) — nur Stereo/Perzeption
from enum import IntEnum      # SIM ONLY (PC) — StairClimber-Skript


# ==========================================
# 0. URDF GENERATOR
# ==========================================
# Gemeinsame Körper-Geometrie: hier ÄNDERN, dann passen URDF UND Controller.
# Länge auf 200mm verkürzt (war 250): Hinterbein-Coxa/Femur saßen sonst auf
# der 17cm-Stufenkante auf. Elektronik passt (LiPo ZEEE 9000mAh = 166mm).
# Breiter (150mm statt 120) → seitlich stabiler.
BODY_L = 0.200; BODY_W = 0.150; BODY_H = 0.040
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
STAIR_RISE = 0.05      # Stufenhöhe [m] (10-cm-Test)
STAIR_RUN  = 0.250     # Stufentiefe [m]

# ST3215 Stall-Drehmoment ~30 kg·cm ≈ 2.94 Nm. Dient als realer Motor-force
# (Sättigung) UND als 100%-Bezug der Drehmomentanzeige — eine Quelle, konsistent.
SERVO_STALL_NM = 2.94

# Positions-Regelsteifigkeit des Servos (PyBullet Kp). 0.05 war für ein
# realistisch "weiches" Bein gedacht, ist aber so nachgiebig, dass der Servo
# (a) den Fuß kaum zügig auf Coxa-Höhe hebt und (b) den Stand-Sweep nicht in
# Körpervortrieb überträgt → Rutschen + Kriechtempo. Der echte ST3215 ist
# deutlich steifer; das Stall-Drehmoment (force) bleibt die Sättigungsgrenze,
# die Drehmomentanzeige also weiter ≤100%. Bei Oszillation Wert senken.
SERVO_POS_GAIN = 0.30

def create_staircase():
    step_ids = []
    step_h = STAIR_RISE; step_d = STAIR_RUN; step_w = 1.200
    x_start = 1.0; n_up = 5

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
    print(f"  5 Stufen aufwärts  (x=1.0–2.25m, +{top_h*100:.0f}cm)")
    print(f"  Plateau            (x=2.25–3.25m)")
    print(f"  5 Stufen abwärts   (x=3.25–4.5m)")
    return step_ids


# ==========================================
# STEREO-KAMERAS
# ==========================================
class StereoCameras:
    """
    IMX296: 1456×1088px, 3.45µm Pixelpitch, f=2.8mm
    Scaling auf 640×480 — FOV bleibt identisch (83.8°H × 67.7°V)
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
#  • frictionAnchor=1: verankert den Kontaktpunkt → belastete Füße KRIECHEN nicht
#    mehr unter Tangentiallast (behebt das Rückwärtsrutschen). Ohne Anchor löst
#    PyBullets Solver den Reibkegel iterativ und lässt Rest-Schlupf zu.
#  • restitution=0: kein Rückprall (ein 3-kg-Roboter mit Gummifüßen prallt nicht).
#  • contactStiffness/Damping: weiche, GEDÄMPFTE Kontaktfeder statt der steifen
#    Default-ERP-Feder → der Fuß federt nicht (kein Hüpfen). k=15000 N/m: statische
#    Fußlast ~5 N → Eindrücken 0.3 mm (realistisch fest). Dämpfung c=1500 ist ggü.
#    dem kritischen c=2·√(k·m)≈420 (m≈3 kg) deutlich überdämpft → garantiert kein
#    Nachschwingen. MUSS auf BEIDE Kontaktpartner (Fuß UND Boden/Stufe), sonst
#    greift nur die halbe Nachgiebigkeit.
#  • spinning/rollingFriction klein: etwas Dreh-/Rollwiderstand gegen Zappeln.
FOOT_FRICTION   = 1.6
GROUND_FRICTION = 1.6
CONTACT_K       = 15000.0
CONTACT_C       = 1500.0

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
      senkt die Beinspitze (down-positiv) → negativer Femurwinkel = aufwärts.
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

    def step_h_max(self, stance_z):
        """
        Maximale Schritt-Hubhöhe relativ zur Standfußhöhe `stance_z`
        (stance_z < 0). Fußspitze darf FOOT_Z_MAX über Hüfte nicht
        überschreiten → max. Hub = FOOT_Z_MAX - stance_z.
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
        # nahe an die volle Streckung (325 mm) in JEDE Richtung – inkl. weit
        # über Schulterhöhe (Mittelbein-Tuck) und tief abgesenkt (Greifer).

        # --- Coxa (Yaw) ---
        theta_c = math.atan2(y, x)

        # --- horizontale Reichweite ab Femurgelenk ---
        L = math.sqrt(x * x + y * y) - self.L_C
        if L < 0.02:
            L = 0.02
            ok = False

        # --- Geradlinige Distanz Femurgelenk→Fuß, auf Reichweite clampen ---
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

    # Rückwärtskompatibler 3-Tupel-Aufruf (wie V4 calculate_leg_angles)
    def calculate_leg_angles(self, x, y, z):
        tc, tf, tt, _ = self.solve(x, y, z)
        return tc, tf, tt


class BalanceController:
    """
    PD-Regler, der die Körpernormale zur Schwerkraft ausrichtet
    (Roll/Pitch → 0). Gibt additive Roll/Pitch-KORREKTUREN zurück, die
    über die Gang-IK gelegt werden ("IK-Balance-Überlagerung").

    Negatives Feedback: gemessener Nase-hoch-Pitch ⇒ Kommando senkt die
    Nase. Vorzeichen hängt von der Lage-Konvention ab → über
    PITCH_SIGN/ROLL_SIGN an Sim bzw. IMU anpassbar.

    Reine math-Logik: auf dem ESP32 mit IMU-Winkeln (rad) speisen.
    """
    # Die kommandierte Lage-Rotation der Fußziele ist invers zur gemessenen
    # Euler-Lage (kommandierter Pitch>0 → Nase HOCH → Euler-Pitch wird negativ).
    # Daher +1.0, damit der Regler die gemessene Neigung gegen 0 fährt
    # (statt sie zu verstärken — vorher kippte der Körper nach vorne).
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
    drückt gegen ein Hindernis, kommt aber nicht weiter) — über mehrere Zyklen
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


# ==========================================
# STAIR CLIMBER
# ==========================================
# ==========================================
# TUCK-AND-STEP STAIR CLIMBER
# ==========================================
# Rollierendes Stufenmuster — kein Ablegen auf der Stufe:
#
#  Einmalig (erste Stufe):
#   RAISE      → Körper auf 240mm
#   TUCK_FRONT → Vorderbeine tucken (Femur ~80°, Fuß 97mm über Stufe)
#   FRONT_STEP1→ Vorderbeine auf Stufe 1 absetzen
#
#  Rollzyklus (wiederholt für jede Stufe):
#   RAISE_ON   → Körper auf Stufenniveau aufrichten (body = level + NOM)
#   PITCH_BACK → Leicht nach hinten neigen (~10°), Gewicht auf Mid/Rear
#   FRONT_NEXT → Vorderbeine auf nächste Stufe (nur -20mm under Hüfte @ body_h!)
#   BODY_PUSH  → Körper vorwärts schieben
#   MID_STEP   → Mittelbeine auf aktuelle Stufe (= normale Standhöhe)
#   REAR_STEP  → Hinterbeine auf aktuelle Stufe
#   → zurück zu RAISE_ON mit level++
#
# Geometrie-Vorteile:
#   Einmal aufgerichtet: Vorderbein-Reach = 36% max (sehr einfach)
#   Mittelbeine = normale Standhöhe beim Aufsetzen (keine extra Hubhöhe)
#   Hinterbeine gestreckt = verhindert Rückwärtskippen in FRONT_NEXT

from enum import IntEnum

class TuckPhase(IntEnum):
    IDLE         = 0
    RAISE        = 1   # Körper auf 240mm, Gait 4 (Zentaur-Vorbereitung)
    TUCK_FRONT   = 2   # Vorderbeine tucken
    FRONT_STEP1  = 3   # Vorderbeine auf Stufe 1 absetzen
    RAISE_ON     = 4   # Körper auf level*STEP_H + NOM aufrichten
    PITCH_BACK   = 5   # Leicht nach hinten neigen, Gewicht umlagern
    FRONT_NEXT   = 6   # Vorderbeine auf nächste Stufe
    BODY_PUSH    = 7   # Körper vorwärts schieben (Mid/Rear schieben)
    MID_STEP     = 8   # Mittelbeine auf aktuelle Stufe
    REAR_STEP    = 9   # Hinterbeine auf aktuelle Stufe
    NORMALIZE    = 10  # Normalisieren wenn alle Stufen fertig


TUCK_DUR = {
    TuckPhase.RAISE:       160,
    TuckPhase.TUCK_FRONT:  120,
    TuckPhase.FRONT_STEP1: 140,
    TuckPhase.RAISE_ON:    160,
    TuckPhase.PITCH_BACK:   80,
    TuckPhase.FRONT_NEXT:  120,
    TuckPhase.BODY_PUSH:   200,
    TuckPhase.MID_STEP:    150,
    TuckPhase.REAR_STEP:   150,
    TuckPhase.NORMALIZE:   160,
}

TUCK_NAMES = {v: k for k, v in TuckPhase.__members__.items()}


class ContinuousStairClimber:
    """
    Rollierender Tuck-and-Step Treppensteiger.
    Tuck nur für erste Stufe, danach direktes Reaching da Körper
    auf Stufenniveau aufgerichtet ist (Vorderbein-Reach nur 36%).
    """
    STEP_H    = 0.170
    BODY_NOM  = 0.190
    RAISE_H   = 0.060   # Initialer Körperhub
    # Tuck-Zielposition (Fuß in body-frame, Femur ~80° aufwärts)
    TUCK_X    = 0.065   # knapp über Coxa
    TUCK_Y    = 0.040   # ±39mm seitlich (Tibia 15° von vertikal)
    TUCK_Z    = 0.027   # +27mm über Hüfte
    # Swing-Clearance
    SWING_CLR = 0.050
    # max. Anzahl Stufen (Safety)
    MAX_STEPS = 6

    def __init__(self, ctrl):
        self.ctrl    = ctrl
        self._active = False
        self.phase   = TuckPhase.IDLE
        self.timer   = 0
        self._dbg_id = None
        # Aktuelles Stufenniveau (0=Boden, 1=erste Stufe, ...)
        self._current_level  = 0
        # Schwungfortschritt [0..1]
        self._front_t = 0.0
        self._mid_t   = {'mid_right': 0.0, 'mid_left': 0.0}
        self._rear_t  = {'rear_right': 0.0, 'rear_left': 0.0}
        # Gespeicherte Startwerte für Raise
        self._raise_start_bho = 0.0

    # ── Interface ─────────────────────────────────────────────────────
    @property
    def active(self):
        return self._active

    @active.setter
    def active(self, v):
        self._active = v

    def is_swinging(self, leg_name):
        if self.phase == TuckPhase.MID_STEP:
            return leg_name in ('mid_right', 'mid_left')
        if self.phase == TuckPhase.REAR_STEP:
            return leg_name in ('rear_right', 'rear_left')
        if self.phase in (TuckPhase.FRONT_STEP1, TuckPhase.FRONT_NEXT):
            return leg_name in ('front_right', 'front_left')
        return False

    def get_swing_base_z(self, leg_name):
        """Schwungbogen zum Ziel-Level."""
        if self.phase in (TuckPhase.FRONT_STEP1, TuckPhase.FRONT_NEXT):
            t = self._front_t
            target_level = (self._current_level + 1
                            if self.phase == TuckPhase.FRONT_NEXT
                            else 1)
        elif self.phase == TuckPhase.MID_STEP:
            t = self._mid_t.get(leg_name, 1.0)
            target_level = self._current_level
        elif self.phase == TuckPhase.REAR_STEP:
            t = self._rear_t.get(leg_name, 1.0)
            target_level = self._current_level
        else:
            return -(self.BODY_NOM - self._current_level * self.STEP_H)

        # Fuß-Ziel in body-frame:
        # foot_world = target_level * STEP_H
        # body_world = BODY_NOM + bho = BODY_NOM + level*STEP_H
        # foot_body  = foot_world - body_world = -(BODY_NOM - (target-level)*STEP_H)
        # Da bho kürzt sich heraus: foot_body = target_step_z - BODY_NOM
        target_bz = target_level * self.STEP_H - self.BODY_NOM
        start_bz  = (self._current_level - 1) * self.STEP_H - self.BODY_NOM                     if self.phase in (TuckPhase.MID_STEP, TuckPhase.REAR_STEP)                     else -self.BODY_NOM   # von Boden
        peak_bz   = target_level * self.STEP_H + self.SWING_CLR - self.BODY_NOM

        LIFT_F = 0.45
        if t < LIFT_F:
            t1 = t / LIFT_F
            return start_bz + (peak_bz - start_bz) * math.sin(t1 * math.pi / 2)
        else:
            t2 = (t - LIFT_F) / (1.0 - LIFT_F)
            return target_bz + (peak_bz - target_bz) * math.cos(t2 * math.pi / 2)

    def start(self):
        if self._active:
            self._stop()
            print("🪜 TuckStep: Abgebrochen")
            return
        self._active = True
        self._current_level = 0
        self.phase   = TuckPhase.RAISE
        self.timer   = 0
        self._raise_start_bho = self.ctrl.body_height_offset
        self.ctrl.cmd_vel_x = 0.0
        pos, _ = p.getBasePositionAndOrientation(self.ctrl.robot_id)
        print(f"🪜 TuckStep: Gestartet  (x={pos[0]:.2f}m, Treppe bei x=1.0m)")
        self._dbg("🪜 RAISE", [1.0, 0.8, 0.0])

    def update(self):
        if not self._active:
            return
        self.timer += 1
        c   = self.ctrl
        dur = TUCK_DUR[self.phase]
        t_s = self._ss(self.timer, dur)

        # ── RAISE ────────────────────────────────────────────────────
        if self.phase == TuckPhase.RAISE:
            target_bho = self.RAISE_H
            c.body_height_offset = (self._raise_start_bho
                                    + (target_bho - self._raise_start_bho) * t_s)
            c.cmd_vel_x = 0.0
            if self.timer >= dur:
                self._next(TuckPhase.TUCK_FRONT)

        # ── TUCK_FRONT ───────────────────────────────────────────────
        elif self.phase == TuckPhase.TUCK_FRONT:
            # Vorderbeine tucken: Fuß über Stufenkante heben
            # Ziel: base_z = +TUCK_Z, mit Coxa leicht nach vorne
            for name in ('front_right', 'front_left'):
                leg = next(l for l in c.legs if l.name == name)
                side = -1 if 'right' in name else 1
                # eff_base: Fuß knapp über Coxa, leicht seitlich
                c._eff_base[name] = (leg.mount_x + self.TUCK_X * t_s,
                                     leg.base_y * (1 - t_s * 0.3))
                # base_z: Fuß steigt auf +TUCK_Z
                leg.base_z = leg.default_z + (self.TUCK_Z - leg.default_z) * t_s
            if self.timer >= dur:
                self._front_t = 0.0
                self._next(TuckPhase.FRONT_STEP1)

        # ── FRONT_STEP1 ──────────────────────────────────────────────
        elif self.phase == TuckPhase.FRONT_STEP1:
            # Vorderbeine auf Stufe 1 schwingen
            speed = 1.0 / dur
            self._front_t = min(1.0, self._front_t + speed)
            for name in ('front_right', 'front_left'):
                leg = next(l for l in c.legs if l.name == name)
                leg.base_z = self.get_swing_base_z(name)
                # Coxa wieder nach vorne zur Stufe
                c._eff_base[name] = (leg.base_x + 0.050 * self._front_t,
                                     leg.base_y)
            if self._front_t >= 1.0:
                for name in ('front_right', 'front_left'):
                    leg = next(l for l in c.legs if l.name == name)
                    leg.base_z = self.STEP_H - self.BODY_NOM  # Stufe 1
                    c._eff_base[name] = (leg.base_x, leg.base_y)
                self._current_level = 1
                self._next(TuckPhase.RAISE_ON)

        # ── RAISE_ON ────────────────────────────────────────────────
        elif self.phase == TuckPhase.RAISE_ON:
            # Körper auf level*STEP_H + NOM aufrichten
            target_bho = self._current_level * self.STEP_H
            c.body_height_offset += (target_bho - c.body_height_offset) * 0.04
            c.cmd_vel_x = 0.0
            if self.timer >= dur:
                self._next(TuckPhase.PITCH_BACK)

        # ── PITCH_BACK ───────────────────────────────────────────────
        elif self.phase == TuckPhase.PITCH_BACK:
            # Leicht nach hinten neigen → Gewicht auf Mid/Rear
            c.pitch = self._ease(c.pitch, -0.175, self.timer, dur)  # ~-10°  (max ±0.6)
            c.cmd_vel_x = 0.0
            if self.timer >= dur:
                self._front_t = 0.0
                self._next(TuckPhase.FRONT_NEXT)

        # ── FRONT_NEXT ───────────────────────────────────────────────
        elif self.phase == TuckPhase.FRONT_NEXT:
            # Vorderbeine auf nächste Stufe
            # Da Körper aufgerichtet: nur -20mm unter Hüfte → einfacher Reach
            speed = 1.0 / dur
            self._front_t = min(1.0, self._front_t + speed)
            for name in ('front_right', 'front_left'):
                leg = next(l for l in c.legs if l.name == name)
                leg.base_z = self.get_swing_base_z(name)
            if self._front_t >= 1.0:
                next_level = self._current_level + 1
                for name in ('front_right', 'front_left'):
                    leg = next(l for l in c.legs if l.name == name)
                    leg.base_z = next_level * self.STEP_H - self.BODY_NOM
                c.pitch = 0.0
                self._next(TuckPhase.BODY_PUSH)

        # ── BODY_PUSH ────────────────────────────────────────────────
        elif self.phase == TuckPhase.BODY_PUSH:
            # Vorwärtsbewegung: Mid+Rear schieben, Front zieht
            c.cmd_vel_x = 0.040
            c.max_stride_x = 0.18
            # Pitch leicht vorwärts (CG-Kompensation)
            c.pitch = self._ease(c.pitch, 0.10, self.timer, dur)
            if self.timer >= dur:
                c.cmd_vel_x = 0.0
                c.max_stride_x = 0.14
                for name in ('mid_right', 'mid_left'):
                    self._mid_t[name] = 0.0
                self._next(TuckPhase.MID_STEP)

        # ── MID_STEP ─────────────────────────────────────────────────
        elif self.phase == TuckPhase.MID_STEP:
            c.cmd_vel_x = 0.0
            speed = 1.0 / dur
            for name in ('mid_right', 'mid_left'):
                self._mid_t[name] = min(1.0, self._mid_t[name] + speed)
                leg = next(l for l in c.legs if l.name == name)
                leg.base_z = self.get_swing_base_z(name)
            if all(t >= 1.0 for t in self._mid_t.values()):
                for name in ('mid_right', 'mid_left'):
                    leg = next(l for l in c.legs if l.name == name)
                    leg.base_z = self._current_level * self.STEP_H - self.BODY_NOM
                for name in ('rear_right', 'rear_left'):
                    self._rear_t[name] = 0.0
                self._next(TuckPhase.REAR_STEP)

        # ── REAR_STEP ────────────────────────────────────────────────
        elif self.phase == TuckPhase.REAR_STEP:
            c.cmd_vel_x = 0.0
            speed = 1.0 / dur
            for name in ('rear_right', 'rear_left'):
                self._rear_t[name] = min(1.0, self._rear_t[name] + speed)
                leg = next(l for l in c.legs if l.name == name)
                leg.base_z = self.get_swing_base_z(name)
            if all(t >= 1.0 for t in self._rear_t.values()):
                for name in ('rear_right', 'rear_left'):
                    leg = next(l for l in c.legs if l.name == name)
                    leg.base_z = self._current_level * self.STEP_H - self.BODY_NOM
                # Nächste Stufe oder fertig?
                if self._current_level >= self.MAX_STEPS:
                    self._next(TuckPhase.NORMALIZE)
                else:
                    print(f"  🪜 Stufe {self._current_level} fertig → nächste Stufe")
                    self._next(TuckPhase.RAISE_ON)

        # ── NORMALIZE ────────────────────────────────────────────────
        elif self.phase == TuckPhase.NORMALIZE:
            c.pitch = self._ease(c.pitch, 0.0, self.timer, dur)
            c.body_height_offset = self._ease(
                c.body_height_offset,
                self._current_level * self.STEP_H,
                self.timer, dur)
            if self.timer >= dur:
                for leg in c.legs:
                    leg.base_z = self._current_level * self.STEP_H - self.BODY_NOM
                print("✅ Alle Stufen bewältigt")
                self._stop()

        # Debug alle 20 Frames
        if self.timer % 20 == 0:
            prog = int(min(100, self.timer / dur * 100))
            self._dbg(
                f"🪜 {TUCK_NAMES.get(self.phase,'?')}  "
                f"[L{self._current_level}  {prog}%]",
                [0.2, 0.8, 0.2] if self.phase == TuckPhase.BODY_PUSH
                else [1.0, 0.8, 0.0])

    # ── Hilfsmethoden ─────────────────────────────────────────────────
    def _stop(self):
        self._active = False
        self.phase   = TuckPhase.IDLE
        self.timer   = 0
        c = self.ctrl
        c.cmd_vel_x    = 0.0
        c.pitch        = 0.0
        c.max_stride_x = 0.14
        for leg in c.legs:
            leg.base_z = leg.default_z
            c._eff_base[leg.name] = (leg.base_x, leg.base_y)

    def _next(self, phase):
        self.phase = phase
        self.timer = 0
        print(f"  🪜 → {TUCK_NAMES.get(phase, '?')}"
              f"  (Level {self._current_level})")
        self._dbg(f"🪜 {TUCK_NAMES.get(phase,'?')}", [0.8, 0.9, 1.0])

    def _dbg(self, text, color):
        if self.ctrl.robot_id is None: return
        pos, _ = p.getBasePositionAndOrientation(self.ctrl.robot_id)
        if self._dbg_id is not None:
            try: p.removeUserDebugItem(self._dbg_id)
            except: pass
        self._dbg_id = p.addUserDebugText(
            text, [pos[0], pos[1], pos[2] + 0.60],
            textColorRGB=color, textSize=1.2, lifeTime=0.5)

    @staticmethod
    def _ease(current, target, t, dur):
        p = max(0.0, min(1.0, t / dur))
        p = p * p * (3 - 2 * p)
        return current + (target - current) * p

    @staticmethod
    def _ss(t, dur):
        """Smoothstep [0..1]"""
        p = max(0.0, min(1.0, t / dur))
        return p * p * (3 - 2 * p)


# ==========================================
# MANUAL LEG TUNER
# ==========================================
# M-Taste: Tuner-Modus ein/aus
# Im Tuner-Modus: 1-6 = Bein wählen (statt Gangmodus)
# Sliders: Coxa/Femur/Tibia des ausgewählten Beins
# SPACE  : aktuelle Position loggen
# X      : alle 6 Beine loggen
# P      : leg_positions.json speichern

class ManualLegTuner:
    LEG_NAMES = ['front_right','front_left','mid_right',
                 'mid_left','rear_right','rear_left']

    def __init__(self, ctrl):
        self.ctrl     = ctrl
        self.active   = False
        self.sel_idx  = 0              # Index in LEG_NAMES
        self._sliders = {}
        self._logged  = {}
        self._dbg_ids = []
        self._dbg_frame = 0
        self._initialized = False

    def init_sliders(self):
        """Einmalig nach p.connect() aufrufen."""
        self._sliders['coxa']  = p.addUserDebugParameter(
            "Tuner Coxa  [°]", -150, 150, 0)
        self._sliders['femur'] = p.addUserDebugParameter(
            "Tuner Femur [°]", -150, 150, -17)
        self._sliders['tibia'] = p.addUserDebugParameter(
            "Tuner Tibia [°]", -150, 150, 29)
        self._initialized = True
        print("  Leg Tuner: Sliders initialisiert (M = an/aus)")

    @property
    def selected_leg(self):
        return self.LEG_NAMES[self.sel_idx]

    def get_override_angles(self, leg_name):
        """Gibt (tc, tf, tt) zurück wenn dieses Bein manuell gesteuert wird."""
        if not self.active or leg_name != self.selected_leg:
            return None
        if not self._initialized:
            return None
        tc = math.radians(p.readUserDebugParameter(self._sliders['coxa']))
        tf = math.radians(p.readUserDebugParameter(self._sliders['femur']))
        tt = math.radians(p.readUserDebugParameter(self._sliders['tibia']))
        return tc, tf, tt

    def toggle(self):
        self.active = not self.active
        if self.active:
            # Slider auf aktuelle Winkel des gewählten Beins setzen
            self._sync_sliders_to_leg()
            print(f"  🎛  Tuner AN — {self.selected_leg}  (1-6: Bein wählen, SPACE: loggen)")
        else:
            print("  🎛  Tuner AUS")

    def select_leg(self, idx):
        self.sel_idx = idx % len(self.LEG_NAMES)
        self._sync_sliders_to_leg()
        print(f"  🎛  Bein: {self.selected_leg}")

    def log_current(self):
        leg_name = self.selected_leg
        self._do_log(leg_name)

    def log_all(self):
        print("  🎛  Logge alle 6 Beine:")
        for leg in self.LEG_NAMES:
            self._do_log(leg)

    def save(self):
        import json
        fname = "leg_positions.json"
        with open(fname, 'w') as fh:
            json.dump(self._logged, fh, indent=2)
        print(f"  💾 Gespeichert: {fname}  ({len(self._logged)} Beine)")
        for leg, entry in self._logged.items():
            print(f"    {leg}: base_z={entry['base_z']:.4f}  "
                  f"angles={entry['angles_deg']}°")

    def update_display(self):
        """Debug-Text alle 8 Frames aktualisieren."""
        if not self.active:
            # Alte Texte löschen wenn Tuner abgeschaltet
            if self._dbg_ids:
                for d in self._dbg_ids:
                    try: p.removeUserDebugItem(d)
                    except: pass
                self._dbg_ids.clear()
            return

        self._dbg_frame += 1
        if self._dbg_frame % 8 != 0:
            return

        for d in self._dbg_ids:
            try: p.removeUserDebugItem(d)
            except: pass
        self._dbg_ids.clear()

        robot_id = self.ctrl.robot_id
        if robot_id is None:
            return

        # Fußposition berechnen
        leg_name = self.selected_leg
        foot_idx = self.ctrl._foot_link_idx.get(leg_name, -1)
        if foot_idx < 0:
            return

        foot_w = p.getLinkState(robot_id, foot_idx)[0]

        # Körper-Frame
        base_pos, base_orn = p.getBasePositionAndOrientation(robot_id)
        inv_pos, inv_orn   = p.invertTransform(base_pos, base_orn)
        foot_b, _          = p.multiplyTransforms(inv_pos, inv_orn,
                                                   foot_w, [0,0,0,1])

        # Aktuelle Winkel
        jmap = self.ctrl.joint_map
        def get_a(joint):
            return math.degrees(p.getJointState(robot_id, jmap[joint])[0])
        c_deg = get_a(f'{leg_name}_coxa_joint')
        f_deg = get_a(f'{leg_name}_femur_joint')
        t_deg = get_a(f'{leg_name}_tibia_joint')

        lines = [
            f"🎛  {leg_name}",
            f"Coxa:  {c_deg:+6.1f}°",
            f"Femur: {f_deg:+6.1f}°",
            f"Tibia: {t_deg:+6.1f}°",
            f"foot_body: ({foot_b[0]:+.3f}, {foot_b[1]:+.3f}, {foot_b[2]:+.3f})",
            f"base_z = {foot_b[2]:.4f}",
            f"Geloggt: {list(self._logged.keys())}",
        ]
        colors = [
            [1.0, 0.9, 0.2],
            [0.9, 0.9, 0.9], [0.9, 0.9, 0.9], [0.9, 0.9, 0.9],
            [0.6, 1.0, 0.6],
            [0.2, 1.0, 0.5],
            [0.8, 0.8, 0.5],
        ]
        x0 = base_pos[0] - 0.70
        y0 = base_pos[1] - 0.05
        for i, (line, color) in enumerate(zip(lines, colors)):
            did = p.addUserDebugText(
                line, [x0, y0, base_pos[2] + 0.50 - i*0.065],
                textColorRGB=color, textSize=1.1, lifeTime=0.12)
            self._dbg_ids.append(did)

        # Fußpunkt markieren
        did = p.addUserDebugText("◆", list(foot_w),
            textColorRGB=[1,0.2,0.2], textSize=2.0, lifeTime=0.12)
        self._dbg_ids.append(did)

    # ── Intern ────────────────────────────────────────────────────────
    def _sync_sliders_to_leg(self):
        """Slider-Werte auf aktuelle Gelenkwinkel setzen (nur Anzeige-Tipp)."""
        # PyBullet Slider haben kein "setValue" API — wir können nur lesen.
        # Deshalb: Info im Terminal ausgeben.
        robot_id = self.ctrl.robot_id
        if robot_id is None or not self._initialized:
            return
        jmap = self.ctrl.joint_map
        leg  = self.selected_leg
        def get_d(joint):
            return math.degrees(p.getJointState(robot_id, jmap[joint])[0])
        c = get_d(f'{leg}_coxa_joint')
        f = get_d(f'{leg}_femur_joint')
        t = get_d(f'{leg}_tibia_joint')
        print(f"    Aktuelle Winkel: C={c:.1f}° F={f:.1f}° T={t:.1f}°")
        print(f"    → Slider manuell anpassen")

    def _do_log(self, leg_name):
        robot_id = self.ctrl.robot_id
        foot_idx = self.ctrl._foot_link_idx.get(leg_name, -1)
        if foot_idx < 0:
            print(f"  ⚠️  {leg_name}: kein Fuß-Link gefunden")
            return

        foot_w = p.getLinkState(robot_id, foot_idx)[0]
        base_pos, base_orn = p.getBasePositionAndOrientation(robot_id)
        inv_pos, inv_orn   = p.invertTransform(base_pos, base_orn)
        foot_b, _          = p.multiplyTransforms(inv_pos, inv_orn,
                                                   foot_w, [0,0,0,1])

        jmap = self.ctrl.joint_map
        def get_d(joint):
            return round(math.degrees(
                p.getJointState(robot_id, jmap[joint])[0]), 1)

        entry = {
            "angles_deg": [get_d(f'{leg_name}_coxa_joint'),
                           get_d(f'{leg_name}_femur_joint'),
                           get_d(f'{leg_name}_tibia_joint')],
            "foot_world": [round(v, 4) for v in foot_w],
            "foot_body":  [round(v, 4) for v in foot_b],
            "base_z":     round(foot_b[2], 4),
            "body_h":     round(base_pos[2], 4),
        }
        self._logged[leg_name] = entry
        print(f"  📍 {leg_name}: C={entry['angles_deg'][0]}° "
              f"F={entry['angles_deg'][1]}° T={entry['angles_deg'][2]}°  "
              f"base_z={entry['base_z']:.4f}  "
              f"foot_body=({foot_b[0]:.3f},{foot_b[1]:.3f},{foot_b[2]:.3f})")



class SlarcController:
    def __init__(self):
        self.kin = HexapodKinematics()
        self.ik = self.kin              # Alias (V4-Kompatibilität)
        self.balance = BalanceController()
        self.auto_balance = False
        self.roll_bal = 0.0; self.pitch_bal = 0.0
        # Wackelbrett (Balance-Test): kinematisch gekippte Plattform
        self.wobble_id = None; self.wobble_active = False
        self.wobble_t = 0.0; self.wobble_origin = None
        self.robot_id = None
        self.joint_map = {}
        self.cameras = None

        body_l = BODY_L; body_w = BODY_W; mid_y_off = MID_Y_OFFSET
        self.legs = [
            HexapodLeg("front_right",  body_l/2, -body_w/2, -math.radians(30)),
            HexapodLeg("front_left",   body_l/2,  body_w/2,  math.radians(30)),
            HexapodLeg("mid_right",    0,        -(body_w/2 + mid_y_off), -math.radians(90)),
            HexapodLeg("mid_left",     0,         (body_w/2 + mid_y_off),  math.radians(90)),
            HexapodLeg("rear_right",  -body_l/2, -body_w/2, -math.radians(150)),
            HexapodLeg("rear_left",   -body_l/2,  body_w/2,  math.radians(150))
        ]

        self.gait_mode = 1
        self.gait_phase = 0.0
        self.step_height = 0.04
        # Req 1: kinematische Schritthöhen-Obergrenze (relativ zum Nennstand)
        self.STEP_H_MAX = self.kin.step_h_max(-self.kin.BODY_H_NOM)
        self.cmd_vel_x = 0.0; self.cmd_vel_y = 0.0; self.cmd_yaw = 0.0
        self.cur_vel_x = 0.0; self.cur_vel_y = 0.0; self.cur_yaw = 0.0
        self.move_intent = 0.0

        # Req 2: Körperhöhe absolut in [BODY_H_MIN, BODY_H_MAX].
        # Intern weiter als Offset zum Nennstand geführt (StairClimber-kompat.):
        #   body_height = BODY_H_NOM + body_height_offset
        self.body_height_offset = 0.0
        self.BHO_MIN = self.kin.BODY_H_MIN - self.kin.BODY_H_NOM   # ≈ -0.190
        self.BHO_MAX = self.kin.BODY_H_MAX - self.kin.BODY_H_NOM   # ≈ +0.112
        self.pitch = 0.0; self.roll = 0.0
        self.cg_offset_x = 0.0
        self.mid_leg_offset = 0.0
        self.rear_leg_offset = 0.0
        self.zentaur_progress = 0.0
        self.climb_progress = 0.0          # Mode 5: Einblenden des Kletterstands
        self.climb_z = -0.02               # aktuelle Greifer-Aufsetzebene (Mode 5)
        # ── Treppen-Wellengang (Mode 5) ──────────────────────────────
        self.climb_kind = 0                # 0 = FIXED (rise/run), 1 = ADAPTIV
        self.stair_rise = STAIR_RISE       # FIXED: Stufenhöhe [m] (= Sim-Treppe)
        self.stair_run  = STAIR_RUN        # FIXED: Stufentiefe [m] (= Sim-Treppe)
        self.climb_pitch = 0.0             # eingeschwungener Anstellwinkel [rad]
        # Schwung-Hub im Treppenmodus: ABSOLUT (von step_height entkoppelt,
        # damit eine hohe Schritthöhe das Klettern nicht sprengt) und
        # reichweiten-sicher. Körper-Crouch verschafft Reichweiten-Reserve.
        self.climb_lift = 0.22             # vertikaler Hub [m]
        self.climb_crouch = 0.05           # Körper tiefer → mehr Reichweite
        self.mid_crouch = 0.0
        self.rear_crouch = 0.0
        # Manueller Heck-Höhen-Trim (unabhängig von Pitch): hebt/senkt die
        # Hinterbeine. >0 = Heck anheben (Beine strecken sich nach unten).
        self.rear_lift = 0.0
        self.REAR_LIFT_MIN = -0.10
        self.REAR_LIFT_MAX = 0.09        # Heck bis ~Reichweitengrenze anheben
        # Mittelbein-Trim: >0 = Mittelfüße ANHEBEN. Bis deutlich ÜBER
        # Schulterhöhe (Fuß > Hüftebene), begrenzt nur durch die Reichweite.
        self.mid_lift = 0.0
        self.MID_LIFT_MIN = -0.06        # absenken (durch Reichweite begrenzt)
        self.MID_LIFT_MAX = 0.45         # Füße über Schulterhöhe heben
        self.gripper_active = False
        self.grip_blend = 0.0
        self.arm_lift_offset = 0.0
        # Greifer-Absenkung: bis nahe an die volle Beinstreckung nach unten.
        self.ARM_LIFT_MIN = -0.34          # Greifer tief absenken (Stufenkante)
        self.ARM_LIFT_MAX = 0.15
        self.arm_reach_offset = 0.22
        self.ARM_REACH_MAX = 0.34          # weiter nach vorne zur Stufe (Mode 4)
        self.CLIMB_REACH_MAX = 0.26        # Mode 5: weiter ausfahren (s. Hinweis)

        self.phases_tripod = {"front_left": 0.0, "mid_right": 0.0, "rear_left": 0.0,
                              "front_right": 0.5, "mid_left": 0.5, "rear_right": 0.5}
        self.phases_ripple = {"front_left": 0.0,   "mid_right": 0.0,
                              "mid_left": 0.333,   "rear_right": 0.333,
                              "rear_left": 0.666,  "front_right": 0.666}
        self.phases_quad   = {"mid_left": 0.0, "rear_right": 0.25,
                              "mid_right": 0.5, "rear_left": 0.75}
        # Wellengang (Mode 5/Treppe): NUR EIN Bein schwingt, 5 tragen.
        # Seiten ALTERNIEREND (R,L,R,L,R,L) → minimiert Rollen/Waddeln, das
        # sonst eine Seite an den Reichweitenrand drückt (rechtes Bein!).
        self.phases_wave   = {"rear_right": 0/6,  "mid_left": 1/6,
                              "front_right": 2/6,  "rear_left": 3/6,
                              "mid_right": 4/6,    "front_left": 5/6}
        self.max_stride_x = 0.14
        self.max_stride_y = 0.10
        # Req 4: kollisionsfreie Schrittlängen-Obergrenze aus den
        # Abständen benachbarter Ruhe-Fußpunkte herleiten.
        self.MAX_STRIDE = self._compute_max_stride()

        self._cam_frame = 0
        self._show_cam  = False

        # Performance: Foot-Link-Indices gecacht (init nach loadURDF)
        self._foot_link_idx = {}   # leg_name → link_idx
        # Kontakt-Cache: einmal pro Frame aktualisiert
        self._contact_cache = []
        self._contact_frame = -1

        # Modus 3: Neutrale Beinposition adaptiv verschieben
        # Im Treppensteigen: Front-Beine näher zur Körpermitte (weniger weit vorne),
        # Rear-Beine näher zur Mitte (weniger weit hinten) → Mittelbeine kommen auf Stufe
        self._stair_x_bias = 0.0   # aktueller Bias [0..1], smooth interpoliert
        # Effektive Basis-Positionen nach Coxa-Schwenk (gecacht)
        self._eff_base = {n: (l.base_x, l.base_y)
                          for n, l in zip(
                              ['front_right','front_left','mid_right',
                               'mid_left','rear_right','rear_left'],
                              self.legs)}
        # Standbein-Einfrierung: verhindert Bodenschleifen beim Bias-Wechsel
        # None = nicht eingefroren, float = eingefrorene Ziel-X beim Aufsetzen
        leg_names = ['front_right','front_left','mid_right',
                     'mid_left','rear_right','rear_left']
        self._leg_stance_x = {n: None for n in leg_names}  # None oder (x, y) Tuple

        # Modus 3 — Adaptive Terrain (Probe-and-Plant)
        self._leg_floor_z   = {n: 0.0   for n in leg_names}  # Welt-Z letzter Kontakt
        self._leg_frozen    = {n: None  for n in leg_names}  # eingefrorenes step_z
        self._leg_descend   = {n: False for n in leg_names}  # Extended-Descent aktiv
        self._leg_desc_step = {n: 0.0   for n in leg_names}  # step_z im Descent

        # Stall-Erkennung pro Bein (portabel) + zuletzt kommandierter Coxa-Winkel
        self._stall    = {n: StallGuard() for n in leg_names}
        self._cmd_coxa = {n: 0.0 for n in leg_names}
        self.RECOVER_LIFT = 0.10   # zusätzl. Hub beim Freikommen [m]

        # ── Modus 6: deterministischer Foothold-Tripod-Gang ──────────────
        # Perception-Abstraktion (Sim: bekannte Geometrie; HW: Höhenkarte).
        self.stairs = StairModel(STAIR_RISE, STAIR_RUN, x_start=1.0, n_up=5,
                                 plateau_len=1.0)
        self.FH_STAND     = 0.150   # Körperhöhe über Stützfläche [m]
        self.FH_AHEAD     = 0.05    # Vorgriff des Schwungfußes [m]
        self.FH_ADV       = 0.09    # max. Körpervorschub je Halbzyklus [m]
        self.FH_LIFT      = 0.10    # Schwung-Bogenhöhe [m]
        self.FH_PITCH_FRAC= 0.6     # Anteil der Steigung als Körper-Pitch
        self.FH_PITCH_SLEW= 0.04    # rad je Halbzyklus (sanfte Pitch-Annäherung)
        self.FH_LOOKAHEAD = 0.06    # Vorausschau für Foothold-Wahl [m]
        self.FH_RADIUS    = 0.22    # radialer Standabstand (def_x)
        self.FH_TA = ['front_right', 'mid_left',  'rear_right']  # Tripod A
        self.FH_TB = ['front_left',  'mid_right', 'rear_left']   # Tripod B
        self._fh_ready    = False   # beim Betreten initialisieren
        self._fh_bx       = 0.0     # gerenderte (interpolierte) Körper-x [m]
        self._fh_pitch    = 0.0     # gerenderter Körper-Pitch [rad]
        self._fh_bx0      = 0.0     # Halbzyklus-Start x
        self._fh_bxT      = 0.0     # Halbzyklus-Ziel  x
        self._fh_p0       = 0.0     # Halbzyklus-Start Pitch
        self._fh_pT       = 0.0     # Halbzyklus-Ziel  Pitch
        self._fh_phase    = 0.0     # 0..1 innerhalb des Halbzyklus
        self._fh_swingA   = True    # True: Tripod A schwingt, B steht
        self._fh_foot     = {n: (0.0, 0.0, 0.0) for n in leg_names}  # Welt-Footholds
        self._fh_from     = {n: (0.0, 0.0, 0.0) for n in leg_names}  # Schwung-Start

        # ── Modus 7: empirischer Tast-Treppengang (blind, reaktiv) ────────
        self.M7_RADIUS    = 0.22    # radialer Neutral-Standabstand
        self.M7_Z_STAND   = -0.160  # Fuß-z unter Körper im Stand [m]
        self.M7_Z_TOP     = -0.020  # höchste Fußlage (Workspace-nah) [m]
        self.M7_LIFT0     = 0.07    # Grund-Anhebung beim Schwung [m]
        self.M7_LIFT_STEP = 0.010   # Hub-Geschwindigkeit [m/Frame] (sanft → kein Abstoß beim Anheben)
        self.M7_STRIDE    = 0.10    # halbe fore-aft-Spanne (Vor/Zurück) [m]
        self.M7_REACH_V   = 0.007   # Vorwärts-Tastgeschw. [m/Frame]
        self.M7_PROBE_V   = 0.005   # Absenk-/Anhebegeschw. [m/Frame]
        self.M7_SWEEP_V   = 0.0025  # Stand-Rückschwung [m/Frame] (5 Beine → langsamer)
        self.M7_FOLLOW_MAX= 0.16    # max. Boden-Nachführen unter Nennstand [m]
        self.M7_SETTLE    = 200     # Frames: erst Stand sichern, dann gehen
        self.M7_SEEK_DB   = 8       # Frames Kontaktverlust bevor Fuß nachfasst
        self.M7_YAW_RATE  = 0.012   # Drehrate: rad/Frame je Einheit cmd_yaw
        self.M7_LOAD_TH   = 0.70    # Servo-Last-Schwelle = Riser/Blockade
        self.M7_BODY_H    = 0.16    # Ziel-Körperhöhe über der Referenzstufe (Mittelbeine) [m]
        self.M7_PITCH_SP_SIGN = -1.0  # Steigung → Pitch-Sollwert (nose-up). Im GUI
        #   umdrehen, falls der Körper beim Klettern falsch herum kippt.
        self.M7_PITCH_LP  = 0.03    # Tiefpass auf den Pitch-Sollwert (kein Leapfrog-Ruck)
        self.M7_CLIMB_H   = 0.13    # niedrigere Ziel-Höhe BEIM KLETTERN: Körper darf
        #   nicht so hoch über den höchsten Fuß, dass die unteren (Hinter-)Beine
        #   den Boden nicht mehr erreichen (max. ~0.24 m unter Hüfte bei neutral).
        self.M7_REACH_LIMIT = 0.31  # nutzbare Bein-Reichweite Mount→Fuß [m] (mit Marge
        #   unter dem geom. Max ~0.325) für den Über-Streckungs-Deckel der Höhenregelung.
        self.M7_HREG      = 0.010   # Regler-Schritt: Mittelbeine ziehen Körper auf Zielhöhe [m/Frame]
        self.M7_HGAIN     = 0.04    # P-Verstärkung Körperhöhen-Regler (Welt-Fehler → Schritt)
        #   0.10 war zu hoch: beim Klettern springt der höchste Fuß (top) eine Stufe
        #   hin/her, während die Vorderfüße leapfroggen → der Körper hüpfte voll mit.
        #   0.04 glättet die Sprünge (folgt in ~25 statt 10 Frames, reicht fürs Steigen).
        self.M7_Z_CLIMB   = 0.0     # Hub-Ziel = Coxa-Höhe (Fußspitze auf Gelenkebene)
        self.M7_Z_CLIMB_UP = 0.05   # Hub-Ziel BEIM KLETTERN: ÜBER Coxa-Höhe → Reserve,
        #   damit der Schwungfuß den nächsten Riser klar überragt statt anzustoßen.
        self.M7_RETRACT    = 0.10   # EINSTELLBAR: Wind-up-Rückzug [m] — Fuß im Hub erst
        #   so weit nach HINTEN (weg vom Riser), dann hoch+vor → Bogen statt L. Mehr =
        #   mehr Abstand zur Kante. Grenze ~0.12 (sonst Fuß hinter den Frontmount).
        self.M7_RETRACT_V  = 0.008  #   Rückzug-Geschwindigkeit [m/Frame] (so groß, dass
        #   die Distanz in der Hub-Zeit auch erreicht wird).
        self.M7_PITCH_MAX  = 0.22   # Sicherheits-Deckel auf den Pitch-Sollwert [rad].
        #   5-cm-Stufe: atan2(0.05,0.25)≈0.197 → 0.22 kappt die über-schätzende
        #   FK-Mitkopplung genau am ECHTEN Steigungswert. Für 10 cm später auf ~0.38.
        self.M7_SEEK_V     = 0.004  # Stance-Boden-Suche: hängender Standfuß senkt sich
        #   mit dieser Rate [m/Frame], bis er Kontakt spürt → volles Stützpolygon.
        self.M7_STRIDE_CLIMB = 0.10 # Vorwärts-Schwenk auf Coxa-Höhe [m] (Reichweite max)
        self.M7_LIFT_CLEAR = 0.02   # Fuß gilt als "oben", wenn < CLEAR unter Coxa
        #   → hebt auf Welt ~0.14 m, Spiel +0.04 m über die 0.10-Stufe (vorher
        #   0.05 = nur 0.01 m Spiel → schrammte in die senkrechte Stufenwand)
        self.M7_LIFT_RISE  = 0.17   # ODER: Fuß um diesen Betrag über Aufsetzhöhe gehoben
        self.M7_MAX_DEFLECT= 0.15   # max. Fußauslenkung aus Neutrallage [m] (gegen Bein-Kreuzen)
        self.M7_LIFT_CAP   = 150    # Sicherheits-Timeout für die Hub-Phase [Frames]
        self.M7_BODY_V     = 0.0003 # kontinuierlicher Körper-Vortrieb je Frame [m]
        #   → Schwenk-Zeit (2·STRIDE/BODY_V) = Stand-Phase (5·T_swing): kein
        #   Über-Schwenken bis back_lim mehr (vorher 0.0005 → Hinterfuß auf 0.45
        #   horizontal = unerreichbar). Körper ~0.072 m/s.
        self.M7_BODY_OFFSET = 0.22  # EINSTELLBAR: Soll-Abstand Körper↔vorderster Fuß.
        #   Der Körper fährt nur vor, bis der vorderste Standfuß OFFSET vor ihm steht,
        #   dann wartet er aufs nächste Aufsetzen → schwenkt NIE über den Fuß, keilt
        #   kein Schienbein in den Riser. Frontbein-Spanne 0.19..0.39 (neutral 0.29):
        #   größer = Körper bleibt weiter hinten (mehr Reserve, langsamer); kleiner =
        #   näher dran (schneller, Keil-Risiko). Tunen am GUI/Harness.
        self.M7_BACK_LIM   = -0.08  # EINSTELLBAR: max. Rücklage eines Standfußes hinter
        #   die Neutrale [m], bevor der Körper-Vortrieb stoppt (Hinten-Gate). Bei
        #   z≈0.21 überstreckt ein Bein ab ~0.088 Rücklage → -0.08 hält es davor.
        #   Weniger negativ = enger (mehr Reserve, häufigeres Nachsetzen); mehr
        #   negativ = lockerer (Schleif-/Überstreck-Risiko).
        self.M7_HEAD_KP    = 0.06   # Kursregler: Yaw-Korrektur je rad Kursfehler
        self.M7_YAW_MAX    = 0.006  # max. Yaw-Korrektur je Frame [rad] (sanft → kein Kreuzen)
        # WELLENGANG-Reihenfolge: IMMER mit dem VORDEREN Paar
        # beginnen, dann Mitte, dann hinten. Beim Steigen setzen die Vorderbeine
        # zuerst auf die nächste Stufe (noch Platz, kein Drücken gegen die Kante),
        # während Mittel-/Hinterbeine die breite Stützbasis halten und zuletzt
        # nachziehen. Hinten-zuerst schrumpfte die hintere Stütze zu früh und
        # warf SLARC beim Vorderbein-Umsetzen nach hinten um.
        self.M7_WAVE = ['front_right', 'front_left', 'mid_right',
                        'mid_left', 'rear_right', 'rear_left']
        self._m7_ready    = False
        self._m7_state    = {n: 'STANCE' for n in leg_names}
        self._m7_foot     = {n: [0.0, 0.0, 0.0] for n in leg_names}  # Körperframe
        self._m7_liftz    = {n: 0.0 for n in leg_names}  # akt. Schwung-Zielhöhe
        self._m7_wave_i   = 0       # Index des aktuell schwingenden Beins
        self._m7_settle_left = 0    # Frames Settle-Phase übrig
        self._m7_nocontact   = {n: 0 for n in leg_names}  # Kontaktverlust-Zähler
        self._m7_planted_z   = {n: self.M7_Z_STAND for n in leg_names}  # gemerkte Aufsetzhöhe
        self._m7_onstep      = {n: False for n in leg_names}  # Fuß auf einer Stufe (Regler aus)
        self._m7_climbing    = False   # ist gerade im Treppen-Klettermodus (Hub höher)
        self._m7_use_fk      = False   # Pitch aus FK/Ist-Position statt Fußzielen
        self._m7_climb_pitch_sp = 0.0  # Pitch-Sollwert für den Balancer (Fußebene)
        self._m7_swing_n     = {n: 0 for n in leg_names}  # Frames in der Hub-Phase
        self._m7_lift_z0     = {n: 0.0 for n in leg_names}  # Fuß-Welt-z bei Hub-Beginn
        self._m7_phase       = 'WAVE'    # kontinuierlicher Wellengang
        self._m7_yaw_target  = None      # zu haltender Kurs [rad] (beim Losgehen gesetzt)

        # StairClimber (Modus N)
        self.stair_climber = ContinuousStairClimber(self)
        # Manual Leg Tuner (M-Taste)
        self.tuner = ManualLegTuner(self)
        # Bewegungslogger (V-Taste) — CSV für Offline-Analyse
        self.logger = MotionLogger(self)

    def init_pybullet(self, gui=True, build_stairs=True, spawn_can=True):
        generate_hexapod_urdf("slarc_primitives.urdf")
        p.connect(p.GUI if gui else p.DIRECT)
        # Eingebaute GUI-Tastenkürzel abschalten (w=Wireframe, g=Panels,
        # v=Visuals aus, j/k/l, s … kollidieren sonst mit unserer Steuerung).
        # Unsere eigene Tastenabfrage via getKeyboardEvents bleibt aktiv.
        if gui:
            p.configureDebugVisualizer(p.COV_ENABLE_KEYBOARD_SHORTCUTS, 0)
        p.setAdditionalSearchPath(pybullet_data.getDataPath())
        p.setGravity(0, 0, -9.81)
        p.setPhysicsEngineParameter(fixedTimeStep=1./240.,
                                    numSolverIterations=150, numSubSteps=2)

        planeId = p.loadURDF("plane.urdf")
        _set_contact(planeId)

        self.robot_id = p.loadURDF("slarc_primitives.urdf", [0, 0, 0.20])

        for i in range(p.getNumJoints(self.robot_id)):
            info = p.getJointInfo(self.robot_id, i)
            joint_name = info[1].decode('utf-8')
            self.joint_map[joint_name] = i
            if "foot" in joint_name:
                _set_contact(self.robot_id, i, FOOT_FRICTION)
                # Leg-Name aus Joint-Name extrahieren und cachen
                leg = joint_name.replace('_foot_joint', '')
                self._foot_link_idx[leg] = i

        if spawn_can:
            can_mass = 0.350; can_radius = 0.033; can_height = 0.115
            col_can = p.createCollisionShape(p.GEOM_CYLINDER,
                        radius=can_radius, height=can_height)
            vis_can = p.createVisualShape(p.GEOM_CYLINDER,
                        radius=can_radius, length=can_height,
                        rgbaColor=[0.8, 0.1, 0.1, 1])
            self.can_id = p.createMultiBody(can_mass, col_can, vis_can,
                                            basePosition=[0.37, 0, 0.06])
            p.changeDynamics(self.can_id, -1, lateralFriction=2.0,
                             spinningFriction=0.1, rollingFriction=0.1)
        else:
            self.can_id = None

        if build_stairs:
            print("\n  Erzeuge Treppenkomplex...")
            create_staircase()
        if gui:
            print("\n  Initialisiere Stereo-Kameras...")
            self.cameras = StereoCameras()
        else:
            self.cameras = None

        for _ in range(120): p.stepSimulation()
        for i in range(p.getNumJoints(self.robot_id)):
            p.changeDynamics(self.robot_id, i, jointDamping=0.05)
        self.cmd_vel_x = 0.0; self.cmd_vel_y = 0.0
        for _ in range(120): self.update_gait(); p.stepSimulation()
        if gui:
            self.tuner.init_sliders()

    # ====================================================================
    # MODUS 6 — Deterministischer Foothold-Tripod-Gang
    # ====================================================================
    # Statt periodischem "Wackeln, bis es passt" werden die Fußaufsatzpunkte
    # (Footholds) in WELTkoordinaten geplant: auf Tritt-Mitten (nicht auf
    # Kanten), je Bein, im erreichbaren Arbeitsraum. Ein Tripod (3 Beine)
    # schwingt zu seinen neuen Footholds, während der andere stützt; der
    # Körper rückt nur so weit vor, dass die Standbeine erreichbar bleiben.
    # Offline verifiziert: Schwung-Footholds 100% erreichbar (4..17cm),
    # Standbeine 100% (<=12cm) bzw. mm-Transienten (17cm), ganze Treppe.
    #
    # Portabel: Planung/Transform/IK = einfache Mathematik. Sim liefert die
    # virtuelle Körperpose; auf HW kommt sie aus Odometrie + StairModel aus
    # der perzipierten Höhenkarte. Geometrie identisch.

    def _fh_mount_world(self, leg):
        """Hüftgelenk in Weltkoordinaten bei virtueller Körperpose."""
        cp = math.cos(self._fh_pitch); sp = math.sin(self._fh_pitch)
        bz = self.stairs.height_at(self._fh_bx) + self.FH_STAND
        return (self._fh_bx + leg.mount_x * cp,
                leg.mount_y,
                bz - leg.mount_x * sp)

    def _fh_local(self, leg, F):
        """Welt-Foothold F → Bein-Hüftframe (lx, ly, dz) für solve()."""
        cp = math.cos(self._fh_pitch); sp = math.sin(self._fh_pitch)
        bz = self.stairs.height_at(self._fh_bx) + self.FH_STAND
        fbx = (F[0] - self._fh_bx) * cp + (F[2] - bz) * sp
        fby =  F[1]
        fbz = -(F[0] - self._fh_bx) * sp + (F[2] - bz) * cp
        dx = fbx - leg.mount_x; dy = fby - leg.mount_y
        lx =  dx * math.cos(leg.mount_yaw) + dy * math.sin(leg.mount_yaw)
        ly = -dx * math.sin(leg.mount_yaw) + dy * math.cos(leg.mount_yaw)
        return lx, ly, fbz

    def _fh_reachable(self, leg, F):
        lx, ly, dz = self._fh_local(leg, F)
        return self.ik.solve(lx, ly, dz)[3]

    def _fh_neutral_xy(self, leg, ahead=0.0):
        """Radialer Neutral-Foothold (x,y) in Welt, Bein zeigt nach mount_yaw."""
        mwx, mwy, _ = self._fh_mount_world(leg)
        return (mwx + self.FH_RADIUS * math.cos(leg.mount_yaw) + ahead,
                mwy + self.FH_RADIUS * math.sin(leg.mount_yaw))

    def _fh_plan_foothold(self, leg):
        """Foothold wählen: erreichbar; bevorzugt mit Vorwärtsmarge (überlebt
        FH_LOOKAHEAD Körpervorschub), sonst der VORDERSTE erreichbare Tritt –
        das holt die Hinterbeine rechtzeitig auf die nächste Stufe, statt sie
        auf der niedrigen Stufe kleben und den Körper blockieren zu lassen."""
        fx0, fy0 = self._fh_neutral_xy(leg, self.FH_AHEAD)
        cands = []
        for d in (0.0, 0.04, -0.04, 0.08, -0.08, 0.12, -0.12,
                  0.16, -0.16, 0.20, 0.24):
            fx = self.stairs.tread_center(fx0 + d)
            F = (fx, fy0, self.stairs.height_at(fx))
            if self._fh_reachable(leg, F):
                cands.append((abs(d), F, fx))
        if not cands:
            fx = self.stairs.tread_center(fx0)
            return (fx, fy0, self.stairs.height_at(fx))
        # Vorausschau: Footholds, die auch nach FH_LOOKAHEAD noch erreichbar sind
        save = self._fh_bx
        surv = []
        for ad, F, fx in cands:
            self._fh_bx = save + self.FH_LOOKAHEAD
            if self._fh_reachable(leg, F):
                surv.append((ad, F, fx))
            self._fh_bx = save
        if surv:
            surv.sort(key=lambda t: t[0])      # nächster an Neutralstellung
            return surv[0][1]
        cands.sort(key=lambda t: -t[2])        # sonst der vorderste Tritt
        return cands[0][1]

    def _fh_plan_halfcycle(self):
        """Eine Halbzyklus-Bewegung planen: Zielpose (Vorschub gedrosselt durch
        Standbein-Erreichbarkeit, Pitch pro Halbzyklus angenähert) und neue
        Schwung-Footholds bei der Zielpose. _stair_freegait interpoliert dann
        Körper + Schwungbeine über die Frames bis dorthin."""
        legmap = {leg.name: leg for leg in self.legs}
        swing = self.FH_TA if self._fh_swingA else self.FH_TB
        stance = [n for n in legmap if n not in swing]
        self._fh_bx0 = self._fh_bx
        self._fh_p0  = self._fh_pitch
        # größten reichweiten-zulässigen Vorschub suchen (×0.6, KEIN 0-Floor:
        # ein winziges Restkriechen ermöglicht das Lösen aus Klemmlagen)
        a = self.FH_ADV
        save_bx, save_p = self._fh_bx, self._fh_pitch
        for _ in range(14):
            np_ = self._fh_p0 + _clamp(
                self.FH_PITCH_FRAC * self.stairs.slope_at(self._fh_bx0 + a)
                - self._fh_p0, -self.FH_PITCH_SLEW, self.FH_PITCH_SLEW)
            self._fh_bx = self._fh_bx0 + a
            self._fh_pitch = np_
            if all(self._fh_reachable(legmap[n], self._fh_foot[n])
                   for n in stance):
                break
            a *= 0.6
        self._fh_bx, self._fh_pitch = save_bx, save_p
        self._fh_bxT = self._fh_bx0 + a
        self._fh_pT  = self._fh_p0 + _clamp(
            self.FH_PITCH_FRAC * self.stairs.slope_at(self._fh_bxT)
            - self._fh_p0, -self.FH_PITCH_SLEW, self.FH_PITCH_SLEW)
        # Schwung-Footholds bei der ZIELpose planen
        self._fh_bx, self._fh_pitch = self._fh_bxT, self._fh_pT
        for n in swing:
            self._fh_from[n] = self._fh_foot[n]
            self._fh_foot[n] = self._fh_plan_foothold(legmap[n])
        self._fh_bx, self._fh_pitch = self._fh_bx0, self._fh_p0
        self._fh_phase = 0.0

    def _enter_freegait(self):
        """Modus 6 betreten: virtuelle Pose aus Ist-Lage, Footholds setzen,
        ersten Halbzyklus planen."""
        pos, _ = p.getBasePositionAndOrientation(self.robot_id)
        self._fh_bx = pos[0]
        self._fh_pitch = 0.0
        self._fh_phase = 0.0
        self._fh_swingA = True
        self._fh_bx0 = self._fh_bxT = self._fh_bx
        self._fh_p0  = self._fh_pT  = 0.0
        for leg in self.legs:
            fx, fy = self._fh_neutral_xy(leg, 0.0)
            F = (fx, fy, self.stairs.height_at(fx))
            self._fh_foot[leg.name] = F
            self._fh_from[leg.name] = F
        self._fh_ready = True
        self._fh_plan_halfcycle()      # erste Schwunggruppe (TA) planen
        self.auto_balance = True
        print("[Modus 6] Foothold-Tripod-Gang aktiv — deterministische "
              "Fußplatzierung auf Tritten.")

    def _stair_freegait(self):
        if not self._fh_ready:
            self._enter_freegait()

        legmap = {leg.name: leg for leg in self.legs}
        swing = self.FH_TA if self._fh_swingA else self.FH_TB

        # ── Phasenfortschritt aus Fahrbefehl (Pfeil↑/↓, +/−) ──
        speed = abs(self.cmd_vel_x)
        dphase = 0.0 if speed < 1e-4 else min(0.05, 0.012 + speed * 0.05)
        self._fh_phase += dphase

        # ── Körperpose über den Halbzyklus interpolieren (smoothstep). Die
        #    Zielpose (_fh_bxT/_fh_pT) ist so geplant, dass die Standbeine
        #    erreichbar bleiben → Zwischenposen sind es erst recht. ──
        t = self._fh_phase if self._fh_phase < 1.0 else 1.0
        s = t * t * (3.0 - 2.0 * t)
        self._fh_bx    = self._fh_bx0 + (self._fh_bxT - self._fh_bx0) * s
        self._fh_pitch = self._fh_p0  + (self._fh_pT  - self._fh_p0)  * s

        # ── Stall-Überwachung + IK für alle Beine ──
        for leg in self.legs:
            cidx = self.joint_map.get(f"{leg.name}_coxa_joint")
            recovering = False
            if cidx is not None:
                js = p.getJointState(self.robot_id, cidx)
                pos_err = abs(self._cmd_coxa[leg.name] - js[0])
                load_frac = abs(js[3]) / SERVO_STALL_NM
                recovering = self._stall[leg.name].update(pos_err, load_frac)

            if leg.name in swing:
                # Schwung: Bogen von _fh_from → _fh_foot mit Lift
                a = self._fh_from[leg.name]; b = self._fh_foot[leg.name]
                fx = a[0] + (b[0] - a[0]) * s
                fy = a[1] + (b[1] - a[1]) * s
                fz = a[2] + (b[2] - a[2]) * s
                fz += self.FH_LIFT * math.sin(math.pi * t)   # Hubbogen
                F = (fx, fy, fz)
            else:
                F = self._fh_foot[leg.name]                  # fester Welt-Tritt

            lx, ly, dz = self._fh_local(leg, F)
            if recovering:
                dz += self.RECOVER_LIFT      # blockiertes Bein zusätzlich heben
            tc, tf, tt, _ok = self.ik.solve(lx, ly, dz)
            ov = self.tuner.get_override_angles(leg.name)
            if ov: tc, tf, tt = ov
            self.set_servo(f"{leg.name}_coxa_joint",  tc)
            self.set_servo(f"{leg.name}_femur_joint", tf)
            self.set_servo(f"{leg.name}_tibia_joint", tt)
            self._cmd_coxa[leg.name] = tc

        # ── Halbzyklus fertig? → Zielpose committen, Gruppen tauschen,
        #    nächsten Halbzyklus planen ──
        if self._fh_phase >= 1.0:
            self._fh_bx = self._fh_bxT
            self._fh_pitch = self._fh_pT
            self._fh_swingA = not self._fh_swingA
            self._fh_plan_halfcycle()

        # Lage-Feedforward für Anzeige/Balance
        self.body_pitch_cmd = self._fh_pitch

    # ====================================================================
    # MODUS 7 — Empirischer Tast-Treppengang (blind, rein reaktiv)
    # ====================================================================
    # KEIN Geländemodell. Jedes Schwungbein TASTET sich:
    #   1. anheben,
    #   2. nach vorne schwingen; spürt es einen Riser (Vorwärts-Kontakt mit
    #      waagerechter Normale ODER Servo-Last über Schwelle), hebt es höher
    #      und schwingt weiter — bis es über der Stufe ist,
    #   3. weiter vor bis zum Bewegungsraum-Ende, dann absenken bis Tritt-
    #      Kontakt (senkrechte Normale) → aufsetzen.
    # Standbeine schieben den Körper vor (fore-aft-Sweep) und folgen per
    # Kontakt dem Boden. Tripod-Wechsel, sobald alle Schwungbeine stehen →
    # immer 3 Beine unten.
    #
    # Vollständig closed-loop über Kontakt/Last — daher NUR in der laufenden
    # Sim bzw. auf der HW prüfbar, nicht offline. Alle Schwellen oben als
    # M7_* gut tunebar. Auf HW: _m7_foot_contact ← Fußkraftsensor/Load,
    # _m7_servo_load ← Present-Load-Register der ST3215.

    def _m7_neutral(self, leg):
        return (leg.mount_x + self.M7_RADIUS * math.cos(leg.mount_yaw),
                leg.mount_y + self.M7_RADIUS * math.sin(leg.mount_yaw))

    def _m7_reach_h(self, leg):
        """Horizontale Mount→Fuß-Strecke im Körperframe (Über-Streckungs-Maß)."""
        f = self._m7_foot[leg.name]
        return math.hypot(f[0] - leg.mount_x, f[1] - leg.mount_y)

    def _m7_set_leg(self, leg, fx, fy, fz):
        """Körperframe-Fußziel → Lage-Rotation (Balancer) → IK → Servos."""
        cidx = self.joint_map.get(f"{leg.name}_coxa_joint")
        recovering = False
        if cidx is not None:
            js = p.getJointState(self.robot_id, cidx)
            pos_err = abs(self._cmd_coxa[leg.name] - js[0])
            load_frac = abs(js[3]) / SERVO_STALL_NM
            recovering = self._stall[leg.name].update(pos_err, load_frac)
        if recovering:
            fz += self.RECOVER_LIFT
        # ── Lage-Überlagerung (Balancer + I/K/J/L-Trim) wie im Hauptpfad ──
        pe = getattr(self, '_m7_pitch_eff', 0.0)
        re = getattr(self, '_m7_roll_eff', 0.0)
        cy = math.cos(pe); sy = math.sin(pe)
        cx = math.cos(re); sx = math.sin(re)
        rx = fx * cy + fz * sy
        rz = -fx * sy + fz * cy
        ry_new = fy * cx - rz * sx
        rz_new = fy * sx + rz * cx
        dx = rx - leg.mount_x; dy = ry_new - leg.mount_y
        lx =  dx * math.cos(-leg.mount_yaw) - dy * math.sin(-leg.mount_yaw)
        ly =  dx * math.sin(-leg.mount_yaw) + dy * math.cos(-leg.mount_yaw)
        tc, tf, tt, _ok = self.ik.solve(lx, ly, rz_new)
        ov = self.tuner.get_override_angles(leg.name)
        if ov: tc, tf, tt = ov
        self.set_servo(f"{leg.name}_coxa_joint",  tc)
        self.set_servo(f"{leg.name}_femur_joint", tf)
        self.set_servo(f"{leg.name}_tibia_joint", tt)
        self._cmd_coxa[leg.name] = tc

    def _m7_foot_world_z(self, leg):
        """Welt-z der Fußspitze (SIM: getLinkState; ESP32: FK aus Present-Position)."""
        idx = self._foot_link_idx.get(leg.name, -1)
        if idx < 0:
            return 0.0
        return p.getLinkState(self.robot_id, idx)[0][2]

    def _m7_foot_plane_pitch(self, use_fk=False):
        """Neigung der Fußebene [rad] = Pitch-Sollwert fürs Treppensteigen.
        Steigung vorn vs. hinten, NUR aus Füßen MIT BODENKONTAKT. Ein Fuß, der
        den Boden berührt, hat Welt-z = echte Geländehöhe dort → KÖRPER-PITCH-
        UNABHÄNGIG. Hängende Füße werden ausgeschlossen — sonst speist der eigene
        Körper-Pitch sich über die FK-Welt-z selbst zurück (Mitkopplung → Runaway).
        Welt-z immer aus getLinkState (IST), nicht aus den Zielen (die enthalten
        über R den Körper-Pitch). HW-Äquivalent: FK aus Present-Position, gewichtet
        mit dem Mikroschalter-Kontakt. Liefert None, wenn vorn ODER hinten kein
        TRAGENDES Bein da ist. Vordere Füße höher (Aufstieg) → Steigung > 0."""
        legmap = {l.name: l for l in self.legs}
        front = ('front_right', 'front_left')
        rear  = ('rear_right',  'rear_left')

        def world_xz(name):
            idx = self._foot_link_idx.get(name, -1)
            if idx < 0:
                return None
            wp = p.getLinkState(self.robot_id, idx)[0]
            return wp[0], wp[2]

        def avg(group):
            pts = []
            for n in group:
                if self._m7_state[n] != 'STANCE':
                    continue
                if not self._m7_foot_contact(legmap[n])[0]:
                    continue          # nur Füße MIT Kontakt → echtes Gelände
                q = world_xz(n)
                if q is not None:
                    pts.append(q)
            if not pts:
                return None
            return (sum(x for x, _ in pts) / len(pts),
                    sum(z for _, z in pts) / len(pts))

        f = avg(front); r = avg(rear)
        if f is None or r is None or abs(f[0] - r[0]) < 1e-3:
            return None
        return math.atan2(f[1] - r[1], f[0] - r[0])

    def _m7_foot_up(self, leg):
        """True, wenn der Fuß PHYSISCH nahe Coxa-Höhe ist. Closed-loop auf die
        echte Beinstellung statt blindes Vertrauen ins Kommando — der weiche
        Positionsservo hinkt dem Sollwert deutlich nach. ESP32: gleiche Prüfung
        aus Present-Position der Femur-/Tibia-Servos."""
        idx = self._foot_link_idx.get(leg.name, -1)
        if idx < 0:
            return True
        bz = p.getBasePositionAndOrientation(self.robot_id)[0][2]
        return (self._m7_foot_world_z(leg) - bz) >= -self.M7_LIFT_CLEAR

    def _m7_foot_contact(self, leg):
        """(touch, |nz|, horiz) aus dem Kontakt-Cache. nz=senkrecht (Tritt),
        horiz=waagerecht (Riser)."""
        idx = self._foot_link_idx.get(leg.name, -1)
        if idx < 0:
            return (False, 0.0, 0.0)
        for c in self._contact_cache:
            if c[3] != idx:   continue
            if c[9] < 0.5:    continue
            n = c[7]
            return (True, abs(n[2]), math.hypot(n[0], n[1]))
        return (False, 0.0, 0.0)

    def _m7_servo_load(self, leg):
        """max Last über die 3 Servos (Riser/Blockade-Erkennung), normiert."""
        mx = 0.0
        for j in ('coxa', 'femur', 'tibia'):
            idx = self.joint_map.get(f"{leg.name}_{j}_joint")
            if idx is None: continue
            mx = max(mx, abs(p.getJointState(self.robot_id, idx)[3]))
        return mx / SERVO_STALL_NM

    def _enter_feeler(self):
        for leg in self.legs:
            nx, ny = self._m7_neutral(leg)
            self._m7_foot[leg.name] = [nx, ny, self.M7_Z_STAND]
            self._m7_state[leg.name] = 'STANCE'
            self._m7_liftz[leg.name] = self.M7_Z_STAND + self.M7_LIFT0
            self._m7_nocontact[leg.name] = 0
        self._m7_wave_i = 0
        self._m7_stand_z = -self.M7_BODY_H   # gemeinsame Standtiefe (Flach-Regler)
        self.body_height_offset = 0.0     # Mode 7 startet auf M7_BODY_H; W/S verstellt
        self._m7_phase = 'WAVE'
        self._m7_yaw_target = None        # Kurs wird beim Losgehen erfasst
        self._m7_onstep = {leg.name: False for leg in self.legs}
        # NOCH NICHT schwingen — erst stabilen 6-Fuß-Stand herstellen (Settle).
        self._m7_settle_left = self.M7_SETTLE
        self._m7_ready = True
        self.auto_balance = True
        for g in self._stall.values():
            g.reset()
        print("[Modus 7] Tast-Gang: stelle erst stabilen Stand her "
              "(alle Füße zum Boden), dann Pfeil↑ zum Losgehen.")

    def _feeler_gait(self):
        if not self._m7_ready:
            self._enter_feeler()
        self._refresh_contact_cache()
        legmap = {leg.name: leg for leg in self.legs}
        speed = abs(self.cmd_vel_x)
        yaw_user = abs(self.cmd_yaw) > 1e-4
        moving = (speed > 1e-4) or yaw_user
        # ── KURSREGELUNG: Anfangskurs halten (IMU-Yaw), ohne die Treppe zu
        #    "sehen". Q/E übersteuert manuell und setzt den Zielkurs neu. ──
        yaw_now = self._read_body_yaw()
        if self._m7_yaw_target is None:
            self._m7_yaw_target = yaw_now
        if yaw_user:
            self._m7_yaw_target = yaw_now           # manuelles Lenken → neuer Sollkurs
            dyaw = self.cmd_yaw * self.M7_YAW_RATE
        else:
            err = math.atan2(math.sin(yaw_now - self._m7_yaw_target),
                             math.cos(yaw_now - self._m7_yaw_target))  # [-pi,pi]
            dyaw = _clamp(-self.M7_HEAD_KP * err, -self.M7_YAW_MAX, self.M7_YAW_MAX)
        if getattr(self, '_m7_no_heading', False):   # Diagnose-Schalter (Harness)
            dyaw = 0.0
        yawing = abs(dyaw) > 1e-6

        # ── Balancer zuerst berechnen (gilt auch für Settle + alle Beine) ──
        if self.auto_balance:
            roll_m, pitch_m = self._read_body_attitude()
            # Beim Treppensteigen hält der Balancer den Körper PARALLEL zur
            # Fußebene (pitch_sp aus dem Vorframe), nicht zur Schwerkraft → alle
            # Beine im selben moderaten Regime, kein Überstrecken (Katzen-Lösung).
            self.roll_bal, self.pitch_bal = self.balance.update(
                roll_m, pitch_m, 1.0 / 240.0, pitch_sp=self._m7_climb_pitch_sp)
        else:
            self.roll_bal, self.pitch_bal = self.balance.decay()
        self._m7_pitch_eff = self.pitch_bal + self.pitch
        self._m7_roll_eff  = self.roll_bal + self.roll

        # ── SETTLE: erst stabilen Stand herstellen. ALLE Füße fahren nach
        #    unten, bis sie Boden spüren → geplanteter 6-Fuß-Stand, bevor
        #    überhaupt ein Bein schwingt. Behebt das Hochbocken auf 2 Beinen. ──
        if self._m7_settle_left > 0:
            self._m7_settle_left -= 1
            self._m7_pitch_eff = 0.0; self._m7_roll_eff = 0.0  # Balance aus im Settle
            floor = self.M7_Z_STAND - self.M7_FOLLOW_MAX
            ncon = 0
            for leg in self.legs:
                f = self._m7_foot[leg.name]
                touch, nz, horiz = self._m7_foot_contact(leg)
                if touch:
                    ncon += 1
                    self._m7_planted_z[leg.name] = f[2]    # Aufsetzhöhe merken
                elif f[2] > floor:
                    f[2] -= self.M7_PROBE_V                # zum Boden ausfahren
                self._m7_set_leg(leg, f[0], f[1], f[2])
            # Sobald genug Füße tragen, Settle früh beenden und Stand merken
            if ncon >= 5 and self._m7_settle_left > 6:
                self._m7_settle_left = 6
            if self._m7_settle_left == 0:
                self._m7_phase = 'WAVE'
                self._m7_yaw_target = self._read_body_yaw()   # Kurs jetzt halten
                self._m7_wave_i = 0
                n0 = self.M7_WAVE[self._m7_wave_i]     # erstes Schwungbein lösen
                self._m7_state[n0] = 'LIFT'
                self._m7_liftz[n0] = self.M7_Z_STAND + self.M7_LIFT0
                self._m7_swing_n[n0] = 0
            return

        # Gemeinsamer Stand-Halter: hält jeden Standfuß auf seiner gemerkten
        # Gelände-Höhe (planted_z). KEIN kontinuierliches "Boden suchen" mehr —
        # das war eine Aufwärts-Ratsche (Ausfahren tragender Beine drückt den
        # Körper hoch). Das Aufsetzen je Fuß macht ohnehin die PROBE-Phase beim
        # Umsetzen; die Körperhöhe regelt separat die WELT-Mittelbein-Referenz.
        def _hold(n):
            f = self._m7_foot[n]
            touch, nz, horiz = self._m7_foot_contact(legmap[n])
            f[2] = self._m7_planted_z[n]
            self._m7_nocontact[n] = 0 if touch else self._m7_nocontact[n] + 1

        if not moving:
            for n in legmap:
                _hold(n)
        else:
            # ── FUSS-GEKOPPELTER WELLENGANG ──
            # Der Körper schwenkt NIE über die Fußposition: er bleibt OFFSET hinter
            # dem VORDERSTEN Standfuß. Der Vortrieb (adv) läuft nur, solange der
            # vorderste Fuß weiter als OFFSET vor dem Körper steht — sobald er auf
            # OFFSET ran ist, WARTET der Körper, bis ein Schwungbein eine neue Stütze
            # weiter vorn aufsetzt (auf der Stufe!). So keilt sich kein Schienbein in
            # den Riser. GENAU EIN Bein schwingt (LIFT→REACH→PROBE→auf); danach SOFORT
            # das nächste. Kurs wirkt kontinuierlich.
            self._m7_phase = 'WAVE'
            swing_leg = self.M7_WAVE[self._m7_wave_i]
            back_lim = self.M7_BACK_LIM                 # Sicherheits-Rücklage (eng!)
            stance = [n for n in legmap if n != swing_leg]
            # Vortrieb gedrosselt: nur so weit, bis der vorderste Standfuß OFFSET
            # vor dem Körper steht (foremost = größtes f[0] im Körper-Frame).
            foremost = max((self._m7_foot[n][0] for n in stance),
                           default=self.M7_BODY_OFFSET)
            # HINTEN-Gate (Fuß-Kopplung nach hinten): der Körper fährt nur so weit
            # vor, wie der HINTERSTE Standfuß es ohne Überstreckung zulässt. Sonst
            # wird er hinterhergeschleift → Schienbein knickt → Fuß erreicht den
            # Boden nicht mehr (hängt). room = kleinster Abstand eines Standfußes
            # zu seiner Rücklage-Grenze (nx+back_lim). room→0 → Körper hält, bis das
            # betroffene Bein nachsetzt (es kommt im Wellengang dran → kein Deadlock).
            room = min((self._m7_foot[n][0]
                        - (self._m7_neutral(legmap[n])[0] + back_lim)
                        for n in stance), default=self.M7_BODY_V)
            adv = max(0.0, min(self.M7_BODY_V,
                               foremost - self.M7_BODY_OFFSET, room))
            # 1) Standbeine: Körper um adv vortragen + Kurs halten
            for n in stance:
                f = self._m7_foot[n]; nx, ny = self._m7_neutral(legmap[n])
                f[0] = max(f[0] - adv, nx + back_lim)
                if yawing:                              # Kurskorrektur kontinuierlich
                    c2, s2 = math.cos(-dyaw), math.sin(-dyaw)
                    f[0], f[1] = f[0] * c2 - f[1] * s2, f[0] * s2 + f[1] * c2
                _hold(n)
            # 2) Schwungbein: LIFT→REACH→PROBE→aufsetzen→nächstes Bein
            n = swing_leg
            f = self._m7_foot[n]; nx, ny = self._m7_neutral(legmap[n])
            st = self._m7_state[n]
            if st not in ('LIFT', 'REACH', 'PROBE'):    # Sicherheit: Schwung starten
                st = 'LIFT'; self._m7_state[n] = 'LIFT'; self._m7_swing_n[n] = 0
            if st == 'LIFT':
                # Femur hoch. FLACH: bis Coxa-Höhe (foot_up). KLETTERN: ÜBER Coxa
                # (Z_CLIMB_UP) mit geschlossener Regelung auf die ECHTE Fußhöhe →
                # der Fuß ist physisch oben, bevor er vor-greift, und überragt den
                # nächsten Riser mit Reserve (vorher stieß er an).
                if self._m7_swing_n[n] == 0:
                    self._m7_lift_z0[n] = self._m7_foot_world_z(legmap[n])
                z_cap = self.M7_Z_CLIMB_UP if self._m7_climbing else self.M7_Z_CLIMB
                f[2] = min(f[2] + self.M7_LIFT_STEP, z_cap)
                if self._m7_climbing:
                    # Wind-up: Fuß erst nach HINTEN (weg von der Stufenkante), während
                    # er hoch geht → Bogen statt L. Danach holt REACH ihn vor.
                    f[0] = max(f[0] - self.M7_RETRACT_V,
                               nx - self.M7_STRIDE - self.M7_RETRACT)
                else:
                    f[0] += (nx - f[0]) * 0.30      # flach: zur Neutrale falten
                self._m7_swing_n[n] += 1
                risen = self._m7_foot_world_z(legmap[n]) - self._m7_lift_z0[n]
                if self._m7_climbing:
                    bz = p.getBasePositionAndOrientation(self.robot_id)[0][2]
                    up = (self._m7_foot_world_z(legmap[n]) - bz) >= (self.M7_Z_CLIMB_UP - 0.02)
                else:
                    up = (risen >= self.M7_LIFT_RISE or self._m7_foot_up(legmap[n]))
                if up or self._m7_swing_n[n] > self.M7_LIFT_CAP:
                    self._m7_state[n] = 'REACH'
            elif st == 'REACH':
                # nach vorn schwenken (über jede Kante), bis Stride-Front erreicht
                # ODER der Fuß schon einen TRITT berührt (nz≥horiz) → Swing früh
                # abbrechen und aufsetzen, statt ins Leere weiterzuschwenken.
                f[0] += self.M7_REACH_V
                touch, nz, horiz = self._m7_foot_contact(legmap[n])
                if (touch and nz >= horiz) or f[0] >= nx + self.M7_STRIDE:
                    self._m7_state[n] = 'PROBE'
            elif st == 'PROBE':
                f[2] -= self.M7_PROBE_V
                touch, nz, horiz = self._m7_foot_contact(legmap[n])
                planted = (touch and nz >= horiz) or (f[2] <= -0.30)
                if planted:
                    self._m7_state[n] = 'STANCE'
                    self._m7_planted_z[n] = f[2]
                    self._m7_nocontact[n] = 0
                    self._m7_onstep[n] = (f[2] > self.M7_Z_STAND + 0.05)
                    # SOFORT das nächste Bein lösen (kontinuierlich, kein SHIFT).
                    # KEIN x-Reset: das neue Schwungbein ist zurückgeschwenkt und
                    # schwingt von dort über LIFT/REACH nach vorn.
                    self._m7_wave_i = (self._m7_wave_i + 1) % len(self.M7_WAVE)
                    n0 = self.M7_WAVE[self._m7_wave_i]
                    self._m7_state[n0] = 'LIFT'
                    self._m7_swing_n[n0] = 0
                    self._m7_onstep[n0] = False

        # ── Körperhöhe ──
        # FLACH / STILLSTAND: gemeinsame Standtiefe, welt-referenziert auf BODY_H
        #   über Weltnull → alle Füße exakt gleich tief → stabil (B1/B2).
        # KLETTERN (ein Fuß meldet onstep = steht auf einer Stufe): GELÄNDE-
        #   referenziert — Körper BODY_H über der Welt-z der MITTELBEINE; alle
        #   Standbeine gemeinsam verschoben, Füße halten ihre Stufen-Höhe → der
        #   Körper steigt mit der Treppe. Der Tast-Gang selbst schaltet um.
        body_z = self._read_body_z()
        pz_lo = -(self.M7_BODY_H + self.body_height_offset + self.M7_FOLLOW_MAX)
        climbing = moving and any(self._m7_onstep[n] for n in legmap)
        self._m7_climbing = climbing     # Schwung-Hub (nächstes Frame) liest das
        if not climbing:
            desired = self.M7_BODY_H + self.body_height_offset
            self._m7_stand_z = _clamp(
                self._m7_stand_z
                + _clamp((body_z - desired) * self.M7_HGAIN, -self.M7_HREG, self.M7_HREG),
                pz_lo, -0.05)
            for n in legmap:
                if self._m7_state[n] == 'STANCE':
                    self._m7_planted_z[n] = self._m7_stand_z
                    self._m7_foot[n][2] = self._m7_stand_z
            # Pitch-Sollwert sanft auf 0 (waagerecht) zurück
            self._m7_climb_pitch_sp += (0.0 - self._m7_climb_pitch_sp) * self.M7_PITCH_LP
        else:
            # ── KATZEN-LÖSUNG: Körper PARALLEL zur Fußebene, nicht waagerecht ──
            # (1) PITCH-Sollwert = Neigung der Fußebene (vorn vs. hinten), an den
            #     Balancer gegeben → der Körper neigt sich mit der Treppe, alle Beine
            #     bleiben im selben moderaten Regime, KEIN Überstrecken. Damit fällt
            #     die Überstreckungs-Ursache der Oszillation an der Wurzel weg.
            # (2) HÖHE = mittlere Standbein-Länge auf BODY_H (Mittelwert, NICHT max/
            #     median+Deckel → kein Leapfrog-Sprung, kein Aufschwingen). Mit dem
            #     Pitch nimmt das Gelände der Pitch auf → planted_z wandern auf ~gleich.
            slope = self._m7_foot_plane_pitch(self._m7_use_fk)
            if slope is not None:
                sp = self.M7_PITCH_SP_SIGN * slope
                self._m7_climb_pitch_sp += (sp - self._m7_climb_pitch_sp) * self.M7_PITCH_LP
            self._m7_climb_pitch_sp = _clamp(self._m7_climb_pitch_sp,
                                             -self.M7_PITCH_MAX, self.M7_PITCH_MAX)
            stance_c = [n for n in legmap
                        if self._m7_state[n] == 'STANCE'
                        and self._m7_foot_contact(legmap[n])[0]]
            if stance_c:
                # Höhe aus der TATSÄCHLICHEN Körper-z regeln (wie der Flach-Zweig,
                # der funktioniert), Ziel = Geländehöhe der TRAGENDEN Füße + BODY_H.
                # Bricht die Falle: die alte mean-planted_z-Regelung HOB den Körper,
                # wenn fast alle Füße hingen (nur der hohe Stützfuß zählte → er wurde
                # gestreckt → Körper noch höher → noch mehr hängen).
                terrain_z = sum(p.getLinkState(self.robot_id,
                                self._foot_link_idx[n])[0][2]
                                for n in stance_c) / len(stance_c)
                desired_z = terrain_z + self.M7_BODY_H + self.body_height_offset
                shift = _clamp((body_z - desired_z) * self.M7_HGAIN,
                               -self.M7_HREG, self.M7_HREG)
            else:
                shift = 0.0     # kein tragender Fuß → Höhe HALTEN
            for n in legmap:
                if self._m7_state[n] != 'STANCE':
                    continue
                if self._m7_foot_contact(legmap[n])[0]:
                    # tragend → Höhenregler (Mittelwert auf BODY_H)
                    self._m7_planted_z[n] = _clamp(
                        self._m7_planted_z[n] + shift, pz_lo, -0.05)
                else:
                    # HÄNGT → Boden suchen: Fuß senken, bis er Kontakt spürt
                    # (hält das Stützpolygon vollständig; HW: Mikroschalter im Fuß).
                    self._m7_planted_z[n] = _clamp(
                        self._m7_planted_z[n] - self.M7_SEEK_V, pz_lo, -0.05)
                self._m7_foot[n][2] = self._m7_planted_z[n]

        # ── IK für alle Beine ──
        for leg in self.legs:
            fx, fy, fz = self._m7_foot[leg.name]
            self._m7_set_leg(leg, fx, fy, fz)

    def update_gait(self):
        # Modus 6 hat einen eigenen, vollständigen Pfad
        if self.gait_mode == 6:
            self._stair_freegait()
            return

        # Modus 7: empirischer Tast-Treppengang (eigener Pfad)
        if self.gait_mode == 7:
            self._feeler_gait()
            return

        # Kontakt-Cache einmal pro Frame aktualisieren (Performance)
        self._refresh_contact_cache()

        # ContinuousStairClimber hat Vorrang über cmd_vel und body_height
        self.stair_climber.update()

        self.cur_vel_x += (self.cmd_vel_x - self.cur_vel_x) * 0.02
        self.cur_vel_y += (self.cmd_vel_y - self.cur_vel_y) * 0.02
        self.cur_yaw   += (self.cmd_yaw - self.cur_yaw) * 0.02
        is_moving = (abs(self.cur_vel_x) > 0.001 or
                     abs(self.cur_vel_y) > 0.001 or
                     abs(self.cur_yaw)   > 0.001)

        phase_speed = 0.0
        if self.gait_mode == 1: phase_speed = 0.010
        if self.gait_mode == 2: phase_speed = 0.005
        if self.gait_mode == 3: phase_speed = 0.004  # Adaptiv: langsamer
        if self.gait_mode == 4: phase_speed = 0.006  # Zentaur
        if self.gait_mode == 5: phase_speed = 0.005  # Klettern (ruhig)

        if is_moving:
            self.move_intent = min(self.move_intent + 0.05, 1.0)
            self.gait_phase = (self.gait_phase + phase_speed) % 1.0
        else:
            self.move_intent = max(self.move_intent - 0.05, 0.0)
            self.gait_phase = ((self.gait_phase + phase_speed) % 1.0
                               if self.move_intent > 0 else 0.0)

        if self.gait_mode == 4:
            self.zentaur_progress = min(self.zentaur_progress + 0.008, 1.0)
        else:
            self.zentaur_progress = max(self.zentaur_progress - 0.02, 0.0)

        if self.gait_mode == 5:
            self.climb_progress = min(self.climb_progress + 0.01, 1.0)
        else:
            self.climb_progress = max(self.climb_progress - 0.02, 0.0)

        target_grip  = 1.0 if self.gripper_active else 0.0
        self.grip_blend += (target_grip - self.grip_blend) * 0.05

        # CG/Beinlast: Mode 4 voller Zentaur. Mode 5 (Treppe): beim ABSTIEG
        # (Anstellwinkel negativ) CoG nach hinten/bergauf, damit SLARC nicht
        # nach vorne über die Stufen kippt. Aufstieg/Eben: 0.
        target_cg   = (-0.10 * self.zentaur_progress if self.gait_mode == 4 else
                       -0.05 if (self.gait_mode == 5 and self.climb_pitch < -0.02)
                       else 0.0)
        target_mid  =  0.08 * self.zentaur_progress if self.gait_mode == 4 else 0.0
        target_rear = -0.05 * self.zentaur_progress
        target_m_crouch = 0.02 * self.zentaur_progress if self.gait_mode == 4 else 0.0
        target_r_crouch = 0.05 * self.zentaur_progress if self.gait_mode == 4 else 0.0

        # Modus 3: Körperhöhe folgt gemessenem Boden (Probe-and-Plant).
        # Mode 5 (Treppe) nutzt manuelle Körperhöhe (W/S) wie Modus 2.
        if self.gait_mode == 3:
            avg_floor = sum(self._leg_floor_z.values()) / 6
            self.body_height_offset += (avg_floor - self.body_height_offset) * 0.015
        # Coxa-Seitwärtsschwenk NUR Modus 3 (Adaptiv-Terrain breitbeinig).
        # Treppe (Mode 5) braucht fore-aft-Beine zum Hochsteigen → kein Bias.
        if self.gait_mode == 3:
            target_bias = 1.0
            self._stair_x_bias += (target_bias - self._stair_x_bias) * 0.015
        else:
            self._stair_x_bias += (0.0 - self._stair_x_bias) * 0.04

        # Effektive Basis per Lerp zwischen Default und 90°-Seitwärtsstellung
        REACH = 0.220  # Gesamtreichweite der Beine vom Hüftpunkt
        # Mode 5: Greifer-Aufsetzebene (absenkbar via T/G über arm_lift_offset)
        self.climb_z = 0.02 + self.arm_lift_offset
        for leg in self.legs:
            t = self._stair_x_bias  # [0..1]

            if "front" in leg.name and t > 0.001:
                side = -1 if "right" in leg.name else 1
                # Zielposition: Fuß direkt seitlich vom Hüftgelenk (Coxa bei 90°)
                tgt_x = leg.mount_x          # kein Vorwärtsanteil
                tgt_y = leg.mount_y + side * REACH
                ex = leg.base_x * (1 - t) + tgt_x * t
                ey = leg.base_y * (1 - t) + tgt_y * t
                self._eff_base[leg.name] = (ex, ey)
            else:
                # Standardposition. In flachen Modi (1/2/4) base_z sanft auf
                # Default zurückführen (Modus 3/5 verwalten base_z per Boden-Sync).
                self._eff_base[leg.name] = (leg.base_x, leg.base_y)
                if self.gait_mode in (1, 2, 4):
                    leg.base_z += (leg.default_z - leg.base_z) * 0.1

        cg_ready   = self.cg_offset_x / target_cg if target_cg < -1e-6 else 0.0
        front_lift = max(0.0, min(1.0, (cg_ready - 0.85) / 0.15))

        self.cg_offset_x   += (target_cg   - self.cg_offset_x)   * 0.1
        self.mid_leg_offset += (target_mid  - self.mid_leg_offset) * 0.1
        self.rear_leg_offset+= (target_rear - self.rear_leg_offset)* 0.08
        self.mid_crouch     += (target_m_crouch - self.mid_crouch) * 0.1
        self.rear_crouch    += (target_r_crouch - self.rear_crouch)* 0.1

        # ── Lage: Balance-Overlay ODER Treppen-Anstellung ───────────────
        if self.gait_mode == 5:
            # Treppe = schiefe Ebene: Körper parallel zur Rampe anstellen,
            # damit jedes tragende Bein nahezu senkrecht steht (kleiner Hebel
            # → wenig Drehmoment). Auto-Balance hier AUS (würde gegenarbeiten).
            # Anstellwinkel bewusst NICHT voll auf den Rampenwinkel: voll-
            # parallel spreizt die Beine vertikal so weit, dass die Hinterbeine
            # im Schwung aus der Reichweite fallen — und ist lt. Hebelarm ohnehin
            # nicht das Drehmoment-Optimum. 0.6× hält alle Beine erreichbar.
            PITCH_FRAC = 0.6
            if self.climb_kind == 0:        # FIXED: aus rise/run
                pitch_target = PITCH_FRAC * math.atan2(self.stair_rise, self.stair_run)
                # Hub knapp über die Setzstufe, reichweiten-sicher gedeckelt
                self.climb_lift = max(0.18, min(self.stair_rise + 0.06, 0.28))
            else:                            # ADAPTIV: aus gemessenen Fußhöhen
                pitch_target = PITCH_FRAC * self._measure_ramp_angle()
                self.climb_lift = 0.22
            self.climb_pitch += (pitch_target - self.climb_pitch) * 0.02
            # Auto-Crouch: je steiler angestellt, desto tiefer der Körper —
            # sonst drückt die Pitch-Rotation die Vorderfüße aus der Reichweite
            # (Roboter steht/hängt). Hält Stand vorne+hinten erreichbar.
            self.climb_crouch = 0.04 + 0.14 * math.sin(abs(self.climb_pitch))
            self.roll_bal, self.pitch_bal = self.balance.decay()
            pitch_eff = self.climb_pitch + self.pitch   # I/K = Feintrim
            roll_eff  = self.roll
        else:
            # ── Req 3: Balance-Überlagerung (Körpernormale → Schwerkraft) ─
            if self.auto_balance and not self.stair_climber.active:
                roll_m, pitch_m = self._read_body_attitude()
                self.roll_bal, self.pitch_bal = self.balance.update(
                    roll_m, pitch_m, 1.0 / 240.0)
            else:
                self.roll_bal, self.pitch_bal = self.balance.decay()
            pitch_eff = self.pitch + self.pitch_bal
            roll_eff  = self.roll + self.roll_bal

        cy = math.cos(pitch_eff); sy = math.sin(pitch_eff)
        cx = math.cos(roll_eff);  sx = math.sin(roll_eff)

        for leg in self.legs:
            step_z = 0.0   # Schwung-Hub; wird WELT-vertikal nach der Rotation addiert
            # ── Stall-Überwachung (portabel): Coxa Soll-Ist-Fehler + Last ──
            # Hardware: Present-Position- und Present-Load-Register des ST3215.
            recovering = False
            cidx = self.joint_map.get(f"{leg.name}_coxa_joint")
            if cidx is not None and self.robot_id is not None:
                js = p.getJointState(self.robot_id, cidx)
                pos_err = abs(self._cmd_coxa[leg.name] - js[0])
                load_frac = abs(js[3]) / SERVO_STALL_NM
                recovering = self._stall[leg.name].update(pos_err, load_frac)
                if recovering and self._stall[leg.name].recover == StallGuard.RECOVER:
                    print(f"[Stall] {leg.name}: Coxa blockiert (Last "
                          f"{load_frac*100:.0f}%) → Bein hebt an & setzt neu an")
            if self.gait_mode == 4 and "front" in leg.name:
                stance_x, stance_y, stance_z = leg.base_x, leg.base_y, leg.base_z
                y_open   = 0.14  if "left" in leg.name else -0.14
                y_closed = 0.025 if "left" in leg.name else -0.025
                zentaur_x = leg.mount_x + self.arm_reach_offset
                zentaur_y = y_open*(1-self.grip_blend) + y_closed*self.grip_blend
                zentaur_z = 0.02 + self.arm_lift_offset
                t = front_lift
                target_x = stance_x*(1-t) + zentaur_x*t
                target_y = stance_y*(1-t) + zentaur_y*t
                target_z = stance_z*(1-t) + zentaur_z*t
            else:
                stride_x = self.cur_vel_x - self.cur_yaw * leg.base_y
                stride_y = self.cur_vel_y + self.cur_yaw * leg.base_x

                if self.gait_mode == 1:
                    leg_phase = (self.gait_phase + self.phases_tripod[leg.name]) % 1.0
                    st_ratio, sw_ratio, h_mult, s_mult = 0.65, 0.35, 1.0, 1.0
                elif self.gait_mode == 2:
                    leg_phase = (self.gait_phase + self.phases_ripple[leg.name]) % 1.0
                    st_ratio, sw_ratio, h_mult, s_mult = 0.7, 0.3, 2.8, 1.0
                elif self.gait_mode == 3:
                    # Adaptive Terrain: Ripple + hoher Hub + Kontakt-Landing
                    leg_phase = (self.gait_phase + self.phases_ripple[leg.name]) % 1.0
                    st_ratio, sw_ratio, h_mult, s_mult = 0.75, 0.25, 6.0, 0.8
                elif self.gait_mode == 4:  # Zentaur
                    p_offset  = self.phases_quad.get(leg.name, 0.0)
                    leg_phase = (self.gait_phase + p_offset) % 1.0
                    st_ratio, sw_ratio, h_mult, s_mult = 0.8, 0.2, 2.0, 1.5
                else:  # mode 5 = Treppe: einfacher Ripple-Schwung + Auto-Pitch
                    # Gleicher Gang wie Modus 2 (bewährt), KEIN Probe-and-Plant
                    # (das fror den Fuß an der Stufenkante ein). Der eingestellte
                    # Schritt-Hub (P/O) wird hier direkt umgesetzt — der Auto-
                    # Anstellwinkel ist der einzige Unterschied zu Modus 2.
                    leg_phase = (self.gait_phase + self.phases_ripple[leg.name]) % 1.0
                    st_ratio, sw_ratio, h_mult, s_mult = 0.7, 0.3, 2.8, 1.0

                if leg_phase < st_ratio:
                    factor = 1.0 - (2.0*(leg_phase/st_ratio))
                    step_z = 0.0
                    # Modus 3 Standbein: floor_z und base_z synchron halten
                    if self.gait_mode == 3:
                        contact, fz = self._check_foot_contact(leg.name)
                        if contact:
                            self._leg_floor_z[leg.name] = fz
                        leg.base_z = -(0.190 + self.body_height_offset
                                       - self._leg_floor_z[leg.name])
                        # Alle Swing-Zustände zurücksetzen
                        self._leg_frozen[leg.name]  = None
                        self._leg_descend[leg.name] = False
                else:
                    p_val  = (leg_phase - st_ratio) / sw_ratio
                    factor = -1.0 + (2.0*p_val)

                    if self.gait_mode == 3:
                        # ── Probe-and-Plant (nur Adaptiv-Terrain, NICHT Treppe) ──
                        # Aufwärts: Kontakt früher als erwartet → Einfrieren
                        # Abwärts:  Kein Kontakt bei p_val=1 → Extended Descent
                        # ───────────────────────────────────────────────

                        if self._leg_frozen[leg.name] is not None:
                            # Kontakt bereits bestätigt — Höhe halten
                            step_z = self._leg_frozen[leg.name]
                            # Extended Descent beenden falls noch aktiv
                            self._leg_descend[leg.name] = False

                        elif self._leg_descend[leg.name]:
                            # ── Extended Descent (Abwärts-Suche) ────────
                            # Fuß suchte über p_val=1 hinaus — langsam weiter absenken
                            DESCENT_RATE = 0.0008  # m pro Frame
                            self._leg_desc_step[leg.name] = max(
                                0.0,
                                self._leg_desc_step[leg.name] - DESCENT_RATE
                            )
                            step_z = self._leg_desc_step[leg.name]

                            contact, fz = self._check_foot_contact(leg.name)
                            if contact:
                                self._leg_floor_z[leg.name] = fz
                                self._leg_frozen[leg.name]  = step_z
                                self._leg_descend[leg.name] = False
                            elif step_z <= 0.0:
                                # Kein Kontakt bis step_z=0 → Boden sehr tief
                                # Minimalfall: floor_z = aktuell + body_h_offset
                                self._leg_floor_z[leg.name] = (
                                    -0.190 - self.body_height_offset + leg.base_z)
                                self._leg_descend[leg.name] = False

                        else:
                            # ── Lift-First Trajektorie (Modus 3) ────────
                            # Phase 1 (p_val 0..LIFT): Vertikal heben,
                            #   horizontal RÜCKWÄRTS bleiben (Stufenkante frei)
                            # Phase 2 (p_val LIFT..1): Vorwärts schwingen
                            #   und absenken → Kontaktsuche
                            LIFT = 0.45   # 45% Heben, 55% Vorwärts+Absenken
                            max_lift = self.step_height * h_mult * self.move_intent

                            if p_val < LIFT:
                                t1 = p_val / LIFT             # [0..1]
                                # Vertikal: Sinus-Anstieg zur Maxhöhe
                                step_z = math.sin(t1 * math.pi / 2) * max_lift
                                # Horizontal: Bein bleibt hinten (factor überschreiben)
                                factor = -1.0 + t1 * 0.3     # bleibt weitgehend hinten
                            else:
                                t2 = (p_val - LIFT) / (1.0 - LIFT)   # [0..1]
                                # Vertikal: Cosinus-Abstieg von Maxhöhe
                                step_z = math.cos(t2 * math.pi / 2) * max_lift
                                # Horizontal: vorwärts schwingen
                                factor = -0.7 + t2 * 1.7

                                # Kontaktprüfung ab 30% der Absenkphase
                                if t2 > 0.30 and self.move_intent > 0.1:
                                    contact, fz = self._check_foot_contact(leg.name)
                                    if contact:
                                        # Aufwärts-Fall: Kontakt früher → einfrieren
                                        self._leg_floor_z[leg.name] = fz
                                        self._leg_frozen[leg.name]  = step_z

                            # Schwungende ohne Kontakt → Extended Descent
                            if p_val >= 0.98 and self._leg_frozen[leg.name] is None:
                                self._leg_descend[leg.name]   = True
                                self._leg_desc_step[leg.name] = step_z
                    else:
                        sh = self.step_height
                        # Treppe (Mode 5): Hinterbeine werden vom Anstellwinkel
                        # bereits angehoben → weniger Schwung-Hub nötig. 0.6×
                        # macht die 17-cm-Standardtreppe voll erreichbar.
                        if self.gait_mode == 5 and "rear" in leg.name:
                            sh *= 0.6
                        step_z = (math.sin(p_val*math.pi)
                                  * (sh*h_mult)*self.move_intent)

                # Req 1: Schritthub auf kinematische Hüllkurve begrenzen.
                # Die harte Garantie erfolgt unten an target_z (Fuß-Z), hier
                # nur eine grobe obere Schranke gegen Ausreißer.
                if step_z > self.STEP_H_MAX:
                    step_z = self.STEP_H_MAX

                leg_off = (self.mid_leg_offset if "mid" in leg.name else
                           self.rear_leg_offset if "rear" in leg.name else 0.0)
                leg_cr  = (self.mid_crouch if "mid" in leg.name else
                           self.rear_crouch if "rear" in leg.name else 0.0)

                # Effektive Basis (inkl. Coxa-Schwenk in Modus 3)
                eff_bx, eff_by = self._eff_base[leg.name]

                if leg_phase < st_ratio:
                    # ── Standbein ───────────────────────────────────────
                    # Beim ersten Stance-Frame einfrieren — kein Bodenschleifen
                    # bei laufendem Coxa-Schwenk
                    if self._leg_stance_x[leg.name] is None:
                        self._leg_stance_x[leg.name] = (eff_bx, eff_by)
                    home_x, home_y = self._leg_stance_x[leg.name]
                    target_x = (home_x
                                 + factor * ((stride_x * s_mult) / 2.0)
                                 - self.cg_offset_x + leg_off)
                    target_y = (home_y
                                 + factor * ((stride_y * s_mult) / 2.0))
                else:
                    # ── Schwungbein ──────────────────────────────────────
                    # Einfrierung freigeben — Aufsetzen mit aktuellem Schwenkwinkel
                    self._leg_stance_x[leg.name] = None
                    target_x = (eff_bx
                                 + factor * ((stride_x * s_mult) / 2.0)
                                 - self.cg_offset_x + leg_off)
                    target_y = (eff_by
                                 + factor * ((stride_y * s_mult) / 2.0))

                # Wenn StairClimber aktiv: base_z und step_z aus Climber holen
                if self.stair_climber.active:
                    if self.stair_climber.is_swinging(leg.name):
                        # Schwungtrajektorie vom Climber — step_z unterdrücken
                        step_z = 0.0
                    else:
                        # Standbein: step_z unterdrücken (Bein bleibt auf Level)
                        step_z = 0.0

                # Höhen-Trims (unabhängig von Pitch):
                #   rear_lift >0 → Hinterfüße tiefer  → Heck hebt sich
                #   mid_lift  >0 → Mittelfüße höher   → über die Stufenkante
                if "rear" in leg.name:
                    leg_lift = -self.rear_lift
                elif "mid" in leg.name:
                    leg_lift = self.mid_lift
                else:
                    leg_lift = 0.0
                # Boden-/Aufsetzziel OHNE Schwung-Hub. Der Hub (step_z) wird
                # nach der Lage-Rotation welt-vertikal addiert (s.u.), damit er
                # bei angestelltem Körper (Treppe) voll als Höhe wirkt.
                climb_crouch = self.climb_crouch if self.gait_mode == 5 else 0.0
                target_z = (leg.base_z - self.body_height_offset
                            + leg_cr + leg_lift + climb_crouch)

            # ── Auto-Recovery bei erkanntem Stall ──────────────────────────
            # Bein hängt an einem Hindernis (z.B. Stufenkante): höher anheben
            # (welt-vertikal) und Vorschub zurücknehmen → es kommt frei und der
            # Schritt wird neu angesetzt, statt blind weiter dagegenzudrücken.
            if recovering:
                step_z += self.RECOVER_LIFT
                target_x += (leg.base_x - target_x) * 0.6
                target_y += (leg.base_y - target_y) * 0.3

            rx  = target_x*cy + target_z*sy;  ry = target_y
            rz  = -target_x*sy + target_z*cy
            ry_new = ry*cx - rz*sx;           rz_new = ry*sx + rz*cx
            # Schwung-Hub WELT-vertikal (nach Pitch+Roll): voller Höhengewinn
            # auch bei angestelltem Körper, symmetrisch trotz Rollen → beide
            # Vorderbeine kommen gleich weit über die Stufe.
            rz_new += step_z

            dx = rx - leg.mount_x; dy = ry_new - leg.mount_y; dz = rz_new
            local_x =  dx*math.cos(-leg.mount_yaw) - dy*math.sin(-leg.mount_yaw)
            local_y =  dx*math.sin(-leg.mount_yaw) + dy*math.cos(-leg.mount_yaw)

            angles = self.ik.calculate_leg_angles(local_x, local_y, dz)
            # Tuner-Override: manuell gesteuerte Beine überschreiben IK
            override = self.tuner.get_override_angles(leg.name)
            if override:
                tc, tf, tt = override
            elif angles:
                tc, tf, tt = angles
            else:
                continue
            self.set_servo(f"{leg.name}_coxa_joint",  tc)
            self.set_servo(f"{leg.name}_femur_joint", tf)
            self.set_servo(f"{leg.name}_tibia_joint", tt)
            self._cmd_coxa[leg.name] = tc   # für Stall-Erkennung (Soll-Ist)

    def set_servo(self, joint_name, angle_rad):
        if joint_name in self.joint_map:
            p.setJointMotorControl2(
                bodyIndex=self.robot_id,
                jointIndex=self.joint_map[joint_name],
                controlMode=p.POSITION_CONTROL,
                targetPosition=angle_rad,
                # force = realer ST3215-Stall (NICHT mehr 4.0!). Damit kann der
                # Sim nie mehr Drehmoment aufbringen als der echte Servo →
                # Anzeige bleibt ≤100% und Sättigung wird als echtes Problem
                # sichtbar (Bein sackt), statt dass der Sim 'schummelt'.
                force=SERVO_STALL_NM, maxVelocity=4.0,
                positionGain=SERVO_POS_GAIN, velocityGain=1.0)

    def _refresh_contact_cache(self):
        """Kontaktpunkte einmal pro Frame cachen — spart 6× getContactPoints()."""
        import ctypes
        self._contact_cache = p.getContactPoints(bodyA=self.robot_id) or []
        self._contact_frame += 1

    def toggle_wobble(self):
        """Wackelbrett (Balance-Test) ein/aus. Plattform kippt langsam in
        Pitch & Roll; der Roboter steht darauf und der Balancer muss
        gegensteuern. Auto-Balance (B) sollte AN sein."""
        if self.wobble_active:
            if self.wobble_id is not None:
                p.removeBody(self.wobble_id); self.wobble_id = None
            self.wobble_active = False
            print("Wackelbrett: AUS")
            return
        pos, orn = p.getBasePositionAndOrientation(self.robot_id)
        ox, oy, oz = pos[0], pos[1], 0.07
        col = p.createCollisionShape(p.GEOM_BOX, halfExtents=[0.6, 0.6, 0.03])
        vis = p.createVisualShape(p.GEOM_BOX, halfExtents=[0.6, 0.6, 0.03],
                                  rgbaColor=[0.85, 0.5, 0.1, 1.0])
        # Masse 0 = kinematisch: wird per resetBasePositionAndOrientation
        # gekippt und trägt/​neigt den Roboter über Reibung.
        self.wobble_id = p.createMultiBody(0, col, vis, [ox, oy, oz])
        p.changeDynamics(self.wobble_id, -1, lateralFriction=1.2)
        self.wobble_origin = [ox, oy, oz]
        self.wobble_t = 0.0; self.wobble_active = True
        # Roboter auf das Brett heben
        p.resetBasePositionAndOrientation(
            self.robot_id, [pos[0], pos[1], pos[2] + 0.14], orn)
        self.auto_balance = True; self.balance.reset()
        print("Wackelbrett: AN  (Auto-Balance automatisch EIN) — losgehen & beobachten")

    def update_wobble(self):
        if not self.wobble_active or self.wobble_id is None:
            return
        self.wobble_t += 1.0 / 240.0
        # langsame, phasenversetzte Kippung in Roll & Pitch
        roll  = 0.14 * math.sin(2*math.pi*0.12 * self.wobble_t)
        pitch = 0.11 * math.sin(2*math.pi*0.08 * self.wobble_t + 1.0)
        q = p.getQuaternionFromEuler([roll, pitch, 0.0])
        p.resetBasePositionAndOrientation(self.wobble_id, self.wobble_origin, q)

    def _measure_ramp_angle(self):
        """
        ADAPTIVer Anstellwinkel: misst die lokale Rampenneigung aus der
        mittleren Welt-Höhe der Vorder- vs. Hinterfüße.
          θ = atan2(z_front - z_rear, horizontaler Abstand)
        >0 ⇒ vorne höher ⇒ Nase hoch (Treppe aufwärts).

        SIM: Fuß-Weltpositionen via getLinkState. ESP32: dieselbe Größe aus
        Vorwärtskinematik der Beinwinkel + IMU-Lage bzw. Fußkraftsensoren.
        """
        if self.robot_id is None:
            return self.climb_pitch
        fz = []; fx = []; rz = []; rx = []
        for leg in self.legs:
            idx = self._foot_link_idx.get(leg.name, -1)
            if idx < 0:
                continue
            w = p.getLinkState(self.robot_id, idx)[0]
            if "front" in leg.name:
                fx.append(w[0]); fz.append(w[2])
            elif "rear" in leg.name:
                rx.append(w[0]); rz.append(w[2])
        if not fz or not rz:
            return self.climb_pitch
        dz = sum(fz) / len(fz) - sum(rz) / len(rz)
        dx = abs(sum(fx) / len(fx) - sum(rx) / len(rx))
        if dx < 0.05:
            return self.climb_pitch
        return math.atan2(dz, dx)

    def _check_foot_contact(self, leg_name):
        """
        Kontaktprüfung via gecachtem getContactPoints.
        Simuliert ST3215-Drehmomentsensor-Feedback.
        Rückgabe: (contact: bool, world_z: float)
        """
        MIN_FORCE  = 0.4
        target_idx = self._foot_link_idx.get(leg_name, -1)
        if target_idx < 0:
            return False, 0.0
        for c in self._contact_cache:
            if c[3] != target_idx: continue
            if c[9] < MIN_FORCE:   continue
            lstate = p.getLinkState(self.robot_id, target_idx)
            return True, lstate[0][2]
        return False, 0.0

    def _compute_max_stride(self):
        """
        Req 4: Maximale Schrittlänge, bevor benachbarte Beine kollidieren.
        Konservativ: kleinster Abstand zwischen Ruhe-Fußpunkten benachbarter
        Beine. Da zwei aufeinander zu schwingende Beine den Spalt um ~stride
        schließen, gilt  stride_max ≈ min_gap - 2*foot_radius - clearance.
        """
        FOOT_R = 0.015
        CLEAR = 0.030          # Sicherheitsabstand
        # benachbarte Paare derselben Seite (Längsrichtung)
        pairs = [("front_right", "mid_right"), ("mid_right", "rear_right"),
                 ("front_left", "mid_left"), ("mid_left", "rear_left"),
                 ("front_right", "front_left"), ("rear_right", "rear_left")]
        pos = {l.name: (l.base_x, l.base_y) for l in self.legs}
        min_gap = 1e9
        for a, b in pairs:
            ax, ay = pos[a]; bx, by = pos[b]
            min_gap = min(min_gap, math.hypot(ax - bx, ay - by))
        stride = min_gap - 2 * FOOT_R - CLEAR
        # sinnvoll begrenzen (untere Grenze 1 cm, obere ~halbe Reichweite)
        return max(0.02, min(stride, 0.24))

    def _read_body_attitude(self):
        """
        Liefert (roll, pitch) der Körperlage gegenüber der Schwerkraft [rad].
        SIM: aus der Basis-Orientierung. ESP32: hier IMU-Treiber einsetzen
        (MPU6050/BNO055 → roll/pitch). Yaw wird für die Balance nicht benötigt.
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

    def set_gait_from_perception(self, seg_dominant, normal_variance):
        """
        Kopplung an AI Perception-System.
        Wird vom AI-Process über das Blackboard aufgerufen.

        seg_dominant    : dominante Seg-Klasse im vorderen Bildbereich
                          0=FLOOR 1=STEP 2=WALL 3=OBSTACLE 4=VOID 5=TERRAIN
        normal_variance : Varianz der Normals-Vektoren
                          niedrig (<0.05) = glatte Oberfläche
                          hoch    (>0.15) = raue/unbekannte Oberfläche

        Mapping:
          Floor  + beliebige Normals   → Modus 1 (Tripod, schnell)
          Terrain + klare Normals      → Modus 2 (Ripple, stabil)
          Terrain + rauschige Normals  → Modus 3 (Adaptiv, Kontakt)
          Step                         → Modus 3 (Adaptiv, Kontakt)
          Obstacle/Unknown             → Modus 3 + langsam
        """
        FLOOR    = 0
        STEP     = 1
        TERRAIN  = 5
        if not self.stair_climber.active:
            if seg_dominant == FLOOR:
                self.gait_mode = 1
            elif seg_dominant == STEP:
                self.gait_mode = 3
                self.step_height = max(self.step_height, 0.10)
            elif seg_dominant == TERRAIN and normal_variance < 0.08:
                self.gait_mode = 2
            else:
                self.gait_mode = 3

    def process_keyboard(self):
        keys = p.getKeyboardEvents()
        # Während StairClimber: Pfeile sperren, aber cmd_vel_x vom Climber erlaubt
        if not self.stair_climber.active:
            self.cmd_vel_x = 0.0; self.cmd_vel_y = 0.0; self.cmd_yaw = 0.0
        else:
            # Nur Drehen sperren, cmd_vel_x kommt vom Climber
            self.cmd_vel_y = 0.0; self.cmd_yaw = 0.0
        for key, state in keys.items():
            if state & p.KEY_IS_DOWN:
                if not self.stair_climber.active:
                    if key == p.B3G_UP_ARROW:    self.cmd_vel_x =  self.max_stride_x
                    if key == p.B3G_DOWN_ARROW:  self.cmd_vel_x = -self.max_stride_x
                    if key == p.B3G_LEFT_ARROW:  self.cmd_vel_y =  self.max_stride_y
                    if key == p.B3G_RIGHT_ARROW: self.cmd_vel_y = -self.max_stride_y
                    if key == ord('q'): self.cmd_yaw =  0.3
                    if key == ord('e'): self.cmd_yaw = -0.3
                if key == ord('w'): self.body_height_offset = min(self.body_height_offset+0.002, self.BHO_MAX)
                if key == ord('s'): self.body_height_offset = max(self.body_height_offset-0.002, self.BHO_MIN)
                if key == ord('i'): self.pitch = min(self.pitch+0.02,  0.6)
                if key == ord('k'): self.pitch = max(self.pitch-0.02, -0.6)
                if key == ord('j'): self.roll  = min(self.roll +0.02,  0.3)
                if key == ord('l'): self.roll  = max(self.roll -0.02, -0.3)
                if key == ord('t'): self.arm_lift_offset  = min(self.arm_lift_offset +0.003, self.ARM_LIFT_MAX)
                if key == ord('g'): self.arm_lift_offset  = max(self.arm_lift_offset -0.003, self.ARM_LIFT_MIN)
                if key == ord('f'): self.arm_reach_offset = min(self.arm_reach_offset+0.003, self.ARM_REACH_MAX)
                if key == ord('h'): self.arm_reach_offset = max(self.arm_reach_offset-0.003,  0.10)
                if key == ord('z'): self.rear_lift = min(self.rear_lift+0.002, self.REAR_LIFT_MAX)
                if key == ord('u'): self.rear_lift = max(self.rear_lift-0.002, self.REAR_LIFT_MIN)
                if key == ord('a'): self.mid_lift = min(self.mid_lift+0.002, self.MID_LIFT_MAX)
                if key == ord('d'): self.mid_lift = max(self.mid_lift-0.002, self.MID_LIFT_MIN)

            if state & p.KEY_WAS_TRIGGERED:
                # M immer: Tuner togglen
                if key == ord('m'):
                    self.tuner.toggle()

                if self.tuner.active:
                    # ── Tuner-Modus: 1-6 = Bein wählen ─────────────────
                    for i, k in enumerate([ord('1'),ord('2'),ord('3'),
                                           ord('4'),ord('5'),ord('6'),ord('7')]):
                        if key == k:
                            self.tuner.select_leg(i)
                    if key == ord(' '): self.tuner.log_current()
                    if key == ord('x'): self.tuner.log_all()
                    if key == ord('p'): self.tuner.save()
                    # O bleibt Beinhöhe-runter auch im Tuner
                    if key == ord('o'):
                        self.step_height = max(self.step_height - 0.008, self.kin.STEP_H_MIN)
                        print(f"Schritthöhe: {self.step_height*100:.1f} cm")

                else:
                    # ── Normalmodus: alle Gait-Tasten ───────────────────
                    if key == ord('1'):
                        self.gait_mode = 1
                        self._leg_stance_x = {n: None for n in self._leg_stance_x}
                        print("Modus 1: Tripod (Floor)")
                    if key == ord('2'):
                        self.gait_mode = 2
                        self._leg_stance_x = {n: None for n in self._leg_stance_x}
                        print("Modus 2: Ripple (Terrain)")
                    if key == ord('3'):
                        self.gait_mode = 3
                        self.step_height = max(self.step_height, 0.060)
                        self._leg_floor_z  = {n: 0.0   for n in self._leg_floor_z}
                        self._leg_frozen   = {n: None  for n in self._leg_frozen}
                        self._leg_descend  = {n: False for n in self._leg_descend}
                        self._leg_desc_step= {n: 0.0   for n in self._leg_desc_step}
                        self._leg_stance_x = {n: None  for n in self._leg_stance_x}
                        self._stair_x_bias = 0.0
                        print(f"Modus 3: Adaptiv  step={self.step_height*100:.0f}cm "
                              f"max_lift={self.step_height*6*100:.0f}cm")
                    if key == ord('4'):
                        self.gait_mode = 4
                        self._leg_stance_x = {n: None for n in self._leg_stance_x}
                        print("Modus 4: ZENTAUR/Greifen")
                    if key == ord('5'):
                        if self.gait_mode == 5:
                            # Schon im Treppenmodus → FIXED/ADAPTIV umschalten.
                            # Eigene Taste bewusst vermieden: pybullet kapert
                            # 'v'/'w' o.ä. trotz COV_ENABLE_KEYBOARD_SHORTCUTS=0.
                            self.climb_kind = 1 - self.climb_kind
                        else:
                            self.gait_mode = 5
                            self._leg_stance_x = {n: None for n in self._leg_stance_x}
                            self.auto_balance = False
                            # bewährte Treppen-Schritthöhe (per P/O anpassbar)
                            self.step_height = max(self.step_height, 0.10)
                        kind = "ADAPTIV" if self.climb_kind else "FIXED"
                        deg = math.degrees(math.atan2(self.stair_rise, self.stair_run))
                        print(f"Modus 5: TREPPE — Ripple + Auto-Pitch ({kind})  [5 erneut = umschalten]")
                        if self.climb_kind == 0:
                            print(f"   FIXED: rise={self.stair_rise*100:.0f} run={self.stair_run*100:.0f}"
                                  f" → Anstellung {deg:.0f}°  (I/K=Feintrim)")
                        else:
                            print("   ADAPTIV: Anstellung regelt sich aus Fußhöhen")
                        print(f"   Schritthöhe {self.step_height*100:.0f}cm (P/O), Körperhöhe W/S, Pfeil↑ vor")
                    if key == ord('6'):
                        self.gait_mode = 6
                        self._fh_ready = False   # beim ersten Frame initialisieren
                        for g in self._stall.values(): g.reset()
                        print("Modus 6: TREPPE — deterministischer Foothold-"
                              "Tripod-Gang. Pfeil↑ = klettern, Pfeil↓ = zurück.")
                        print("   Footholds werden auf Tritt-Mitten geplant "
                              "(kein Wackeln). Modus 5 bleibt Fallback.")
                    if key == ord('9'):
                        self.gait_mode = 7
                        self._m7_ready = False   # beim ersten Frame initialisieren
                        for g in self._stall.values(): g.reset()
                        print("Modus 7 (Taste 9): TREPPE — empirischer TAST-Gang "
                              "(blind). Pfeil↑ = losgehen. Beine ertasten die Stufen.")
                        print("   Kein Geländemodell — Kontakt + Servo-Last. "
                              "Schwellen M7_* tunebar. Modus 5 bleibt Fallback.")
                    if key == ord('n'):
                        # Alte Auto-Sequenz war zu starr → Klettermodus nutzen.
                        print("ℹ️  N-Sequenz ersetzt: bitte Modus 5 (Klettern) verwenden.")
                    if key == ord('r'):
                        self.stair_climber._stop()
                        self.body_height_offset = 0.0; self.pitch = 0.0; self.roll = 0.0
                        self.balance.reset(); self.roll_bal = 0.0; self.pitch_bal = 0.0
                        self.gait_mode = 1; self.gripper_active = False
                        self.arm_lift_offset = 0.0; self.arm_reach_offset = 0.22
                        self.climb_progress = 0.0; self.zentaur_progress = 0.0
                        self.climb_pitch = 0.0
                        self.rear_lift = 0.0; self.mid_lift = 0.0
                        for leg in self.legs: leg.base_z = leg.default_z
                        self._leg_floor_z  = {n: 0.0   for n in self._leg_floor_z}
                        self._leg_frozen   = {n: None  for n in self._leg_frozen}
                        self._leg_descend  = {n: False for n in self._leg_descend}
                        self._leg_desc_step= {n: 0.0   for n in self._leg_desc_step}
                        self._leg_stance_x = {n: None  for n in self._leg_stance_x}
                        self._stair_x_bias = 0.0
                    if key == ord('p'):
                        self.step_height = min(self.step_height + 0.008, self.STEP_H_MAX)
                        print(f"Schritthöhe: {self.step_height*100:.1f} cm "
                              f"(max {self.STEP_H_MAX*100:.0f})")
                    if key == ord('o'):
                        self.step_height = max(self.step_height - 0.008, self.kin.STEP_H_MIN)
                        print(f"Schritthöhe: {self.step_height*100:.1f} cm")
                    if key == ord('+') or key == ord('8'):
                        self.max_stride_x = min(self.max_stride_x+0.02, self.MAX_STRIDE)
                        print(f"Schrittweite: {self.max_stride_x*100:.0f} cm "
                              f"(max {self.MAX_STRIDE*100:.0f})")
                    if key == ord('-') or key == ord('7'):
                        self.max_stride_x = max(self.max_stride_x-0.02, 0.04)
                        print(f"Schrittweite: {self.max_stride_x*100:.0f} cm")
                    if key == ord(' '):
                        self.gripper_active = not self.gripper_active
                        print("Greifer:", "ZU" if self.gripper_active else "AUF")
                    if key == ord('c'):
                        self._show_cam = not self._show_cam
                        print("Kamera-Debug:", "AN" if self._show_cam else "AUS")
                    if key == ord('b'):
                        self.auto_balance = not self.auto_balance
                        if not self.auto_balance:
                            self.balance.reset()
                        print("Auto-Balance:", "AN" if self.auto_balance else "AUS")
                    if key == ord('y'):
                        self.toggle_wobble()
                    if key == ord('v'):
                        self.logger.toggle()

    def update_camera_debug(self):
        if not self._show_cam or self.cameras is None:
            return
        self._cam_frame += 1
        if self._cam_frame % 30 != 0:
            return
        rgb_l, rgb_r, depth_l = self.cameras.get_images(self.robot_id)
        disp = self.cameras.depth_to_disparity(depth_l)
        pos, _ = p.getBasePositionAndOrientation(self.robot_id)
        p.addUserDebugText(
            f"Cam L: {rgb_l.shape}  Disp max={disp.max():.1f}px",
            [pos[0], pos[1], pos[2]+0.3],
            textColorRGB=[1, 1, 0], lifeTime=1.0, textSize=1.2)

    def update_torque_display(self):
        """
        Per-SERVO-Drehmomentfeedback (Coxa/Femur/Tibia getrennt):
          • ein Balken pro Bein am Fuß, Höhe ∝ Last, Farbe = welcher Servo-Typ
            dominiert (Coxa=cyan, Femur=gelb, Tibia=magenta)
          • zwei persistente Textzeilen über dem Körper:
              WORST: <SERVO> <%>  [<bein>]
              max   Coxa <%> | Femur <%> | Tibia <%>
            → zeigt direkt, ob die Coxa-Gelenke das Problem sind.
        Persistente Items via replaceItemUniqueId, alle 8 Frames.
        """
        if not hasattr(self, '_torque_init'):
            self._torque_init = True
            self._torque_frame = 0
            # Joint-Indices pro Bein NACH TYP (coxa/femur/tibia)
            self._leg_servo_idx = {}   # leg -> {'coxa':i,'femur':i,'tibia':i}
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
            self._bar_ids = {}
            self._txt_id = None; self._txt2_id = None
            self._tau_lp = {}      # (leg, typ) -> tiefpassgefiltertes Verhältnis

        self._torque_frame += 1
        if self._torque_frame % 8 != 0:
            return

        TAU_MAX = SERVO_STALL_NM; WARN = 0.50; CRIT = 0.80
        TYPE_COL = {'coxa': [0.1, 0.8, 0.9],     # cyan
                    'femur': [1.0, 0.8, 0.0],    # gelb
                    'tibia': [0.9, 0.2, 0.9]}    # magenta

        def col(r):
            return ([0.1, 0.9, 0.1] if r < WARN else
                    [1.0, 0.75, 0.0] if r < CRIT else [1.0, 0.1, 0.1])

        type_max = {'coxa': 0.0, 'femur': 0.0, 'tibia': 0.0}
        type_max_leg = {'coxa': '', 'femur': '', 'tibia': ''}
        worst = 0.0; worst_type = ''; worst_leg = ''

        for leg in self.legs:
            servos = self._leg_servo_idx.get(leg.name, {})
            if not servos:
                continue
            leg_max = 0.0; leg_dom = 'femur'
            for typ, idx in servos.items():
                raw = abs(p.getJointState(self.robot_id, idx)[3]) / TAU_MAX
                key = (leg.name, typ)
                lp = self._tau_lp.get(key, raw)
                lp += (raw - lp) * 0.20
                self._tau_lp[key] = lp
                r = min(lp, 1.0)
                if r > type_max[typ]:
                    type_max[typ] = r; type_max_leg[typ] = leg.name
                if r > leg_max:
                    leg_max = r; leg_dom = typ
                if r > worst:
                    worst = r; worst_type = typ; worst_leg = leg.name
            # Balken am Fuß, gefärbt nach dominierendem Servo-Typ
            fidx = self._foot_link_idx.get(leg.name, -1)
            if fidx < 0:
                continue
            fp = p.getLinkState(self.robot_id, fidx)[0]
            base = [fp[0], fp[1], fp[2] + 0.02]
            top  = [fp[0], fp[1], fp[2] + 0.02 + 0.06 + leg_max * 0.32]
            c = TYPE_COL[leg_dom]
            if leg.name in self._bar_ids:
                self._bar_ids[leg.name] = p.addUserDebugLine(
                    base, top, lineColorRGB=c, lineWidth=14,
                    replaceItemUniqueId=self._bar_ids[leg.name])
            else:
                self._bar_ids[leg.name] = p.addUserDebugLine(
                    base, top, lineColorRGB=c, lineWidth=14)

        pos, _ = p.getBasePositionAndOrientation(self.robot_id)
        line1 = (f"WORST: {worst_type.upper()} {worst*100:.0f}%  "
                 f"[{worst_leg.replace('_',' ')}]")
        line2 = (f"max  Coxa {type_max['coxa']*100:.0f}% | "
                 f"Femur {type_max['femur']*100:.0f}% | "
                 f"Tibia {type_max['tibia']*100:.0f}%")
        c = col(worst)
        t1 = [pos[0], pos[1], pos[2] + 0.60]
        t2 = [pos[0], pos[1], pos[2] + 0.50]
        if self._txt_id is not None:
            self._txt_id = p.addUserDebugText(line1, t1, textColorRGB=c,
                                textSize=2.4, replaceItemUniqueId=self._txt_id)
        else:
            self._txt_id = p.addUserDebugText(line1, t1, textColorRGB=c,
                                textSize=2.4)
        if self._txt2_id is not None:
            self._txt2_id = p.addUserDebugText(line2, t2,
                                textColorRGB=[0.85, 0.85, 0.85], textSize=1.8,
                                replaceItemUniqueId=self._txt2_id)
        else:
            self._txt2_id = p.addUserDebugText(line2, t2,
                                textColorRGB=[0.85, 0.85, 0.85], textSize=1.8)


# ==========================================
# Bewegungslogger (Sim-only) — Taste V
# ==========================================
class MotionLogger:
    """
    Schreibt pro N Frames eine CSV-Zeile mit dem REALEN Closed-Loop-Zustand:
      Körperpose (x/y/z, roll/pitch/yaw), Körpergeschwindigkeit (lin/ang),
      Balancer (roll_bal/pitch_bal), Fahrbefehl (cmd_vx/cmd_yaw) und je Bein
      Fuß-Weltposition, Bodenkontakt, die drei Servo-Drehmomente sowie den
      Mode-7-Tastzustand.
    Zweck: Test live laufen lassen → CSV hochladen → Verhalten an Messdaten
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
                "roll_bal", "pitch_bal"]
        for n in self._legs():
            cols += [f"{n}_fx", f"{n}_fy", f"{n}_fz", f"{n}_contact",
                     f"{n}_tau_coxa", f"{n}_tau_femur", f"{n}_tau_tibia",
                     f"{n}_state"]
        return cols

    def toggle(self):
        self.stop() if self.active else self.start()

    def start(self):
        import os, time, csv
        if self.ctrl.robot_id is None:
            print("[Logger] Roboter noch nicht bereit."); return
        ts = time.strftime("%Y%m%d_%H%M%S")
        self.path = os.path.join(os.getcwd(), f"slarc_log_{ts}.csv")
        self.f = open(self.path, "w", newline="")
        self.writer = csv.writer(self.f)
        self.writer.writerow(self._header())
        self.active = True; self.frame = 0; self.rows = 0; self.t0 = None
        print(f"[Logger] AUFNAHME gestartet → {self.path}  (Taste V stoppt)")

    def stop(self):
        if not self.active: return
        self.active = False
        try:
            self.f.flush(); self.f.close()
        except Exception:
            pass
        print(f"[Logger] gestoppt. {self.rows} Zeilen → {self.path}")

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
        # Bodenkontakte einsammeln (Fuß-Link-Index → True)
        contacts = {}
        for ct in (p.getContactPoints(bodyA=rid) or []):
            if ct[9] >= 0.5:
                contacts[ct[3]] = True
        row = [f"{t:.3f}", self.frame, c.gait_mode,
               f"{pos[0]:.4f}", f"{pos[1]:.4f}", f"{pos[2]:.4f}",
               f"{roll:.4f}", f"{pitch:.4f}", f"{yaw:.4f}",
               f"{lin[0]:.4f}", f"{lin[1]:.4f}", f"{lin[2]:.4f}",
               f"{ang[0]:.4f}", f"{ang[1]:.4f}", f"{ang[2]:.4f}",
               f"{c.cmd_vel_x:.3f}", f"{getattr(c,'cmd_yaw',0.0):.3f}",
               f"{getattr(c,'roll_bal',0.0):.4f}",
               f"{getattr(c,'pitch_bal',0.0):.4f}"]
        for n in self._legs():
            fidx = c._foot_link_idx.get(n, -1)
            if fidx >= 0:
                fp = p.getLinkState(rid, fidx)[0]
                fx, fy, fz = fp[0], fp[1], fp[2]
                con = 1 if fidx in contacts else 0
            else:
                fx = fy = fz = 0.0; con = 0
            taus = []
            for j in ('coxa', 'femur', 'tibia'):
                jidx = c.joint_map.get(f"{n}_{j}_joint")
                taus.append(abs(p.getJointState(rid, jidx)[3])
                            if jidx is not None else 0.0)
            state = c._m7_state.get(n, '') if c.gait_mode == 7 else ''
            row += [f"{fx:.4f}", f"{fy:.4f}", f"{fz:.4f}", con,
                    f"{taus[0]:.3f}", f"{taus[1]:.3f}", f"{taus[2]:.3f}", state]
        self.writer.writerow(row)
        self.rows += 1
        if self.rows % 120 == 0:      # ~alle 2 s sichern
            self.f.flush()


# ==========================================
# MAIN
# ==========================================
def main():
    robot = SlarcController()
    robot.init_pybullet()

    print("\n=== SLARC V6 — Flex-IK + Balance + StallGuard + Treppen-Modi ===")
    print(f" Schritthöhe max : {robot.STEP_H_MAX*100:.0f} cm  (Femur 90°/Knie 160°)")
    print(f" Körperhöhe      : 0 … {robot.kin.BODY_H_MAX*100:.0f} cm")
    print(f" Schrittlänge max: {robot.MAX_STRIDE*100:.0f} cm  (kollisionsfrei)")
    print(" ─────────────────────────────────────────────")
    print(" Pfeile    : Laufen (gesperrt während Treppen-Sequenz)")
    print(" Q/E       : Drehen")
    print(" W/S       : Körper heben/senken (0…max)")
    print(" I/K       : Pitch           J/L : Roll")
    print(" Z/U       : Heck heben/senken (Hinterbeine, unabhängig von Pitch)")
    print(" A/D       : Mittelbeine anheben/absenken (bis über Schulterhöhe)")
    print(" B         : Auto-Balance an/aus (Körpernormale → Schwerkraft)")
    print(" Y         : Wackelbrett ein/aus (Balance im Gehen testen)")
    print(" 1/2/3/4   : Tripod / Ripple / Adaptiv(Terrain) / Zentaur")
    print(" 5         : TREPPE — angestellter Wellengang (5 erneut: FIXED↔ADAPTIV)")
    print(" 6         : TREPPE — deterministischer Foothold-Tripod-Gang")
    print(" 7         : TREPPE — empirischer TAST-Gang (blind, Kontakt/Last)")
    print(" T/G       : Greifer heben/absenken (bis -34cm)  F/H : vor/zurück")
    print(" Leertaste : Greifer Auf/Zu")
    print(" P / O     : Schritthöhe +/-0.8cm (kinematisch begrenzt)")
    print(" + / -  o. 8/7: Schrittlänge +/-2cm (kollisionsfrei begrenzt)")
    print(" C         : Kamera-Debug an/aus")
    print(" V         : Bewegungslogger an/aus (CSV → Arbeitsverzeichnis)")
    print(" R         : Reset (auch Treppen-Abbruch + Balance)")
    print(" Drehmoment-Anzeige: Balkenfarbe = dominierender Servo")
    print("   (Coxa=cyan, Femur=gelb, Tibia=magenta); Text zeigt max je Typ.")
    print(" ─────────────────────────────────────────────")
    print(" Treppen steigen (Modus 5 — Treppe als schiefe Ebene):")
    print("   • Prinzip: Körper wird in den Stufenwinkel angestellt, dann")
    print("     metachronaler Wellengang (1 Bein schwingt, 5 tragen) — jedes")
    print("     Bein rückt pro Zyklus eine Stufe nach. Niemand wartet.")
    print("   1) frontal vor die Treppe fahren")
    print("   2) Taste 5 → Körper stellt sich an (Auto-Balance geht aus)")
    print("   3) V wählt: FIXED (Winkel aus rise/run) oder ADAPTIV (misst Rampe)")
    print("   4) Pfeil ↑ langsam halten → SLARC steigt Stufe für Stufe hoch")
    print("      FIXED: bei Bedarf I/K = Anstellung feintrimmen")
    print("   ABWÄRTS: ADAPTIV nutzen (5 erneut) — misst die Rampe, kippt die")
    print("      Nase automatisch nach unten, CoG verlagert sich nach hinten.")
    print(" ─────────────────────────────────────────────")
    print(" Drehmoment: Balken je Bein + %-Anzeige  grün<50% gelb<80% rot>80%")
    print(" I / K     : Pitch ±0.6 rad (±34°)")
    print(" ─────────────────────────────────────────────")
    print(" M         : Leg Tuner an/aus")
    print("   (Tuner) 1-6: Bein wählen  SPACE: loggen")
    print("   (Tuner) X: alle loggen    P: JSON speichern")
    print("\n Treppenkomplex bei x=1.0m")
    print(" → SLARC vor erster Stufe positionieren, dann N drücken\n")

    try:
        while True:
            robot.process_keyboard()
            robot.update_gait()
            robot.update_wobble()
            robot.update_camera_debug()
            robot.update_torque_display()
            robot.tuner.update_display()
            p.stepSimulation()
            robot.logger.tick()
            time.sleep(1. / 240.)
    except KeyboardInterrupt:
        p.disconnect()


if __name__ == '__main__':
    main()
