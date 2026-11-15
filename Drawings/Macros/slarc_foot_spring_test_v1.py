# -*- coding: utf-8 -*-
"""
SLARC – Fuß-Hülse mit Federzungen, Stiften und Schaltschraube (Testreihe).   V1.0
FreeCAD 0.21 / 1.0 – Makro ausführen oder:
    exec(open(r"PFAD/slarc_foot_spring_test_v1.py", encoding="utf-8").read())

Konzept (Marco, 15.11.2026), passend zum Bein-Makro V9.11
- Gleitpassungen klemmen (TPU und PETG, auch 30.4/0.4). Daher großes Spiel CLEAR je Seite: die Hülse berührt
  die Tibia nur an den Federnocken und den Stiften.
- Rückstellung + Zentrierung: vier Federzungen (Wurzel oben, freies Ende am Hülsenboden), innen je eine Nocke,
  deren obere 45°-Flanke auf einer 45°-Fase der Tibia-Spitze (Pyramidenstumpf) liegt. Drückt der Fuß ein,
  biegt die Fase die Zunge nach außen; die Zunge schiebt die Hülse über die Schräge zurück.
  Vorspannung in Ruhe PRE, am Anschlag PRE + PIN_TRAV (seitlich = axial bei 45°).
- Verliersicherung + Anschlag: zwei Zylinderschrauben M3x10 in Einschmelzbuchsen (M3, 5.7 lang, Ø4.6) in Augen
  auf den 28-mm-Seiten; die Spitzen laufen in den Langlöchern der Tibia (pin_x, pin_trav). Ruhe: Federn
  drücken den Stift ans fußseitige Ende; Anschlag: Stift am knieseitigen Ende, Boden noch GAP_P vor der Stirn.
- Schaltpunkt: Zylinderschraube M3x6 direkt ins PETG über dem Stößel (1.9 außermittig, Kerbe = Stößelseite).
  Schalter mit dem Stößel zur Oberseite der Tibia (oben beim Druck) einsetzen, Hülse mit der Kerbe dorthin.
- Druck: Stirnwand auf dem Bett, ohne Stützen (Nocken mit 45°-Unterseite, Augen mit 45°-Unterseite).
  Die Zungen hängen unten frei; damit ihre erste Schicht nicht in der Luft liegt, tragen je zwei dünne
  Druckstege (POST_W breit) das freie Ende über dem Spalt. NACH DEM DRUCK MIT DEM SEITENSCHNEIDER ENTFERNEN.
  An der Wurzel geht die Zunge mit 45° in die volle Wanddicke über (kein Überhang).
- Testreihe: Zungendicke TONGUE_T, Wert vertieft auf der +Y-Seite neben der Zunge.

Federkraft grob (E_PETG ~2000 MPa, Biegebalken, ohne Reibung), Zungen 8 breit:
  t 0.8: Ruhe ca. 0.5 N, Anschlag ca. 3 N (Summe der 4 Zungen, seitlich ~ axial bei 45°)
  t 1.0: etwa doppelt so viel. Biegedehnung am Anschlag < 1.2 %.

Koordinaten: Z = Druckrichtung (Z = 0 Bett = Außenseite Stirnwand), h = Z - END_T (ab Hülsenboden innen),
X = Gelenkachsrichtung der Tibia (28-mm-Seite, Stößel bei +X), Y = 20-mm-Richtung der Tibia.
Maße aus slarc_leg_freecad_v9.py (dort ändern, hier nachziehen): link_w, link_h, roof_p, tip_zc, pin_x,
pin_trav, XE (= foot_seg - foot_r - foot_trav).
"""
import os
import FreeCAD as App
import Part

V = App.Vector

# --- Werte aus dem Bein-Makro V9.11 ---
LINK_W = 20.0      # Y
LINK_H = 28.0      # X
ROOF_P = 4.0       # Fasen auf den 28-mm-Seiten ab |y| = ROOF_P
TIP_ZC = 11.0      # Fasen auf den 20-mm-Seiten ab |x| = TIP_ZC
XE = 123.0         # Tibia-Stirn ab Knickmitte
PIN_X = 96.0       # Langloch-Mitte ab Knickmitte
PIN_TRAV = 1.5     # Weg

# --- Hülse ---
TONGUE_T = [0.8, 1.0]      # Testreihe: Zungendicke
CLEAR = 1.0        # Spiel je Seite
WALL = 1.6
END_T = 8.0        # Stirnwand
INNER_L = 33.0     # Hülsenboden bis Öffnung
GAP_P = 0.5        # Boden vor der Tibia-Stirn am Anschlag (Stift trägt, nicht der Boden)
PRE = 0.3          # Vorspannung der Federn in Ruhe
TW = 8.0           # Zungenbreite
TL_Y, TL_X = 15.0, 18.0    # Zungenlänge auf den 28- bzw. 20-mm-Seiten (Y-Seite kürzer wegen Auge)
T_FREE = 0.8       # Spalt unter dem freien Zungenende
SLOT = 0.6         # Schlitzbreite seitlich
POST_W = 1.0       # Druckstege unter dem freien Zungenende (nach dem Druck abknipsen)
NOSE_Y = 7.5       # Nockenspitze |y| (28-mm-Seiten)
NOSE_X = 12.5      # Nockenspitze |x| (20-mm-Seiten)
# Schaltschraube
SCR_X, SCR_D, SCR_WALL, CB_D = 1.9, 2.8, 2.5, 6.5
# Augen für die Stifte
BOSS_W = 9.0       # Breite (X) und Höhe des Auges
BOSS_Y = 18.0      # Außenfläche (Kopfauflage M3x10 -> Spitze bei |y| = 8, Langlochgrund 7.5)
INS_D, INS_L = 4.0, 6.0    # Einschmelzbuchse M3 Ø4.6 x 5.7
PIN_HOLE = 3.4
TXT_H, TXT_D = 5.0, 0.4
PITCH = 46.0

H_PIN = (XE + GAP_P) - (PIN_X - PIN_TRAV / 2)     # Stiftmitte über dem Boden (Anschlag) = 28.25

FONTS = [r"C:/Windows/Fonts/arialbd.ttf", r"C:/Windows/Fonts/arial.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
         "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
         "/Library/Fonts/Arial Bold.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"]
FONT = next((f for f in FONTS if os.path.exists(f)), None)


def box(x0, y0, z0, lx, ly, lz):
    return Part.makeBox(lx, ly, lz, V(x0, y0, z0))


def prism_yz(pts, x0, lx):
    """Polygon in der Y-Z-Ebene, entlang X extrudiert."""
    w = Part.makePolygon([V(x0, y, z) for y, z in pts] + [V(x0, pts[0][0], pts[0][1])])
    return Part.Face(w).extrude(V(lx, 0, 0))


def prism_xz(pts, y0, ly):
    """Polygon in der X-Z-Ebene, entlang Y extrudiert."""
    w = Part.makePolygon([V(x, y0, z) for x, z in pts] + [V(pts[0][0], y0, pts[0][1])])
    return Part.Face(w).extrude(V(0, ly, 0))


def text_cut(text, y_face, cx, cz):
    if not FONT:
        return None
    try:
        chars = Part.makeWireString(text, FONT, TXT_H, 0)
        faces = [Part.Face(Part.Shape(ch), "Part::FaceMakerBullseye") for ch in chars if ch]
        t = faces[0]
        for f in faces[1:]:
            t = t.fuse(f)
        t = t.extrude(V(0, 0, TXT_D + 0.2))
        bb = t.BoundBox
        t.translate(V(-(bb.XMin + bb.XMax) / 2, -(bb.YMin + bb.YMax) / 2, 0))
        t.rotate(V(0, 0, 0), V(1, 0, 0), -90)
        t.translate(V(cx, y_face - TXT_D, cz))
        return t
    except Exception as e:
        print("Schrift nicht möglich (%s)" % e)
        return None


def sleeve(t):
    ix, iy = LINK_H / 2 + CLEAR, LINK_W / 2 + CLEAR          # 15, 11 (halbe Innenmaße)
    ox, oy = ix + WALL, iy + WALL
    h_open = END_T + INNER_L
    s = box(-ox, -oy, 0, 2 * ox, 2 * oy, h_open).cut(box(-ix, -iy, END_T, 2 * ix, 2 * iy, h_open))
    z0 = END_T                                                # Hülsenboden innen

    # Augen für die Stifte (±Y), Unterseite 45° zur Wand hin
    zp = z0 + H_PIN
    for sy in (1, -1):
        pts = [(iy, zp + BOSS_W / 2), (BOSS_Y, zp + BOSS_W / 2), (BOSS_Y, zp - BOSS_W / 2),
               (iy, zp - BOSS_W / 2 - (BOSS_Y - iy))]
        pts = [(sy * y, z) for y, z in pts]
        s = s.fuse(prism_yz(pts, -BOSS_W / 2, BOSS_W))
    for sy in (1, -1):
        ax = V(0, -sy, 0)
        s = s.cut(Part.makeCylinder(INS_D / 2, INS_L, V(0, sy * BOSS_Y, zp), ax))
        s = s.cut(Part.makeCylinder(PIN_HOLE / 2, BOSS_Y - iy + 1, V(0, sy * BOSS_Y, zp), ax))

    # Federzungen: Wand im Zungenbereich weg, Zunge (Dicke t, innen bündig) wieder rein, Nocke dran
    for side, tl in (("Y", TL_Y), ("X", TL_X)):
        for sg in (1, -1):
            top = z0 + T_FREE + tl
            if side == "Y":
                s = s.cut(box(-TW / 2 - SLOT, iy - 0.1 if sg > 0 else -oy - 0.1, z0, TW + 2 * SLOT, WALL + 0.2,
                              T_FREE + tl))
                y0 = iy if sg > 0 else -iy - t
                s = s.fuse(box(-TW / 2, y0, z0 + T_FREE, TW, t, tl))
                for px in (-TW / 2, TW / 2 - POST_W):                   # Druckstege
                    s = s.fuse(box(px, y0, z0 - 0.1, POST_W, t, T_FREE + 0.2))
                d = WALL - t                                            # 45°-Übergang an der Wurzel
                ramp = [(iy + t, top - d), (iy + WALL + 0.01, top + 0.01), (iy + t, top + 0.01)]
                s = s.fuse(prism_yz([(sg * y, z) for y, z in ramp], -TW / 2, TW))
                # Nocke: obere Flanke y - h = (ROOF_P - GAP_P - PIN_TRAV) - PRE, Unterseite 45°, Spitze 0.6
                k = ROOF_P - GAP_P - PIN_TRAV - PRE
                ht = NOSE_Y - k
                pts = [(iy, z0 + ht - 0.6 - (iy - NOSE_Y)), (NOSE_Y, z0 + ht - 0.6), (NOSE_Y, z0 + ht),
                       (iy, z0 + ht + (iy - NOSE_Y))]
                s = s.fuse(prism_yz([(sg * y, z) for y, z in pts], -TW / 2, TW))
            else:
                s = s.cut(box(ix - 0.1 if sg > 0 else -ox - 0.1, -TW / 2 - SLOT, z0, WALL + 0.2, TW + 2 * SLOT,
                              T_FREE + tl))
                x0 = ix if sg > 0 else -ix - t
                s = s.fuse(box(x0, -TW / 2, z0 + T_FREE, t, TW, tl))
                for py in (-TW / 2, TW / 2 - POST_W):                   # Druckstege
                    s = s.fuse(box(x0, py, z0 - 0.1, t, POST_W, T_FREE + 0.2))
                d = WALL - t
                ramp = [(ix + t, top - d), (ix + WALL + 0.01, top + 0.01), (ix + t, top + 0.01)]
                s = s.fuse(prism_xz([(sg * x, z) for x, z in ramp], -TW / 2, TW))
                k = TIP_ZC - GAP_P - PIN_TRAV - PRE
                ht = NOSE_X - k
                pts = [(ix, z0 + ht - 0.3 - (ix - NOSE_X)), (NOSE_X, z0 + ht - 0.3), (NOSE_X, z0 + ht),
                       (ix, z0 + ht + (ix - NOSE_X))]
                s = s.fuse(prism_xz([(sg * x, z) for x, z in pts], -TW / 2, TW))

    # Schaltschraube über dem Stößel (+X), Kopf versenkt; Kerbe außen auf der +X-Seite unten
    s = s.cut(Part.makeCylinder(SCR_D / 2, END_T + 1, V(SCR_X, 0, -0.5)))
    s = s.cut(Part.makeCylinder(CB_D / 2, END_T - SCR_WALL + 0.5, V(SCR_X, 0, -0.5)))
    s = s.cut(box(ox - 0.5, -0.4 - TW, 1.0, 1.0, 0.8, 6.0))
    t_ = text_cut("%.1f" % t, oy, -10.5, z0 + 8)
    if t_ is not None:
        s = s.cut(t_)
    return s.removeSplitter()


doc = App.newDocument("SLARC_Foot_Spring_Test")
parts = []
for i, t in enumerate(TONGUE_T):
    p = sleeve(t)
    p.translate(V((i - (len(TONGUE_T) - 1) / 2) * PITCH, 0, 0))
    o = doc.addObject("Part::Feature", "Sleeve_T%02d" % int(round(t * 10)))
    o.Shape = p
    parts.append(p)
allp = doc.addObject("Part::Feature", "Foot_Spring_Test")
allp.Shape = Part.makeCompound(parts)
doc.recompute()
print("Federhülsen erzeugt: Zungendicke", TONGUE_T, "| Stifthöhe %.2f | Schrift:" % H_PIN, FONT or "keine")
try:
    import FreeCADGui as Gui
    if Gui.ActiveDocument:
        for o in doc.Objects:
            if o.Name.startswith("Sleeve_"):
                o.Visibility = False
        Gui.SendMsgToActiveView("ViewFit")
except Exception:
    pass
