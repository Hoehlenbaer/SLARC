#!/usr/bin/env python3
"""
SLARC Simulation V5
===================
V4 + vollflexibler IK-Kern mit kinematisch hergeleiteten Grenzen,
Gelenklimits/Anti-Kollision und aktiver Balance-Überlagerung.

Neuerungen gegenüber V4
-----------------------
1. Schritthöhe       : 1 cm … kinematisches Maximum (Femur 90° auf,
                       Knie ~160°). Echte Fuß-Z-Hüllkurve statt Magic-Cap.
2. Körperhöhe        : 0 cm (Bauchlage) … max. gestreckte Beine.
                       Absolut parametrisiert (BODY_H_MIN/NOM/MAX).
3. Balance-Overlay   : Hält Körpernormale zur Schwerkraft (Roll/Pitch→0)
                       per PD-Regler auf IMU/Lagewinkel. Läuft additiv
                       über den Gang ("IK-Balance-Überlagerung"). Taste B.
4. Schrittlänge      : 1 cm … kollisionsfreies Maximum, aus den
                       Nachbarbein-Abständen berechnet.
5. ESP32-Portierung  : Der Kinematik-/Gang-/Balance-KERN nutzt
                       ausschließlich `math` (keine numpy/pybullet/enum).
                       Siehe Markierung "PORTABLE CORE (ESP32)".

ESP32-Portabilität
------------------
Alles zwischen den Markern
    # >>> PORTABLE CORE (ESP32) >>>
    # <<< PORTABLE CORE (ESP32) <<<
ist reine `math`-Logik und nach MicroPython/C++ übertragbar.
Auf dem ESP32 wird `_read_body_attitude()` durch einen echten
IMU-Treiber (MPU6050/BNO055) ersetzt; pybullet/numpy/enum bleiben
auf PC/Raspberry-Pi-Seite (Simulation, Stereo, StairClimber-Skript).

Tastenbelegung (Ergänzungen)
  B : Auto-Balance an/aus
  N : Treppensteige-Sequenz starten / abbrechen
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
STAIR_RISE = 0.170     # Stufenhöhe [m]
STAIR_RUN  = 0.250     # Stufentiefe [m]

# ST3215 Stall-Drehmoment ~30 kg·cm ≈ 2.94 Nm. Dient als realer Motor-force
# (Sättigung) UND als 100%-Bezug der Drehmomentanzeige — eine Quelle, konsistent.
SERVO_STALL_NM = 2.94

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
        p.changeDynamics(sid, -1, lateralFriction=1.5)
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
    p.changeDynamics(pl_id, -1, lateralFriction=1.5)
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
        p.changeDynamics(sid, -1, lateralFriction=1.5)
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

    def update(self, roll_meas, pitch_meas, dt):
        # IMU-Tiefpass (gegen Rauschen/Schritt-Impulse)
        self._r_f += (roll_meas - self._r_f) * self.lp
        self._p_f += (pitch_meas - self._p_f) * self.lp
        d_r = (self._r_f - self._r_prev) / dt if dt > 1e-6 else 0.0
        d_p = (self._p_f - self._p_prev) / dt if dt > 1e-6 else 0.0
        self._r_prev = self._r_f; self._p_prev = self._p_f

        r_cmd = self.ROLL_SIGN * (self.kp * self._r_f + self.kd * d_r)
        p_cmd = self.PITCH_SIGN * (self.kp * self._p_f + self.kd * d_p)
        r_cmd = _clamp(r_cmd, -self.max_corr, self.max_corr)
        p_cmd = _clamp(p_cmd, -self.max_corr, self.max_corr)

        # sanftes Nachführen (kein Sprung)
        self.r_out += (r_cmd - self.r_out) * self.slew
        self.p_out += (p_cmd - self.p_out) * self.slew
        return self.r_out, self.p_out

    def decay(self):
        # bei deaktivierter Balance Korrektur sanft auf 0 fahren
        self.r_out *= 0.9; self.p_out *= 0.9
        return self.r_out, self.p_out


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

        # StairClimber (Modus N)
        self.stair_climber = ContinuousStairClimber(self)
        # Manual Leg Tuner (M-Taste)
        self.tuner = ManualLegTuner(self)

    def init_pybullet(self):
        generate_hexapod_urdf("slarc_primitives.urdf")
        p.connect(p.GUI)
        # Eingebaute GUI-Tastenkürzel abschalten (w=Wireframe, g=Panels,
        # v=Visuals aus, j/k/l, s … kollidieren sonst mit unserer Steuerung).
        # Unsere eigene Tastenabfrage via getKeyboardEvents bleibt aktiv.
        p.configureDebugVisualizer(p.COV_ENABLE_KEYBOARD_SHORTCUTS, 0)
        p.setAdditionalSearchPath(pybullet_data.getDataPath())
        p.setGravity(0, 0, -9.81)
        p.setPhysicsEngineParameter(fixedTimeStep=1./240.,
                                    numSolverIterations=100, numSubSteps=2)

        planeId = p.loadURDF("plane.urdf")
        p.changeDynamics(planeId, -1, lateralFriction=1.5,
                         spinningFriction=0.01, rollingFriction=0.01)

        self.robot_id = p.loadURDF("slarc_primitives.urdf", [0, 0, 0.20])

        for i in range(p.getNumJoints(self.robot_id)):
            info = p.getJointInfo(self.robot_id, i)
            joint_name = info[1].decode('utf-8')
            self.joint_map[joint_name] = i
            if "foot" in joint_name:
                p.changeDynamics(self.robot_id, i, lateralFriction=2.0,
                                 spinningFriction=0.01, rollingFriction=0.01,
                                 contactStiffness=10000.0, contactDamping=1000.0)
                # Leg-Name aus Joint-Name extrahieren und cachen
                leg = joint_name.replace('_foot_joint', '')
                self._foot_link_idx[leg] = i

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

        print("\n  Erzeuge Treppenkomplex...")
        create_staircase()
        print("\n  Initialisiere Stereo-Kameras...")
        self.cameras = StereoCameras()

        for _ in range(120): p.stepSimulation()
        for i in range(p.getNumJoints(self.robot_id)):
            p.changeDynamics(self.robot_id, i, jointDamping=0.05)
        self.cmd_vel_x = 0.0; self.cmd_vel_y = 0.0
        for _ in range(120): self.update_gait(); p.stepSimulation()
        self.tuner.init_sliders()

    def update_gait(self):
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
                positionGain=0.05, velocityGain=1.0)

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
                                           ord('4'),ord('5'),ord('6')]):
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
        Gut sichtbares Drehmoment-Feedback:
          • dicker, farbiger Balken pro Bein (Höhe ∝ Last) am jeweiligen Fuß
          • große, persistente %-Anzeige des Maximums über dem Körper
        Persistente Items via replaceItemUniqueId (kein Flackern), alle 8 Frames.
        """
        if not hasattr(self, '_torque_init'):
            self._torque_init = True
            self._torque_frame = 0
            # Joint-Indices pro Bein gruppieren (coxa/femur/tibia, ohne foot)
            self._leg_joint_idx = {}
            for i in range(p.getNumJoints(self.robot_id)):
                nm = p.getJointInfo(self.robot_id, i)[1].decode('utf-8')
                if 'foot' in nm:
                    continue
                for leg in self.legs:
                    if nm.startswith(leg.name):
                        self._leg_joint_idx.setdefault(leg.name, []).append(i)
                        break
            self._bar_ids = {}     # leg_name -> debug line id
            self._txt_id = None
            self._tau_lp = {}      # leg_name -> tiefpassgefiltertes Verhältnis

        self._torque_frame += 1
        if self._torque_frame % 8 != 0:
            return

        TAU_MAX = SERVO_STALL_NM; WARN = 0.50; CRIT = 0.80

        def col(r):
            return ([0.1, 0.9, 0.1] if r < WARN else
                    [1.0, 0.75, 0.0] if r < CRIT else [1.0, 0.1, 0.1])

        overall = 0.0; overall_leg = ""
        for leg in self.legs:
            idxs = self._leg_joint_idx.get(leg.name, [])
            if not idxs:
                continue
            raw = max(abs(p.getJointState(self.robot_id, i)[3]) for i in idxs) / TAU_MAX
            # Tiefpass: anhaltende Last statt Aufprall-/Beschleunigungsspitzen
            lp = self._tau_lp.get(leg.name, raw)
            lp += (raw - lp) * 0.20
            self._tau_lp[leg.name] = lp
            ratio = min(lp, 1.0)
            if ratio > overall:
                overall = ratio; overall_leg = leg.name
            # Balken am Fuß: senkrecht, Höhe ∝ Last, dick & farbig
            fidx = self._foot_link_idx.get(leg.name, -1)
            if fidx < 0:
                continue
            fp = p.getLinkState(self.robot_id, fidx)[0]
            base = [fp[0], fp[1], fp[2] + 0.02]
            top  = [fp[0], fp[1], fp[2] + 0.02 + 0.06 + ratio * 0.32]
            c = col(ratio)
            if leg.name in self._bar_ids:
                self._bar_ids[leg.name] = p.addUserDebugLine(
                    base, top, lineColorRGB=c, lineWidth=14,
                    replaceItemUniqueId=self._bar_ids[leg.name])
            else:
                self._bar_ids[leg.name] = p.addUserDebugLine(
                    base, top, lineColorRGB=c, lineWidth=14)

        pos, _ = p.getBasePositionAndOrientation(self.robot_id)
        txt = f"{overall*100:.0f}%  tau (Dauerlast)  [{overall_leg.replace('_',' ')}]"
        tpos = [pos[0], pos[1], pos[2] + 0.55]
        c = col(overall)
        if self._txt_id is not None:
            self._txt_id = p.addUserDebugText(
                txt, tpos, textColorRGB=c, textSize=2.6,
                replaceItemUniqueId=self._txt_id)
        else:
            self._txt_id = p.addUserDebugText(
                txt, tpos, textColorRGB=c, textSize=2.6)


# ==========================================
# MAIN
# ==========================================
def main():
    robot = SlarcController()
    robot.init_pybullet()

    print("\n=== SLARC V5 — Flex-IK + Balance-Overlay + StairClimber ===")
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
    print(" T/G       : Greifer heben/absenken (bis -34cm)  F/H : vor/zurück")
    print(" Leertaste : Greifer Auf/Zu")
    print(" P / O     : Schritthöhe +/-0.8cm (kinematisch begrenzt)")
    print(" + / -  o. 8/7: Schrittlänge +/-2cm (kollisionsfrei begrenzt)")
    print(" C         : Kamera-Debug an/aus")
    print(" R         : Reset (auch Treppen-Abbruch + Balance)")
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
            time.sleep(1. / 240.)
    except KeyboardInterrupt:
        p.disconnect()


if __name__ == '__main__':
    main()
