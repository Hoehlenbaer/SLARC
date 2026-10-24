# -*- coding: utf-8 -*-
"""
SLARC – obere + untere Baseplate inkl. Coxa-Servo-Aufnahme, Elektronik und Energieversorgung.   V2.7 (Akku-Riegel: Bajonett-Stift mittig, werkzeuglos)
FreeCAD 0.21 / 1.0: Makro ausführen. Parameter in P (unten) ändern und Makro neu ausführen
(die Plattenkontur mit den Schwenkfreigängen ist hier bewusst als Python-Geometrie gebaut,
nicht über Spreadsheet-Ausdrücke).

Koordinaten (wie slarc_sim_V10): X = vorn, Y = links, Z = oben, Ursprung = Körpermitte,
Z = 0 = Oberkante Hüllmaß der Coxa-Servos (ST3215 liegt mit Horn nach oben zwischen den Platten).

V2.7
- Akku-Riegel ohne Zukaufteile: ein gedruckter Stift (Ø8) mittig hinter dem Akku (zwischen Balancer- und Hauptkabel), von unten durch die untere Platte
  bis in eine Führungsbohrung der oberen Platte gesteckt (beidseitig gelagert). Bajonett wie eine Glühbirne:
  Stift mit der Nase nach hinten (Rille im Kopf längs X) einstecken, hochdrücken, 90° drehen -> Nase rastet in
  eine Kerbe oben in der unteren Platte (Rille quer = zu).
  Zum Akkuwechsel: hochdrücken, zurückdrehen, Stift nach unten herausziehen, Akku nach hinten herausziehen.
  Auf der Platte bleibt nichts stehen; das hintere Taschenende ist eine Rampe (Akku gleitet die 2 mm hoch).
  Obere Platte hinten: 2 Führungsbohrungen (neu drucken).
  Ein Stück Moosgummi zwischen Kopf und Plattenunterseite (lat foam, 5 mm -> 3 mm) zieht die Nase in die Kerbe,
  damit sich der Stift auch in Rückenlage nicht losvibriert.

V2.6
- Untere Platte hinten links (neben dem Akku-Ausgang): Halter für die Robot-Seite der Akkustecker, separat gedruckt,
  2x M3 + Mutter. Unten Deans-Stecker (Stifte, Robot-Seite), darüber der Balancer-Adapter zum BMS-Messkabel.
  Stecköffnungen zeigen nach hinten (Abziehrichtung = Ausziehrichtung des Akkus). Rückwand mit Kabelschlitzen
  (Gehäuse kann beim Einstecken nicht nach vorn rutschen), Kabelbinderschlitze für den Halt beim Abziehen.
  Reihenfolge laut Daly: zuerst Hauptstecker (B-) verbinden, dann Balancer; trennen umgekehrt.
  Steckermaße sind Startwerte (Deans-Gehäuse 13 x 7.5 x 19, Balancer-Adapter wie JST-XH 4-pol.) -> nachmessen.

V2.5
- Obere Platte hinten: DC-DC-Wandler 12 V -> 5 V für den Pi 5 (Fulree F35J5V5A1S-C, 46.2 x 27.5 x 14,
  Laschen an den kurzen Seiten, Spitze-Spitze 63.2, offene Schlitze 4 mm). Befestigung 2x M3 + Mutter,
  Langlöcher in der Platte (scr_in ± adj) gleichen die unbekannte Schlitztiefe aus.
- Zwei Modulplätze (je 2x M3 im Abstand 2*mod_dx): "MCP" für den IO-Expander MCP23017 (Fußkontakte,
  Status-LEDs) und "MUX" als Reserve (I2C-Multiplexer/Hub). Die Module sitzen auf eigenen kleinen
  Trägern (separat gedruckt, sobald die Platinenmaße feststehen) -> die Platte muss dafür nicht neu gedruckt werden.
- Der hintere Plattenteil wird kopfüber gedruckt: deshalb nur Bohrungen, keine Aufbauten oben.

V2
- Untere Platte: gleiche Kontur, Freischnitte für die untere Gabelwange, Öffnung für die Servostecker
  (Buchsen sitzen in der Einbuchtung auf der Servo-Unterseite), Stützbolzen + Sicherungsschrauben,
  integrierte Säulen zur oberen Platte (M3 durchgehend), Batteriefach mit Schienen/Anschlag/Gurtschlitzen
  (Batterie nach hinten herausziehbar), BMS-Platz mit Gurtschlitzen, 8-fach-Relais quer auf Bolzen.
- Obere Platte: Säulenpositionen und Stoßschrauben an die Belegung zwischen den Platten angepasst.

Inhalt obere Platte
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
    hub_r=13.0, arm_l=23.95, arm_w=13.0, fork_clr=1.5,   # arm_l = r_clr + bridge_t aus Bein V6
    # Servo-Details im Servo-Frame (aus ST3215.step)
    raised=(-34.5, -9.4, 7.3),      # erhabener Deckelteil: X von..bis, ±Y (STEP -34.2/±7.0 + Spiel)
    srv_holes=[(-29.0, 10.2), (-29.0, -10.2)], srv_hole_d=2.4,
    cb_d=4.4, cb_rest=1.5,          # Senkung für 2x5-Servoschrauben: 1.5 mm Material unter dem Kopf
    # Elektronik
    pi_x=115.0, pi_so=6.0, pi_hole_d=2.7,          # Pi 5: Mitte X, Bolzenhöhe, M2.5
    gdr_x=42.5, gdr_so=12.0, gdr_hole_d=2.7,       # Treiberboard: Lochbild-Mitte X, Bolzen (Stiftleiste unten 9.4)
    relay_on_top=False, relay_x=-110.0, relay_so=5.0, relay_hole_d=3.2,   # Option: Relais oben hinten
    # Untere Platte / zwischen den Platten
    z_lt=-35.0,             # Oberseite untere Platte = Unterkante Servo-Hüllmaß
    plug=(-29.7, -14.0, 11.0),      # Steckeröffnung im Servo-Frame: X von..bis, ±Y
    srv_holes_bot=[(-32.7, 10.2), (-32.7, -10.2)], boss_bot=1.8,   # Unterseite -33.1 -> Bolzen bis -33.2
    col_d=8.0, col_hole_d=3.4,                      # Säulen (M3 x 45 durchgehend + Mutter)
    bat_x0=-167.0, bat_x1=5.0, bat_w=52.0, bat_h=32.0, bat_pocket=2.0, rail_h=8.0,
    bat_straps=[-125.0, -45.0],
    bms=(10.0, 85.0, 50.0, 14.0), bms_straps=[47.5],
    relay_low_x=118.25,     # Relais quer (90° gedreht) zwischen den Platten, Mitte X
    # Kamera
    cam_x=182.0,            # Frontfläche der Kamerahalterung
    ped_h=10.0,             # Sockelhöhe (Freiraum für FPC-Kabel unter der Halterung)
    cam_base=65.0,          # Baseline (muss zur Halterung passen; 65 -> Platz für Trigger-Platine)
    # Kabel / Abstandsbolzen / Teilung
    slots=[(0.0, 0.0, 12.0, 34.0), (-80.0, 0.0, 12.0, 40.0), (-150.0, 0.0, 12.0, 40.0), (150.0, 0.0, 10.0, 30.0)],
    standoffs=[(155.0, 35.0), (155.0, -35.0), (60.0, 45.0), (60.0, -45.0),
               (-40.0, 48.0), (-40.0, -48.0), (-125.0, 55.0), (-125.0, -55.0)],
    # hinten keine Säulen: Batterie-Ausbauweg + Schwenkbereich der hinteren Coxas; die 6 Servos tragen mit
    so_hole_d=3.2,
    # V2.5: DC-DC 12 V -> 5 V (Pi 5) und Modulplätze, alle auf dem hinteren Teil der oberen Platte
    dcdc=dict(x=-115.0, y=-35.0, L=46.2, W=27.5, H=14.0, tip=63.2, tab_t=4.0, tab_w=12.0,
              scr_in=3.5,       # Schraubenmitte ab Laschenspitze (Schlitz offen nach außen; PRÜFEN)
              adj=1.5),         # Langloch ± entlang X
    mod_dx=21.0,                # Modulträger: M3-Bohrungen bei ±mod_dx (entlang X)
    mods=[("MCP", -115.0, 35.0), ("MUX", -115.0, 0.0)],   # MUX liegt über der Batterie: Mutter max. 4 mm hoch
    m3_d=3.4,
    # V2.6: Steckerhalter Akku (Robot-Seite), sitzt auf der unteren Platte; Stecker zeigen nach -X (hinten)
    conn=dict(x_front=-190.0, y0=28.0,          # Stirnseite (Stecköffnungen) und Innenkante (Akku-Schiene endet bei y 29)
              deans=(19.0, 13.0, 7.5),          # Deans-Stecker Robot-Seite: Länge (X), Breite (Y), Höhe (Z) – NACHMESSEN
              bal=(10.0, 12.4, 5.8),            # Balancer-Adapter (JST-XH 4-pol. als Startwert): L, B, H – NACHMESSEN
              clr=0.25, wall=1.6, floor=2.0, back=3.0, slot=(6.0, 3.0),   # Spiel, Wände, Rückwand, Kabelschlitz B x H
              flange=8.0, holes=(-194.0, -164.0)),                         # Laschen vorn/hinten mit M3
    # V2.7: Akku-Riegel (Bajonett-Stifte hinter dem Akku, Kopf unter der unteren Platte)
    lat=dict(x=-171.0, ys=(0.0,),               # Stiftachse(n), ein Stift mittig zwischen den Kabelabgängen; Vorderkante x + d/2 = -167 = Akku-Ende
             d=8.0, clr=0.25,                    # Stift Ø, radiales Spiel in Bohrung/Schale
             lug_w=3.0, lug_r=7.0, lug_h=2.5,    # Nase: Breite, Außenradius, Höhe
             notch=0.8, key_clr=0.3,             # Rastkerbe-Tiefe, Spiel Nase/Schlitz
             foam=3.0,                           # Abstand Kopf - Plattenunterseite (Moosgummi 5 mm gepresst)
             top=2.5,                            # Stiftende: so tief steckt der Stift in der oberen Platte (Führung)
             ramp=4.0,                           # Rampe am hinteren Taschenende (2 mm hoch auf 4 mm)
             head_d=20.0, head_h=5.0),           # Griffkopf (gerändelt, Rille zeigt die Nasenrichtung)
    split_x=-40.0, lap=24.0, lap_screws=[-65.0, -32.0, 32.0, 65.0],   # Vorderteil 252 x 209 mm
)
STEP_DIR = r""

# Stereo-Halterung (identisch zu slarc_stereo_mount_v1_4.py)
CAM = dict(pcb=39, hole_s=34, pilot_d=1.7, so_d=5, so_h=2, plate_t=4, holder_w=24.4, holder_h=16.3,
           win_c=.8, rim_c=.6, rim_t=3, bot_t=4, rim_d=12, fpc_w=20, fpc_off=.5, ear_l=10, ear_hole=3.2,
           trig_w=0.0, trig_off=0.0,   # trig_w > 0: Kabelschlitze oben für Trigger/Strobe (z.B. 28.5)
           tpcb_w=20.0, tpcb_h=22.0, tpcb_c=0.3, tpcb_d=0.5,
           imu=True, imu_hs=13.6, imu_hz=2.0, imu_pd=2.1, imu_depth=6.0, imu_so=1.5, imu_sod=4.5)   # V1.4: ICM20948 oben

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
Z_LT = P["z_lt"]               # Oberseite untere Platte
Z_LB = Z_LT - P["t"]           # Unterseite untere Platte


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
        if g.trig_w > 0:
            neg.append(box(cx + g.trig_off - g.trig_w / 2, H2 - g.rim_t - 1, ZB - 1, g.trig_w, g.rim_t + 2, g.rim_d + 1))
        for hx, hy in ((1, 1), (-1, 1), (-1, -1), (1, -1)):
            pos.append(cyl(cx + hx * g.hole_s / 2, hy * g.hole_s / 2, 0, g.so_d / 2, g.so_h + .5))
            neg.append(cyl(cx + hx * g.hole_s / 2, hy * g.hole_s / 2, -.1, g.pilot_d / 2, g.so_h + g.plate_t - .9))
        neg.append(cyly(sx * (W2 + g.ear_l / 2), -H2b - 1, (ZB + ZF) / 2, g.ear_hole / 2, g.bot_t + 2))
        if g.imu:
            ix, iz = sx * g.imu_hs / 2, ZF - g.imu_hz
            pos.append(cyly(ix, H2 - 0.5, iz, g.imu_sod / 2, g.imu_so + 0.5))
            neg.append(cyly(ix, H2 - g.imu_depth, iz, g.imu_pd / 2, g.imu_depth + g.imu_so + 0.2))
    neg.append(box(-g.tpcb_w / 2 - g.tpcb_c, -g.tpcb_h / 2 - g.tpcb_c, g.so_h - 0.01,
                   g.tpcb_w + 2 * g.tpcb_c, g.tpcb_h + 2 * g.tpcb_c, g.tpcb_d + 0.01))
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


def dcdc_screws():
    d = P["dcdc"]; e = d["tip"] / 2 - d["scr_in"]
    return [(d["x"] - e, d["y"]), (d["x"] + e, d["y"])]


def dcdc_holes(z0, h):
    """Langlöcher M3 unter den offenen Laschenschlitzen."""
    r, a = P["m3_d"] / 2, P["dcdc"]["adj"]
    out = []
    for sx, sy in dcdc_screws():
        out += [cyl(sx - a, sy, z0, r, h), cyl(sx + a, sy, z0, r, h), box(sx - a, sy - r, z0, 2 * a, 2 * r, h)]
    return out


def mod_holes():
    return [(x + s * P["mod_dx"], y) for _, x, y in P["mods"] for s in (-1, 1)]


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
            neg.append(rcyl(x, y, yaw, hx, hy, zb + P["cb_rest"], P["cb_d"] / 2, t + P["ped_h"]))
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
    neg += dcdc_holes(zb - 1, t + 2)
    neg += latch_top_neg(zb, t)                         # V2.7: Führung Akku-Riegel
    for hx, hy in mod_holes():
        neg.append(cyl(hx, hy, zb - 1, P["m3_d"] / 2, t + 2))
    plate = cut(fuse(pos), neg)
    # V2.1: Hinterteil trägt die obere Stoßhälfte -> wird kopfüber gedruckt (oben flach), Vorderteil normal
    front, rear = split(plate, zb, upper_front=False)
    return dict(plate=plate, front=front, rear=rear, bracket=xform(br, cam_matrix(dims)),
                bracket_local=br, dims=dims)


def split(plate, zb, upper_front):
    """Teilung bei split_x mit Überlappstoß; ein Teil behält im Stoß die obere, das andere die untere Hälfte."""
    t, sx, lap, big = P["t"], P["split_x"], P["lap"], 1000.0
    lo = box(sx - lap / 2, -big, zb - 1, lap, 2 * big, t / 2 + 1)          # untere Hälfte Stoßbereich
    hi = box(sx - lap / 2, -big, zb + t / 2, lap, 2 * big, 100)            # obere Hälfte (inkl. Aufbauten)
    front = cut(plate, [box(-big, -big, zb - 1, big + sx - lap / 2, 2 * big, 200), lo if upper_front else hi])
    rear = cut(plate, [box(sx + lap / 2, -big, zb - 1, big, 2 * big, 200), hi if upper_front else lo])
    return front, rear


def relay_holes_low():
    return [(P["relay_low_x"] + dx, dy) for dx in (-25.4, 25.4) for dy in (-66.1, 66.1)]


def conn_dims():
    c = P["conn"]
    dl, dw, dh = c["deans"]; bl, bw_, bh = c["bal"]; k, wl = c["clr"], c["wall"]
    W = max(dw, bw_) + 2 * k + 2 * wl                              # Breite (Y)
    L = max(dl, bl) + c["back"]                                     # Länge (X) ohne Laschen
    z1 = c["floor"] + dh + 2 * k                                    # Oberkante Deans-Tasche
    z2 = z1 + wl + bh + 2 * k                                       # Oberkante Balancer-Tasche
    H = z2 + wl
    yc = c["y0"] + W / 2
    return dict(W=W, L=L, H=H, z1=z1, z2=z2, yc=yc)


def conn_holder():
    """Steckerhalter (Platte-Koordinaten, steht auf Z_LT). Zwei übereinanderliegende Tunnel, offen nach -X."""
    c, d = P["conn"], conn_dims()
    x0, zt, yc = c["x_front"], Z_LT, d["yc"]
    dl, dw, dh = c["deans"]; bl, bw_, bh = c["bal"]; k = c["clr"]
    body = box(x0, c["y0"], zt, d["L"], d["W"], d["H"])
    fl = box(x0 - c["flange"], c["y0"] + d["W"] / 2 - 5.0, zt, d["L"] + 2 * c["flange"], 10.0, 3.0)   # Laschen
    pos = [body, fl]
    neg = [box(x0 - 1, yc - dw / 2 - k, zt + c["floor"], dl + 1, dw + 2 * k, dh + 2 * k),          # Deans-Tunnel
           box(x0 - 1, yc - bw_ / 2 - k, zt + d["z1"] + c["wall"], bl + 1, bw_ + 2 * k, bh + 2 * k)]  # Balancer-Tunnel
    sw, sh = c["slot"]
    neg.append(box(x0 + dl - 1, yc - sw / 2, zt + c["floor"] + (dh - sh) / 2, d["L"], sw, sh + 2 * k))   # Kabel Deans
    neg.append(box(x0 + bl - 1, yc - sw / 2, zt + d["z1"] + c["wall"], d["L"], sw, bh + 2 * k))          # Kabel Balancer
    for xh in c["holes"]:
        neg.append(cyl(xh, yc, zt - 1, P["m3_d"] / 2, 10))
    for xs in (x0 + 5.0, x0 + 12.0):                                 # Kabelbinder quer über beide Tunnel (2.5er)
        neg.append(box(xs - 1.5, c["y0"] - 1, zt + d["H"] - 1.4, 3.0, d["W"] + 2, 1.4))
    return cut(fuse(pos), neg)


def latch_bottom_neg():
    """V2.7: Bohrung, Schlitz nach hinten und Rastkerben für die Akku-Riegel in der unteren Platte.
    Keine Aufbauten: nach dem Ziehen der Stifte ist der Ausziehweg des Akkus frei."""
    L, zb, zt = P["lat"], Z_LB, Z_LT
    ri = L["d"] / 2 + L["clr"]
    kw, kr = L["lug_w"] + 2 * L["key_clr"], L["lug_r"] + L["key_clr"] + 0.2
    neg = []
    for y in L["ys"]:
        x = L["x"]
        neg.append(cyl(x, y, zb - 1, ri, P["t"] + 2))
        neg.append(rbox(x, y, 180.0, 0, -kw / 2, zb - 1, kr, kw, P["t"] + 2))               # Schlitz nach hinten
        for a in (90.0, 270.0):                                                              # Rastkerben (beide Drehrichtungen)
            neg.append(rbox(x, y, a, 0, -kw / 2, zt - L["notch"], kr, kw, L["notch"] + 1))
    # Rampe statt Stufe am hinteren Taschenende: Akku gleitet beim Herausziehen die 2 mm hoch
    pk, x0 = P["bat_pocket"], P["bat_x0"]
    if FC:
        w = P["bat_w"]
        pr = Part.makePolygon([V(x0 + 0.01, -w / 2, zt - pk), V(x0 - L["ramp"], -w / 2, zt + 0.01),
                               V(x0 + 0.01, -w / 2, zt + 0.01), V(x0 + 0.01, -w / 2, zt - pk)])
        neg.append(Part.Face(pr).extrude(V(0, w, 0)))
    return neg


def latch_top_neg(zb, t):
    """V2.7: Führungsbohrungen in der oberen Platte (Stiftende), unten angefast (Platte hinten wird kopfüber gedruckt)."""
    L = P["lat"]; ri = L["d"] / 2 + L["clr"]
    neg = []
    for y in L["ys"]:
        neg.append(cyl(L["x"], y, zb - 1, ri, t + 2))
        if FC:
            neg.append(Part.makeCone(ri + 1.5, ri, 1.5, V(L["x"], y, zb - 0.01)))
    return neg


def latch_pin(x=0.0, y=0.0, lock=90.0, world=True):
    """V2.7: Riegelstift. world=True: Einbaulage (Nase in der Kerbe bei Winkel lock), sonst Drucklage (Kopf auf z=0)."""
    L = P["lat"]
    zh = Z_LB - L["foam"]                                   # Oberseite Kopf
    zl = Z_LT - L["notch"]                                   # Unterseite Nase (liegt in der Kerbe der unteren Platte)
    if not world:
        x, y, dz = 0.0, 0.0, -(zh - L["head_h"])
    else:
        dz = 0.0
    r = L["d"] / 2
    head = cyl(x, y, zh - L["head_h"] + dz, L["head_d"] / 2, L["head_h"])
    shaft = cyl(x, y, zh - 0.01 + dz, r, Z_B + L["top"] - zh + 0.01)
    lug = rbox(x, y, lock, r - 0.5, -L["lug_w"] / 2, zl + dz, L["lug_r"] - r + 0.5, L["lug_w"], L["lug_h"])
    neg = []
    n = 16                                                   # Rändel
    for i in range(n):
        a = 360.0 * i / n
        neg.append(rbox(x, y, a, L["head_d"] / 2 - 0.8, -1.0, zh - L["head_h"] - 1 + dz, 2.0, 2.0, L["head_h"] + 2))
    neg.append(rbox(x, y, lock, -L["head_d"] / 2 - 1, -1.0, zh - L["head_h"] - 1 + dz, L["head_d"] + 2, 2.0, 1.8))   # Rille = Nasenrichtung
    return cut(fuse([head, shaft, lug]), neg)


def build_bottom():
    t, zb, zt = P["t"], Z_LB, Z_LT
    col_h = Z_B - zt                                   # Säule bis Unterseite obere Platte
    pos = [plate_outline(zb, t)]
    for sx, sy in P["standoffs"]:
        pos.append(cyl(sx, sy, zt - 0.5, P["col_d"] / 2, col_h + 0.5))
    for name, x, y, yaw in P["coxa"]:
        for hx, hy in P["srv_holes_bot"]:
            pos.append(rcyl(x, y, yaw, hx, hy, zt - 0.5, 2.5, P["boss_bot"] + 0.5))
    bx0, bx1, bw, rh = P["bat_x0"], P["bat_x1"], P["bat_w"], P["rail_h"]
    for y0 in (bw / 2, -bw / 2 - 3.0):
        pos.append(box(bx0, y0, zt - 0.5, bx1 - bx0, 3.0, rh + 0.5))          # Schienen
    pos.append(box(bx1, -bw / 2 - 3.0, zt - 0.5, 3.0, bw + 6.0, rh + 0.5))   # Anschlag vorn
    for hx, hy in relay_holes_low():
        pos.append(cyl(hx, hy, zt - 0.5, 3.5, P["relay_so"] + 0.5))
    neg = []
    for name, x, y, yaw in P["coxa"]:
        neg.append(sweep_2d(x, y, yaw, zb - 1, t + 2))
        px0, px1, py = P["plug"]
        neg.append(rbox(x, y, yaw, px0, -py, zb - 1, px1 - px0, 2 * py, t + 2))
        for hx, hy in P["srv_holes_bot"]:
            neg.append(rcyl(x, y, yaw, hx, hy, zb - 1, P["srv_hole_d"] / 2, t + P["boss_bot"] + 2))
            # Senkung von unten bis 1.5 mm unter die Bolzenoberkante (-33.2)
            neg.append(rcyl(x, y, yaw, hx, hy, zb - 1, P["cb_d"] / 2, (zt + P["boss_bot"] - P["cb_rest"]) - (zb - 1)))
    neg.append(box(bx0, -bw / 2, zt - P["bat_pocket"], bx1 - bx0, bw, P["bat_pocket"] + 1))
    for xs in P["bat_straps"]:
        for s in (-1, 1):
            neg.append(box(xs - 11, s * (bw / 2 + 5.5) - 1.5, zb - 1, 22, 3, t + 2))
    m0, m1, mw, mh = P["bms"]
    for xs in P["bms_straps"]:
        for s in (-1, 1):
            neg.append(box(xs - 11, s * (mw / 2 + 3.5) - 1.5, zb - 1, 22, 3, t + 2))
    for sx, sy in P["standoffs"]:
        neg.append(cyl(sx, sy, zb - 1, P["col_hole_d"] / 2, col_h + t + 2))
    for hx, hy in relay_holes_low():
        neg.append(cyl(hx, hy, zb - 1, P["relay_hole_d"] / 2, t + P["relay_so"] + 2))
    for sy in P["lap_screws"]:
        neg.append(cyl(P["split_x"], sy, zb - 1, 1.6, t + 2))
    for xh in P["conn"]["holes"]:                      # V2.6: Steckerhalter
        neg.append(cyl(xh, conn_dims()["yc"], zb - 1, P["m3_d"] / 2, t + 2))
    neg += latch_bottom_neg()                          # V2.7: Akku-Riegel
    plate = cut(fuse(pos), neg)
    front, rear = split(plate, zb, upper_front=False)   # Säulen stehen auf der oberen Stoßhälfte -> hinteres Teil
    return dict(plate=plate, front=front, rear=rear)


def payload_boxes():
    """Platzhalter Batterie und BMS (Welt)."""
    bx0, bx1, bw = P["bat_x0"], P["bat_x1"], P["bat_w"]
    m0, m1, mw, mh = P["bms"]
    return [("Battery_3S_9000", box(bx0 + 1, -25, Z_LT - P["bat_pocket"], 170, 50, P["bat_h"]), (0.85, 0.75, 0.1)),
            ("BMS_Daly_3S", box(m0, -mw / 2, Z_LT, m1 - m0, mw, mh), (0.2, 0.2, 0.8)),
            ("DCDC_5V_Fulree", dcdc_shape(), (0.75, 0.75, 0.78))] + \
           [("Modulplatz_" + n, box(x - P["mod_dx"] - 4, y - 12, Z_T, 2 * P["mod_dx"] + 8, 24, 0.6), (0.9, 0.2, 0.2))
            for n, x, y in P["mods"]]


def dcdc_shape():
    """Platzhalter Wandler: Gehäuse + Laschen mit offenen 4-mm-Schlitzen."""
    d = P["dcdc"]
    body = box(d["x"] - d["L"] / 2, d["y"] - d["W"] / 2, Z_T, d["L"], d["W"], d["H"])
    tabs = [box(d["x"] - d["tip"] / 2, d["y"] - d["tab_w"] / 2, Z_T, d["tip"], d["tab_w"], d["tab_t"])]
    slots = []
    for sx, sy in dcdc_screws():
        out = 1 if sx > d["x"] else -1
        slots += [cyl(sx, sy, Z_T - 1, 2.0, d["tab_t"] + 2),
                  box(min(sx, sx + out * 10), sy - 2.0, Z_T - 1, 10, 4.0, d["tab_t"] + 2)]
    return cut(fuse([body] + tabs), slots)


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
    rel_files = ("Relay_Module_-_8_Channel.STEP", "Relay Module - 8 Channel.STEP")
    if P["relay_on_top"]:
        out.append(("Relay8", rel_files, ((1, 0, 0, P["relay_x"]), (0, 0, -1, 0), (0, 1, 0, Z_T + P["relay_so"] + 2.13))))
    else:
        out.append(("Relay8", rel_files, mul(m_rz(90, P["relay_low_x"], 0, Z_LT + P["relay_so"] + 2.13),
                                              ((1, 0, 0, 0), (0, 0, -1, 0), (0, 1, 0, 0)))))
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
    doc = App.newDocument("SLARC_Baseplates")
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
    gb = build_bottom()
    add("Baseplate_Bottom_Front", gb["front"], (0.08, 0.08, 0.08))
    add("Baseplate_Bottom_Rear", gb["rear"], (0.12, 0.12, 0.12))
    for n, shp, col in payload_boxes():
        add(n, shp, col)
    add("Connector_Holder", conn_holder(), (0.08, 0.08, 0.08))      # V2.6
    for i, y in enumerate(P["lat"]["ys"]):                          # V2.7: Akku-Riegel (eingerastet, Nase nach außen)
        add("Battery_Latch_%d" % (i + 1), latch_pin(P["lat"]["x"], y, 90.0 if y > 0 else 270.0), (0.85, 0.35, 0.1))
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
    print("Baseplates erzeugt: je Vorder- + Hinterteil (Teilung bei x = %.0f)" % P["split_x"])


if FC:
    run_freecad()
