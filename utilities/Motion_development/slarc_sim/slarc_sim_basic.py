import pybullet as p
import pybullet_data
import time
import math

# ==========================================
# 0. URDF GENERATOR
# ==========================================
def generate_hexapod_urdf(filename="slarc_primitives.urdf"):
    body_l = 0.200; body_w = 0.120; body_h = 0.040
    coxa_l = 0.040; femur_l = 0.120; tibia_l = 0.160
    
    legs = [
        ("front_right",  body_l/2, -body_w/2, -math.radians(30)),
        ("front_left",   body_l/2,  body_w/2,  math.radians(30)),
        ("mid_right",    0,        -body_w/2, -math.radians(90)),
        ("mid_left",     0,         body_w/2,  math.radians(90)),
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
    </link>"""
    urdf += "</robot>"
    with open(filename, "w") as f: f.write(urdf)

# ==========================================
# 1. REINE MATHEMATIK (IK & Spider-Stance Fix)
# ==========================================
class HexapodIK:
    def __init__(self):
        self.L_C = 0.040; self.L_F = 0.120; self.L_T = 0.160

    def calculate_leg_angles(self, x, y, z):
        theta_c = math.atan2(y, x)
        L = math.sqrt(x**2 + y**2) - self.L_C
        D = math.sqrt(L**2 + z**2)
        if D > (self.L_F + self.L_T): D = self.L_F + self.L_T - 0.001 

        # FIX: Knie zeigt nach außen/oben!
        alpha = math.atan2(z, L) 
        beta = math.acos((self.L_F**2 + D**2 - self.L_T**2) / (2 * self.L_F * D))
        theta_f = alpha + beta # PLUS sorgt für Spider-Stance (Knie hoch)
        
        gamma = math.acos((self.L_F**2 + self.L_T**2 - D**2) / (2 * self.L_F * self.L_T))
        theta_t = gamma - math.pi # Tibia knickt wieder nach unten
        
        return theta_c, theta_f, theta_t

# ==========================================
# 2. BEIN-KLASSE (Kapselt jedes Bein für C++)
# ==========================================
class HexapodLeg:
    def __init__(self, name, m_x, m_y, m_yaw, tripod_group):
        self.name = name
        self.mount_x = m_x
        self.mount_y = m_y
        self.mount_yaw = m_yaw
        self.tripod_group = tripod_group
        
        # Lokale Standard-Fußposition (Abstand von der Schulter)
        def_x = 0.12; def_y = 0.00; def_z = -0.18
        
        # Globale Standard-Fußposition (Abstand vom Körperzentrum)
        self.base_x = m_x + def_x * math.cos(m_yaw) - def_y * math.sin(m_yaw)
        self.base_y = m_y + def_x * math.sin(m_yaw) + def_y * math.cos(m_yaw)
        self.base_z = def_z

# ==========================================
# 3. ROBOTER KONTROLLE (Body Kinematics & Gait)
# ==========================================
class SlarcController:
    def __init__(self):
        self.ik = HexapodIK()
        self.robot_id = None
        self.joint_map = {}
        
        body_l = 0.200; body_w = 0.120
        self.legs = [
            HexapodLeg("front_right",  body_l/2, -body_w/2, -math.radians(30),  2),
            HexapodLeg("front_left",   body_l/2,  body_w/2,  math.radians(30),  1),
            HexapodLeg("mid_right",    0,        -body_w/2, -math.radians(90),  1),
            HexapodLeg("mid_left",     0,         body_w/2,  math.radians(90),  2),
            HexapodLeg("rear_right",  -body_l/2, -body_w/2, -math.radians(150), 2),
            HexapodLeg("rear_left",   -body_l/2,  body_w/2,  math.radians(150), 1)
        ]
        
        self.gait_phase = 0.0
        self.step_height = 0.04
        
        # Geschwindigkeits-Vektoren
        self.cmd_vel_x = 0.0 # Vorwärts
        self.cmd_vel_y = 0.0 # Seitwärts
        self.cmd_yaw   = 0.0 # Drehen
        
        # Höhen-Offset des Chassis (Verändert durch W/S)
        self.body_height_offset = 0.0 

    def init_pybullet(self):
        generate_hexapod_urdf("slarc_primitives.urdf")
        p.connect(p.GUI)
        p.setAdditionalSearchPath(pybullet_data.getDataPath())
        p.setGravity(0, 0, -9.81)
        p.loadURDF("plane.urdf")
        
        self.robot_id = p.loadURDF("slarc_primitives.urdf", [0, 0, 0.30])
        for i in range(p.getNumJoints(self.robot_id)):
            info = p.getJointInfo(self.robot_id, i)
            self.joint_map[info[1].decode('utf-8')] = i

    def update_gait(self):
        is_moving = abs(self.cmd_vel_x) > 0.001 or abs(self.cmd_vel_y) > 0.001 or abs(self.cmd_yaw) > 0.001
        
        if is_moving:
            self.gait_phase += 0.02
            if self.gait_phase > 1.0: self.gait_phase -= 1.0
        else:
            self.gait_phase = 0.0 # Park-Position

        for leg in self.legs:
            # 1. Schrittweite für DIESES Bein berechnen (Translation + Rotation)
            # Beim Drehen schwingen die äußeren Beine schneller als die inneren.
            stride_x = self.cmd_vel_x - self.cmd_yaw * leg.base_y
            stride_y = self.cmd_vel_y + self.cmd_yaw * leg.base_x
            
            leg_phase = self.gait_phase if leg.tripod_group == 1 else (self.gait_phase + 0.5) % 1.0

            # 2. Position auf der Lauf-Kurve
            if leg_phase < 0.5:
                # STANCE (Fuß am Boden, Körper schiebt vor)
                p_val = leg_phase / 0.5
                factor = 1.0 - (2.0 * p_val) 
                step_x = factor * (stride_x / 2.0)
                step_y = factor * (stride_y / 2.0)
                step_z = 0.0
            else:
                # SWING (Fuß in der Luft)
                p_val = (leg_phase - 0.5) / 0.5
                factor = -1.0 + (2.0 * p_val)
                step_x = factor * (stride_x / 2.0)
                step_y = factor * (stride_y / 2.0)
                step_z = math.sin(p_val * math.pi) * self.step_height

            # 3. Globale Zielposition des Fußes relativ zum Körperzentrum
            target_x = leg.base_x + step_x
            target_y = leg.base_y + step_y
            target_z = leg.base_z + step_z - self.body_height_offset

            # 4. In das lokale Schulter-Koordinatensystem umrechnen
            dx = target_x - leg.mount_x
            dy = target_y - leg.mount_y
            dz = target_z
            
            local_x = dx * math.cos(-leg.mount_yaw) - dy * math.sin(-leg.mount_yaw)
            local_y = dx * math.sin(-leg.mount_yaw) + dy * math.cos(-leg.mount_yaw)
            local_z = dz

            # 5. IK anwenden
            angles = self.ik.calculate_leg_angles(local_x, local_y, local_z)
            if angles:
                tc, tf, tt = angles
                # Vorzeichen für Femur und Tibia abhängig von PyBullet-URDF Achsen
                self.set_servo(f"{leg.name}_coxa_joint", tc)
                self.set_servo(f"{leg.name}_femur_joint", -tf) 
                self.set_servo(f"{leg.name}_tibia_joint", -tt) 

    def set_servo(self, joint_name, angle_rad):
        if joint_name in self.joint_map:
            p.setJointMotorControl2(
                bodyIndex=self.robot_id, jointIndex=self.joint_map[joint_name],
                controlMode=p.POSITION_CONTROL, targetPosition=angle_rad, force=3.0
            )

    def process_keyboard(self):
        keys = p.getKeyboardEvents()
        
        self.cmd_vel_x = 0.0
        self.cmd_vel_y = 0.0
        self.cmd_yaw = 0.0
        
        max_stride = 0.08 # 8cm Schrittweite
        max_turn = 0.3    # Drehrate

        for key, state in keys.items():
            if state & p.KEY_IS_DOWN:
                # Laufen (Pfeiltasten)
                if key == p.B3G_UP_ARROW:    self.cmd_vel_x = max_stride
                if key == p.B3G_DOWN_ARROW:  self.cmd_vel_x = -max_stride
                if key == p.B3G_LEFT_ARROW:  self.cmd_vel_y = max_stride
                if key == p.B3G_RIGHT_ARROW: self.cmd_vel_y = -max_stride
                
                # Drehen (Q / E)
                if key == ord('q'): self.cmd_yaw = max_turn
                if key == ord('e'): self.cmd_yaw = -max_turn
                
                # Höhe (W / S) - Erlaubt +- 5cm Höhenverstellung
                if key == ord('w'): self.body_height_offset = min(self.body_height_offset + 0.002, 0.05)
                if key == ord('s'): self.body_height_offset = max(self.body_height_offset - 0.002, -0.05)

# ==========================================
# 4. HAUPTSCHLEIFE
# ==========================================
def main():
    robot = SlarcController()
    robot.init_pybullet()
    print("SLARC Kinematik & Gait Engine V2 aktiv!")
    print("Steuerung:")
    print(" Pfeiltasten : Laufen (Vor/Zurück/Strafe)")
    print(" Q / E       : Auf der Stelle drehen (Gait-basiert)")
    print(" W / S       : Körper heben / senken")
    
    try:
        while True:
            robot.process_keyboard()
            robot.update_gait()
            p.stepSimulation()
            time.sleep(1./240.)
    except KeyboardInterrupt:
        p.disconnect()
        print("Simulation beendet.")

if __name__ == '__main__':
    main()