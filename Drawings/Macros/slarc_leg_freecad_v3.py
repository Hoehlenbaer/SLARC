# -*- coding: utf-8 -*-
"""
SLARC – parametrisches Bein (Coxa/Femur/Tibia) mit 3x ST3215, doppelt gelagert.   V3
FreeCAD 0.21 / 1.0 – Makro ausführen oder in der Python-Konsole:
    exec(open(r"PFAD/slarc_leg_freecad_v3.py", encoding="utf-8").read())

V3
- ST3215-Maße aus dem Hersteller-STEP übernommen (Achse 10.1 mm von der Stirnseite, Hüllmaß 45.2x24.7x35.0,
  Horn Ø18.8 steht 2.1 mm über der Hülle, Rückseitenscheibe Ø18.8 mit 4x M3 auf Ø14, 0.15 mm unter der Hülle).
- Doppellagerung über die servo-eigene Rückseitenscheibe: untere Gabelwange wird darauf geschraubt
  (kein 684-Lager mehr). Distanzbund boss_h auf der Wange hält Abstand zum Gehäuseboden und zum Mittelzapfen.
- Ist ST3215.step vorhanden (SERVO_STEP oder neben dem Makro / im Makro-Ordner), wird es als Servo eingesetzt,
  sonst ein Ersatzkörper. Die Aufnahme-Taschen bleiben parametrisch (Hüllquader).

V2
- Tibia geknickt: Segment 1 (Knie -> Knick), Fußsegment um tib_bend (Default 60°) nach unten abgewinkelt.
  Die Sehne Knieachse -> Fußspitze bleibt tibia_len (=150, wie in der Sim). tib_a wird daraus berechnet,
  tib_delta = Winkelversatz Servo-Null -> Sehne (Offset für Sim/IK, falls dort die gerade Tibia bleibt).
- Neutralhaltung: q_femur = -30 (Femur 30° nach oben), q_tibia = 60 -> Segment 1 läuft 30° nach unten,
  Fußsegment senkrecht.
- Fuß = separates TPU-Teil (Foot_TPU): Kugelkappe + Hülse über dem Gliedende + seitliche Rippen (Grip-Pads).
- Material/Farben: PETG schwarz (Strukturteile), PLA orange (Deco_*-Zierleisten, aufgesetzt), TPU (Foot_TPU).

Aufbau
- Alle Maße + Gelenkwinkel im Spreadsheet "Params" (Spalte B, Aliase). Ändern -> Ctrl+R.
- Kinematik als verschachtelte App::Parts: Leg > J1_Coxa > J2_base > J2_Femur > J3_base > J3_Tibia
  Gelenk-Frame: Ursprung auf der Servoachse (Gehäuse-Oberseite), Z = Drehachse, X = zum nächsten Gelenk,
  positiver Winkel = nach unten.
- Doppellagerung: Gabel je Gelenk, obere Wange auf dem Horn, untere Wange auf der servo-eigenen Rückscheibe.
- Druckteile je ein Solid: Body_Mount, Coxa_Part, Femur_Part, Tibia_Part, Foot_TPU, Deco_*.

ACHTUNG: ST3215-Maße (Achsversatz, Horn, Lochkreis, Rückseitenzapfen) sind Startwerte – gegen STEP prüfen.
"""
import os
import re
import FreeCAD as App
import Part

SERVO_STEP = r""          # Pfad zur ST3215.step; leer = neben dem Makro bzw. im Makro-Ordner suchen
# Lage des Hersteller-STEP (ST3215.step, Feetech 2022): Achse || Y bei x=-25.5, z=0; Hülle oben y=+7.5
STEP_AXIS_X = -25.5
STEP_TOP_Y = 7.5

V = App.Vector
ROT = App.Rotation

# ---------------------------------------------------------------- Parameter
PARAMS = [
    # name,        wert,   kommentar
    ("servo_L",    45.2,  "ST3215 Hüllmaß Länge (STEP)"),
    ("servo_W",    24.7,  "ST3215 Hüllmaß Breite (STEP)"),
    ("servo_H",    35.0,  "ST3215 Hüllmaß Höhe ohne Horn/Scheibe (STEP)"),
    ("servo_ax",   10.1,  "Achse -> nahe Stirnseite (STEP)"),
    ("horn_d",     18.8,  "Horn- und Rückscheiben-Ø (STEP)"),
    ("horn_t",      2.1,  "Hülle oben -> Hornfläche (STEP)"),
    ("rear_t",      0.15, "Hülle unten -> Rückscheibenfläche (STEP)"),
    ("horn_bc",    14.0,  "Lochkreis Horn/Rückscheibe (STEP: Rückscheibe 4x M3; Horn im STEP ohne Löcher -> prüfen)"),
    ("horn_pa",     0.0,  "Winkellage Lochbild [deg] (STEP: Löcher auf 0/90/180/270)"),
    ("horn_hole",   3.2,  "Durchgang Schrauben M3"),
    ("center_d",    7.0,  "Mittelbohrung in den Wangen (Hornschraube / Zapfen der Rückscheibe)"),
    ("boss_h",      1.0,  "Distanzbund untere Wange (Zapfen steht 0.55 über Rückscheibe)"),
    ("cheek_t",     4.0,  "Dicke obere Wange (Hornseite)"),
    ("cheek_b_t",   4.0,  "Dicke untere Wange (Rückscheibe)"),
    ("bridge_t",    4.0,  "Dicke Gabelsteg"),
    ("fork_w",     26.0,  "Breite Gabelwangen"),
    ("clr",         1.5,  "Freigang Gabelsteg zur Servo-Ecke"),
    ("fit",         0.2,  "Passungsspiel Servo-Aufnahme"),
    ("wall",        2.5,  "Wandstärke Servo-Aufnahme"),
    ("link_w",     20.0,  "Glied-Querschnitt in Beinebene"),
    ("link_h",     28.0,  "Glied-Querschnitt entlang Gelenkachse"),
    ("link_wall",   2.0,  "Wandstärke Hohlprofil"),
    ("coxa_len",   60.0,  "Coxa: Achse-Achse"),
    ("femur_len", 175.0,  "Femur: Achse-Achse"),
    ("tibia_len", 150.0,  "Tibia: Knieachse -> Fußspitze (Sehne, = Sim-Wert)"),
    ("tib_bend",   60.0,  "Knick Tibia -> Fußsegment [deg], nach unten"),
    ("foot_seg",   60.0,  "Fußsegment: Knick -> Fußspitze"),
    ("foot_r",     16.0,  "TPU-Fußkugel Radius"),
    ("boot_l",     30.0,  "TPU-Fuß: Hülsenlänge über dem Glied"),
    ("boot_t",      2.0,  "TPU-Fuß: Wandstärke Hülse"),
    ("rib_p",       4.5,  "TPU-Rippen Teilung"),
    ("rib_w",       1.5,  "TPU-Rippen Breite"),
    ("rib_h",       1.0,  "TPU-Rippen Höhe"),
    ("deco_t",      1.2,  "PLA-Zierleiste Dicke"),
    ("deco_m",      4.0,  "PLA-Zierleiste Randabstand"),
    ("q_coxa",      0.0,  "Gelenkwinkel Coxa [deg]"),
    ("q_femur",   -30.0,  "Gelenkwinkel Femur [deg], + = nach unten"),
    ("q_tibia",    60.0,  "Gelenkwinkel Tibia [deg], + = nach unten (bezogen auf Segment 1)"),
]
DERIVED = [
    ("zb",    "=-servo_H - rear_t - boss_h - cheek_b_t",          "Unterseite untere Wange"),
    ("zc",    "=(horn_t + cheek_t + zb)/2",                       "Z-Mitte der Gabel (Gliedebene)"),
    ("r_clr", "=sqrt(servo_ax^2 + (servo_W/2)^2) + clr",           "Innenradius Gabelsteg"),
    ("back",  "=servo_L - servo_ax + wall",                        "Achse -> Außenseite Aufnahme-Rückwand"),
    ("tib_a", "=-foot_seg*cos(tib_bend) + sqrt(tibia_len^2 - (foot_seg*sin(tib_bend))^2)",
              "Tibia-Segment 1: Knieachse -> Knick (aus Sehne berechnet)"),
    ("tib_delta", "=atan(foot_seg*sin(tib_bend)/(tib_a + foot_seg*cos(tib_bend)))",
              "Winkel Segment 1 -> Sehne [deg] (Offset für Sim/IK)"),
]
ALIASES = {p[0] for p in PARAMS} | {d[0] for d in DERIVED}
RIBS = 6   # Anzahl Rippen je Seite (fest, Teilung über rib_p)


def E(expr):
    """Alias-Namen im Ausdruck mit 'Params.' prefixen."""
    return re.sub(r"\b([A-Za-z_]\w*)\b",
                  lambda m: "Params." + m.group(1) if m.group(1) in ALIASES else m.group(1),
                  str(expr))


# ---------------------------------------------------------------- Frames
class Fr:
    """Starres Teil-Frame innerhalb eines Containers: Translation (Ausdrücke) + feste Rotation.
    rx=True: Rx(-90°), d.h. lokal Z -> +Y, lokal Y -> -Z (Coxa -> Femur)."""
    def __init__(self, tx="0", ty="0", tz="0", rx=False):
        self.t, self.rx = (tx, ty, tz), rx
        self.rot = ROT(V(1, 0, 0), -90) if rx else ROT()

    def base(self, x, y, z):
        tx, ty, tz = self.t
        if self.rx:
            return (f"{tx} + ({x})", f"{ty} + ({z})", f"{tz} - ({y})")
        return (f"{tx} + ({x})", f"{ty} + ({y})", f"{tz} + ({z})")


I = Fr()

# ---------------------------------------------------------------- Dokument
doc = App.newDocument("SLARC_Leg")
GUI = App.GuiUp
if GUI:
    import FreeCADGui as Gui



def _find_step():
    cands = [SERVO_STEP] if SERVO_STEP else []
    try:
        cands.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "ST3215.step"))
    except NameError:
        pass
    try:
        cands.append(os.path.join(App.getUserMacroDir(True), "ST3215.step"))
    except Exception:
        pass
    for c in cands:
        if c and os.path.isfile(c):
            return c
    return None


STEP_SHAPE = None
_sp = _find_step()
if _sp:
    _sh = Part.read(_sp)
    # STEP -> Servo-Frame: X = -(x - STEP_AXIS_X), Y = z, Z = y - STEP_TOP_Y  (det = +1)
    _m = App.Matrix(-1, 0, 0, STEP_AXIS_X,
                    0, 0, 1, 0,
                    0, 1, 0, -STEP_TOP_Y,
                    0, 0, 0, 1)
    _sh.transformShape(_m)
    STEP_SHAPE = Part.makeCompound([_sh])     # Location bleibt im Kind, Feature-Placement frei
    print("ST3215.step geladen:", _sp, STEP_SHAPE.BoundBox)
else:
    print("ST3215.step nicht gefunden -> Ersatzkörper")

sheet = doc.addObject("Spreadsheet::Sheet", "Params")
sheet.set("A1", "Parameter"); sheet.set("B1", "Wert"); sheet.set("C1", "Kommentar")
row = 2
for name, val, com in PARAMS:
    sheet.set(f"A{row}", name); sheet.set(f"B{row}", str(val)); sheet.set(f"C{row}", com)
    sheet.setAlias(f"B{row}", name); row += 1
for name, formula, com in DERIVED:
    sheet.set(f"A{row}", name); sheet.set(f"B{row}", formula); sheet.set(f"C{row}", com)
    sheet.setAlias(f"B{row}", name); row += 1
sheet.setColumnWidth("C", 380)
doc.recompute()


def _x(o, prop, e):
    o.setExpression(prop, E(e))


def _place(o, fr, x, y, z):
    o.Placement = App.Placement(V(), fr.rot)
    bx, by, bz = fr.base(x, y, z)
    _x(o, "Placement.Base.x", bx); _x(o, "Placement.Base.y", by); _x(o, "Placement.Base.z", bz)


def _hide(o):
    try:
        o.Visibility = False
    except Exception:
        pass
    if GUI:
        o.ViewObject.Visibility = False


def _color(o, rgb):
    if GUI:
        o.ViewObject.ShapeColor = rgb


def box(g, n, fr, x0, y0, z0, L, W, H):
    o = doc.addObject("Part::Box", n); g.addObject(o)
    _x(o, "Length", L); _x(o, "Width", W); _x(o, "Height", H)
    _place(o, fr, x0, y0, z0)
    return o


def cyl(g, n, fr, x, y, z0, r, h):
    o = doc.addObject("Part::Cylinder", n); g.addObject(o)
    _x(o, "Radius", r); _x(o, "Height", h)
    _place(o, fr, x, y, z0)
    return o


def sph(g, n, fr, x, y, z, r):
    o = doc.addObject("Part::Sphere", n); g.addObject(o)
    _x(o, "Radius", r)
    _place(o, fr, x, y, z)
    return o


def rpt(px, py, ang, lx, ly):
    """Punkt (lx, ly) in einem um ang [deg] um Z gedrehten Frame mit Ursprung (px, py)."""
    return (f"({px}) + ({lx})*cos({ang}) - ({ly})*sin({ang})",
            f"({py}) + ({lx})*sin({ang}) + ({ly})*cos({ang})")


def rbox(g, n, px, py, ang, lx0, ly0, z0, L, W, H):
    """Box in einem um ang gedrehten Frame (Ursprung px, py); Ecke bei (lx0, ly0, z0)."""
    o = doc.addObject("Part::Box", n); g.addObject(o)
    _x(o, "Length", L); _x(o, "Width", W); _x(o, "Height", H)
    o.Placement = App.Placement(V(), ROT(V(0, 0, 1), 0))
    _x(o, "Placement.Rotation.Angle", ang)
    bx, by = rpt(px, py, ang, lx0, ly0)
    _x(o, "Placement.Base.x", bx); _x(o, "Placement.Base.y", by); _x(o, "Placement.Base.z", z0)
    return o


def fuse(g, n, shapes):
    if len(shapes) == 1:
        return shapes[0]
    o = doc.addObject("Part::MultiFuse", n); g.addObject(o)
    o.Shapes = shapes
    if hasattr(o, "Refine"):
        o.Refine = True
    for s in shapes:
        _hide(s)
    return o


def cut(g, n, base, tools):
    tool = fuse(g, n + "_tools", tools)
    o = doc.addObject("Part::Cut", n); g.addObject(o)
    o.Base, o.Tool = base, tool
    if hasattr(o, "Refine"):
        o.Refine = True
    _hide(base); _hide(tool)
    return o


def part(parent, n, fixed_fr=None, angle=None):
    """App::Part als Gelenk-Frame. fixed_fr: feste Lage im Parent; angle: Gelenkwinkel-Alias (Drehung um Z)."""
    p = doc.addObject("App::Part", n)
    if parent is not None:
        parent.addObject(p)
    if fixed_fr is not None:
        _place(p, fixed_fr, 0, 0, 0)
    if angle is not None:
        p.Placement = App.Placement(V(), ROT(V(0, 0, 1), 0))
        _x(p, "Placement.Rotation.Angle", angle)   # Grad
    return p


# ---------------------------------------------------------------- Farben / Material
COL_PETG = (0.08, 0.08, 0.08)   # PETG schwarz
COL_PLA = (1.00, 0.45, 0.00)    # PLA orange
COL_TPU = (0.30, 0.30, 0.33)    # TPU
COL_SERVO = (0.20, 0.20, 0.26)


# ---------------------------------------------------------------- Bauteile
def servo(g, n, fr):
    """ST3215 im Servo-Frame: Achse = Z, Ursprung = Hülle oben auf der Achse, Horn +Z, Gehäuse nach -X/-Z."""
    if STEP_SHAPE is not None:
        s = doc.addObject("Part::Feature", "ST3215_" + n); g.addObject(s)
        s.Shape = STEP_SHAPE
        _place(s, fr, 0, 0, 0)
    else:
        case = box(g, n + "_case", fr, "-(servo_L - servo_ax)", "-servo_W/2", "-servo_H",
                   "servo_L", "servo_W", "servo_H")
        horn = cyl(g, n + "_horn", fr, 0, 0, 0, "horn_d/2", "horn_t")
        rear = cyl(g, n + "_rear", fr, 0, 0, "-servo_H - rear_t", "horn_d/2", "rear_t + 0.5")
        s = fuse(g, "ST3215_" + n, [case, horn, rear])
    _color(s, COL_SERVO)
    return s


def fork_pos(g, n, fr):
    """Gabel: obere Wange auf dem Horn, untere Wange mit Distanzbund auf der Rückscheibe."""
    xl = "r_clr + bridge_t"
    return [
        box(g, n + "_cheek_top", fr, 0, "-fork_w/2", "horn_t", xl, "fork_w", "cheek_t"),
        cyl(g, n + "_hub_top", fr, 0, 0, "horn_t", "fork_w/2", "cheek_t"),
        box(g, n + "_cheek_bot", fr, 0, "-fork_w/2", "zb", xl, "fork_w", "cheek_b_t"),
        cyl(g, n + "_hub_bot", fr, 0, 0, "zb", "fork_w/2", "cheek_b_t"),
        cyl(g, n + "_boss_bot", fr, 0, 0, "zb + cheek_b_t", "horn_d/2", "boss_h"),
        box(g, n + "_bridge", fr, "r_clr", "-fork_w/2", "zb", "bridge_t", "fork_w",
            "horn_t + cheek_t - zb"),
    ]


def fork_neg(g, n, fr):
    """4x M3 durch obere Wange (Horn) und untere Wange+Bund (Rückscheibe), Mittelbohrungen."""
    t = []
    for i in range(4):
        a = f"(horn_pa + {90 * i})"
        hx, hy = f"horn_bc/2*cos{a}", f"horn_bc/2*sin{a}"
        t.append(cyl(g, f"{n}_hole_top{i}", fr, hx, hy, "horn_t - 0.5", "horn_hole/2", "cheek_t + 1"))
        t.append(cyl(g, f"{n}_hole_bot{i}", fr, hx, hy, "zb - 0.5", "horn_hole/2",
                     "cheek_b_t + boss_h + 1"))
    t.append(cyl(g, n + "_ctr_top", fr, 0, 0, "horn_t - 0.5", "center_d/2", "cheek_t + 1"))
    t.append(cyl(g, n + "_ctr_bot", fr, 0, 0, "zb - 0.5", "center_d/2", "cheek_b_t + boss_h + 1"))
    return t


def beam(g, n, fr, x0, x1, hollow):
    pos = [box(g, n + "_beam", fr, x0, "-link_w/2", "zc - link_h/2",
               f"({x1}) - ({x0})", "link_w", "link_h")]
    neg = []
    if hollow:
        neg.append(box(g, n + "_beam_in", fr, f"({x0}) + link_wall", "-link_w/2 + link_wall",
                       "zc - link_h/2 + link_wall", f"({x1}) - ({x0}) - 2*link_wall",
                       "link_w - 2*link_wall", "link_h - 2*link_wall"))
    return pos, neg


def cradle(g, n, fr):
    pos = [box(g, n + "_cradle", fr, "-back", "-servo_W/2 - wall", "-servo_H",
               "back", "servo_W + 2*wall", "servo_H")]
    neg = [box(g, n + "_pocket", fr, "-(servo_L - servo_ax) - fit", "-servo_W/2 - fit",
               "-servo_H - 1", "servo_L + 2*fit + 10", "servo_W + 2*fit", "servo_H + 2")]
    return pos, neg


def deco(g, n, x0, x1):
    """PLA-Zierleisten auf beiden Seitenflächen (±Z) eines geraden Glieds, aufgesetzt."""
    for s, z0 in (("A", "zc + link_h/2"), ("B", "zc - link_h/2 - deco_t")):
        d = box(g, f"Deco_{n}_{s}", I, f"({x0}) + deco_m", "-link_w/2 + deco_m", z0,
                f"({x1}) - ({x0}) - 2*deco_m", "link_w - 2*deco_m", "deco_t")
        _color(d, COL_PLA)


# ---------------------------------------------------------------- Bein
X0 = "r_clr + bridge_t - 0.5"

leg = part(None, "Leg")

# Körperseite
servo(leg, "Coxa", I)
p, nn = cradle(leg, "Body", I)
body = cut(leg, "Body_Mount", fuse(leg, "Body_pos", p), nn)
_color(body, COL_PETG)

# J1 – Coxa
j1 = part(leg, "J1_Coxa", angle="q_coxa")
F = Fr("coxa_len", "-zc", "zc", rx=True)
pos = fork_pos(j1, "Coxa", I); neg = fork_neg(j1, "Coxa", I)
b_p, b_n = beam(j1, "Coxa", I, X0, "coxa_len - back + 0.5", hollow=False)
c_p, c_n = cradle(j1, "FemurSrv", F)
coxa = cut(j1, "Coxa_Part", fuse(j1, "Coxa_pos", pos + b_p + c_p), neg + b_n + c_n)
_color(coxa, COL_PETG)
servo(j1, "Femur", F)

# J2 – Femur
j2b = part(j1, "J2_base", fixed_fr=F)
j2 = part(j2b, "J2_Femur", angle="q_femur")
T = Fr("femur_len", "0", "0")
pos = fork_pos(j2, "Femur", I); neg = fork_neg(j2, "Femur", I)
b_p, b_n = beam(j2, "Femur", I, X0, "femur_len - back + 0.5", hollow=True)
c_p, c_n = cradle(j2, "TibiaSrv", T)
femur = cut(j2, "Femur_Part", fuse(j2, "Femur_pos", pos + b_p + c_p), neg + b_n + c_n)
_color(femur, COL_PETG)
deco(j2, "Femur", X0, "femur_len - back")
servo(j2, "Tibia", T)

# J3 – Tibia (geknickt)
j3b = part(j2, "J3_base", fixed_fr=T)
j3 = part(j3b, "J3_Tibia", angle="q_tibia")
BEND = "tib_bend"
XB = "foot_seg - foot_r"            # Fußsegment-lokal: Gliedende = Kugelmitte
XS = "foot_seg - foot_r - boot_l"   # Fußsegment-lokal: Beginn TPU-Hülse

pos = fork_pos(j3, "Tibia", I); neg = fork_neg(j3, "Tibia", I)
seg1 = box(j3, "Tibia_seg1", I, X0, "-link_w/2", "zc - link_h/2",
           f"tib_a - ({X0})", "link_w", "link_h")
seg1_in = box(j3, "Tibia_seg1_in", I, f"({X0}) + link_wall", "-link_w/2 + link_wall",
              "zc - link_h/2 + link_wall", f"tib_a - ({X0}) - link_wall",
              "link_w - 2*link_wall", "link_h - 2*link_wall")
knuckle = cyl(j3, "Tibia_knuckle", I, "tib_a", 0, "zc - link_h/2", "link_w/2", "link_h")
seg2 = rbox(j3, "Tibia_seg2", "tib_a", 0, BEND, 0, "-link_w/2", "zc - link_h/2",
            XB, "link_w", "link_h")
seg2_in = rbox(j3, "Tibia_seg2_in", "tib_a", 0, BEND, 0, "-link_w/2 + link_wall",
               "zc - link_h/2 + link_wall", XS, "link_w - 2*link_wall", "link_h - 2*link_wall")
tibia = cut(j3, "Tibia_Part", fuse(j3, "Tibia_pos", pos + [seg1, knuckle, seg2]),
            neg + [seg1_in, seg2_in])
_color(tibia, COL_PETG)
deco(j3, "Tibia", X0, "tib_a - link_w/2")

# TPU-Fuß: Kugelkappe + Hülse + Rippen, Gliedende ausgespart
cx, cy = rpt("tib_a", 0, BEND, XB, 0)
ball = sph(j3, "Foot_ball", I, cx, cy, "zc", "foot_r")
sleeve = rbox(j3, "Foot_sleeve", "tib_a", 0, BEND, XS, "-link_w/2 - boot_t",
              "zc - link_h/2 - boot_t", "boot_l", "link_w + 2*boot_t", "link_h + 2*boot_t")
ribs = []
for i in range(RIBS):
    for s, z0 in (("A", "zc + link_h/2 + boot_t"), ("B", "zc - link_h/2 - boot_t - rib_h")):
        ribs.append(rbox(j3, f"Foot_rib{s}{i}", "tib_a", 0, BEND, f"({XS}) + 3 + {i}*rib_p",
                         "-link_w/2 - boot_t", z0, "rib_w", "link_w + 2*boot_t", "rib_h"))
socket = rbox(j3, "Foot_socket", "tib_a", 0, BEND, f"({XS}) - 1", "-link_w/2", "zc - link_h/2",
              "boot_l + 1", "link_w", "link_h")
foot = cut(j3, "Foot_TPU", fuse(j3, "Foot_pos", [ball, sleeve] + ribs), [socket])
_color(foot, COL_TPU)

doc.recompute()
if GUI:
    Gui.activeDocument().activeView().viewFront()
    Gui.SendMsgToActiveView("ViewFit")
print("SLARC-Bein V3 erzeugt. tib_a = %s mm, tib_delta = %s"
      % (sheet.get("tib_a"), sheet.get("tib_delta")))
