# -*- coding: utf-8 -*-
# SLARC – Gesamtmodell headless exportieren (ein STL je sichtbarem Teil + manifest.json mit Farbkategorie).
# Aufruf: freecadcmd export_assembly.py   (FreeCAD 1.0+, dauert einige Minuten)
import FreeCAD as App, Mesh, json, os
f=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "Drawings", "Macros", "slarc_assembly_v1.py")
exec(compile(open(f).read(),f,"exec"),{"__name__":"x","__file__":f})
d=App.getDocument("SLARC")
OUT=os.path.join(os.path.dirname(os.path.abspath(__file__)), "parts") + os.sep
os.makedirs(OUT,exist_ok=True)
SKIP=("Leg_Test_Stand","Body_Mount")
legs=[o for o in d.Objects if o.Label.startswith("Leg_")]
masters=[o for o in legs if o.TypeId=="App::Part"]
links=[o for o in legs if o.TypeId=="App::Link"]
def leaves(o):
    out=[]
    for c in getattr(o,"Group",[]):
        if c.TypeId=="App::Part": out+=leaves(c)
        elif c.Visibility and hasattr(c,"Shape") and not c.Shape.isNull(): out.append(c)
    return out
inleg=set()
for m in masters:
    for c in leaves(m): inleg.add(c.Name)
manifest=[]
def dump(name, shape, pl, cat):
    s = shape.copy(); s.Placement = pl
    m = Mesh.Mesh(); m.addFacets(s.tessellate(0.15))
    m.write(OUT + name + ".stl"); manifest.append({"file": name + ".stl", "cat": cat})
def cat_of(n):
    for k,c in (("ST3215","servo"),("Deco","deco"),("Foot_TPU","foot"),("Microswitch","switch"),("PCB_","pcb"),("RaspberryPi","pi"),
                ("GeneralDriver","pcb"),("Relay","pcb"),("IMX296","pcb"),("Lens","lens"),("Battery_Latch","accent"),("Power_Button","accent"),
                ("Cover","cover"),("Battery","battery"),("BMS","pcb"),("DCDC","pcb")):
        if k in n: return c
    return "print"
cnt=0
# Beine: Master in eigener Lage, Links über Link-Placement
for m in masters:
    for c in leaves(m):
        gp=c.getGlobalPlacement()
        s=c.Shape.copy(); s.Placement=gp
        dump("%s__%s"%(m.Label,c.Name), s, gp, cat_of(c.Name)); cnt+=1
for lk in links:
    mst=lk.LinkedObject
    for c in leaves(mst):
        gp=lk.Placement.multiply(mst.Placement.inverse()).multiply(c.getGlobalPlacement())
        s=c.Shape.copy(); s.Placement=gp
        dump("%s__%s"%(lk.Label,c.Name), s, gp, cat_of(c.Name)); cnt+=1
for o in d.Objects:
    if o.Name in inleg or o in legs or any(o.Name.startswith(k) or o.Label.startswith(k) for k in SKIP): continue
    if o.TypeId in ("App::Part","App::Link","Spreadsheet::Sheet","App::Origin","App::Line","App::Plane","App::DocumentObjectGroup"): continue
    if o.InList: continue          # nur Wurzel-Features
    if not getattr(o,"Visibility",True) or not hasattr(o,"Shape") or o.Shape.isNull(): continue
    dump(o.Name, o.Shape.copy(), o.Shape.Placement, cat_of(o.Name)); cnt+=1
json.dump(manifest,open(OUT+"manifest.json","w"),indent=0)
print("exported",cnt)
from collections import Counter; print(Counter(m["cat"] for m in manifest))
