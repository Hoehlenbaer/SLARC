# -*- coding: utf-8 -*-
"""
SLARC – Stereo-Kamerahalterung für 2x IMX296-Modul mit M12-Objektiv (39x39 mm Board).   V1.5.2
(V1.5.2: Objektiv ZH3019-14 als Kontrollkörper (LENS); Kamera-STEP wird auch als \"IMX296 With M12.stp\" gefunden)
(V1.5.1: IMU-Bunde bis zur Frontfläche verlängert (D-Form) – sie hingen beim Druck auf der Front 0.25 mm über dem Bett in der Luft)
(V1.5: Ecken gerundet – obere Rahmenecken R corner_r, Laschenenden rund (ear_r), Kehle zwischen Rahmen und Lasche
 (ear_fil). Sieht weniger kastig aus und die runden Ecken der Frontfläche heben sich beim Druck kaum ab.)
(V1.4.1: Bunde der IMU-Kernlöcher 0.5 mm nach hinten (imu_hz 2.5) – standen 0.25 mm über die Frontfläche, Druck auf der Front ging nicht)
(V1.4: Platz für die Zusatz-IMU ICM20948 (Pimoroni-Breakout 19x19, 2x M2.5 im Abstand 13.6 mm, 2.7 mm von den Kanten) mittig auf dem oberen
 Rahmen -> starr zum Stereo-Paar, nahe der Mitte zwischen den optischen Achsen; per IMU_MOUNT abschaltbar)
(V1.3: Trigger-Schlitze per TRIG_SLOTS abschaltbar, Standard aus – die Kabel laufen nach hinten weg)
(V1.2: Kabelschlitz oben für Trigger/Strobe-Stiftleisten, Tasche für Trigger-Verteilerplatine zwischen
 den Kameras, Baseline 65 mm)
(V1.1: Aliase W2/H2/H2b umbenannt – FreeCAD lehnt Zellnamen-ähnliche Aliase ab)
FreeCAD 0.21 / 1.0 – Makro ausführen oder:
    exec(open(r"PFAD/slarc_stereo_mount_v1.py", encoding="utf-8").read())

Konzept
- Ein Bauteil: Frontplatte mit zwei Fenstern für die M12-Halter, umlaufender Rahmen nach hinten
  (oben, unten, seitlich) als Torsionsversteifung. Beide Boards liegen auf Distanzbolzen an der Rückseite
  derselben Platte -> Sensorebenen koplanar, optische Achsen parallel (Fertigungslage: Frontfläche aufs Druckbett).
- Boards von hinten mit 4x M2 je Board (selbstschneidend in PETG, Sackloch, Frontfläche bleibt geschlossen).
- FPC-Buchsen auf der Board-Rückseite unten -> Kabelschlitze im unteren Rahmen.
- Befestigung am Körper: zwei seitliche Laschen mit M3-Durchgang (senkrecht).
- Objektive ragen vorn heraus -> Fokus von vorn zugänglich, keine Vignettierung durch die Platte.

Koordinaten: X = quer (Baseline), Y = oben, Z = Blickrichtung. Z=0 = Board-Oberseite (Bauteilseite).
Kamera-STEP (IMX296_With_M12.stp) wird, falls vorhanden, zur Kontrolle eingesetzt (Board-Oberseite im STEP z=2.5).
"""
import os
import re
import FreeCAD as App
import Part

CAM_STEP = r""        # Pfad zum Kamera-STEP; leer = neben dem Makro / im Makro-Ordner suchen
CAM_STEP_NAMES = ("IMX296_With_M12.stp", "IMX296 With M12.stp", "IMX296_With_M12 (2).stp", "IMX296_With_M12.step")
CAM_STEP_BOARD_TOP = 2.5
CAM_SENSOR_Z = 1.7      # Sensoroberfläche über der Board-Oberseite (STEP: z 4.2 - 2.5)
LENS = True             # M12-Objektiv ZH3019-14 als Kontrollkörper einsetzen (kein Druckteil)
IMU_MOUNT = True      # True = Platz für ICM20948 (VIO/SLAM, Pi-I2C) oben auf dem Rahmen
TRIG_SLOTS = False    # True = Kabelschlitze im oberen Rahmen für die Trigger-/Strobe-Stiftleisten (Breite trig_w)

V = App.Vector
ROT = App.Rotation

PARAMS = [
    ("baseline",  65.0, "Stereo-Baseline (Achsabstand) [mm] – 65 statt 60, damit die Trigger-Platine dazwischen passt"),
    ("pcb",       39.0, "Boardkante (quadratisch, STEP)"),
    ("hole_s",    34.0, "Lochabstand Befestigungslöcher (STEP, Ø2.0)"),
    ("pilot_d",    1.7, "Kernloch M2 selbstschneidend in PETG"),
    ("so_d",       5.0, "Distanzbolzen Ø"),
    ("so_h",       2.0, "Distanzbolzen Höhe (Board-Oberseite -> Platte)"),
    ("plate_t",    4.0, "Frontplatte Dicke"),
    ("holder_w",  24.4, "M12-Halter Breite (STEP)"),
    ("holder_h",  16.3, "M12-Halter Höhe (STEP)"),
    ("win_c",      0.8, "Spiel Fenster um den Halter"),
    ("rim_c",      0.6, "Spiel Boardkante -> Rahmen"),
    ("rim_t",      3.0, "Rahmen Wandstärke oben/seitlich"),
    ("bot_t",      4.0, "Rahmen Wandstärke unten (Laschenebene)"),
    ("rim_d",     12.0, "Rahmentiefe hinter der Board-Oberseite"),
    ("fpc_w",     20.0, "Kabelschlitz Breite (15-pol. FPC 1 mm)"),
    ("fpc_off",    0.5, "Kabelschlitz X-Versatz zur Achse (STEP: Buchse -10.5..+11.5)"),
    ("trig_w",    28.5, "Kabelschlitz oben für Trigger-/Strobe-Stiftleisten (gegenüber CSI)"),
    ("trig_off",   0.0, "Kabelschlitz oben: X-Versatz zur Kameraachse"),
    ("tpcb_w",    20.0, "Trigger-Verteilerplatine Breite (quer)"),
    ("tpcb_h",    22.0, "Trigger-Verteilerplatine Höhe"),
    ("tpcb_c",     0.3, "Spiel Platinentasche"),
    ("tpcb_d",     0.5, "Tiefe Platinentasche (Lage für Klebeband)"),
    ("ear_l",     10.0, "Befestigungslasche Länge"),
    ("ear_hole",   3.2, "Befestigungslasche Bohrung (M3)"),
    ("corner_r",   6.0, "V1.5: Radius obere Rahmenecken (Ansicht von vorn); innen bleibt die Ecke für das Board eckig -> min. Wand 1.76"),
    ("ear_r",      2.0, "V1.5: Radius Laschenenden (2.0 = halbrund bei bot_t 4)"),
    ("ear_fil",    2.5, "V1.5: Kehle Rahmen -> Lasche (Material dazu, Schraubenkopf M3 bleibt frei)"),
    ("imu_hs",    13.6, "ICM20948-Breakout: Lochabstand (quer, X), Löcher M2.5"),
    ("imu_hz",     2.5, "ICM20948: Lochreihe hinter der Frontfläche (Lochmitte in der Frontplatte; Bund Ø4.5 endet 0.25 hinter der Front -> Frontfläche bleibt eben)"),
    ("imu_pd",     2.1, "ICM20948: Kernloch M2.5 selbstschneidend in PETG"),
    ("imu_depth",  6.0, "ICM20948: Kernlochtiefe ab Rahmenoberkante"),
    ("imu_so",     1.5, "ICM20948: Distanzbund unter dem Board (Lötstellen der Stiftleiste)"),
    ("imu_sod",    4.5, "ICM20948: Distanzbund Ø"),
    ("imu_b",     19.0, "ICM20948: Boardkante (quadratisch, Platzhalter)"),
    ("imu_e",      2.7, "ICM20948: Lochmitte -> vordere Boardkante"),
]
DERIVED = [
    ("x_half",  "=baseline/2 + pcb/2 + rim_c + rim_t", "halbe Außenbreite Rahmen"),
    ("y_top",  "=pcb/2 + rim_c + rim_t",              "Oberkante Rahmen"),
    ("y_bot", "=pcb/2 + rim_c + bot_t",              "Unterkante Rahmen (Betrag)"),
    ("zmin_mm", "=1.86*baseline",                  "Mindestdistanz [mm] bei fx=357px, 192px max. Disparität"),
]
ALIASES = {p[0] for p in PARAMS} | {d[0] for d in DERIVED}


def E(expr):
    return re.sub(r"\b([A-Za-z_]\w*)\b",
                  lambda m: "Params." + m.group(1) if m.group(1) in ALIASES else m.group(1), str(expr))


doc = App.newDocument("SLARC_Stereo")
GUI = App.GuiUp
if GUI:
    import FreeCADGui as Gui

sheet = doc.addObject("Spreadsheet::Sheet", "Params")
sheet.set("A1", "Parameter"); sheet.set("B1", "Wert"); sheet.set("C1", "Kommentar")
row = 2
for name, val, com in PARAMS + DERIVED:
    sheet.set(f"A{row}", name); sheet.set(f"B{row}", str(val)); sheet.set(f"C{row}", com)
    sheet.setAlias(f"B{row}", name); row += 1
sheet.setColumnWidth("C", 420)
doc.recompute()

grp = doc.addObject("App::Part", "StereoMount")


def _x(o, prop, e):
    o.setExpression(prop, E(e))


def _hide(o):
    if GUI:
        o.ViewObject.Visibility = False


def box(n, x0, y0, z0, L, W, H):
    o = doc.addObject("Part::Box", n); grp.addObject(o)
    _x(o, "Length", L); _x(o, "Width", W); _x(o, "Height", H)
    _x(o, "Placement.Base.x", x0); _x(o, "Placement.Base.y", y0); _x(o, "Placement.Base.z", z0)
    return o


def cylz(n, x, y, z0, d, h):
    o = doc.addObject("Part::Cylinder", n); grp.addObject(o)
    _x(o, "Radius", f"({d})/2"); _x(o, "Height", h)
    _x(o, "Placement.Base.x", x); _x(o, "Placement.Base.y", y); _x(o, "Placement.Base.z", z0)
    return o


def cyly(n, x, y0, z, d, h):
    """Zylinder entlang +Y."""
    o = doc.addObject("Part::Cylinder", n); grp.addObject(o)
    _x(o, "Radius", f"({d})/2"); _x(o, "Height", h)
    o.Placement = App.Placement(V(), ROT(V(1, 0, 0), -90))
    _x(o, "Placement.Base.x", x); _x(o, "Placement.Base.y", y0); _x(o, "Placement.Base.z", z)
    return o


def round_corner(n, x, y, sx, sy, r, z0, h, convex=True):
    """V1.5: Ecke (x, y) in der XY-Ansicht runden. Konvex: (sx, sy) zeigt von der Ecke ins Material, das Eckstück
    wird abgezogen. Konkav: (sx, sy) zeigt in den freien Raum, die Kehle wird ergänzt. Rückgabe: Part::Cut (Box - Zylinder)."""
    bx = f"({x}) - ({r})" if sx < 0 else f"({x})"
    by = f"({y}) - ({r})" if sy < 0 else f"({y})"
    cx, cy = f"({x}) + ({sx})*({r})", f"({y}) + ({sy})*({r})"
    b = box(n + "_box", bx, by, z0, r, r, h)
    c = cylz(n + "_cyl", cx, cy, f"({z0}) - 1", f"2*({r})", f"({h}) + 2")
    o = doc.addObject("Part::Cut", n); grp.addObject(o)
    o.Base, o.Tool = b, c
    _hide(b); _hide(c)
    return o


def fuse(n, shapes):
    o = doc.addObject("Part::MultiFuse", n); grp.addObject(o)
    o.Shapes = shapes
    if hasattr(o, "Refine"):
        o.Refine = True
    for s in shapes:
        _hide(s)
    return o


ZB = "-rim_d"                    # Rahmen-Hinterkante
ZF = "so_h + plate_t"            # Frontfläche
DEPTH = f"({ZF}) - ({ZB})"

pos = [
    box("Plate", "-x_half", "-y_bot", "so_h", "2*x_half", "y_top + y_bot", "plate_t"),
    box("Rim_top", "-x_half", "y_top - rim_t", ZB, "2*x_half", "rim_t", DEPTH),
    box("Rim_bot", "-x_half", "-y_bot", ZB, "2*x_half", "bot_t", DEPTH),
    box("Rim_L", "-x_half", "-y_bot", ZB, "rim_t", "y_top + y_bot", DEPTH),
    box("Rim_R", "x_half - rim_t", "-y_bot", ZB, "rim_t", "y_top + y_bot", DEPTH),
    box("Ear_L", "-x_half - ear_l", "-y_bot", ZB, "ear_l", "bot_t", DEPTH),
    box("Ear_R", "x_half", "-y_bot", ZB, "ear_l", "bot_t", DEPTH),
]
neg = []
for c, sx in (("L", -1), ("R", 1)):
    cx = f"({sx})*baseline/2"
    neg.append(box(f"Win_{c}", f"{cx} - holder_w/2 - win_c", "-holder_h/2 - win_c", "so_h - 1",
                   "holder_w + 2*win_c", "holder_h + 2*win_c", "plate_t + 2"))
    if TRIG_SLOTS:
        neg.append(box(f"TRIG_{c}", f"{cx} + trig_off - trig_w/2", "y_top - rim_t - 1", f"({ZB}) - 1",
                       "trig_w", "rim_t + 2", "rim_d + 1"))
    neg.append(box(f"FPC_{c}", f"{cx} + fpc_off - fpc_w/2", "-y_bot - 1", f"({ZB}) - 1",
                   "fpc_w", "bot_t + 2", "rim_d + 1"))
    for i, (hx, hy) in enumerate(((1, 1), (-1, 1), (-1, -1), (1, -1))):
        px, py = f"{cx} + ({hx})*hole_s/2", f"({hy})*hole_s/2"
        pos.append(cylz(f"SO_{c}{i}", px, py, 0, "so_d", "so_h + 0.5"))
        neg.append(cylz(f"Pilot_{c}{i}", px, py, -0.1, "pilot_d", "so_h + plate_t - 0.9"))
neg.append(box("TPCB_pocket", "-tpcb_w/2 - tpcb_c", "-tpcb_h/2 - tpcb_c", "so_h - 0.01",
               "tpcb_w + 2*tpcb_c", "tpcb_h + 2*tpcb_c", "tpcb_d + 0.01"))
if IMU_MOUNT:                       # Zusatz-IMU oben mittig, Board flach auf zwei Distanzbunden
    IZ = f"({ZF}) - imu_hz"
    for i, sx in enumerate((-1, 1)):
        ix = f"({sx})*imu_hs/2"
        pos.append(cyly(f"IMU_so{i}", ix, "y_top - 0.5", IZ, "imu_sod", "imu_so + 0.5"))
        pos.append(box(f"IMU_pad{i}", f"{ix} - imu_sod/2", "y_top - 0.5", IZ, "imu_sod", "imu_so + 0.5", "imu_hz"))   # V1.5.1: bis zur Front -> steht auf dem Bett
        neg.append(cyly(f"IMU_pilot{i}", ix, "y_top - imu_depth", IZ, "imu_pd", "imu_depth + imu_so + 0.2"))
# V1.5: Ecken runden (Ansicht von vorn). Material liegt von der Ecke aus in Richtung (-sx, -sy) -> konvex
ZH = f"({DEPTH}) + 2"
for c, sx in (("L", -1), ("R", 1)):
    neg.append(round_corner(f"Round_top_{c}", f"({sx})*x_half", "y_top", -sx, -1, "corner_r", f"({ZB}) - 1", ZH))
    ex = f"({sx})*(x_half + ear_l)"
    neg.append(round_corner(f"Round_ear_top_{c}", ex, "-y_bot + bot_t", -sx, -1, "ear_r", f"({ZB}) - 1", ZH))
    neg.append(round_corner(f"Round_ear_bot_{c}", ex, "-y_bot", -sx, 1, "ear_r", f"({ZB}) - 1", ZH))
    # Kehle: Ecke bei (±x_half, -y_bot + bot_t), freier Raum liegt in Richtung (+sx, +1)
    pos.append(round_corner(f"Fillet_ear_{c}", f"({sx})*x_half", "-y_bot + bot_t", sx, 1, "ear_fil", ZB, DEPTH, convex=False))
for c, sx in (("L", -1), ("R", 1)):
    neg.append(cyly(f"EarHole_{c}", f"({sx})*(x_half + ear_l/2)", "-y_bot - 1",
                    f"(({ZB}) + ({ZF}))/2", "ear_hole", "bot_t + 2"))

body = fuse("Mount_pos", pos)
tool = fuse("Mount_neg", neg)
mount = doc.addObject("Part::Cut", "Stereo_Mount"); grp.addObject(mount)
mount.Base, mount.Tool = body, tool
if hasattr(mount, "Refine"):
    mount.Refine = True
_hide(body); _hide(tool)
if GUI:
    mount.ViewObject.ShapeColor = (0.08, 0.08, 0.08)


if IMU_MOUNT:                       # Platzhalter Breakout (nur Kontrolle, kein Druckteil)
    imu = box("ICM20948_board", "-imu_b/2", "y_top + imu_so", f"({ZF}) - imu_hz + imu_e - imu_b", "imu_b", 1.6, "imu_b")
    if GUI:
        imu.ViewObject.ShapeColor = (0.55, 0.10, 0.55)


# ---------------------------------------------------------------- Kamera-STEP zur Kontrolle
def _find_cam():
    dirs = []
    try:
        dirs.append(os.path.dirname(os.path.abspath(__file__)))
    except NameError:
        pass
    try:
        dirs.append(App.getUserMacroDir(True))
    except Exception:
        pass
    cands = [CAM_STEP] if CAM_STEP else []
    cands += [os.path.join(d, n) for d in dirs for n in CAM_STEP_NAMES]
    for c in cands:
        if c and os.path.isfile(c):
            return c
    return None


def lens_zh3019(z_img):
    """M12-Objektiv ZH3019-14 (2.8 mm, F2.2) nach Herstellerzeichnung, rotationssymmetrisch um +Z.
    z_img = Bildebene (Sensoroberfläche) = Bezugskante der Zeichnung. Abstände davor: Objektivende 5.59,
    Gewinde M12 bis 16.4, Hals Ø10.7, Kopf Ø14 von 17.76 bis 21.71 (Stirn), Glaskuppel bis 22.0.
    Gemaßt sind nur M12, Ø14, 5.59, 21.71, 22 – der Rest ist aus der Zeichnung abgegriffen (±0.2).
    Beim Scharfstellen verschiebt sich das Objektiv um ein paar Zehntel."""
    import Part
    zs = lambda d: z_img + d
    pts = [(0.0, zs(5.59)), (5.5, zs(5.59)), (6.0, zs(6.4)), (6.0, zs(15.9)), (5.35, zs(16.4)), (5.35, zs(17.76)),
           (7.0, zs(17.76)), (7.0, zs(21.71)), (5.55, zs(21.71))]
    for i in range(1, 7):                                   # Glaskuppel 0.29 mm über der Stirn
        r = 5.55 * (1 - i / 6.0)
        pts.append((r, zs(21.71 + 0.29 * (1 - (r / 5.55) ** 2))))
    pts.append((0.0, zs(5.59)))
    w = Part.makePolygon([App.Vector(r, 0, z) for r, z in pts])
    return Part.Solid(Part.Shell(Part.Face(Part.Wire(w)).revolve(App.Vector(0, 0, 0), App.Vector(0, 0, 1), 360).Faces))


_cp = _find_cam()
if _cp:
    cam_shape = Part.makeCompound([Part.read(_cp)])
    for c, sx in (("L", -1), ("R", 1)):
        o = doc.addObject("Part::Feature", f"IMX296_{c}"); grp.addObject(o)
        o.Shape = cam_shape
        o.Placement = App.Placement(V(0, 0, -CAM_STEP_BOARD_TOP), ROT())
        _x(o, "Placement.Base.x", f"({sx})*baseline/2")
        if GUI:
            o.ViewObject.ShapeColor = (0.10, 0.45, 0.20)
    print("Kamera-STEP geladen:", _cp)
else:
    print("Kamera-STEP nicht gefunden -> nur Halterung")
if LENS:
    _ls = lens_zh3019(CAM_SENSOR_Z)
    for c, sx in (("L", -1), ("R", 1)):
        o = doc.addObject("Part::Feature", f"Lens_ZH3019_{c}"); grp.addObject(o)
        o.Shape = _ls
        _x(o, "Placement.Base.x", f"({sx})*baseline/2")
        if GUI:
            o.ViewObject.ShapeColor = (0.75, 0.75, 0.78)

doc.recompute()
if GUI:
    Gui.activeDocument().activeView().viewIsometric()
    Gui.SendMsgToActiveView("ViewFit")
print("Stereo-Halterung erzeugt. Baseline = %s mm, Mindestdistanz ca. %s mm"
      % (sheet.get("baseline"), sheet.get("zmin_mm")))
