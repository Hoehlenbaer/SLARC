# -*- coding: utf-8 -*-
"""
SLARC – Gleithülse PETG mit Federzungen für den zweiteiligen Fuß (Testreihe).   V1.0
FreeCAD 0.21 / 1.0 – Makro ausführen oder:
    exec(open(r"PFAD/slarc_foot_slider_test_v1.py", encoding="utf-8").read())

Hintergrund (14.11.2026)
- Der einteilige TPU-Fuß hat zwei Probleme: Gleitpassung TPU auf PETG streut stark, und der innere Anschlag
  ist eine TPU-Brücke (ungleichmäßig, Tibiaspitze schlägt an, Fuß kann nicht mehr gleiten).
- Neues Konzept, zweiteilig: starre Gleithülse aus PETG auf dem Tibia-Ende, darüber später ein TPU-Überzug
  (Kugel, Griff, Dämpfung), der keine Präzision mehr braucht.

Gleithülse
- Gedruckt mit der geschlossenen Stirnwand auf dem Bett: die innere Anschlagfläche liegt auf massivem Material,
  ohne Brücke und eben. Anschlag = Tibia-Stirnfläche (XE im Bein-Makro).
- Halt ohne neue Tibia: zwei Federzungen (U-Schlitze) auf den 20-mm-Seiten, an der Spitze je ein starrer Haken,
  der in die vorhandene Nut der Tibia greift (Nut 1.0 tief, 2.9 lang). Haken ragt HOOK_P über die Tibia;
  Weg zwischen Anschlag und Haken an der Nutwand ca. 1.2 mm (wie TPU-Fuß).
- Schaltpunkt einstellbar: Gewindeeinsatz M3 (5.7 lang, Ø4.6, wie Panzersäulen) in der Stirnwand, von außen
  eingeschmolzen; Madenschraube M3x8 drückt durch die offene Schaltertasche auf den Stößel. Einstellen:
  Hülse auf Anschlag drücken, Schraube eindrehen bis der Schalter klickt, dann ca. 1/8 Umdrehung weiter.
- Testreihe: Spiel CLEAR je Seite, Wert vertieft auf einer 28-mm-Seite.

Maße aus slarc_leg_freecad_v9.py (dort ändern, hier nachziehen): link_w, link_h, foot_trav, lip_w, Nut.
Koordinaten: Z = Druckrichtung (Z=0 Bett = Außenseite Stirnwand), X = link_h-Richtung (Haken), Y = link_w.
"""
import os
import FreeCAD as App
import Part

V = App.Vector

# --- Werte aus dem Bein-Makro V9 ---
LINK_W = 20.0      # Glied quer zur Gelenkachse
LINK_H = 28.0      # Glied entlang der Gelenkachse; Nuten auf den beiden 20-mm-Seiten (x = ±LINK_H/2)
INNER_L = 30.0     # Stirnwand innen bis Öffnung (= boot_l): Haken liegt bei Anschlag 0.2 mm in der Nut

# --- Hülse ---
CLEAR = [0.2, 0.3, 0.4]   # Gleitspiel je Seite (PETG-Bohrungen werden je Seite ca. 0.12 enger)
WALL = 1.6         # Wand (4 Linien)
END_T = 6.0        # Stirnwand (Gewindeeinsatz 5.7 lang)
INS_D = 4.0        # Bohrung Gewindeeinsatz M3 Ø4.6 (Einschmelzen)
HOOK_W = 1.5       # Haken axial (= lip_w)
HOOK_P = 0.6       # Haken über Tibia-Oberfläche (Nut 1.0 tief -> 0.4 Luft am Nutgrund)
HOOK_CH = 0.6      # Einführschräge 45° an der Öffnungsseite des Hakens
TONGUE_W = 12.0    # Zungenbreite
TONGUE_L = 14.0    # Zungenlänge ab Öffnung
SLOT = 0.8         # Schlitzbreite
TXT_H, TXT_D = 5.0, 0.4   # Beschriftung vertieft
PITCH = 40.0

FONTS = [r"C:/Windows/Fonts/arialbd.ttf", r"C:/Windows/Fonts/arial.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
         "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
         "/Library/Fonts/Arial Bold.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"]
FONT = next((f for f in FONTS if os.path.exists(f)), None)


def box(x0, y0, z0, lx, ly, lz):
    return Part.makeBox(lx, ly, lz, V(x0, y0, z0))


def hook(sx, c, iy, z_top):
    """Haken an der Innenseite der Zunge bei x = sx*ix/2: Profil in X-Z, über die Zungenbreite extrudiert.
    Unterseite flach (Rastfläche zur Stirnwand hin), Oberseite 45° (Einführschräge)."""
    ix2 = LINK_H / 2 + c                      # Innenfläche der Hülse
    p = c + HOOK_P                            # Überstand ab Innenfläche
    z0 = z_top - HOOK_W
    pts = [(ix2, z0), (ix2 - p, z0), (ix2 - p, z_top - HOOK_CH), (ix2 - c, z_top), (ix2, z_top), (ix2, z0)]
    pts = [V(sx * x, -TONGUE_W / 2, z) for x, z in pts]
    face = Part.Face(Part.makePolygon(pts))
    return face.extrude(V(0, TONGUE_W, 0))


def text_cut(text, y_face, cz):
    """Vertiefte Zahl auf der 28-mm-Seite (y = y_face), Mitte bei z = cz."""
    if not FONT:
        return None
    try:
        chars = Part.makeWireString(text, FONT, TXT_H, 0)
        faces = [Part.Face(Part.Shape(ch), "Part::FaceMakerBullseye") for ch in chars if ch]
        t = faces[0]
        for f in faces[1:]:
            t = t.fuse(f)
        t = t.extrude(V(0, 0, TXT_D + 0.2))        # in der XY-Ebene, dann aufstellen
        bb = t.BoundBox
        t.translate(V(-(bb.XMin + bb.XMax) / 2, -(bb.YMin + bb.YMax) / 2, 0))
        t.rotate(V(0, 0, 0), V(1, 0, 0), -90)     # Text steht in der XZ-Ebene, Tiefe in +Y
        t.translate(V(0, y_face - TXT_D, cz))
        return t
    except Exception as e:
        print("Schrift nicht möglich (%s)" % e)
        return None


def slider(c):
    ix, iy = LINK_H + 2 * c, LINK_W + 2 * c
    ox, oy = ix + 2 * WALL, iy + 2 * WALL
    h = END_T + INNER_L
    s = box(-ox / 2, -oy / 2, 0, ox, oy, h).cut(box(-ix / 2, -iy / 2, END_T, ix, iy, h))
    # Gewindeeinsatz mittig (über dem Stößel), durch die Stirnwand
    s = s.cut(Part.makeCylinder(INS_D / 2, END_T + 1, V(0, 0, -0.5)))
    # Zungen: U-Schlitze in den beiden x-Wänden
    for sx in (1, -1):
        x0 = ix / 2 - 0.1 if sx > 0 else -ox / 2 - 0.1
        for y in (TONGUE_W / 2, -TONGUE_W / 2 - SLOT):
            s = s.cut(box(x0, y, h - TONGUE_L, WALL + 0.2, SLOT, TONGUE_L + 1))
        s = s.fuse(hook(sx, c, iy, h))
    t = text_cut("%.1f" % c, oy / 2, END_T + 9)
    if t is not None:
        s = s.cut(t)
    return s.removeSplitter()


doc = App.newDocument("SLARC_Foot_Slider_Test")
parts = []
for i, c in enumerate(CLEAR):
    p = slider(c)
    p.translate(V((i - (len(CLEAR) - 1) / 2) * PITCH, 0, 0))
    o = doc.addObject("Part::Feature", "Slider_%02d" % int(round(c * 100)))
    o.Shape = p
    parts.append(p)
allp = doc.addObject("Part::Feature", "Foot_Slider_Test")
allp.Shape = Part.makeCompound(parts)
doc.recompute()
print("Gleithülsen erzeugt: Spiel", CLEAR, "| Schrift:", FONT or "keine")
try:
    import FreeCADGui as Gui
    if Gui.ActiveDocument:
        for o in doc.Objects:
            if o.Name.startswith("Slider_"):
                o.Visibility = False
        Gui.SendMsgToActiveView("ViewFit")
except Exception:
    pass
