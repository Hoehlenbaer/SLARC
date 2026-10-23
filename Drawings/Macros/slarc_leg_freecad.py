# -*- coding: utf-8 -*-
"""
SLARC – parametrisches Bein (Coxa/Femur/Tibia) mit 3x ST3215, doppelt gelagert.
FreeCAD 0.21 / 1.0 – Makro ausführen (Makro > Makros... > Ausführen) oder in der Python-Konsole:
    exec(open(r"PFAD/slarc_leg_freecad.py", encoding="utf-8").read())

Aufbau
- Alle Maße + Gelenkwinkel im Spreadsheet "Params" (Spalte B, Aliase). Ändern -> Ctrl+R (Recompute).
- Kinematik als verschachtelte App::Parts:  Leg > J1_Coxa > J2_base > J2_Femur > J3_base > J3_Tibia
  Jedes Gelenk-Frame: Ursprung auf der Servoachse in Höhe der Gehäuse-Oberseite (Hornseite),
  Z = Drehachse, X = Richtung zum nächsten Gelenk.
- Doppellagerung: Gabel ("Fork") je Gelenk. Obere Wange auf das Horn geschraubt, untere Wange
  trägt ein Kugellager (Default 684ZZ, 4x9x4) auf einem Zapfen an der Servo-Rückseite.
- Je Starrkörper EIN Solid (Body_Mount, Coxa_Part, Femur_Part, Tibia_Part) -> direkt als STL exportierbar.

ACHTUNG: ST3215-Maße (Achsversatz, Hornmaße, Lochkreis, Rückseitenzapfen) sind Startwerte –
gegen Datenblatt/STEP von Feetech/Waveshare prüfen und in "Params" eintragen.
"""
import re
import FreeCAD as App

V = App.Vector
ROT = App.Rotation

# ---------------------------------------------------------------- Parameter
PARAMS = [
    # name,        wert,   kommentar
    ("servo_L",    45.2,  "ST3215 Gehäuselänge"),
    ("servo_W",    24.7,  "ST3215 Gehäusebreite"),
    ("servo_H",    35.0,  "ST3215 Gehäusehöhe (ohne Horn) = Abstand Hornseite-Rückseite"),
    ("servo_ax",   11.0,  "Achse -> nahe Stirnseite (PRÜFEN)"),
    ("horn_d",     20.0,  "Horn-Durchmesser (PRÜFEN)"),
    ("horn_t",      3.0,  "Gehäuseoberkante -> Hornfläche (PRÜFEN)"),
    ("horn_bc",    14.0,  "Horn-Lochkreis (PRÜFEN)"),
    ("horn_hole",   2.7,  "Bohrung Hornschrauben (M2.5)"),
    ("bear_d",      4.0,  "Lager innen / Zapfen (684ZZ)"),
    ("bear_D",      9.0,  "Lager außen"),
    ("bear_B",      4.0,  "Lagerbreite"),
    ("gap",         1.0,  "Spalt Servo-Rückseite -> untere Wange"),
    ("cheek_t",     4.0,  "Dicke obere Wange (Hornseite)"),
    ("cheek_b_t",   5.5,  "Dicke untere Wange (Lagerseite)"),
    ("bridge_t",    4.0,  "Dicke Gabelsteg"),
    ("fork_w",     26.0,  "Breite Gabelwangen"),
    ("clr",         1.5,  "Freigang Gabelsteg zur Servo-Ecke"),
    ("fit",         0.2,  "Passungsspiel Servo-Aufnahme"),
    ("wall",        2.5,  "Wandstärke Servo-Aufnahme"),
    ("link_w",     20.0,  "Glied-Querschnitt Breite"),
    ("link_h",     28.0,  "Glied-Querschnitt Höhe"),
    ("link_wall",   2.0,  "Wandstärke Hohlprofil"),
    ("foot_r",      9.0,  "Fußkugel-Radius"),
    ("pad_t",       3.0,  "TPU-Pad Dicke"),
    ("pad_l",      35.0,  "TPU-Pad Länge"),
    ("coxa_len",   60.0,  "Coxa: Achse-Achse"),
    ("femur_len", 175.0,  "Femur: Achse-Achse"),
    ("tibia_len", 150.0,  "Tibia: Achse-Fußspitze"),
    ("q_coxa",      0.0,  "Gelenkwinkel Coxa [deg]"),
    ("q_femur",   -15.0,  "Gelenkwinkel Femur [deg], + = nach unten"),
    ("q_tibia",    90.0,  "Gelenkwinkel Tibia [deg], + = nach unten (ROM ca. +-105)"),
]
DERIVED = [
    ("zc",    "=(horn_t + cheek_t - servo_H - gap - cheek_b_t)/2", "Z-Mitte der Gabel (Gliedebene)"),
    ("r_clr", "=sqrt(servo_ax^2 + (servo_W/2)^2) + clr",           "Innenradius Gabelsteg"),
    ("back",  "=servo_L - servo_ax + wall",                        "Achse -> Außenseite Aufnahme-Rückwand"),
]
ALIASES = {p[0] for p in PARAMS} | {d[0] for d in DERIVED}


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


# ---------------------------------------------------------------- Bauteile
def servo(g, n, fr):
    """ST3215 im Servo-Frame: Achse = Z, Hornseite oben, Gehäuse nach -X (proximal) und -Z.
    Inkl. Gegenlager-Zapfen an der Rückseite."""
    case = box(g, n + "_case", fr, "-(servo_L - servo_ax)", "-servo_W/2", "-servo_H",
               "servo_L", "servo_W", "servo_H")
    horn = cyl(g, n + "_horn", fr, 0, 0, 0, "horn_d/2", "horn_t")
    pin = cyl(g, n + "_pin", fr, 0, 0, "-servo_H - gap - cheek_b_t", "bear_d/2", "gap + cheek_b_t")
    s = fuse(g, "ST3215_" + n, [case, horn, pin])
    _color(s, (0.15, 0.15, 0.17))
    return s


def bearing(g, n, fr):
    o = cyl(g, n + "_brg_o", fr, 0, 0, "-servo_H - gap - bear_B", "bear_D/2", "bear_B")
    i = cyl(g, n + "_brg_i", fr, 0, 0, "-servo_H - gap - bear_B - 0.5", "bear_d/2", "bear_B + 1")
    b = cut(g, "Bearing_" + n, o, [i])
    _color(b, (0.75, 0.75, 0.8))
    return b


def fork_pos(g, n, fr):
    """Gabel um den Servo dieses Gelenks (positive Körper)."""
    zb = "-servo_H - gap - cheek_b_t"
    xl = "r_clr + bridge_t"
    return [
        box(g, n + "_cheek_top", fr, 0, "-fork_w/2", "horn_t", xl, "fork_w", "cheek_t"),
        cyl(g, n + "_hub_top", fr, 0, 0, "horn_t", "fork_w/2", "cheek_t"),
        box(g, n + "_cheek_bot", fr, 0, "-fork_w/2", zb, xl, "fork_w", "cheek_b_t"),
        cyl(g, n + "_hub_bot", fr, 0, 0, zb, "fork_w/2", "cheek_b_t"),
        box(g, n + "_bridge", fr, "r_clr", "-fork_w/2", zb, "bridge_t", "fork_w",
            "horn_t + cheek_t + servo_H + gap + cheek_b_t"),
    ]


def fork_neg(g, n, fr):
    """Bohrungen: Hornschrauben, Hornmitte, Lagersitz, Durchgang."""
    t = []
    k = "horn_bc/2*0.70711"
    for i, (sx, sy) in enumerate([(1, 1), (-1, 1), (-1, -1), (1, -1)]):
        t.append(cyl(g, f"{n}_hornhole{i}", fr, f"{sx}*{k}", f"{sy}*{k}", "horn_t - 0.5",
                     "horn_hole/2", "cheek_t + 1"))
    t.append(cyl(g, n + "_hornctr", fr, 0, 0, "horn_t - 0.5", 1.6, "cheek_t + 1"))
    t.append(cyl(g, n + "_brg_seat", fr, 0, 0, "-servo_H - gap - bear_B", "bear_D/2", "bear_B + 0.5"))
    t.append(cyl(g, n + "_brg_thru", fr, 0, 0, "-servo_H - gap - cheek_b_t - 0.5",
                 "(bear_d + 1)/2", "cheek_b_t + 1"))
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
    """C-förmige Aufnahme für einen Servo (Rückwand + Seitenwände, oben/unten offen)."""
    pos = [box(g, n + "_cradle", fr, "-back", "-servo_W/2 - wall", "-servo_H",
               "back", "servo_W + 2*wall", "servo_H")]
    neg = [box(g, n + "_pocket", fr, "-(servo_L - servo_ax) - fit", "-servo_W/2 - fit",
               "-servo_H - 1", "servo_L + 2*fit + 10", "servo_W + 2*fit", "servo_H + 2")]
    return pos, neg


# ---------------------------------------------------------------- Bein
COL_PART = (0.95, 0.55, 0.10)
COL_TPU = (0.10, 0.10, 0.10)
X0 = "r_clr + bridge_t - 0.5"

leg = part(None, "Leg")

# Körperseite: Coxa-Servo fest am Body
servo(leg, "Coxa", I)
p, nn = cradle(leg, "Body", I)
body = cut(leg, "Body_Mount", fuse(leg, "Body_pos", p), nn)
_color(body, (0.6, 0.6, 0.6))

# J1 – Coxa (dreht um vertikale Achse)
j1 = part(leg, "J1_Coxa", angle="q_coxa")
F = Fr("coxa_len", "-zc", "zc", rx=True)          # Femur-Servo-Frame in J1
pos = fork_pos(j1, "Coxa", I); neg = fork_neg(j1, "Coxa", I)
b_p, b_n = beam(j1, "Coxa", I, X0, "coxa_len - back + 0.5", hollow=False)
c_p, c_n = cradle(j1, "FemurSrv", F)
coxa = cut(j1, "Coxa_Part", fuse(j1, "Coxa_pos", pos + b_p + c_p), neg + b_n + c_n)
_color(coxa, COL_PART)
bearing(j1, "Coxa", I)
servo(j1, "Femur", F)

# J2 – Femur
j2b = part(j1, "J2_base", fixed_fr=F)
j2 = part(j2b, "J2_Femur", angle="q_femur")
T = Fr("femur_len", "0", "0")                      # Tibia-Servo-Frame in J2
pos = fork_pos(j2, "Femur", I); neg = fork_neg(j2, "Femur", I)
b_p, b_n = beam(j2, "Femur", I, X0, "femur_len - back + 0.5", hollow=True)
c_p, c_n = cradle(j2, "TibiaSrv", T)
femur = cut(j2, "Femur_Part", fuse(j2, "Femur_pos", pos + b_p + c_p), neg + b_n + c_n)
_color(femur, COL_PART)
bearing(j2, "Femur", I)
servo(j2, "Tibia", T)

# J3 – Tibia
j3b = part(j2, "J3_base", fixed_fr=T)
j3 = part(j3b, "J3_Tibia", angle="q_tibia")
pos = fork_pos(j3, "Tibia", I); neg = fork_neg(j3, "Tibia", I)
b_p, b_n = beam(j3, "Tibia", I, X0, "tibia_len - foot_r", hollow=True)
foot = sph(j3, "Foot", I, "tibia_len - foot_r", 0, "zc", "foot_r")
tibia = cut(j3, "Tibia_Part", fuse(j3, "Tibia_pos", pos + b_p + [foot]), neg + b_n)
_color(tibia, COL_PART)
# seitliche TPU-Pads (auf den Flächen senkrecht zur Gelenkachse-Ebene, also +-Z im Tibia-Frame)
for s, z0 in (("A", "zc + link_h/2"), ("B", "zc - link_h/2 - pad_t")):
    pad = box(j3, "TPU_Pad_" + s, I, "tibia_len - foot_r - pad_l", "-link_w/2", z0,
              "pad_l", "link_w", "pad_t")
    _color(pad, COL_TPU)
bearing(j3, "Tibia", I)

doc.recompute()
if GUI:
    Gui.activeDocument().activeView().viewIsometric()
    Gui.SendMsgToActiveView("ViewFit")
print("SLARC-Bein erzeugt. Parameter in 'Params' ändern, dann Ctrl+R.")
