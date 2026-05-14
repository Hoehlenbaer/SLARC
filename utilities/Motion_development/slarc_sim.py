import pybullet as p
import pybullet_data
import time
import math

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
# 1. REINE MATHEMATIK (IK Panzer)
# ==========================================
class HexapodIK:
    def __init__(self):
        self.L_C = 0.040; self.L_F = 0.120; self.L_T = 0.160

    def calculate_leg_angles(self, x, y, z):
        theta_c = math.atan2(y, x)
        L = math.sqrt(x**2 + y**2) - self.L_C
        if L < 0.02: L = 0.02
        
        D = math.sqrt(L**2 + z**2)
        if D > (self.L_F + self.L_T): 
            D = self.L_F + self.L_T - 0.001 
        min_D = abs(self.L_F - self.L_T)
        if D < min_D: 
            D = min_D + 0.001

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

        # NEU: Variablen für den Squat (In-die-Knie-Gehen)
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
        self.phases_quad =   {"mid_left": 0.0, "rear_right": 0.25,
                              "mid_right": 0.5, "rear_left": 0.75}

        self.max_stride_x = 0.14
        self.max_stride_y = 0.10

    def init_pybullet(self):
        generate_hexapod_urdf("slarc_primitives.urdf")
        p.connect(p.GUI)
        p.setAdditionalSearchPath(pybullet_data.getDataPath())
        p.setGravity(0, 0, -9.81)
        p.setPhysicsEngineParameter(fixedTimeStep=1./240., numSolverIterations=100, numSubSteps=2)
        
        planeId = p.loadURDF("plane.urdf")
        p.changeDynamics(planeId, -1, lateralFriction=1.5, spinningFriction=0.01, rollingFriction=0.01)
        
        self.robot_id = p.loadURDF("slarc_primitives.urdf", [0, 0, 0.15])
        
        for i in range(p.getNumJoints(self.robot_id)):
            info = p.getJointInfo(self.robot_id, i)
            joint_name = info[1].decode('utf-8')
            self.joint_map[joint_name] = i
            if "foot" in joint_name:
                p.changeDynamics(self.robot_id, i, lateralFriction=2.0, spinningFriction=0.01, rollingFriction=0.01,
                                 contactStiffness=10000.0, contactDamping=1000.0)

        can_mass = 0.350 
        can_radius = 0.033 
        can_height = 0.115 
        col_canId = p.createCollisionShape(p.GEOM_CYLINDER, radius=can_radius, height=can_height)
        vis_canId = p.createVisualShape(p.GEOM_CYLINDER, radius=can_radius, length=can_height, rgbaColor=[0.8, 0.1, 0.1, 1])
        self.can_id = p.createMultiBody(baseMass=can_mass, baseCollisionShapeIndex=col_canId, baseVisualShapeIndex=vis_canId, basePosition=[0.37, 0, 0.06])
        p.changeDynamics(self.can_id, -1, lateralFriction=2.0, spinningFriction=0.1, rollingFriction=0.1)

        for _ in range(120): p.stepSimulation()
        for i in range(p.getNumJoints(self.robot_id)): p.changeDynamics(self.robot_id, i, jointDamping=0.05)
        self.cmd_vel_x = 0.0; self.cmd_vel_y = 0.0
        for _ in range(120): self.update_gait(); p.stepSimulation()

    def update_gait(self):
        self.cur_vel_x += (self.cmd_vel_x - self.cur_vel_x) * 0.02
        self.cur_vel_y += (self.cmd_vel_y - self.cur_vel_y) * 0.02
        self.cur_yaw   += (self.cmd_yaw - self.cur_yaw) * 0.02
        is_moving = abs(self.cur_vel_x) > 0.001 or abs(self.cur_vel_y) > 0.001 or abs(self.cur_yaw) > 0.001
        
        phase_speed = 0.0
        if self.gait_mode == 1: phase_speed = 0.010
        if self.gait_mode == 2: phase_speed = 0.005
        if self.gait_mode == 3: phase_speed = 0.006 

        if is_moving:
            self.move_intent = min(self.move_intent + 0.05, 1.0)
            self.gait_phase = (self.gait_phase + phase_speed) % 1.0
        else:
            self.move_intent = max(self.move_intent - 0.05, 0.0)
            self.gait_phase = (self.gait_phase + phase_speed) % 1.0 if self.move_intent > 0 else 0.0

        if self.gait_mode == 3:
            self.zentaur_progress = min(self.zentaur_progress + 0.008, 1.0)
        else:
            self.zentaur_progress = max(self.zentaur_progress - 0.02, 0.0)

        target_grip = 1.0 if self.gripper_active else 0.0
        self.grip_blend += (target_grip - self.grip_blend) * 0.05

        target_cg = -0.10 * self.zentaur_progress if self.gait_mode == 3 else 0.0
        target_mid = 0.08 * self.zentaur_progress if self.gait_mode == 3 else 0.0
        target_rear = -0.05 * self.zentaur_progress
        
        # NEU: Das Squat-Tuning! Hinterbeine knicken um satte 5 cm ein.
        target_m_crouch = 0.02 * self.zentaur_progress if self.gait_mode == 3 else 0.0
        target_r_crouch = 0.05 * self.zentaur_progress if self.gait_mode == 3 else 0.0
        
        cg_ready = self.cg_offset_x / target_cg if target_cg < -1e-6 else 0.0
        front_lift = max(0.0, min(1.0, (cg_ready - 0.85) / 0.15))
        
        self.cg_offset_x += (target_cg - self.cg_offset_x) * 0.1
        self.mid_leg_offset += (target_mid - self.mid_leg_offset) * 0.1
        self.rear_leg_offset += (target_rear - self.rear_leg_offset) * 0.08
        
        self.mid_crouch += (target_m_crouch - self.mid_crouch) * 0.1
        self.rear_crouch += (target_r_crouch - self.rear_crouch) * 0.1

        cy = math.cos(self.pitch); sy = math.sin(self.pitch)
        cx = math.cos(self.roll);  sx = math.sin(self.roll)

        for leg in self.legs:
            if self.gait_mode == 3 and "front" in leg.name:
                stance_x, stance_y, stance_z = leg.base_x, leg.base_y, leg.base_z
                y_open = 0.14 if "left" in leg.name else -0.14
                y_closed = 0.025 if "left" in leg.name else -0.025 
                
                zentaur_x = leg.mount_x + self.arm_reach_offset 
                zentaur_y = y_open * (1.0 - self.grip_blend) + y_closed * self.grip_blend
                zentaur_z = 0.02 + self.arm_lift_offset 
                
                t = front_lift
                target_x = stance_x * (1-t) + zentaur_x * t
                target_y = stance_y * (1-t) + zentaur_y * t
                target_z = stance_z * (1-t) + zentaur_z * t
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
                    p_offset = self.phases_quad.get(leg.name, 0.0)
                    leg_phase = (self.gait_phase + p_offset) % 1.0
                    st_ratio, sw_ratio, h_mult, s_mult = 0.8, 0.2, 2.0, 1.5 

                if leg_phase < st_ratio:
                    factor = 1.0 - (2.0 * (leg_phase / st_ratio)); step_z = 0.0
                else:
                    p_val = (leg_phase - st_ratio) / sw_ratio
                    factor = -1.0 + (2.0 * p_val); step_z = math.sin(p_val * math.pi) * (self.step_height * h_mult) * self.move_intent

                leg_off = self.mid_leg_offset if "mid" in leg.name else (self.rear_leg_offset if "rear" in leg.name else 0.0)
                # NEU: Den Crouch-Offset auf Z anwenden
                leg_cr = self.mid_crouch if "mid" in leg.name else (self.rear_crouch if "rear" in leg.name else 0.0)
                
                target_x = leg.base_x + factor * ((stride_x * s_mult) / 2.0) - self.cg_offset_x + leg_off
                target_y = leg.base_y + factor * ((stride_y * s_mult) / 2.0)
                target_z = leg.base_z + step_z - self.body_height_offset + leg_cr

            rx = target_x * cy + target_z * sy; ry = target_y
            rz = -target_x * sy + target_z * cy
            ry_new = ry * cx - rz * sx; rz_new = ry * sx + rz * cx

            dx = rx - leg.mount_x; dy = ry_new - leg.mount_y; dz = rz_new
            local_x = dx * math.cos(-leg.mount_yaw) - dy * math.sin(-leg.mount_yaw)
            local_y = dx * math.sin(-leg.mount_yaw) + dy * math.cos(-leg.mount_yaw)

            angles = self.ik.calculate_leg_angles(local_x, local_y, dz)
            if angles:
                tc, tf, tt = angles
                self.set_servo(f"{leg.name}_coxa_joint", tc)
                self.set_servo(f"{leg.name}_femur_joint", tf) 
                self.set_servo(f"{leg.name}_tibia_joint", tt) 

    def set_servo(self, joint_name, angle_rad):
        if joint_name in self.joint_map:
            p.setJointMotorControl2(bodyIndex=self.robot_id, 
                                    jointIndex=self.joint_map[joint_name], 
                                    controlMode=p.POSITION_CONTROL, 
                                    targetPosition=angle_rad, 
                                    force=4.0, 
                                    maxVelocity=5.0,
                                    positionGain=0.05, 
                                    velocityGain=1.0)

    def process_keyboard(self):
        keys = p.getKeyboardEvents()
        self.cmd_vel_x = 0.0; self.cmd_vel_y = 0.0; self.cmd_yaw = 0.0
        for key, state in keys.items():
            if state & p.KEY_IS_DOWN:
                if key == p.B3G_UP_ARROW:    self.cmd_vel_x = self.max_stride_x
                if key == p.B3G_DOWN_ARROW:  self.cmd_vel_x = -self.max_stride_x
                if key == p.B3G_LEFT_ARROW:  self.cmd_vel_y = self.max_stride_y
                if key == p.B3G_RIGHT_ARROW: self.cmd_vel_y = -self.max_stride_y
                if key == ord('q'): self.cmd_yaw = 0.3
                if key == ord('e'): self.cmd_yaw = -0.3
                if key == ord('w'): self.body_height_offset = min(self.body_height_offset + 0.002, 0.05)
                if key == ord('s'): self.body_height_offset = max(self.body_height_offset - 0.002, -0.05)
                if key == ord('i'): self.pitch = min(self.pitch + 0.02, 0.3)
                if key == ord('k'): self.pitch = max(self.pitch - 0.02, -0.3)
                if key == ord('j'): self.roll = min(self.roll + 0.02, 0.3)
                if key == ord('l'): self.roll = max(self.roll - 0.02, -0.3)
                
                if key == ord('t'): self.arm_lift_offset = min(self.arm_lift_offset + 0.002, 0.15)
                if key == ord('g'): self.arm_lift_offset = max(self.arm_lift_offset - 0.002, -0.05)
                if key == ord('f'): self.arm_reach_offset = min(self.arm_reach_offset + 0.002, 0.28) 
                if key == ord('h'): self.arm_reach_offset = max(self.arm_reach_offset - 0.002, 0.10) 

            if state & p.KEY_WAS_TRIGGERED:
                if key == ord('1'): self.gait_mode = 1; print("Modus: Tripod")
                if key == ord('2'): self.gait_mode = 2; print("Modus: Ripple")
                if key == ord('3'): self.gait_mode = 3; print("Modus: ZENTAUR (Dynamic Squat)")
                if key == ord('r'): 
                    self.body_height_offset = 0.0; self.pitch = 0.0; self.roll = 0.0
                    self.gait_mode = 1; self.gripper_active = False
                    self.arm_lift_offset = 0.0; self.arm_reach_offset = 0.22
                
                if key == ord('+'): 
                    self.max_stride_x = min(self.max_stride_x + 0.02, 0.16)
                    print(f"Schrittweite erhöht: {self.max_stride_x * 100:.0f} cm")
                if key == ord('-'): 
                    self.max_stride_x = max(self.max_stride_x - 0.02, 0.02)
                    print(f"Schrittweite verringert: {self.max_stride_x * 100:.0f} cm")
                
                if key == ord(' '): 
                    self.gripper_active = not self.gripper_active
                    print("Greifer:", "ZU" if self.gripper_active else "AUF")

def main():
    robot = SlarcController(); robot.init_pybullet()
    print("\n=== SLARC V9.2 (Kinematic Singularity Fix) ===")
    print(" + / -     : Schrittweite ändern")
    print(" 1, 2, 3   : Modus wechseln")
    print(" W / S     : Körper heben / senken")
    print(" Leertaste : Greifer Auf/Zu")
    print(" T / G     : Arme heben / senken")
    print(" F / H     : Arme vor / zurück")
    print(" Pfeile    : Laufen\n")
    try:
        while True:
            robot.process_keyboard(); robot.update_gait(); p.stepSimulation(); time.sleep(1./240.)
    except KeyboardInterrupt: p.disconnect()

if __name__ == '__main__': main()