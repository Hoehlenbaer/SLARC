# -*- coding: utf-8 -*-
"""
SLARC – Passungsringe für den TPU-Fuß (Gleitspiel auf der Tibia).   V1.1
FreeCAD 0.21 / 1.0 – Makro ausführen oder:
    exec(open(r"PFAD/slarc_foot_fit_test_v1.py", encoding="utf-8").read())

V1.1 (13.11.2026)
- Lippenüberstand wie Bein V9.9: lip_p 0.5 statt 0.8 (Nut 1.0 tief). Erkennbar am Punkt rechts auf der Lasche. Reihe 0.5–0.8, um zu prüfen, ob die
  kürzere Lippe das Haften beseitigt. V1.0 (Lippe 0.8, Spiel 0.3–1.0): alle Ringe hafteten gleich.

Zweck
- Der erste TPU-Fuß (slide_c 0.3) ist zu eng zum Gleiten (Marco, 13.11.2026: innen ca. 20.2 x 28 statt
  20.6 x 28.6). Statt jedes Mal den ganzen Fuß zu drucken: kurze Viereck-Ringe mit dem Hülsenquerschnitt
  des Fußes und mit der gestuften Rastlippe, Gleitspiel slide_c gestuft. Alle Ringe auf einem Druck.
- Ring = Abschnitt der Fußhülse ab der Öffnung: Wand boot_t, Lippen wie im Bein-Makro V9 (an den beiden
  20-mm-Seiten, halbe Höhe an der Öffnung als Einführschräge, dann volle Höhe). Die Lippe ragt immer
  lip_h über die Tibia-Oberfläche hinaus, unabhängig vom Spiel (wie im Fuß).
- Druck wie der Fuß: Öffnung (Lippenseite) auf dem Bett, ohne Stützen.
- Markierung: Lasche außen am Ring mit dem Spiel als erhabener Zahl ("0.5" = slide_c 0.5 mm je Seite).
  Ohne Schriftdatei stattdessen Punkte: Anzahl = Nummer der Variante (1 = kleinstes Spiel).

Test: Ring von der Fußspitze her auf die Tibia schieben, bis die Lippen in die Nuten schnappen.
Der passende Ring gleitet leicht und ohne Wackeln über die 1 mm Federweg und rastet sicher.
Das Spiel dieses Rings kommt als slide_c ins Bein-Makro.

Maße aus slarc_leg_freecad_v9.py (dort ändern, hier nachziehen): link_w, link_h, boot_t, lip_w, lip_p.
Koordinaten: Z = Druckrichtung (Z=0 Bett = Öffnung), X = link_h-Richtung, Y = link_w-Richtung.
"""
import os
import FreeCAD as App
import Part

V = App.Vector

# --- Werte aus dem Bein-Makro V9 ---
LINK_W = 20.0      # Glied quer zur Gelenkachse (Lippen an diesen Seiten)
LINK_H = 28.0      # Glied entlang der Gelenkachse
BOOT_T = 2.0       # Wand der Fußhülse
LIP_W = 1.5        # Lippe axial (halb gestuft)
LIP_H = 0.5        # V1.1: Lippe über Tibia-Oberfläche = lip_p im Bein-Makro (Nut ist 1.0 tief)

# --- Testreihe ---
CLEAR = [0.5, 0.6, 0.7, 0.8]   # V1.1: slide_c je Seite (V1.0: 0.3–1.0 mit Lippe 0.8)
RING_H = 8.0       # Ringhöhe (axial)
COLS = 4           # Anordnung auf dem Bett
PITCH_X = 46.0     # Raster
PITCH_Y = 40.0
TAB_L, TAB_W, TAB_T = 15.0, 8.0, 1.2      # Beschriftungslasche (flach auf dem Bett)
TXT_H, TXT_T = 5.0, 0.6                   # Schrifthöhe, erhabene Höhe

FONTS = [r"C:/Windows/Fonts/arialbd.ttf", r"C:/Windows/Fonts/arial.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
         "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
         "/Library/Fonts/Arial Bold.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"]
FONT = next((f for f in FONTS if os.path.exists(f)), None)


def box(x0, y0, z0, lx, ly, lz):
    return Part.makeBox(lx, ly, lz, V(x0, y0, z0))


def number(text, cx, cy):
    """Zahl zentriert bei (cx, cy) auf Höhe TAB_T, Leserichtung entlang X."""
    if not FONT:
        return None
    try:
        chars = Part.makeWireString(text, FONT, TXT_H, 0)
        faces = [Part.Face(Part.Shape(ch), "Part::FaceMakerBullseye") for ch in chars if ch]
        if not faces:
            return None
        t = faces[0]
        for f in faces[1:]:
            t = t.fuse(f)
        t = t.extrude(V(0, 0, TXT_T))
        bb = t.BoundBox
        t.translate(V(cx - (bb.XMin + bb.XMax) / 2, cy - (bb.YMin + bb.YMax) / 2, TAB_T))
        return t
    except Exception as e:
        print("Schrift nicht möglich (%s), Punkte statt Zahl" % e)
        return None


def dots(n, cx, cy):
    out = []
    for i in range(n):
        c = Part.makeCylinder(0.9, TXT_T, V(cx - (n - 1) * 1.25 + i * 2.5, cy, TAB_T))
        out.append(c)
    return out


def ring(c, idx):
    """Ring für Spiel c, Mitte im Ursprung. Liefert Solid."""
    ix, iy = LINK_H + 2 * c, LINK_W + 2 * c          # innen
    ox, oy = ix + 2 * BOOT_T, iy + 2 * BOOT_T        # außen
    r = box(-ox / 2, -oy / 2, 0, ox, oy, RING_H).cut(box(-ix / 2, -iy / 2, -1, ix, iy, RING_H + 2))
    # Rastlippen an den beiden 20-mm-Seiten (x = ±ix/2), über die ganze Innenbreite
    for sx in (1, -1):
        for z0, hh in ((0.0, LIP_H / 2), (LIP_W / 2, LIP_H)):
            p = hh + c                                   # Überstand ab Hülsen-Innenfläche
            x0 = ix / 2 - p if sx > 0 else -ix / 2
            r = r.fuse(box(x0, -iy / 2, z0, p, iy, LIP_W / 2))
    # Lasche außen an einer 28-mm-Seite (y+), flach auf dem Bett
    tab = box(-TAB_L / 2, oy / 2 - 0.5, 0, TAB_L, TAB_W + 0.5, TAB_T)
    r = r.fuse(tab)
    cy = oy / 2 + TAB_W / 2
    t = number("%.1f" % c, 0, cy)
    for d in ([t] if t is not None else dots(idx + 1, 0, cy)):
        r = r.fuse(d)
    # V1.1: Punkt am Laschenende unterscheidet die Reihe mit Lippe 0.5 von V1.0 (Lippe 0.8, ohne Punkt)
    r = r.fuse(Part.makeCylinder(0.9, TXT_T, V(TAB_L / 2 - 1.6, cy, TAB_T)))
    return r.removeSplitter()


def build():
    shapes = []
    for i, c in enumerate(CLEAR):
        s = ring(c, i)
        rows = (len(CLEAR) + COLS - 1) // COLS
        s.translate(V((i % COLS - (COLS - 1) / 2) * PITCH_X, -(i // COLS - (rows - 1) / 2) * PITCH_Y, 0))
        shapes.append(s)
    return shapes


doc = App.newDocument("SLARC_Foot_Fit_Rings")
rings = build()
for i, (c, s) in enumerate(zip(CLEAR, rings)):
    o = doc.addObject("Part::Feature", "Ring_%02d" % int(round(c * 100)))
    o.Shape = s
all_ = doc.addObject("Part::Feature", "Foot_Fit_Rings")
all_.Shape = Part.makeCompound(rings)
doc.recompute()
print("Passungsringe erzeugt: slide_c", CLEAR, "| Schrift:", FONT or "keine (Punkte)")
try:
    import FreeCADGui as Gui
    if Gui.ActiveDocument:
        for o in doc.Objects:
            if o.Name.startswith("Ring_"):
                o.Visibility = False
        Gui.SendMsgToActiveView("ViewFit")
except Exception:
    pass
