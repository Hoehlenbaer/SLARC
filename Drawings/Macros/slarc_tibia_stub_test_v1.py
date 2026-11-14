# -*- coding: utf-8 -*-
"""
SLARC – Tibia-Endstück als Testteil (Schaltertasche, Anschlusskammer, Nuten für die Fuß-Gleithülse).   V1.0
FreeCAD 0.21 / 1.0 – Makro ausführen oder:
    exec(open(r"PFAD/slarc_tibia_stub_test_v1.py", encoding="utf-8").read())

Zweck (14.11.2026)
- Fuß-Gleithülse und Schalter testen, ohne die ganze Tibia neu zu drucken. Marcos Tibia hat noch die
  Schaltertasche vor V9.7 (Pins stoßen an), und in der Nut können Stützreste sitzen.
- Baut das Bein-Makro (slarc_leg_freecad_v9.py, gleicher Ordner), nimmt Tibia_Part, legt das Fußsegment
  entlang +X und schneidet ab CUT_X (Abstand ab Knickmitte, wie XV/XS/XE im Bein-Makro) ab.
- Druckausrichtung wie die Tibia (Gelenkachse senkrecht), aber das Segment liegt hier mit der Unterseite
  direkt auf dem Bett: die untere Nut ist ein offener Schlitz am Bett, keine Stützen nötig.
  In der ganzen Tibia liegt diese Seite frei über dem Bett (Baumstützen) - Unterschied beim Test beachten.
- Ergebnis: Objekt "Tibia_Stub" (Ursprung: Schnittfläche bei x = 0, Unterseite z = 0).
"""
import os
import FreeCAD as App
import Part

CUT_X = 89.5       # Schnitt ab Knickmitte; Hohlraum endet bei XV = 89 -> Endstück massiv

_here = os.path.dirname(os.path.abspath(__file__))
_leg = os.path.join(_here, "slarc_leg_freecad_v9.py")
exec(compile(open(_leg, encoding="utf-8").read(), _leg, "exec"), {"__name__": "__slarc_sub__", "__file__": _leg})

d = App.ActiveDocument
sh = d.getObject("Params")
bend = float(sh.get("tib_bend"))
tib_a = float(sh.get("tib_a"))
s = d.getObject("Tibia_Part").Shape.copy()
s.rotate(App.Vector(tib_a, 0, 0), App.Vector(0, 0, 1), -bend)       # Fußsegment entlang +X
bb = s.BoundBox
cut = Part.makeBox(bb.XMax - (tib_a + CUT_X) + 1, bb.YLength + 2, bb.ZLength + 2,
                   App.Vector(tib_a + CUT_X, bb.YMin - 1, bb.ZMin - 1))
stub = s.common(cut).removeSplitter()
sb = stub.BoundBox
stub.translate(App.Vector(-sb.XMin, -(sb.YMin + sb.YMax) / 2, -sb.ZMin))
o = d.addObject("Part::Feature", "Tibia_Stub")
o.Shape = stub
d.recompute()
sb = stub.BoundBox
print("Tibia_Stub: %.1f x %.1f x %.1f mm, %.2f cm3" % (sb.XLength, sb.YLength, sb.ZLength, stub.Volume / 1000))
