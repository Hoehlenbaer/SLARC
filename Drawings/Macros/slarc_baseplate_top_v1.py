# -*- coding: utf-8 -*-
"""
SLARC – obere Baseplate (Elektronikträger) inkl. Coxa-Servo-Aufnahme.   V1
FreeCAD 0.21 / 1.0: Makro ausführen. Parameter in P (unten) ändern und Makro neu ausführen
(die Plattenkontur mit den Schwenkfreigängen ist hier bewusst als Python-Geometrie gebaut,
nicht über Spreadsheet-Ausdrücke).

Koordinaten (wie slarc_sim_V10): X = vorn, Y = links, Z = oben, Ursprung = Körpermitte,
Z = 0 = Oberkante Hüllmaß der Coxa-Servos (ST3215 liegt mit Horn nach oben zwischen den Platten).

Inhalt
- Platte 400 x 150 (BODY_L x BODY_W) + seitliche Lappen für die mittleren Coxa-Servos.
- Je Coxa: Freischnitt für die obere Gabelwange über den Schwenkbereich ±coxa_rom,
  Zentriertasche für den erhabenen Gehäuseteil des Servos, 2 Sicherungsschrauben (Gehäusebohrungen).
- Elektronik oben: Raspberry Pi 5 (+ Hailo-8 HAT+), Waveshare General Driver for Robots,
  Stereo-Kamerahalterung vorn auf zwei Sockeln (Kabel-Freiraum für die FPCs darunter).
- Durchbrüche für Kabel nach unten, Bohrungen für Abstandsbolzen zur unteren Platte.
- Teilung in zwei Druckteile mit überlappendem Stoß (split_x, lap).
STEP-Modelle (Pi, Treiber, Relais, Kameras, ST3215) werden zur Kontrolle eingesetzt, wenn sie neben dem
Makro, im Makro-Ordner oder in STEP_DIR liegen.
"""
import math
import os

# ============================================================ Parameter
P = dict(
    # Körper / Coxa (aus slarc_sim_V10.py)
    body_l=400.0, body_w=150.0,
    coxa=[("FR", 200.0, -75.0, -30.0), ("FL", 200.0, 75.0, 30.0),
          ("MR", 0.0, -115.0, -90.0), ("ML", 0.0, 115.0, 90.0),
          ("RR", -200.0, -75.0, -150.0), ("RL", -200.0, 75.0, 150.0)],
    coxa_rom=95.0,          # Schwenkbereich ± [deg] für den Freischnitt (mech. Grenze Gabel/Gehäuse ca. ±98°)
    lobe_w=40.0,            # Breite der Lappen für die mittleren Servos (Ecken liegen im Freischnitt -> keine Spitzen)
    # Platte
    t=4.0,                  # Plattendicke
    pk=0.9,                 # Tiefe Zentriertasche (Platte liegt auf dem erhabenen Gehäuseteil; Seitenstege 1.1 tiefer)
    # Coxa-Gabel (aus Bein V4) + Freigang
    hub_r=13.0, arm_l=21.45, arm_w=13.0, fork_clr=1.5,
    # Servo-Details im Servo-Frame (aus ST3215.step)
    raised=(-34.5, -9.4, 7.3),      # erhabener Deckelteil: X von..bis, ±Y (STEP -34.2/±7.0 + Spiel)
    srv_holes=[(-29.0, 10.2), (-29.0, -10.2)], srv_hole_d=2.2,
    # Elektronik
    pi_x=115.0, pi_so=6.0, pi_hole_d=2.7,          # Pi 5: Mitte X, Bolzenhöhe, M2.5
    gdr_x=42.5, gdr_so=12.0, gdr_hole_d=2.7,       # Treiberboard: Lochbild-Mitte X, Bolzen (Stiftleiste unten 9.4)
    relay_on_top=False, relay_x=-110.0, relay_so=5.0, relay_hole_d=3.2,
    # Kamera
    cam_x=182.0,            # Frontfläche der Kamerahalterung
    ped_h=10.0,             # Sockelhöhe (Freiraum für FPC-Kabel unter der Halterung)
    cam_base=60.0,          # Baseline (muss zur Halterung passen)
    # Kabel / Abstandsbolzen / Teilung
    slots=[(0.0, 0.0, 12.0, 34.0), (-80.0, 0.0, 12.0, 40.0), (-150.0, 0.0, 12.0, 40.0), (150.0, 0.0, 10.0, 30.0)],
    standoffs=[(125.0, 55.0), (125.0, -55.0), (-125.0, 55.0), (-125.0, -55.0),
               (-40.0, 40.0), (-40.0, -40.0), (60.0, 45.0), (60.0, -45.0)],
    so_hole_d=3.2,
    split_x=-40.0, lap=24.0, lap_screws=[-62.0, -20.0, 20.0, 62.0],   # Vorderteil 252 x 209 mm
)
STEP_DIR = r""

# Stereo-Halterung (identisch zu slarc_stereo_mount_v1.py)
CAM = dict(pcb=39, hole_s=34, pilot_d=1.7, so_d=5, so_h=2, plate_t=4, holder_w=24.4, holder_h=16.3,
           win_c=.8, rim_c=.6, rim_t=3, bot_t=4, rim_d=12, fpc_w=20, fpc_off=.5, ear_l=10, ear_hole=3.2)

# ============================================================ Geometrie-Backend
try:
    import FreeCAD as App
    import Part
    FC = True
except ImportError:
    FC = False

if FC:
    V = App.Vector

    def box(x, y, z, L, W, H):
        return Part.makeBox(L, W, H, V(x, y, z))

    def cyl(x, y, z, r, h, ang=360.0, start=0.0):
        s = Part.makeCylinder(r, h, V(x, y, z), V(0, 0, 1), ang)
        if start:
            s.rotate(V(x, y, z), V(0, 0, 1), start)
        return s

    def cyly(x, y, z, r, h):
        return Part.makeCylinder(r, h, V(x, y, z), V(0, 1, 0))

    def xform(s, m):
        mm = App.Matrix(*m[0], *m[1], *m[2], 0, 0, 0, 1)
        s2 = s.copy(); s2.transformShape(mm)
        return s2

    def fuse(L):
        s = L[0]
        if len(L) > 1:
            s = s.multiFuse(L[1:])
        return s.removeSplitter()

    def cut(a, L):
        return a.cut(fuse(L)).removeSplitter() if L else a

    def common(a, b):
        return a.common(b)

    def read_step(p):
        return Part.read(p)
else:
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse, BRepAlgoAPI_Cut, BRepAlgoAPI_Common
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    from OCP.gp import gp_Pnt, gp_Ax2, gp_Dir, gp_Trsf
    from OCP.STEPControl import STEPControl_Reader

    def box(x, y, z, L, W, H):
        return BRepPrimAPI_MakeBox(gp_Pnt(x, y, z), L, W, H).Shape()

    def cyl(x, y, z, r, h, ang=360.0, start=0.0):
        s = BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(x, y, z), gp_Dir(0, 0, 1)), r, h, math.radians(ang)).Shape()
        if start:
            c, sn = math.cos(math.radians(start)), math.sin(math.radians(start))
            s = xform(s, ((c, -sn, 0, x - c * x + sn * y), (sn, c, 0, y - sn * x - c * y), (0, 0, 1, 0)))
        return s

    def cyly(x, y, z, r, h):
        return BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(x, y, z), gp_Dir(0, 1, 0)), r, h).Shape()

    def xform(s, m):
        t = gp_Trsf(); t.SetValues(*m[0], *m[1], *m[2])
        return BRepBuilderAPI_Transform(s, t, True).Shape()

    def fuse(L):
        s = L[0]
        for o in L[1:]:
            s = BRepAlgoAPI_Fuse(s, o).Shape()
        return s

    def cut(a, L):
        return BRepAlgoAPI_Cut(a, fuse(L)).Shape() if L else a

    def common(a, b):
        return BRepAlgoAPI_Common(a, b).Shape()

    def read_step(p):
        r = STEPControl_Reader(); r.ReadFile(p); r.TransferRoots()
        return r.OneShape()


# ============================================================ Hilfen
def m_rz(deg, tx=0.0, ty=0.0, tz=0.0):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return ((c, -s, 0, tx), (s, c, 0, ty), (0, 0, 1, tz))


def mul(a, b):
    """3x4 * 3x4 (affin)."""
    r = []
    for i in range(3):
        row = [sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)]
        row.append(sum(a[i][k] * b[k][3] for k in range(3)) + a[i][3])
        r.append(tuple(row))
    return tuple(r)


def rbox(cx, cy, yaw, x0, y0, z0, L, W, H):
    """Box im um yaw gedrehten Frame mit Ursprung (cx, cy)."""
    return xform(box(x0, y0, z0, L, W, H), m_rz(yaw, cx, cy))


def rcyl(cx, cy, yaw, lx, ly, z0, r, h):
    c, s = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    return cyl(cx + lx * c - ly * s, cy + lx * s + ly * c, z0, r, h)


Z_B = -P["pk"]                 # Plattenunterseite
Z_T = Z_B + P["t"]             # Plattenoberseite


def sweep_2d(cx, cy, yaw, z0, h):
    """Freischnitt der oberen Gabelwange über ±coxa_rom: erweiterter Sektor + Endlagen-Rechtecke + Nabe."""
    rom = P["coxa_rom"]; c = P["fork_clr"]
    L, W = P["arm_l"] + c, P["arm_w"] + c
    R = math.hypot(L, W)
    ext = rom + math.degrees(math.asin(W / L))      # Punkte mit r > L liegen bis asin(W/L) jenseits der Endlage
    parts = [cyl(cx, cy, z0, P["hub_r"] + c, h)]
    parts.append(cyl(cx, cy, z0, R, h) if ext >= 180 else cyl(cx, cy, z0, R, h, ang=2 * ext, start=yaw - ext))
    for s in (-1, 1):
        parts.append(rbox(cx, cy, yaw + s * rom, 0, -W, z0, L, 2 * W, h))
    return fuse(parts)


# ============================================================ Stereo-Halterung (Bracket-Frame)
def cam_bracket():
    g = type("g", (), dict(CAM, baseline=P["cam_base"]))
    W2 = g.baseline / 2 + g.pcb / 2 + g.rim_c + g.rim_t; H2 = g.pcb / 2 + g.rim_c + g.rim_t
    H2b = g.pcb / 2 + g.rim_c + g.bot_t; ZB = -g.rim_d; ZF = g.so_h + g.plate_t; D = ZF - ZB
    pos = [box(-W2, -H2b, g.so_h, 2 * W2, H2 + H2b, g.plate_t), box(-W2, H2 - g.rim_t, ZB, 2 * W2, g.rim_t, D),
           box(-W2, -H2b, ZB, 2 * W2, g.bot_t, D), box(-W2, -H2b, ZB, g.rim_t, H2 + H2b, D),
           box(W2 - g.rim_t, -H2b, ZB, g.rim_t, H2 + H2b, D),
           box(-W2 - g.ear_l, -H2b, ZB, g.ear_l, g.bot_t, D), box(W2, -H2b, ZB, g.ear_l, g.bot_t, D)]
    neg = []
    for sx in (-1, 1):
        cx = sx * g.baseline / 2
        neg.append(box(cx - g.holder_w / 2 - g.win_c, -g.holder_h / 2 - g.win_c, g.so_h - 1,
                       g.holder_w + 2 * g.win_c, g.holder_h + 2 * g.win_c, g.plate_t + 2))
        neg.append(box(cx + g.fpc_off - g.fpc_w / 2, -H2b - 1, ZB - 1, g.fpc_w, g.bot_t + 2, g.rim_d + 1))
        for hx, hy in ((1, 1), (-1, 1), (-1, -1), (1, -1)):
            pos.append(cyl(cx + hx * g.hole_s / 2, hy * g.hole_s / 2, 0, g.so_d / 2, g.so_h + .5))
            neg.append(cyl(cx + hx * g.hole_s / 2, hy * g.hole_s / 2, -.1, g.pilot_d / 2, g.so_h + g.plate_t - .9))
        neg.append(cyly(sx * (W2 + g.ear_l / 2), -H2b - 1, (ZB + ZF) / 2, g.ear_hole / 2, g.bot_t + 2))
    return cut(fuse(pos), neg), dict(W2=W2, H2=H2, H2b=H2b, ZF=ZF, ZB=ZB, ear_y=W2 + g.ear_l / 2, D=D)


def cam_matrix(dims):
    """Bracket-Frame (X quer, Y oben, Z vorn) -> Welt (X vorn, Y links, Z oben)."""
    return ((0, 0, 1, P["cam_x"] - dims["ZF"]), (1, 0, 0, 0), (0, 1, 0, Z_T + P["ped_h"] + dims["H2b"]))


# ============================================================ Platte
def plate_outline(z0, h):
    bl, bw = P["body_l"], P["body_w"]
    parts = [box(-bl / 2, -bw / 2, z0, bl, bw, h)]
    for _, x, y, yaw in P["coxa"]:
        if abs(abs(yaw) - 90) < 1e-6:
            sy = 1 if y > 0 else -1
            y0 = bw / 2 - 5 if sy > 0 else y
            parts.append(box(x - P["lobe_w"] / 2, y0, z0, P["lobe_w"], abs(y) - bw / 2 + 5, h))
    return fuse(parts)


def pi_holes():
    # Pi 5 lokal (STEP): Löcher (-39 | 19.1, ±24.5); eingebaut um +90° gedreht, Mitte bei (pi_x, 0)
    return [(P["pi_x"] - ly, lx) for lx in (-39.0, 19.1) for ly in (-24.5, 24.5)]


def gdr_holes():
    return [(P["gdr_x"] + dx, dy) for dx in (-24.5, 24.5) for dy in (-29.0, 29.0)]


def relay_holes():
    return [(P["relay_x"] + dx, dy) for dx in (-66.1, 66.1) for dy in (-25.4, 25.4)]


def PEDESTALS(dims):
    """(y0, Breite) der Sockel: unter den Laschen (innen verkürzt -> Servoschraube bleibt frei) + Mitte."""
    e = dims["ear_y"]
    return [(e - 3.0, 9.0), (-e - 6.0, 9.0), (-8.0, 16.0)]


def build():
    t, zb = P["t"], Z_B
    br, dims = cam_bracket()
    pos = [plate_outline(zb, t)]
    # Kamerasockel: unter den Laschen + Mitte, Tiefe = Halterungstiefe
    x1 = P["cam_x"] - dims["D"]
    for y0, w in PEDESTALS(dims):
        pos.append(box(x1, y0, Z_T - 0.5, dims["D"], w, P["ped_h"] + 0.5))
    neg = []
    for name, x, y, yaw in P["coxa"]:
        neg.append(sweep_2d(x, y, yaw, zb - 1, t + P["ped_h"] + 2))
        rx0, rx1, ry = P["raised"]
        neg.append(rbox(x, y, yaw, rx0, -ry, zb - 0.1, rx1 - rx0, 2 * ry, P["pk"] + 0.2))  # Decke bei z=+0.1
        for hx, hy in P["srv_holes"]:
            neg.append(rcyl(x, y, yaw, hx, hy, zb - 1, P["srv_hole_d"] / 2, t + 2))
    # Bohrungen Elektronik
    for hx, hy in pi_holes():
        neg.append(cyl(hx, hy, zb - 1, P["pi_hole_d"] / 2, t + 2))
    for hx, hy in gdr_holes():
        neg.append(cyl(hx, hy, zb - 1, P["gdr_hole_d"] / 2, t + 2))
    if P["relay_on_top"]:
        for hx, hy in relay_holes():
            neg.append(cyl(hx, hy, zb - 1, P["relay_hole_d"] / 2, t + 2))
    # Kamera-Laschen: M3 durch Sockel + Platte
    for yc in (dims["ear_y"], -dims["ear_y"]):
        neg.append(cyl(P["cam_x"] - dims["D"] / 2, yc, zb - 1, 1.6, t + P["ped_h"] + 2))
    for (sx, sy, sw, sl) in P["slots"]:
        neg.append(box(sx - sw / 2, sy - sl / 2, zb - 1, sw, sl, t + 2))
    for (sx, sy) in P["standoffs"]:
        neg.append(cyl(sx, sy, zb - 1, P["so_hole_d"] / 2, t + 2))
    for sy in P["lap_screws"]:
        neg.append(cyl(P["split_x"], sy, zb - 1, 1.6, t + 2))
    plate = cut(fuse(pos), neg)
    # Teilung mit Überlappungsstoß
    sx, lap, big = P["split_x"], P["lap"], 1000.0
    front = cut(plate, [box(-big, -big, zb - 1, big + sx - lap / 2, 2 * big, t + 50),
                        box(sx - lap / 2, -big, zb - 1, lap, 2 * big, t / 2 + 1)])
    rear = cut(plate, [box(sx + lap / 2, -big, zb - 1, big, 2 * big, t + 50),
                       box(sx - lap / 2, -big, zb + t / 2, lap, 2 * big, t + 50)])
    return dict(plate=plate, front=front, rear=rear, bracket=xform(br, cam_matrix(dims)),
                bracket_local=br, dims=dims)


# ============================================================ Platzierung der STEP-Modelle
def servo_matrix(x, y, yaw):
    # ST3215.step -> Servo-Frame (Achse Z, Hülle oben z=0, Gehäuse nach -X), dann Gier + Position
    m_step = ((-1, 0, 0, -25.5), (0, 0, 1, 0), (0, 1, 0, -7.5))
    return mul(m_rz(yaw, x, y, 0), m_step)


def placements():
    """(Name, STEP-Dateinamen, Matrix)"""
    out = [("RaspberryPi5", ("raspberry_pi_5.stp",), m_rz(90, P["pi_x"], 0, Z_T + P["pi_so"])),
           ("GeneralDriver", ("General_Driver_for_Robots_STEP.step", "General Driver for Robots STEP.step"),
            m_rz(0, P["gdr_x"] - 28.0, -32.5, Z_T + P["gdr_so"] + 0.41))]
    if P["relay_on_top"]:
        out.append(("Relay8", ("Relay_Module_-_8_Channel.STEP", "Relay Module - 8 Channel.STEP"),
                    ((1, 0, 0, P["relay_x"]), (0, 0, -1, 0), (0, 1, 0, Z_T + P["relay_so"] + 2.13))))
    for name, x, y, yaw in P["coxa"]:
        out.append(("ST3215_" + name, ("ST3215.step",), servo_matrix(x, y, yaw)))
    return out


def cam_placements(dims):
    m = cam_matrix(dims)
    return [("IMX296_" + n, ("IMX296_With_M12.stp", "IMX296 With M12.stp", "IMX296_With_M12 (2).stp"),
             mul(m, ((1, 0, 0, sx * P["cam_base"] / 2), (0, 1, 0, 0), (0, 0, 1, -2.5))))
            for n, sx in (("L", 1), ("R", -1))]


def find_step(names):
    dirs = [STEP_DIR] if STEP_DIR else []
    try:
        dirs.append(os.path.dirname(os.path.abspath(__file__)))
    except NameError:
        pass
    if FC:
        try:
            dirs.append(App.getUserMacroDir(True))
        except Exception:
            pass
    for d in dirs:
        for n in names:
            p = os.path.join(d, n)
            if d and os.path.isfile(p):
                return p
    return None


# ============================================================ FreeCAD
def run_freecad():
    doc = App.newDocument("SLARC_Baseplate_Top")
    gui = App.GuiUp
    if gui:
        import FreeCADGui as Gui
    g = build()

    def add(name, shape, color, vis=True):
        o = doc.addObject("Part::Feature", name); o.Shape = shape
        if gui:
            o.ViewObject.ShapeColor = color; o.ViewObject.Visibility = vis
        return o

    add("Baseplate_Top_Front", g["front"], (0.08, 0.08, 0.08))
    add("Baseplate_Top_Rear", g["rear"], (0.12, 0.12, 0.12))
    add("Stereo_Mount", g["bracket"], (0.08, 0.08, 0.08))
    cache = {}
    for name, files, m in placements() + cam_placements(g["dims"]):
        p = find_step(files)
        if not p:
            print("STEP fehlt:", files[0]); continue
        if p not in cache:
            cache[p] = read_step(p)
        col = (0.2, 0.2, 0.26) if name.startswith("ST3215") else (0.1, 0.45, 0.2)
        add(name, xform(cache[p], m), col)
    doc.recompute()
    if gui:
        Gui.activeDocument().activeView().viewIsometric(); Gui.SendMsgToActiveView("ViewFit")
    print("Obere Baseplate erzeugt: Vorderteil + Hinterteil (Teilung bei x = %.0f)" % P["split_x"])


if FC:
    run_freecad()
