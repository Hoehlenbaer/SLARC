import json, math
D = json.load(open("/tmp/claude-0/run/urdf_data.json"))
L, G = D["links"], D["geo"]
P = G["P"]
OUT = "/tmp/claude-0/urdf/slarc_urdf/slarc_cad.urdf"
mm = 0.001
COXA = [("front_right", 200.0, -75.0, -30.0, "R"), ("front_left", 200.0, 75.0, 30.0, "L"),
        ("mid_right", 0.0, -115.0, -90.0, "R"), ("mid_left", 0.0, 115.0, 90.0, "L"),
        ("rear_right", -200.0, -75.0, -150.0, "R"), ("rear_left", -200.0, 75.0, 150.0, "L")]
LIM = {"coxa": 95.0, "femur": 112.0, "tibia": 112.0}   # mech. Grenzen aus dem CAD (Bein V9.1: Berührung ab 117°)


def f(v): return "%.6g" % v


def inertial(k):
    l = L[k]; m = l["m"] / 1000.0; c = [v * mm for v in l["c"]]; I = l["I"]; s = 1e-9
    return ('<inertial><origin xyz="%s %s %s"/><mass value="%s"/>'
            '<inertia ixx="%s" ixy="%s" ixz="%s" iyy="%s" iyz="%s" izz="%s"/></inertial>'
            % (f(c[0]), f(c[1]), f(c[2]), f(m), f(I[0][0] * s), f(I[0][1] * s), f(I[0][2] * s),
               f(I[1][1] * s), f(I[1][2] * s), f(I[2][2] * s)))


def mesh(fname, rgba, name):
    return ('<visual><geometry><mesh filename="meshes/%s" scale="0.001 0.001 0.001"/></geometry>'
            '<material name="%s"><color rgba="%s"/></material></visual>' % (fname, name, rgba))


def bbox_col(bb, pad=0.0):
    x0, x1, y0, y1, z0, z1 = bb
    return ('<collision><origin xyz="%s %s %s"/><geometry><box size="%s %s %s"/></geometry></collision>'
            % (f((x0 + x1) / 2 * mm), f((y0 + y1) / 2 * mm), f((z0 + z1) / 2 * mm),
               f((x1 - x0 + pad) * mm), f((y1 - y0 + pad) * mm), f((z1 - z0 + pad) * mm)))


def box(cx, cy, cz, sx, sy, sz, pitch=0.0):
    return ('<collision><origin xyz="%s %s %s" rpy="0 %s 0"/><geometry><box size="%s %s %s"/></geometry></collision>'
            % (f(cx * mm), f(cy * mm), f(cz * mm), f(pitch), f(sx * mm), f(sy * mm), f(sz * mm)))


PETG = "0.12 0.12 0.13 1"
cam = G["cam_bb"]
u = []
u.append('<?xml version="1.0"?>\n<!-- SLARC aus dem FreeCAD-Modell (SLARC.FCStd): Femur %g / Tibia-Sehne %g / Knick %g°, Masse %.0f g.\n'
         '     Generiert, nicht von Hand ändern. Gelenk-Namen und Vorzeichen wie slarc_sim_V10 (+ = nach unten). -->'
         % (P["femur_len"], P["tibia_len"], P["tib_bend"], D["total"]))
u.append('<robot name="slarc">')
u.append('  <link name="base_link">')
u.append('    ' + mesh("base.stl", PETG, "petg"))
u.append('    ' + box(0, 0, -17.95, 400, 150, 42.1))                      # beide Platten + Coxa-Servos
u.append('    ' + box(0, 0, -17.95, 40, 200, 42.1))                       # Lappen mittlere Coxas
u.append('    <collision><geometry><mesh filename="meshes/cover_hull.stl" scale="0.001 0.001 0.001"/></geometry></collision>')
u.append('    ' + box((cam[0] + cam[1]) / 2, 0, (cam[4] + cam[5]) / 2, cam[1] - cam[0], cam[3] - cam[2], cam[5] - cam[4]))
u.append('    ' + inertial("base_"))
u.append('  </link>')
b = math.radians(P["tib_bend"]); ta = P["tib_a"]; seg2 = P["foot_seg"] - P["foot_r"]
ball = G["BALL_T"]
for name, x, y, yaw, s in COXA:
    lim = {k: math.radians(v) for k, v in LIM.items()}
    u.append(f'''  <joint name="{name}_coxa_joint" type="revolute">
    <parent link="base_link"/><child link="{name}_coxa"/>
    <origin xyz="{f(x*mm)} {f(y*mm)} 0" rpy="0 0 {f(math.radians(yaw))}"/><axis xyz="0 0 1"/>
    <limit lower="{f(-lim['coxa'])}" upper="{f(lim['coxa'])}" effort="2.94" velocity="4.71"/>
  </joint>
  <link name="{name}_coxa">
    {mesh("coxa_%s.stl" % s, PETG, "petg")}
    {bbox_col(L["coxa_" + s]["bb"])}
    {inertial("coxa_" + s)}
  </link>
  <joint name="{name}_femur_joint" type="revolute">
    <parent link="{name}_coxa"/><child link="{name}_femur"/>
    <origin xyz="{f(P['coxa_len']*mm)} 0 {f(P['zc']*mm)}"/><axis xyz="0 1 0"/>
    <limit lower="{f(-lim['femur'])}" upper="{f(lim['femur'])}" effort="2.94" velocity="4.71"/>
  </joint>
  <link name="{name}_femur">
    {mesh("femur_%s.stl" % s, PETG, "petg")}
    {bbox_col(L["femur_" + s]["bb"])}
    {inertial("femur_" + s)}
  </link>
  <joint name="{name}_tibia_joint" type="revolute">
    <parent link="{name}_femur"/><child link="{name}_tibia"/>
    <origin xyz="{f(P['femur_len']*mm)} 0 0"/><axis xyz="0 1 0"/>
    <limit lower="{f(-lim['tibia'])}" upper="{f(lim['tibia'])}" effort="2.94" velocity="4.71"/>
  </joint>
  <link name="{name}_tibia">
    {mesh("tibia_%s.stl" % s, PETG, "petg")}
    {box(6.5, 0, 0, 39, 46, 26)}
    {box((26 + ta) / 2, 0, 0, ta - 26 + 10, P['link_h'], P['link_w'])}
    {box(ta + seg2 / 2 * math.cos(b), 0, -seg2 / 2 * math.sin(b), seg2 - 8, P['link_h'], P['link_w'], b)}
    {inertial("tibia_" + s)}
  </link>
  <joint name="{name}_foot_joint" type="fixed">
    <parent link="{name}_tibia"/><child link="{name}_foot"/>
    <origin xyz="{f(ball[0]*mm)} 0 {f(ball[2]*mm)}"/>
  </joint>
  <link name="{name}_foot">
    {mesh("foot_%s.stl" % s, "0.30 0.31 0.34 1", "tpu")}
    <collision><geometry><sphere radius="{f(P['foot_r']*mm)}"/></geometry></collision>
    {inertial("foot_" + s)}
  </link>''')
u.append('</robot>\n')
open(OUT, "w").write("\n".join(u))
print("ok", OUT)
