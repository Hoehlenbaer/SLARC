# -*- coding: utf-8 -*-
"""
SLARC – Gleithülse PETG mit Federzungen für den zweiteiligen Fuß (Testreihe).   V1.2
FreeCAD 0.21 / 1.0 – Makro ausführen oder:
    exec(open(r"PFAD/slarc_foot_slider_test_v1.py", encoding="utf-8").read())

V1.2 (14.11.2026)
- Hülse 0.4 gleitet und rastet, aber der Weg im eingerasteten Zustand ist sehr klein (< 0.2 mm statt 1.2).
  Eine Änderung nach der anderen: Spiel fest 0.4, Innenlänge (Stirnwand bis Öffnung = Lage der Haken)
  29.6 / 30.0 / 30.4. Längere Hülse -> Haken weiter zum Knie -> mehr Weg bis zur fußseitigen Nutwand,
  aber weniger Luft zur knieseitigen Nutwand beim Anschlag. Beschriftung = Innenlänge.
- Stößel sitzt nicht mittig, sondern ca. 1.9 mm außermittig entlang der 28-mm-Richtung (X) (Marco gemessen).
  Je nachdem, wie herum Schalter und Hülse sitzen, liegt er bei X = +1.9 oder -1.9: zwei Schraublöcher bei
  ±SCR_X, gemeinsame Langsenkung. Benutzt wird das Loch über dem Stößel, das andere bleibt leer.

V1.1 (14.11.2026)
- Statt Gewindeeinsatz + Madenschraube: Zylinderschraube M3x6 (vorhanden, ISO 4762) direkt in PETG geschnitten
  (Kernloch SCR_D), Kopf in einer Senkung von außen. Der Kopf liegt nicht auf, die Schraube hält durch die
  Reibung im selbst geschnittenen Gewinde. Stirnwand 8 statt 6 mm, damit der Kopf versenkt bleibt.

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
- Schaltpunkt einstellbar: Zylinderschraube M3x6 von außen durch die Stirnwand, direkt ins PETG geschnitten.
  Das Schraubenende drückt durch die offene Schaltertasche auf den Stößel. Überstand innen = 6 - SCR_WALL -
  Kopfabstand zum Senkungsgrund, also 0 bis 3.5 mm. Einstellen: Hülse auf Anschlag drücken, Schraube eindrehen,
  bis der Schalter klickt, dann ca. 1/8 Umdrehung weiter (0.06 mm).
- Testreihe: VARIANTS (Spiel, Innenlänge), Innenlänge vertieft auf einer 28-mm-Seite (V1.0/V1.1: Spiel).

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
# V1.2: Varianten (Spiel je Seite, Innenlänge). V1.1: Spiel 0.2/0.3/0.4 bei 30.0 -> 0.4 gleitet gut.
VARIANTS = [(0.4, 29.6), (0.4, 30.0), (0.4, 30.4)]
WALL = 1.6         # Wand (4 Linien)
END_T = 8.0        # V1.1: Stirnwand (Senkung für den Kopf + Gewindewand)
SCR_D = 2.8        # V1.1: Kernloch M3 im Modell (PETG-Bohrungen ca. 0.12 je Seite enger -> ca. 2.55)
SCR_WALL = 2.5     # V1.1: Gewindewand innen (Schraube M3x6 greift hier)
CB_D = 6.5         # V1.1: Senkung für den Zylinderkopf Ø5.5 x 3
SCR_X = 1.9        # V1.2: Stößel außermittig (sw_po im Bein-Makro) -> Löcher bei X = ±SCR_X
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


def slider(c, inner_l=INNER_L):
    ix, iy = LINK_H + 2 * c, LINK_W + 2 * c
    ox, oy = ix + 2 * WALL, iy + 2 * WALL
    h = END_T + inner_l
    s = box(-ox / 2, -oy / 2, 0, ox, oy, h).cut(box(-ix / 2, -iy / 2, END_T, ix, iy, h))
    # V1.1: Schraube mittig (über dem Stößel): Kernloch durch, Kopfsenkung von außen (Bettseite)
    cbh = END_T - SCR_WALL + 0.5
    for sx in (1, -1):                                          # V1.2: zwei Löcher über den Stößellagen
        s = s.cut(Part.makeCylinder(SCR_D / 2, END_T + 1, V(sx * SCR_X, 0, -0.5)))
        s = s.cut(Part.makeCylinder(CB_D / 2, cbh, V(sx * SCR_X, 0, -0.5)))
    s = s.cut(box(-SCR_X, -CB_D / 2, -0.5, 2 * SCR_X, CB_D, cbh))
    # Zungen: U-Schlitze in den beiden x-Wänden
    for sx in (1, -1):
        x0 = ix / 2 - 0.1 if sx > 0 else -ox / 2 - 0.1
        for y in (TONGUE_W / 2, -TONGUE_W / 2 - SLOT):
            s = s.cut(box(x0, y, h - TONGUE_L, WALL + 0.2, SLOT, TONGUE_L + 1))
        s = s.fuse(hook(sx, c, iy, h))
    t = text_cut("%.1f" % inner_l, oy / 2, END_T + 9)          # V1.2: Innenlänge
    if t is not None:
        s = s.cut(t)
    return s.removeSplitter()


doc = App.newDocument("SLARC_Foot_Slider_Test")
parts = []
for i, (c, il) in enumerate(VARIANTS):
    p = slider(c, il)
    p.translate(V((i - (len(VARIANTS) - 1) / 2) * PITCH, 0, 0))
    o = doc.addObject("Part::Feature", "Slider_%02d_L%03d" % (int(round(c * 100)), int(round(il * 10))))
    o.Shape = p
    parts.append(p)
allp = doc.addObject("Part::Feature", "Foot_Slider_Test")
allp.Shape = Part.makeCompound(parts)
doc.recompute()
print("Gleithülsen erzeugt (Spiel, Innenlänge):", VARIANTS, "| Schrift:", FONT or "keine")
try:
    import FreeCADGui as Gui
    if Gui.ActiveDocument:
        for o in doc.Objects:
            if o.Name.startswith("Slider_"):
                o.Visibility = False
        Gui.SendMsgToActiveView("ViewFit")
except Exception:
    pass
