# -*- coding: utf-8 -*-
"""
SLARC – parametrisches Bein (Coxa/Femur/Tibia) mit 3x ST3215, doppelt gelagert.   V9
FreeCAD 0.21 / 1.0 – Makro ausführen oder in der Python-Konsole:
    exec(open(r"PFAD/slarc_leg_freecad_v8.py", encoding="utf-8").read())

V9 (gespiegelte Beine)
- MIRROR = True erzeugt das Spiegelbild des Beins (Spiegelebene = senkrechte Ebene durch die Coxa-Achse in Beinrichtung).
  Umgesetzt durch Konjugation aller Gelenk-Frames (Rotation R -> M R M) und Spiegelung der lokalen Geometrie, damit alle
  Teile echte Volumenkörper bleiben (STL-Export, Booleans). Die Servos bleiben echte ST3215 – im gespiegelten Bein sind
  Femur- und Tibia-Servo um ihre Längsachse um 180° gedreht eingebaut (Horn auf der anderen Seite).
- Gelenkwinkel behalten ihre Bedeutung: + = nach unten bzw. Coxa im Spiegelsinn. In der Software ist die Drehrichtung
  der gespiegelten Servos umzukehren.

V8 (Festigkeit + Kabelführung)
- Gabelsteg an Femur- und Tibiagelenk 6 statt 4 mm (bridge_t2). Die Coxa-Gabel bleibt bei 4 mm (dort ist der Steg
  mit der Femur-Aufnahme verschmolzen; dicker ginge nur mit längerer Coxa).
- Rampen (Part::Wedge) oben und unten zwischen Gabelsteg und Glied: Übergang von der 46 mm hohen Gabel auf den
  28 mm hohen Träger ohne Kerbstufe, Länge ramp_l. Sie liegen in Druckrichtung flach -> keine Stützen.
- Kabelbinder-Ösen: Schlitzpaare durch die Oberseite des Femur (3x) und der Tibia (1x, Zugentlastung Fußschalter),
  für 2.5er/3.6er Kabelbinder.
- Zierleisten beginnen hinter den Rampen; an der Tibia sitzen Leiste und Kabelbinder-Öse auf dem Fußsegment
  (V8.1: funktioniert damit auch bei Knick nahe am Knie).

V7 (TPU-Fuß für 95A, Druck mit Öffnung nach unten ohne Stützen)
- Innendecke des Fußes: nur noch eine schmale Druckfläche (±roof_p) über dem Stößel, seitlich 45°-Dachflächen.
  Die Brücke schrumpft von 20.5 auf 8 mm. Das Tibia-Ende ist passend 45° angefast; am Anschlag liegen
  Druckfläche und beide Dachflächen gleichzeitig an (Lastpfad bleibt Tibia -> TPU, nicht über den Schalter).
- Mikroschalter um 90° gedreht (lange Seite entlang der Gelenkachse), damit er in die schmale Druckfläche passt.
  Haltestifte jetzt quer (entlang der Beinebene), als 1.2er Vierkantlöcher.
- Rastlippen gestuft (halbe Höhe an der Öffnung) als Einführschräge – 95A lässt sich damit aufschieben.

V6
- Servo komplett eingehaust: geschlossener Rahmen um das Gehäuse (hinten, beide Seiten UND vorn vor der Achse),
  unten zwei Auflagelaschen. Der Servo wird von oben eingesetzt und nur von unten mit zwei 2x5-Blechschrauben
  (Gehäusebohrungen X=-32.7, Y=±10.2) gegen die Laschen gezogen.
  Lastpfad: Kräfte in X/Y gehen formschlüssig in den Rahmen, nach unten in die Laschen; nur Zug nach oben
  belastet die Schrauben – axial, nicht auf Abscherung.
- Damit der vordere Rahmensteg Platz hat, steht der Gabelsteg weiter außen: clr 1.5 -> 4.0 (r_clr 17.45 -> 19.95).
  Der Rahmen ist außen auf r_clr - ring_c beschnitten -> die Gabel läuft bei jedem Winkel frei daran vorbei.
- Coxa-Glied: Steg beginnt bei r_clr (sonst negative Länge bei 60 mm Coxa).
- Baseplates: Freischnitt arm_l = r_clr + bridge_t = 23.95 (slarc_baseplates_v2.py, V2.2).

V4
- Fußsegment 90 mm, Neutralhaltung q_femur = -15 / q_tibia = 45 (Fußsegment senkrecht).
- Fußkontakt: Mikroschalter in einer Tasche im Tibia-Ende, Stößel zeigt zum Fuß. Der TPU-Fuß gleitet als
  Hülse auf dem Tibia-Ende (Rastlippen in einer Nut, Federweg foot_trav) und drückt beim Aufsetzen auf den
  Stößel. Anschlag = Tibia-Stirnfläche. Schaltweg bis Anschlag = foot_trav - foot_gap
  -> muss zwischen Vorlaufweg und Vorlauf+Nachlauf des Schalters liegen.
  Kabel: Kanal vom Schalter in das Hohlprofil, Austritt kurz hinter dem Knie.

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

MIRROR = False           # True = gespiegeltes Bein (linke Körperseite)
MIR = -1 if MIRROR else 1
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
    ("bridge_t2",    6.0,  "Gabelsteg Femur/Tibia (Coxa: bridge_t)"),
    ("ramp_l",     15.0,  "Rampe Gabelsteg -> Träger, Länge"),
    ("bridge_t",    4.0,  "Dicke Gabelsteg"),
    ("fork_w",     26.0,  "Breite Gabelwangen"),
    ("clr",         4.0,  "Freigang Gabelsteg zur Servo-Ecke (Platz für vorderen Rahmensteg)"),
    ("fit",         0.2,  "Passungsspiel Servo-Aufnahme"),
    ("wall",        2.5,  "Wandstärke Servo-Aufnahme"),
    ("lip_t",       3.0,  "Laschen unten: Dicke unter dem Hüllmaß"),
    ("wall_f",      2.0,  "Rahmen: vorderer Steg vor der Achse"),
    ("ring_c",      1.0,  "Rahmen: Abstand zum Gabelsteg (Beschnitt auf r_clr - ring_c)"),
    ("tab_x",      30.5,  "Laschen unten: Beginn hinter der Achse (Steckerbuchsen bis -29.2)"),
    ("tab_y",       6.0,  "Laschen unten: Abstand von Mitte (Lücke für die Servokabel nach hinten)"),
    ("bot_z",      33.2,  "Laschen unten: Oberkante unter Hülle oben (Unterseite an den Bohrungen -33.1)"),
    ("hole_bx",    32.7,  "Gehäusebohrung unten: X hinter Achse (STEP)"),
    ("hole_y",     10.2,  "Gehäusebohrungen: ±Y (STEP)"),
    ("scr_d",       2.4,  "Durchgang Blechschraube 2x5"),
    ("cb_d",        4.4,  "Senkung für Schraubenkopf"),
    ("cb_rest",     1.5,  "Material unter dem Schraubenkopf"),
    ("link_w",     20.0,  "Glied-Querschnitt in Beinebene"),
    ("link_h",     28.0,  "Glied-Querschnitt entlang Gelenkachse"),
    ("link_wall",   2.0,  "Wandstärke Hohlprofil"),
    ("coxa_len",   60.0,  "Coxa: Achse-Achse"),
    ("femur_len", 175.0,  "Femur: Achse-Achse"),
    ("tibia_len", 150.0,  "Tibia: Knieachse -> Fußspitze (Sehne, = Sim-Wert)"),
    ("tib_bend",   60.0,  "Knick Tibia -> Fußsegment [deg], nach unten"),
    ("foot_seg",   90.0,  "Fußsegment: Knick -> Fußspitze"),
    ("foot_r",     16.0,  "TPU-Fußkugel Radius"),
    ("boot_l",     30.0,  "TPU-Fuß: Hülsenlänge über dem Glied"),
    ("boot_t",      2.0,  "TPU-Fuß: Wandstärke Hülse"),
    ("rib_p",       4.5,  "TPU-Rippen Teilung"),
    ("rib_w",       1.5,  "TPU-Rippen Breite"),
    ("rib_h",       1.0,  "TPU-Rippen Höhe"),
    ("foot_trav",   1.0,  "Federweg TPU-Fuß bis Anschlag"),
    ("foot_gap",    0.2,  "Ruhespalt TPU-Kappe -> Schalterstößel"),
    ("slide_c",     0.3,  "Gleitspiel TPU-Hülse auf Tibia (95A ist griffig -> etwas mehr Spiel)"),
    ("lip_w",       1.5,  "Rastlippe TPU Breite"),
    ("lip_h",       0.8,  "Rastlippe TPU Höhe = Nuttiefe"),
    ("sw_L",       12.8,  "Mikroschalter Länge, quer (PRÜFEN – Typ D2F angenommen)"),
    ("sw_T",        5.8,  "Mikroschalter Dicke, entlang Gelenkachse (PRÜFEN)"),
    ("sw_H",        6.5,  "Mikroschalter Höhe ohne Stößel, entlang Fußsegment (PRÜFEN)"),
    ("sw_pl",       1.0,  "Stößelüberstand (PRÜFEN)"),
    ("sw_pw",       2.4,  "Stößelbreite"),
    ("sw_hs",       6.5,  "Befestigungslöcher Abstand (PRÜFEN)"),
    ("sw_hx",       2.0,  "Befestigungslöcher: Abstand von der Anschlussseite (PRÜFEN)"),
    ("sw_hd",       1.2,  "Befestigungsstifte Ø (bündig, TPU-Hülse gleitet drüber)"),
    ("roof_p",      4.0,  "TPU-Fuß: halbe Breite der Druckfläche (außen 45°-Dach)"),
    ("wire_w",      4.0,  "Kabelkanal Breite"),
    ("wire_h",      3.0,  "Kabelkanal Höhe"),
    ("deco_t",      1.2,  "PLA-Zierleiste Dicke"),
    ("deco_m",      4.0,  "PLA-Zierleiste Randabstand"),
    ("q_coxa",      0.0,  "Gelenkwinkel Coxa [deg]"),
    ("q_femur",   -15.0,  "Gelenkwinkel Femur [deg], + = nach unten"),
    ("q_tibia",    45.0,  "Gelenkwinkel Tibia [deg], + = nach unten (bezogen auf Segment 1)"),
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
        self.rot_m = ROT(V(1, 0, 0), 90) if rx else ROT()      # M R M (Spiegelung y -> -y)
        self.ycol_m = (0, 0, 1) if rx else (0, 1, 0)             # Bild der lokalen y-Achse unter rot_m

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


def _place(o, fr, x, y, z, W=None):
    """Platzierung im Frame fr. Gespiegelt: Rotation M R M, Basis M b; Quader zusätzlich um -W entlang des Bilds
    der lokalen y-Achse verschoben (die gespiegelte Box beginnt an ihrer anderen Ecke)."""
    bx, by, bz = fr.base(x, y, z)
    if MIR > 0:
        o.Placement = App.Placement(V(), fr.rot)
    else:
        o.Placement = App.Placement(V(), fr.rot_m)
        by = f"-({by})"
        if W is not None:
            cy, cz = fr.ycol_m[1], fr.ycol_m[2]
            if cy:
                by = f"{by} - ({W})"
            if cz:
                bz = f"({bz}) - ({W})"
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
    _place(o, fr, x0, y0, z0, W)
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
    bx, by = rpt(px, py, ang, lx0, ly0)
    if MIR > 0:
        _x(o, "Placement.Rotation.Angle", ang)
    else:                                   # Spiegelbild: Drehung -ang, Ecke an der gegenüberliegenden Kante
        _x(o, "Placement.Rotation.Angle", f"-({ang})")
        bx, by = f"({bx}) - ({W})*sin({ang})", f"-({by}) - ({W})*cos({ang})"
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
        _x(p, "Placement.Rotation.Angle", angle if MIR > 0 else f"-({angle})")   # Grad
    return p


# ---------------------------------------------------------------- Farben / Material
COL_PETG = (0.08, 0.08, 0.08)   # PETG schwarz
COL_PLA = (1.00, 0.45, 0.00)    # PLA orange
COL_TPU = (0.30, 0.30, 0.33)    # TPU
COL_SERVO = (0.20, 0.20, 0.26)
COL_SW = (0.80, 0.10, 0.10)


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


def fork_pos(g, n, fr, bt="bridge_t"):
    """Gabel: obere Wange auf dem Horn, untere Wange mit Distanzbund auf der Rückscheibe."""
    xl = f"r_clr + {bt}"
    return [
        box(g, n + "_cheek_top", fr, 0, "-fork_w/2", "horn_t", xl, "fork_w", "cheek_t"),
        cyl(g, n + "_hub_top", fr, 0, 0, "horn_t", "fork_w/2", "cheek_t"),
        box(g, n + "_cheek_bot", fr, 0, "-fork_w/2", "zb", xl, "fork_w", "cheek_b_t"),
        cyl(g, n + "_hub_bot", fr, 0, 0, "zb", "fork_w/2", "cheek_b_t"),
        cyl(g, n + "_boss_bot", fr, 0, 0, "zb + cheek_b_t", "horn_d/2", "boss_h"),
        box(g, n + "_bridge", fr, "r_clr", "-fork_w/2", "zb", bt, "fork_w",
            "horn_t + cheek_t - zb"),
    ]


def wedge(g, n, x0, x1, x20, x21, y0, y1, hw):
    """Part::Wedge, um X um +90° gedreht: Wedge-Y -> Z (Höhe), Wedge-Z -> -Y (Breite ±hw)."""
    o = doc.addObject("Part::Wedge", n); g.addObject(o)
    o.Placement = App.Placement(V(), ROT(V(1, 0, 0), 90))
    for prop, e in (("Xmin", x0), ("Xmax", x1), ("X2min", x20), ("X2max", x21), ("Ymin", y0), ("Ymax", y1),
                    ("Zmin", f"-({hw})"), ("Zmax", hw), ("Z2min", f"-({hw})"), ("Z2max", hw)):
        _x(o, prop, e)
    return o


def ramps(g, n, x1):
    """Rampen oben/unten vom Gabelsteg auf den Träger (Frame I)."""
    return [wedge(g, n + "_ramp_top", x1, f"({x1}) + ramp_l", x1, f"({x1}) + 0.5",
                  "zc + link_h/2", "horn_t + cheek_t", "link_w/2"),
            wedge(g, n + "_ramp_bot", x1, f"({x1}) + 0.5", x1, f"({x1}) + ramp_l",
                  "zb", "zc - link_h/2", "link_w/2")]


def ties(g, n, xs):
    """Kabelbinder-Schlitzpaare durch die Oberseite (-Y) eines Hohlträgers."""
    out = []
    for i, x in enumerate(xs):
        for k, sz in enumerate((-1, 1)):
            out.append(box(g, f"{n}_tie{i}{k}", I, f"({x}) - 2", "-link_w/2 - 1", f"zc + ({sz})*5 - 1",
                           4, "link_wall + 1.5", 2))
    return out


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


def common(g, n, a, b):
    o = doc.addObject("Part::Common", n); g.addObject(o)
    o.Base, o.Tool = a, b
    _hide(a); _hide(b)
    return o


def cradle(g, n, fr):
    """Geschlossener Rahmen um den Servo (oben/unten offen) + untere Auflagelaschen.
    Rückgabe: pos, neg (Grundkörper), lip_pos, lip_neg (nach dem Ausschneiden der Tasche angefügt)."""
    YW = "servo_W/2 + wall"
    rear = box(g, n + "_cradle", fr, "-back", f"-({YW})", "-servo_H", "back", f"2*({YW})", "servo_H")
    front = common(g, n + "_ring",
                   box(g, n + "_ring_box", fr, 0, f"-({YW})", "-servo_H", "servo_ax + fit + wall_f", f"2*({YW})", "servo_H"),
                   cyl(g, n + "_ring_cyl", fr, 0, 0, "-servo_H - 1", "r_clr - ring_c", "servo_H + 2"))
    pos = [rear, front]
    neg = [box(g, n + "_pocket", fr, "-(servo_L - servo_ax) - fit", "-servo_W/2 - fit",
               "-servo_H - 1", "servo_L + 2*fit", "servo_W + 2*fit", "servo_H + 2")]
    lp = []
    for s, y0 in (("L", "tab_y"), ("R", f"-({YW})")):
        lp.append(box(g, f"{n}_tab_bot{s}", fr, "-back", y0, "-servo_H - lip_t", "back - tab_x",
                      f"({YW}) - tab_y", "lip_t + servo_H - bot_z"))
    ln = []
    for i, sy in enumerate((1, -1)):
        hy = f"({sy})*hole_y"
        ln.append(cyl(g, f"{n}_scr_b{i}", fr, "-hole_bx", hy, "-servo_H - lip_t - 1", "scr_d/2",
                      "lip_t + servo_H - bot_z + 2"))
        ln.append(cyl(g, f"{n}_cb_b{i}", fr, "-hole_bx", hy, "-servo_H - lip_t - 1", "cb_d/2",
                      "lip_t + servo_H - bot_z - cb_rest + 1"))
    return pos, neg, lp, ln


def with_lips(g, n, core, lp, ln):
    """Laschen an den fertigen Grundkörper anfügen und Schraubenlöcher/Senkungen schneiden."""
    return cut(g, n, fuse(g, n + "_lips", [core] + lp), ln)


def deco(g, n, x0, x1):
    """PLA-Zierleisten auf beiden Seitenflächen (±Z) eines geraden Glieds, aufgesetzt."""
    for s, z0 in (("A", "zc + link_h/2"), ("B", "zc - link_h/2 - deco_t")):
        d = box(g, f"Deco_{n}_{s}", I, f"({x0}) + deco_m", "-link_w/2 + deco_m", z0,
                f"({x1}) - ({x0}) - 2*deco_m", "link_w - 2*deco_m", "deco_t")
        _color(d, COL_PLA)


# ---------------------------------------------------------------- Bein
X0 = "r_clr + bridge_t - 0.5"
X1 = "r_clr + bridge_t2 - 0.5"          # Trägerbeginn Femur/Tibia

leg = part(None, "Leg")

# Körperseite
servo(leg, "Coxa", I)
p, nn, lp, ln = cradle(leg, "Body", I)
body = with_lips(leg, "Body_Mount", cut(leg, "Body_core", fuse(leg, "Body_pos", p), nn), lp, ln)
_color(body, COL_PETG)

# J1 – Coxa
j1 = part(leg, "J1_Coxa", angle="q_coxa")
F = Fr("coxa_len", "-zc", "zc", rx=True)
pos = fork_pos(j1, "Coxa", I); neg = fork_neg(j1, "Coxa", I)
b_p, b_n = beam(j1, "Coxa", I, "r_clr", "coxa_len - back + 0.5", hollow=False)
c_p, c_n, lp, ln = cradle(j1, "FemurSrv", F)
coxa = with_lips(j1, "Coxa_Part", cut(j1, "Coxa_core", fuse(j1, "Coxa_pos", pos + b_p + c_p), neg + b_n + c_n), lp, ln)
_color(coxa, COL_PETG)
servo(j1, "Femur", F)

# J2 – Femur
j2b = part(j1, "J2_base", fixed_fr=F)
j2 = part(j2b, "J2_Femur", angle="q_femur")
T = Fr("femur_len", "0", "0")
pos = fork_pos(j2, "Femur", I, "bridge_t2") + ramps(j2, "Femur", X1); neg = fork_neg(j2, "Femur", I)
b_p, b_n = beam(j2, "Femur", I, X1, "femur_len - back + 0.5", hollow=True)
b_n += ties(j2, "Femur", [f"({X1}) + ramp_l + 8", "(femur_len - back + ramp_l + r_clr)/2", "femur_len - back - 10"])
c_p, c_n, lp, ln = cradle(j2, "TibiaSrv", T)
femur = with_lips(j2, "Femur_Part", cut(j2, "Femur_core", fuse(j2, "Femur_pos", pos + b_p + c_p), neg + b_n + c_n), lp, ln)
_color(femur, COL_PETG)
deco(j2, "Femur", f"({X1}) + ramp_l", "femur_len - back")
servo(j2, "Tibia", T)

# J3 – Tibia (geknickt) mit Fußkontakt-Schalter
j3b = part(j2, "J3_base", fixed_fr=T)
j3 = part(j3b, "J3_Tibia", angle="q_tibia")
BEND = "tib_bend"
# Positionen entlang des Fußsegments (lokal, ab Knickmitte), Ruhelage
XI = "foot_seg - foot_r"                 # Innenboden TPU-Kappe = Kugelmitte
XE = f"({XI}) - foot_trav"               # Tibia-Stirnfläche = Anschlag
XS = f"({XI}) - boot_l"                  # Öffnung TPU-Hülse / Rastlippe
XP = f"({XI}) - foot_gap - sw_pl"        # Schalter Stößelseite
XSW = f"({XP}) - sw_H"                   # Schalter Anschlussseite
XV = f"({XS}) - foot_trav - 4"           # Ende Hohlraum, Endstück massiv


def s2box(n, lx0, ly0, z0, L, W, H):
    return rbox(j3, n, "tib_a", 0, BEND, lx0, ly0, z0, L, W, H)


def s2cyl(n, lx, ly, z0, r, h):
    px, py = rpt("tib_a", 0, BEND, lx, ly)
    return cyl(j3, n, I, px, py, z0, r, h)


pos = fork_pos(j3, "Tibia", I, "bridge_t2") + ramps(j3, "Tibia", X1); neg = fork_neg(j3, "Tibia", I)
seg1 = box(j3, "Tibia_seg1", I, X1, "-link_w/2", "zc - link_h/2",
           f"tib_a - ({X1})", "link_w", "link_h")
seg1_in = box(j3, "Tibia_seg1_in", I, f"({X1}) + link_wall", "-link_w/2 + link_wall",
              "zc - link_h/2 + link_wall", f"tib_a - ({X1}) - link_wall",
              "link_w - 2*link_wall", "link_h - 2*link_wall")
knuckle = cyl(j3, "Tibia_knuckle", I, "tib_a", 0, "zc - link_h/2", "link_w/2", "link_h")
seg2 = s2box("Tibia_seg2", 0, "-link_w/2", "zc - link_h/2", XE, "link_w", "link_h")
neg += [seg1_in,
        s2box("Tibia_seg2_in", 0, "-link_w/2 + link_wall", "zc - link_h/2 + link_wall", XV,
              "link_w - 2*link_wall", "link_h - 2*link_wall"),
        s2box("Tibia_wire", f"({XV}) - 1", "-wire_w/2", "zc - wire_h/2", f"({XSW}) - ({XV}) + 2",
              "wire_w", "wire_h"),
        s2box("Tibia_swpocket", XSW, "-sw_T/2 - fit", "zc - sw_L/2 - fit", f"({XE}) - ({XSW}) + 1",
              "sw_T + 2*fit", "sw_L + 2*fit"),
        box(j3, "Tibia_wire_exit", I, f"({X1}) + 6", "-link_w/2 - 1", "zc - 3", 10, "link_wall + 2", 6)]
for k, sz in enumerate((-1, 1)):       # Kabelbinder-Öse am Fußsegment (Zugentlastung Schalterkabel)
    neg.append(s2box(f"Tibia_tie{k}", "link_w/2 + 4", "-link_w/2 - 1", f"zc + ({sz})*5 - 1", 4, "link_wall + 1.5", 2))
for s_, z0 in (("A", "zc + link_h/2 - lip_h - 0.2"), ("B", "zc - link_h/2 - 1")):
    neg.append(s2box(f"Tibia_groove{s_}", f"({XS}) - foot_trav - 0.2", "-link_w/2 - 1", z0,
                     "lip_w + foot_trav + 0.4", "link_w + 2", "lip_h + 1.2"))
for i, sz in enumerate((-1, 1)):       # Haltestifte quer durch die Seitenwände (Vierkant)
    neg.append(s2box(f"Tibia_swpin{i}", f"({XSW}) + sw_hx - sw_hd/2", "-link_w/2 - 1",
                     f"zc + ({sz})*sw_hs/2 - sw_hd/2", "sw_hd", "link_w + 2", "sw_hd"))
SQ = "0.70711"


def r45(n, sgn, u0, v0, z0, L, W, H):
    """Box in einem um ±45° (zusätzlich zum Knick) gedrehten Frame: u = (x ± y)/√2."""
    return rbox(j3, n, "tib_a", 0, f"({BEND}) + ({sgn})*45", u0, v0, z0, L, W, H)


def roof_cut(n, sgn, xr, hw):
    """Halbraum oberhalb der 45°-Fläche x + |y| = xr + roof_p, begrenzt auf den Eckbereich (|y| <= hw)."""
    v0 = (f"((roof_p) - ({xr}))*{SQ} - 3" if sgn > 0 else f"(({xr}) + roof_p - 2*({hw}))*{SQ} - 3")
    return r45(n, sgn, f"(({xr}) + roof_p)*{SQ}", v0, "zc - link_h/2 - 2", 20,
               f"(2*({hw}) - 2*roof_p)*{SQ} + 6", "link_h + 4")


for s_, sg in (("L", 1), ("R", -1)):          # Tibia-Ende 45° anfasen
    neg.append(roof_cut(f"Tibia_roof{s_}", sg, XE, "link_w/2"))
tibia = cut(j3, "Tibia_Part", fuse(j3, "Tibia_pos", pos + [seg1, knuckle, seg2]), neg)
_color(tibia, COL_PETG)
for s_, z0 in (("A", "zc + link_h/2"), ("B", "zc - link_h/2 - deco_t")):   # Zierleisten auf dem Fußsegment
    d = s2box(f"Deco_Tibia_{s_}", "link_w/2 + deco_m", "-link_w/2 + deco_m", z0,
              f"({XS}) - foot_trav - 3 - link_w/2 - 2*deco_m", "link_w - 2*deco_m", "deco_t")
    _color(d, COL_PLA)

# Mikroschalter (Platzhalter)
sw = fuse(j3, "Microswitch", [
    s2box("SW_body", XSW, "-sw_T/2", "zc - sw_L/2", "sw_H", "sw_T", "sw_L"),
    s2box("SW_plunger", XP, "-sw_pw/2", "zc - sw_pw/2", "sw_pl", "sw_pw", "sw_pw")])
_color(sw, COL_SW)

# TPU-Fuß: Kugelkappe + Gleithülse + Grip-Rippen + Rastlippen
cx, cy = rpt("tib_a", 0, BEND, XI, 0)
OW, OH = "link_w + 2*(slide_c + boot_t)", "link_h + 2*(slide_c + boot_t)"
ball = sph(j3, "Foot_ball", I, cx, cy, "zc", "foot_r")
sleeve = s2box("Foot_sleeve", XS, "-link_w/2 - slide_c - boot_t", "zc - link_h/2 - slide_c - boot_t",
               "boot_l", OW, OH)
ribs = []
for i in range(RIBS):
    for s_, z0 in (("A", "zc + link_h/2 + slide_c + boot_t"),
                   ("B", "zc - link_h/2 - slide_c - boot_t - rib_h")):
        ribs.append(s2box(f"Foot_rib{s_}{i}", f"({XS}) + 3 + {i}*rib_p",
                          "-link_w/2 - slide_c - boot_t", z0, "rib_w", OW, "rib_h"))
socket = s2box("Foot_socket", f"({XS}) - 1", "-link_w/2 - slide_c", "zc - link_h/2 - slide_c",
               "boot_l + 1", "link_w + 2*slide_c", "link_h + 2*slide_c")
body_tpu = cut(j3, "Foot_body", fuse(j3, "Foot_pos", [ball, sleeve] + ribs), [socket])
lips = []
for s_, sz in (("A", 1), ("B", -1)):          # gestufte Rastlippen: halbe Höhe an der Öffnung = Einführschräge
    for k, (dx, hh) in enumerate((("0", "lip_h/2"), ("lip_w/2", "lip_h"))):
        z0 = f"zc + link_h/2 - ({hh})" if sz > 0 else "zc - link_h/2 - slide_c"
        lips.append(s2box(f"Foot_lip{s_}{k}", f"({XS}) + {dx}", "-link_w/2 - slide_c", z0,
                          "lip_w/2", "link_w + 2*slide_c", f"({hh}) + slide_c"))
# Innendach: 45°-Keile füllen die Ecken der Kappe, übrig bleibt die Druckfläche ±roof_p
HS = "link_w/2 + slide_c"
wedges = []
for s_, sg in (("L", 1), ("R", -1)):
    sock2 = s2box(f"Foot_sock2{s_}", f"({XS}) - 1", f"-({HS})", "zc - link_h/2 - slide_c",
                  "boot_l + 1", f"2*({HS})", "link_h + 2*slide_c")
    wedges.append(common(j3, f"Foot_roof{s_}", roof_cut(f"Foot_roofcut{s_}", sg, XI, HS), sock2))
foot = fuse(j3, "Foot_TPU", [body_tpu] + lips + wedges)
_color(foot, COL_TPU)

doc.recompute()
if GUI:
    Gui.activeDocument().activeView().viewFront()
    Gui.SendMsgToActiveView("ViewFit")
print("SLARC-Bein V9 erzeugt" + (" (gespiegelt)" if MIRROR else "") + ". tib_a = %s mm, tib_delta = %s"
      % (sheet.get("tib_a"), sheet.get("tib_delta")))
