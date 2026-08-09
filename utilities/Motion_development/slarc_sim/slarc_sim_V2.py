import pybullet as p
import pybullet_data
import time
import math
import numpy as np

# ==========================================
# 0. URDF GENERATOR
# ==========================================
def generate_hexapod_urdf(filename="slarc_primitives.urdf"):
    body_l = 0.250; body_w = 0.120; body_h = 0.040
    coxa_l = 0.040; femur_l = 0.120; tibia_l = 0.160
    foot_radius = 0.015  
    mid_y_offset = 0.040
    
    legs = [
        ("front_right",  body_l/2, -body_w/2, -math.radians(30)),
        ("front_left",   body_l/2,  body_w/2,  math.radians(30)),
        ("mid_right",    0,        -(body_w/2 + mid_y_offset), -math.radians(90)),
        ("mid_left",     0,         (body_w/2 + mid_y_offset),  math.radians(90)),
        ("rear_right",  -body_l/2, -body_w/2, -math.radians(150)),
        ("rear_left",   -body_l/2,  body_w/2,  math.radians(150))
    ]

    urdf = f"""<?xml version="1.0"?>
<robot name="slarc">
    <link name="base_link">
        <visual><geometry><box size="{body_l} {body_w} {body_h}"/></geometry><material name="grey"><color rgba="0.5 0.5 0.5 1"/></material></visual>
        <collision><geometry><box size="{body_l} {body_w} {body_h}"/></geometry></collision>
        <inertial><mass value="1.0"/><inertia ixx="0.01" ixy="0" ixz="0" iyy="0.01" iyz="0" izz="0.01"/></inertial>
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
        <inertial><mass value="0.05"/><inertia ixx="0.0001" ixy="0" ixz="0" iyy="0.0001" iyz="0" izz="0.0001"/></inertial>
    </link>
    <joint name="{name}_femur_joint" type="revolute">
        <parent link="{name}_coxa"/><child link="{name}_femur"/>
        <origin xyz="{coxa_l} 0 0" rpy="0 0 0"/><axis xyz="0 1 0"/>
        <limit lower="-3.14" upper="3.14" effort="3.0" velocity="3.14"/>
    </joint>
    <link name="{name}_femur">
        <visual><origin xyz="{femur_l/2} 0 0"/><geometry><box size="{femur_l} 0.02 0.02"/></geometry><material name="green"><color rgba="0.2 0.8 0.2 1"/></material></visual>
        <collision><origin xyz="{femur_l/2} 0 0"/><geometry><box size="{femur_l} 0.02 0.02"/></geometry></collision>
        <inertial><mass value="0.08"/><inertia ixx="0.0001" ixy="0" ixz="0" iyy="0.0001" iyz="0" izz="0.0001"/></inertial>
    </link>
    <joint name="{name}_tibia_joint" type="revolute">
        <parent link="{name}_femur"/><child link="{name}_tibia"/>
        <origin xyz="{femur_l} 0 0" rpy="0 0 0"/><axis xyz="0 1 0"/>
        <limit lower="-3.14" upper="3.14" effort="3.0" velocity="3.14"/>
    </joint>
    <link name="{name}_tibia">
        <visual><origin xyz="{tibia_l/2} 0 0"/><geometry><box size="{tibia_l} 0.015 0.015"/></geometry><material name="blue"><color rgba="0.2 0.2 0.8 1"/></material></visual>
        <collision><origin xyz="{tibia_l/2} 0 0"/><geometry><box size="{tibia_l} 0.015 0.015"/></geometry></collision>
        <inertial><mass value="0.06"/><inertia ixx="0.0001" ixy="0" ixz="0" iyy="0.0001" iyz="0" izz="0.0001"/></inertial>
    </link>
    <joint name="{name}_foot_joint" type="fixed">
        <parent link="{name}_tibia"/><child link="{name}_foot"/>
        <origin xyz="{tibia_l} 0 0" rpy="0 0 0"/>
    </joint>
    <link name="{name}_foot">
        <visual><geometry><sphere radius="{foot_radius}"/></geometry><material name="black"><color rgba="0 0 0 1"/></material></visual>
        <collision><geometry><sphere radius="{foot_radius}"/></geometry></collision>
        <inertial><mass value="0.01"/><inertia ixx="0.00001" ixy="0" ixz="0" iyy="0.00001" iyz="0" izz="0.00001"/></inertial>
    </link>"""
    urdf += "</robot>"
    with open(filename, "w") as f: f.write(urdf)


# ==========================================
# TREPPE + RAMPE
# ==========================================
def create_staircase():
    """
    Layout (X-Achse = Laufrichtung):
      x=1.0..1.5  : 5 Stufen aufwärts  (h=0.04m, d=0.20m)
      x=1.5..2.5  : Rampe abwärts      (Gefälle zurück auf Bodenniveau)
      x=2.5..3.5  : 10 kleine Stufen   (h=0.02m, d=0.10m) abwärts
    """
    step_ids = []

    # ── 5 Stufen aufwärts ────────────────────────────────────────────
    step_h    = 0.040   # Stufenhöhe
    step_d    = 0.200   # Stufentiefe
    step_w    = 1.200   # Breite (quer)
    x_start   = 1.0
    n_up      = 5

    for i in range(n_up):
        h_total = step_h * (i + 1)          # kumulative Höhe
        cx = x_start + i * step_d + step_d / 2
        cz = h_total / 2

        col = p.createCollisionShape(p.GEOM_BOX,
                halfExtents=[step_d/2, step_w/2, h_total/2])
        vis = p.createVisualShape(p.GEOM_BOX,
                halfExtents=[step_d/2, step_w/2, h_total/2],
                rgbaColor=[0.75, 0.75, 0.70, 1])
        sid = p.createMultiBody(0, col, vis, basePosition=[cx, 0, cz])
        p.changeDynamics(sid, -1, lateralFriction=1.5)
        step_ids.append(sid)

    top_h   = step_h * n_up                 # 0.20 m — Plateau oben
    x_top   = x_start + n_up * step_d       # 2.0 m

    # ── Plateau (hält Niveau top_h, 1 m lang) ───────────────────────
    plateau_len = 1.00
    plateau_cx  = x_top + plateau_len / 2   # 2.5 m
    plateau_cz  = top_h / 2

    col_pl = p.createCollisionShape(p.GEOM_BOX,
                halfExtents=[plateau_len/2, step_w/2, top_h/2])
    vis_pl = p.createVisualShape(p.GEOM_BOX,
                halfExtents=[plateau_len/2, step_w/2, top_h/2],
                rgbaColor=[0.60, 0.80, 0.60, 1])
    pl_id = p.createMultiBody(0, col_pl, vis_pl,
                               basePosition=[plateau_cx, 0, plateau_cz])
    p.changeDynamics(pl_id, -1, lateralFriction=1.5)
    step_ids.append(pl_id)

    # ── 10 kleine Stufen abwärts ──────────────────────────────────────
    small_h   = 0.020
    small_d   = 0.100
    x_down    = x_top + plateau_len         # 3.0 m
    n_down    = 10

    for i in range(n_down):
        h_total = top_h - small_h * (i + 1)   # Höhe nimmt ab
        if h_total <= 0:
            h_total = 0.005
        cx = x_down + i * small_d + small_d / 2
        cz = h_total / 2

        col = p.createCollisionShape(p.GEOM_BOX,
                halfExtents=[small_d/2, step_w/2, h_total/2])
        vis = p.createVisualShape(p.GEOM_BOX,
                halfExtents=[small_d/2, step_w/2, h_total/2],
                rgbaColor=[0.70, 0.70, 0.80, 1])
        sid = p.createMultiBody(0, col, vis, basePosition=[cx, 0, cz])
        p.changeDynamics(sid, -1, lateralFriction=1.5)
        step_ids.append(sid)

    print(f"  Treppenkomplex erstellt: {len(step_ids)} Objekte")
    print(f"  Layout: 5 Stufen aufwärts  (x=1.0–2.0m, +{top_h*100:.0f}cm)")
    print(f"         Plateau (Niveau)    (x=2.0–3.0m)")
    print(f"         10 Stufen abwärts   (x=3.0–4.0m)")
    return step_ids


# ==========================================
# STEREO-KAMERASYSTEM
# ==========================================
class StereoCameras:
    """
    Dual-Kamera mit SLARC-Parametern:
      Baseline  : 50 mm
      Brennweite: 2.8 mm → bei Sensor 1/2.9" (2.76×2.07mm) ≈ FOV 53°h
      Auflösung : 640×480 (wie im Training)

    Die Kameraposition folgt dem Roboter-Körper.
    """
    # IMX296: 1456×1088px, 3.45µm pitch → Sensor 5.02×3.75mm
    # Bei 2.8mm Brennweite: FOV_h = 2*atan(5.02/2/2.8) = 83° (volle Auflösung)
    # Bei 640×480 nach Downscale (Crop-Faktor ~2.3): FOV ≈ 53° horizontal
    IMG_W   = 640
    IMG_H   = 480
    NEAR    = 0.01   # m
    FAR     = 10.0   # m

    # Brennweite in Pixeln (fx = f_mm / pixel_pitch * scale)
    # pixel_pitch bei 640px = 5.02mm/640 ≈ 7.84µm → fx = 2.8/0.00784 ≈ 357px
    FX = 357.0
    FY = 357.0

    # FOV aus fx berechnen (für PyBullet-API):
    # fov_v = 2 * atan(IMG_H/2 / FY) in Grad
    FOV_V = math.degrees(2 * math.atan(IMG_H / 2 / FY))   # ≈ 67°

    BASELINE = 0.050  # 50 mm

    def __init__(self):
        self._proj = p.computeProjectionMatrixFOV(
            fov=self.FOV_V,
            aspect=self.IMG_W / self.IMG_H,
            nearVal=self.NEAR,
            farVal=self.FAR
        )
        print(f"  Stereo-Kameras initialisiert:")
        print(f"    Baseline  : {self.BASELINE*1000:.0f} mm")
        print(f"    Brennweite: 2.8 mm  (fx≈{self.FX:.0f}px @ {self.IMG_W}×{self.IMG_H})")
        print(f"    FOV       : {self.FOV_V:.1f}° vertikal")

    def get_images(self, robot_id):
        """
        Gibt (rgb_l, rgb_r, depth_l) zurück.
        rgb_*   : [H, W, 4] RGBA uint8
        depth_l : [H, W]    float32, metrische Tiefe in Metern
        """
        pos, orn = p.getBasePositionAndOrientation(robot_id)
        rot = p.getMatrixFromQuaternion(orn)
        # Vorwärtsvektor (X im Körper-KS)
        fwd = [rot[0], rot[3], rot[6]]
        # Aufwärtsvektor (Z im Körper-KS)
        up  = [rot[2], rot[5], rot[8]]
        # Rechtsvektor (Y negativ im Körper-KS)
        rgt = [-rot[1], -rot[4], -rot[7]]

        # Kamera 10cm vor und 5cm über dem Körpermittelpunkt
        cam_base = [
            pos[0] + fwd[0]*0.10 + up[0]*0.05,
            pos[1] + fwd[1]*0.10 + up[1]*0.05,
            pos[2] + fwd[2]*0.10 + up[2]*0.05,
        ]
        target = [
            cam_base[0] + fwd[0],
            cam_base[1] + fwd[1],
            cam_base[2] + fwd[2],
        ]

        def cam_pos(side):
            sign = -0.5 if side == 'left' else 0.5
            return [
                cam_base[0] + rgt[0] * self.BASELINE * sign,
                cam_base[1] + rgt[1] * self.BASELINE * sign,
                cam_base[2] + rgt[2] * self.BASELINE * sign,
            ]

        def render(eye):
            view = p.computeViewMatrix(eye, target, up)
            _, _, rgb, depth_buf, _ = p.getCameraImage(
                self.IMG_W, self.IMG_H, view, self._proj,
                renderer=p.ER_TINY_RENDERER
            )
            # depth_buf ist [0,1] → metrische Tiefe
            depth = self.FAR * self.NEAR / (
                self.FAR - (self.FAR - self.NEAR) * np.array(depth_buf))
            return np.array(rgb, dtype=np.uint8).reshape(self.IMG_H, self.IMG_W, 4), depth.astype(np.float32)

        rgb_l, depth_l = render(cam_pos('left'))
        rgb_r, _       = render(cam_pos('right'))
        return rgb_l, rgb_r, depth_l

    def depth_to_disparity(self, depth_m):
        """
        Tiefe → Disparität in Pixeln (GT für Stereo-Training).
        disp = fx * baseline / depth
        """
        disp = np.zeros_like(depth_m)
        valid = depth_m > self.NEAR
        disp[valid] = self.FX * self.BASELINE / depth_m[valid]
        return disp


# ==========================================
# 1. REINE MATHEMATIK (IK)
# ==========================================
class HexapodIK:
    def __init__(self):
        self.L_C = 0.040; self.L_F = 0.120; self.L_T = 0.160

    def calculate_leg_angles(self, x, y, z):
        theta_c = math.atan2(y, x)
        L = math.sqrt(x**2 + y**2) - self.L_C
        if L < 0.02: L = 0.02
        D = math.sqrt(L**2 + z**2)
        if D > (self.L_F + self.L_T): D = self.L_F + self.L_T - 0.001
        min_D = abs(self.L_F - self.L_T)
        if D < min_D: D = min_D + 0.001
        gamma = math.atan2(abs(z), L)
        val_f = (self.L_F**2 + D**2 - self.L_T**2) / (2 * self.L_F * D)
        val_f = max(-1.0, min(1.0, val_f))
        alpha = math.acos(val_f)
        theta_f = gamma - alpha
        val_t = (self.L_F**2 + self.L_T**2 - D**2) / (2 * self.L_F * self.L_T)
        val_t = max(-1.0, min(1.0, val_t))
        beta = math.acos(val_t)
        theta_t = math.pi - beta
        return theta_c, theta_f, theta_t

class HexapodLeg:
    def __init__(self, name, m_x, m_y, m_yaw):
        self.name = name
        self.mount_x = m_x; self.mount_y = m_y; self.mount_yaw = m_yaw
        def_x = 0.18; def_y = 0.00; def_z = -0.15
        self.base_x = m_x + def_x * math.cos(m_yaw) - def_y * math.sin(m_yaw)
        self.base_y = m_y + def_x * math.sin(m_yaw) + def_y * math.cos(m_yaw)
        self.base_z = def_z


# ==========================================
# 2. KONTROLLER
# ==========================================
class SlarcController:
    def __init__(self):
        self.ik = HexapodIK()
        self.robot_id = None
        self.joint_map = {}
        self.cameras = None

        body_l = 0.250; body_w = 0.120; mid_y_off = 0.040
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
        self.cmd_vel_x = 0.0; self.cmd_vel_y = 0.0; self.cmd_yaw = 0.0
        self.cur_vel_x = 0.0; self.cur_vel_y = 0.0; self.cur_yaw = 0.0
        self.move_intent = 0.0

        self.body_height_offset = 0.0
        self.pitch = 0.0; self.roll = 0.0
        self.cg_offset_x = 0.0
        self.mid_leg_offset = 0.0
        self.rear_leg_offset = 0.0
        self.zentaur_progress = 0.0
        self.mid_crouch = 0.0
        self.rear_crouch = 0.0
        self.gripper_active = False
        self.grip_blend = 0.0
        self.arm_lift_offset = 0.0
        self.arm_reach_offset = 0.22

        self.phases_tripod = {"front_left": 0.0, "mid_right": 0.0, "rear_left": 0.0,
                              "front_right": 0.5, "mid_left": 0.5, "rear_right": 0.5}
        self.phases_ripple = {"front_left": 0.0,   "mid_right": 0.0,
                              "mid_left": 0.333,   "rear_right": 0.333,
                              "rear_left": 0.666,  "front_right": 0.666}
        self.phases_quad   = {"mid_left": 0.0, "rear_right": 0.25,
                              "mid_right": 0.5, "rear_left": 0.75}
        self.max_stride_x = 0.14
        self.max_stride_y = 0.10

        # Kamera-Anzeige-Toggle
        self._cam_frame = 0
        self._show_cam  = False

    def init_pybullet(self):
        generate_hexapod_urdf("slarc_primitives.urdf")
        p.connect(p.GUI)
        p.setAdditionalSearchPath(pybullet_data.getDataPath())
        p.setGravity(0, 0, -9.81)
        p.setPhysicsEngineParameter(fixedTimeStep=1./240.,
                                    numSolverIterations=100, numSubSteps=2)

        planeId = p.loadURDF("plane.urdf")
        p.changeDynamics(planeId, -1, lateralFriction=1.5,
                         spinningFriction=0.01, rollingFriction=0.01)

        # SLARC startet vor der Treppe
        self.robot_id = p.loadURDF("slarc_primitives.urdf", [0, 0, 0.15])

        for i in range(p.getNumJoints(self.robot_id)):
            info = p.getJointInfo(self.robot_id, i)
            joint_name = info[1].decode('utf-8')
            self.joint_map[joint_name] = i
            if "foot" in joint_name:
                p.changeDynamics(self.robot_id, i, lateralFriction=2.0,
                                 spinningFriction=0.01, rollingFriction=0.01,
                                 contactStiffness=10000.0, contactDamping=1000.0)

        # Dose
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

        # Treppe + Rampe
        print("\n  Erzeuge Treppenkomplex...")
        create_staircase()

        # Stereo-Kameras
        print("\n  Initialisiere Stereo-Kameras...")
        self.cameras = StereoCameras()

        for _ in range(120): p.stepSimulation()
        for i in range(p.getNumJoints(self.robot_id)):
            p.changeDynamics(self.robot_id, i, jointDamping=0.05)
        self.cmd_vel_x = 0.0; self.cmd_vel_y = 0.0
        for _ in range(120): self.update_gait(); p.stepSimulation()

    def update_gait(self):
        self.cur_vel_x += (self.cmd_vel_x - self.cur_vel_x) * 0.02
        self.cur_vel_y += (self.cmd_vel_y - self.cur_vel_y) * 0.02
        self.cur_yaw   += (self.cmd_yaw - self.cur_yaw) * 0.02
        is_moving = (abs(self.cur_vel_x) > 0.001 or
                     abs(self.cur_vel_y) > 0.001 or
                     abs(self.cur_yaw)   > 0.001)

        phase_speed = 0.0
        if self.gait_mode == 1: phase_speed = 0.010
        if self.gait_mode == 2: phase_speed = 0.005
        if self.gait_mode == 3: phase_speed = 0.006

        if is_moving:
            self.move_intent = min(self.move_intent + 0.05, 1.0)
            self.gait_phase = (self.gait_phase + phase_speed) % 1.0
        else:
            self.move_intent = max(self.move_intent - 0.05, 0.0)
            self.gait_phase = ((self.gait_phase + phase_speed) % 1.0
                               if self.move_intent > 0 else 0.0)

        if self.gait_mode == 3:
            self.zentaur_progress = min(self.zentaur_progress + 0.008, 1.0)
        else:
            self.zentaur_progress = max(self.zentaur_progress - 0.02, 0.0)

        target_grip  = 1.0 if self.gripper_active else 0.0
        self.grip_blend += (target_grip - self.grip_blend) * 0.05

        target_cg   = -0.10 * self.zentaur_progress if self.gait_mode == 3 else 0.0
        target_mid  =  0.08 * self.zentaur_progress if self.gait_mode == 3 else 0.0
        target_rear = -0.05 * self.zentaur_progress
        target_m_crouch = 0.02 * self.zentaur_progress if self.gait_mode == 3 else 0.0
        target_r_crouch = 0.05 * self.zentaur_progress if self.gait_mode == 3 else 0.0

        cg_ready   = self.cg_offset_x / target_cg if target_cg < -1e-6 else 0.0
        front_lift = max(0.0, min(1.0, (cg_ready - 0.85) / 0.15))

        self.cg_offset_x   += (target_cg   - self.cg_offset_x)   * 0.1
        self.mid_leg_offset += (target_mid  - self.mid_leg_offset) * 0.1
        self.rear_leg_offset+= (target_rear - self.rear_leg_offset)* 0.08
        self.mid_crouch     += (target_m_crouch - self.mid_crouch) * 0.1
        self.rear_crouch    += (target_r_crouch - self.rear_crouch)* 0.1

        cy = math.cos(self.pitch); sy = math.sin(self.pitch)
        cx = math.cos(self.roll);  sx = math.sin(self.roll)

        for leg in self.legs:
            if self.gait_mode == 3 and "front" in leg.name:
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
                    p_offset  = self.phases_quad.get(leg.name, 0.0)
                    leg_phase = (self.gait_phase + p_offset) % 1.0
                    st_ratio, sw_ratio, h_mult, s_mult = 0.8, 0.2, 2.0, 1.5

                if leg_phase < st_ratio:
                    factor = 1.0 - (2.0*(leg_phase/st_ratio)); step_z = 0.0
                else:
                    p_val  = (leg_phase - st_ratio) / sw_ratio
                    factor = -1.0 + (2.0*p_val)
                    step_z = math.sin(p_val*math.pi)*(self.step_height*h_mult)*self.move_intent

                leg_off = (self.mid_leg_offset if "mid" in leg.name else
                           self.rear_leg_offset if "rear" in leg.name else 0.0)
                leg_cr  = (self.mid_crouch if "mid" in leg.name else
                           self.rear_crouch if "rear" in leg.name else 0.0)

                target_x = leg.base_x + factor*((stride_x*s_mult)/2.0) - self.cg_offset_x + leg_off
                target_y = leg.base_y + factor*((stride_y*s_mult)/2.0)
                target_z = leg.base_z + step_z - self.body_height_offset + leg_cr

            rx  = target_x*cy + target_z*sy;  ry = target_y
            rz  = -target_x*sy + target_z*cy
            ry_new = ry*cx - rz*sx;           rz_new = ry*sx + rz*cx

            dx = rx - leg.mount_x; dy = ry_new - leg.mount_y; dz = rz_new
            local_x =  dx*math.cos(-leg.mount_yaw) - dy*math.sin(-leg.mount_yaw)
            local_y =  dx*math.sin(-leg.mount_yaw) + dy*math.cos(-leg.mount_yaw)

            angles = self.ik.calculate_leg_angles(local_x, local_y, dz)
            if angles:
                tc, tf, tt = angles
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
                force=4.0, maxVelocity=5.0,
                positionGain=0.05, velocityGain=1.0)

    def process_keyboard(self):
        keys = p.getKeyboardEvents()
        self.cmd_vel_x = 0.0; self.cmd_vel_y = 0.0; self.cmd_yaw = 0.0
        for key, state in keys.items():
            if state & p.KEY_IS_DOWN:
                if key == p.B3G_UP_ARROW:    self.cmd_vel_x =  self.max_stride_x
                if key == p.B3G_DOWN_ARROW:  self.cmd_vel_x = -self.max_stride_x
                if key == p.B3G_LEFT_ARROW:  self.cmd_vel_y =  self.max_stride_y
                if key == p.B3G_RIGHT_ARROW: self.cmd_vel_y = -self.max_stride_y
                if key == ord('q'): self.cmd_yaw =  0.3
                if key == ord('e'): self.cmd_yaw = -0.3
                if key == ord('w'): self.body_height_offset = min(self.body_height_offset+0.002,  0.05)
                if key == ord('s'): self.body_height_offset = max(self.body_height_offset-0.002, -0.05)
                if key == ord('i'): self.pitch = min(self.pitch+0.02,  0.3)
                if key == ord('k'): self.pitch = max(self.pitch-0.02, -0.3)
                if key == ord('j'): self.roll  = min(self.roll +0.02,  0.3)
                if key == ord('l'): self.roll  = max(self.roll -0.02, -0.3)
                if key == ord('t'): self.arm_lift_offset  = min(self.arm_lift_offset +0.002,  0.15)
                if key == ord('g'): self.arm_lift_offset  = max(self.arm_lift_offset -0.002, -0.05)
                if key == ord('f'): self.arm_reach_offset = min(self.arm_reach_offset+0.002,  0.28)
                if key == ord('h'): self.arm_reach_offset = max(self.arm_reach_offset-0.002,  0.10)

            if state & p.KEY_WAS_TRIGGERED:
                if key == ord('1'): self.gait_mode = 1; print("Modus: Tripod")
                if key == ord('2'): self.gait_mode = 2; print("Modus: Ripple")
                if key == ord('3'): self.gait_mode = 3; print("Modus: ZENTAUR")
                if key == ord('r'):
                    self.body_height_offset = 0.0; self.pitch = 0.0; self.roll = 0.0
                    self.gait_mode = 1; self.gripper_active = False
                    self.arm_lift_offset = 0.0; self.arm_reach_offset = 0.22
                if key == ord('p'):
                    self.step_height = min(self.step_height + 0.005, 0.12)
                    print(f"Beinehöhe: {self.step_height*100:.1f} cm")
                if key == ord('o'):
                    self.step_height = max(self.step_height - 0.005, 0.01)
                    print(f"Beinehöhe: {self.step_height*100:.1f} cm")
                if key == ord('+'):
                    self.max_stride_x = min(self.max_stride_x+0.02, 0.16)
                    print(f"Schrittweite: {self.max_stride_x*100:.0f} cm")
                if key == ord('-'):
                    self.max_stride_x = max(self.max_stride_x-0.02, 0.02)
                    print(f"Schrittweite: {self.max_stride_x*100:.0f} cm")
                if key == ord(' '):
                    self.gripper_active = not self.gripper_active
                    print("Greifer:", "ZU" if self.gripper_active else "AUF")
                if key == ord('c'):
                    self._show_cam = not self._show_cam
                    print("Kamera-Debug:", "AN" if self._show_cam else "AUS")

    def update_camera_debug(self):
        """Zeigt Kamerabild alle 30 Frames als Debug-Text in PyBullet."""
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
            textColorRGB=[1, 1, 0], lifeTime=1.0, textSize=1.2
        )


def main():
    robot = SlarcController()
    robot.init_pybullet()

    print("\n=== SLARC V3 — Treppe + Stereo-Kameras ===")
    print(" Pfeile    : Laufen          Q/E : Drehen")
    print(" W/S       : Körper heben/senken")
    print(" I/K       : Pitch           J/L : Roll")
    print(" 1/2/3     : Tripod/Ripple/Zentaur")
    print(" T/G       : Arme heben/senken")
    print(" F/H       : Arme vor/zurück")
    print(" Leertaste : Greifer Auf/Zu")
    print(" C         : Kamera-Debug an/aus")
    print(" R         : Reset")
    print(" P / O     : Beinehöhe größer / kleiner")
    print("\n Treppenkomplex bei x=1.0–4.0m")
    print(" 5 Stufen aufwärts → Plateau → 10 kleine Stufen abwärts\n")

    try:
        while True:
            robot.process_keyboard()
            robot.update_gait()
            robot.update_camera_debug()
            p.stepSimulation()
            time.sleep(1. / 240.)
    except KeyboardInterrupt:
        p.disconnect()


if __name__ == '__main__':
    main()