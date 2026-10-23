# -*- coding: utf-8 -*-
"""
SLARC – Rückenpanzer (Cover) über der oberen Baseplate.   V1.1
(V1.1: leichter – Wand 2.4 mm, Waben 9 mm / Steg 2.4 mm, Rautenfenster in den Seitenwänden, schmalere
 Zwischenspanten, hohle Säulen, Kamm 3 mm)
FreeCAD 0.21 / 1.0: Makro ausführen. Parameter in C (unten) ändern und neu ausführen.

Idee: Käfer-Rückenschild. Querschnitt = Satteldach mit Firstlinie (wie die Naht zwischen den Deckflügeln),
Seitenwände senkrecht, Draufsicht vorn breit und eckig (Halsschild über Pi/Treiber), hinten rund auslaufend.
Die Dachflächen und Seitenwände sind als Wabengitter durchbrochen, Firstband, Traufband und Spanten bleiben voll.

Aufgaben
- Schutz der Elektronik bei Stürzen: Last geht über die Dachflächen in 6 Säulen, die genau auf den
  Säulenpositionen der Baseplates stehen -> Kraftfluss Panzer -> Säule -> Platte -> Säule -> untere Platte.
- Selbstaufrichten: Auf dem Rücken liegt SLARC nur auf der schmalen Firstlinie, der Schwerpunkt liegt
  rund 100 mm darüber -> keine stabile Rückenlage, er kippt zur Seite auf eine Dachfläche (Dachneigung roof_a).
  Von dort drücken die Beine der oberen Seite den Körper weiter über die Traufkante. (In der Sim prüfen.)

Befestigung
- Die Säulen der Baseplates (M3) werden umgedreht: Schraube M3x50 (statt M3x45) von unten durch untere Platte,
  Säule und obere Platte (zusammen 42 mm) in einen Gewindeeinsatz M3 (Einschmelzmutter) unten in der Panzersäule.
  Gilt für die 6 Panzersäulen; die Säulen bei x = -40 und ohne Panzer: weiter M3x45 + Mutter.

Druck
- Zwei Teile, Teilung bei x = split_x (Spant mit 3x M3x12 + Mutter). Grundfläche aufs Bett, keine Stützen
  nötig: Dachneigung 40° (Überhang 50° – mit PETG und Lüfter machbar), Waben spitz zum First (selbsttragend),
  Seitenfenster spitzbogig. Firstband ist eine Brücke von max. Spantabstand -> Spanten alle span_dx.

Koordinaten wie slarc_baseplates_v2 (X vorn, Y links, Z oben, Z = 0 Oberkante Servo-Hüllmaß).
Die Unterkante des Panzers liegt auf der Plattenoberseite Z_T.
"""
import math

import FreeCAD as App
import Part

V = App.Vector

C = dict(
    Z_T=3.1,                 # Oberseite obere Baseplate (aus slarc_baseplates_v2: -pk + t)
    x_rear=-190.0, x_front=158.0,       # Länge (vorn endet der Panzer hinter dem Kamerahalter, x 164)
    xc=-15.0, w0=62.0,                  # Draufsicht: größte Halbbreite
    a_rear=175.0, n_rear=4.0,           # hinten Superellipse (rund)
    a_front=230.0, n_front=6.0,         # vorn fast eckig (Halsschild)
    roof_a=40.0,                        # Dachneigung [deg]
    ridge=[(-190.0, 34.0), (-170.0, 52.0), (-130.0, 66.0), (-60.0, 74.0), (20.0, 80.0), (90.0, 88.0), (158.0, 88.0)],
    t=2.4,                   # Wandstärke (V1.1: 3.0 -> 2.4, leichter)
    split_x=-15.0,           # Teilung (Spant mit Flansch)
    span_dx=[-160.0, -70.0, 83.0],   # nicht über DC-DC/Modulplätzen (x -147..-83)   # weitere Spanten (innen, volle Rippe)
    span_w=4.0, flange=8.0,  # Teilungs-/Frontspant: Breite (X), Flanschtiefe nach innen (trägt die Schrauben)
    rib_w=3.0, rib_flange=5.0,   # Zwischenspanten (V1.1: schmaler)
    posts=[(155.0, 35.0), (155.0, -35.0), (60.0, 45.0), (60.0, -45.0),
           (-125.0, 55.0), (-125.0, -55.0)],   # V1.1: 6 statt 8 (bei x -40 trägt der Teilungsspant)
    post_d=10.0, post_id=6.0, insert_d=4.0, insert_h=9.0,   # Gewindeeinsatz M3 (5.7 lang, 4.6 außen -> Bohrung 4.0); Bohrung tiefer für M3x50
    hex_r=9.0, rib=2.4,      # Waben: Umkreisradius, Stegbreite (V1.1: offener, 6.5/3.0 -> 9.0/2.4)
    band_ridge=6.0, band_eave=4.0,
    wall_r=7.0,              # Seitenwand-Rauten: max. halbe Breite
    crest_w=3.0, crest_h=5.0,           # Firstkamm (Naht der Deckflügel): Auflagelinie in Rückenlage
    port_win=(92.0, 140.0),             # großes Seitenfenster für die Pi-Anschlüsse (beidseitig)
    notch=[(-150.0, 16.0), (-95.0, 16.0), (-15.0, 0.0), (30.0, 18.0)],   # Kabeldurchlässe unten (x, Breite; 0 = aus)
    bolt_d=3.4,
)


# ============================================================ Grundform
def halfwidth(x):
    c = C
    if x < c["xc"]:
        u = min(1.0, abs(x - c["xc"]) / c["a_rear"]); n = c["n_rear"]
    else:
        u = min(1.0, abs(x - c["xc"]) / c["a_front"]); n = c["n_front"]
    return c["w0"] * max(0.0, 1.0 - u ** n) ** (1.0 / n)


def ridge(x):
    pts = C["ridge"]
    if x <= pts[0][0]:
        return pts[0][1]
    for (x0, h0), (x1, h1) in zip(pts, pts[1:]):
        if x <= x1:
            s = (x - x0) / (x1 - x0)
            s = s * s * (3 - 2 * s)            # weich
            return h0 + (h1 - h0) * s
    return pts[-1][1]


TAN = math.tan(math.radians(C["roof_a"]))


def section(x, off=0.0, zbot=0.0):
    """Querschnitt (y, z) relativ zur Plattenoberseite; off = Versatz nach innen (Wandstärke)."""
    w, H = halfwidth(x), ridge(x)
    ze = max(H - w * TAN, 2.0)
    if off:
        Hi = H - off / math.cos(math.radians(C["roof_a"]))
        wi = w - off
        zei = Hi - wi * TAN
        return [(-wi, zbot), (-wi, zei), (0.0, Hi), (wi, zei), (wi, zbot)]
    return [(-w, zbot), (-w, ze), (0.0, H), (w, ze), (w, zbot)]


def wire_at(x, off=0.0, zbot=0.0):
    pts = [V(x, y, C["Z_T"] + z) for y, z in section(x, off, zbot)]
    return Part.makePolygon(pts + [pts[0]])


def loft(x0, x1, n, off=0.0, zbot=0.0):
    """Geradlinige Loft (ruled) über Stationen, die zu den Enden hin dichter liegen (keine Überschwinger)."""
    xs = [x0 + (x1 - x0) * (1 - math.cos(math.pi * i / (n - 1))) / 2 for i in range(n)]
    return Part.makeLoft([wire_at(x, off, zbot) for x in xs], True, True)


def slab(x0, x1):
    return Part.makeBox(x1 - x0, 400, 300, V(x0, -200, C["Z_T"] - 50))


# ============================================================ Aufbau
def build():
    c = C
    xr, xf, t = c["x_rear"], c["x_front"], c["t"]
    outer = loft(xr + 0.5, xf, 64)
    inner = loft(xr + 0.5 + t + 2, xf + 1, 64, off=t, zbot=-1.0)
    shell = outer.cut(inner)
    skin = shell
    # 1) Waben + Fenster über die ganze Fläche schneiden
    shell = shell.cut(Part.makeCompound(roof_windows() + wall_windows() + notches()))
    # 2) danach Spanten, Säulen und Firstkamm einsetzen (laufen als Rippen über die Waben)
    inner2 = loft(xr + 4.0, xf + 1, 64, off=t + c["flange"], zbot=-1.0)   # Endflächen nicht deckungsgleich mit outer
    ring = outer.cut(inner2)
    sp = [slab(c["split_x"] - c["span_w"], c["split_x"] + c["span_w"]), slab(xf - c["span_w"], xf + 1)]
    ring3 = outer.cut(loft(xr + 4.0, xf + 1, 64, off=t + c["rib_flange"], zbot=-1.0))
    ribs = [ring3.common(slab(x - c["rib_w"] / 2, x + c["rib_w"] / 2)) for x in c["span_dx"]]
    posts = [Part.makeCylinder(c["post_d"] / 2, 200, V(px, py, c["Z_T"])).common(outer) for px, py in c["posts"]]
    pads = [Part.makeCylinder(c["post_d"] / 2 + 5.0, 300, V(px, py, c["Z_T"] - 1)).common(skin) for px, py in c["posts"]]
    shell = shell.fuse([ring.common(s) for s in sp] + ribs + posts + pads + [crest()])   # Dachhaut um jede Säule bleibt geschlossen
    # 3) Gewindeeinsätze unten in den Säulen, darüber hohl (Rohr), oben bleibt das Dach geschlossen
    neg = [Part.makeCylinder(c["insert_d"] / 2, c["insert_h"], V(px, py, c["Z_T"] - 1)) for px, py in c["posts"]]
    inner_t = loft(xr + 0.5 + t + 2, xf - 2, 64, off=t + 1.5, zbot=-1.0)   # Rohr endet 1.5 mm unter der Dachinnenseite
    for px, py in c["posts"]:
        z0 = c["Z_T"] + c["insert_h"] + 2
        neg.append(Part.makeCylinder(c["post_id"] / 2, 200, V(px, py, z0)).common(inner_t))
    shell = shell.cut(Part.makeCompound(neg)).removeSplitter()
    # Teilungsspant: 3 Schrauben M3 entlang X (First, beide Traufen)
    bolts = []
    xs = c["split_x"]
    for y, z in bolt_points(xs):
        bolts.append(Part.makeCylinder(c["bolt_d"] / 2, 30, V(xs - 15, y, c["Z_T"] + z), V(1, 0, 0)))
    shell = shell.cut(Part.makeCompound(bolts))
    front = shell.common(slab(xs, 400)).removeSplitter()
    rear = shell.common(slab(-400, xs)).removeSplitter()
    return dict(shell=shell, front=front, rear=rear, outer=outer)


def crest():
    """Kamm auf der Firstlinie: senkrechte Rippe, folgt ridge(x)."""
    c = C
    xs = [c["x_rear"] + 8 + i * (c["x_front"] - c["x_rear"] - 10) / 60 for i in range(61)]
    top = [V(x, 0, c["Z_T"] + ridge(x) + c["crest_h"]) for x in xs]
    bot = [V(x, 0, c["Z_T"] + ridge(x) - 3) for x in reversed(xs)]
    f = Part.Face(Part.makePolygon(top + bot + [top[0]]))
    s = f.extrude(V(0, c["crest_w"], 0)); s.translate(V(0, -c["crest_w"] / 2, 0))
    return s


def bolt_points(x):
    w, H = halfwidth(x), ridge(x)
    t, f = C["t"], C["flange"]
    d = t + f / 2                                   # Mitte des Flansches
    zr = H - d / math.cos(math.radians(C["roof_a"]))
    ze = H - w * TAN
    return [(0.0, zr - 3.0), (w - d, ze * 0.55), (-(w - d), ze * 0.55)]


def keep_out_x(x, r):
    c = C
    xs = [c["split_x"]] + c["span_dx"]
    if x - r < c["x_rear"] + 14 or x + r > c["x_front"] - c["span_w"] - 3:
        return True
    return False                       # Spanten/Säulen werden nach dem Wabenschnitt eingesetzt


def hexagon(cx, cy, r, axis="z", z0=0.0, h=1.0, pointy="y"):
    """Sechseck-Prisma. pointy: Achse der Spitzen ('y' für Dachwaben, 'z' für Wandfenster)."""
    pts = []
    for k in range(6):
        a = math.radians(90 + 60 * k)
        u, v = r * math.cos(a), r * math.sin(a)    # v = Spitzenrichtung
        pts.append((u, v))
    if axis == "z":
        P = [V(cx + u, cy + v, z0) for u, v in pts]
        d = V(0, 0, h)
    else:                                           # Prisma entlang Y, Spitzen in Z
        P = [V(cx + u, z0, cy + v) for u, v in pts]
        d = V(0, h, 0)
    f = Part.Face(Part.makePolygon(P + [P[0]]))
    return f.extrude(d)


def roof_windows():
    c = C
    r, rib = c["hex_r"], c["rib"]
    dx = math.sqrt(3) * r + rib                     # Spalten (X)
    dy = 1.5 * (r + rib / math.sqrt(3))             # Reihen (Y)
    out = []
    j = 0
    y = c["band_ridge"] + r
    rows = []
    while y < c["w0"]:
        rows.append(y); y += dy
    for j, yy in enumerate(rows):
        for sgn in (1, -1):
            x = c["x_rear"] + (dx / 2 if j % 2 else 0.0)
            while x < c["x_front"]:
                ok = not keep_out_x(x, math.sqrt(3) / 2 * r)
                cy = sgn * yy
                if ok:                                  # alle 6 Ecken innerhalb der Dachfläche (Traufband frei)
                    for k in range(6):
                        a = math.radians(90 + 60 * k)
                        xe, ye = x + r * math.cos(a), abs(cy + r * math.sin(a))
                        if ye > halfwidth(xe) - c["t"] - c["band_eave"] or ye < c["band_ridge"]:
                            ok = False
                if ok:
                    out.append(hexagon(x, cy, r, "z", c["Z_T"] + 1.0, 250))
                x += dx
    return out


def ywin(sgn, w):
    """Y-Start eines 14 mm langen Schnittprismas, das nur die Seitenwand (Dicke t) durchtrennt."""
    return w - 8.0 if sgn > 0 else -w - 6.0


def wall_windows():
    """Seitenwände: steile Rauten (V1.1, druckbar ohne Stützen) + große Pi-Anschlussfenster."""
    c = C
    out = []
    x = c["x_rear"] + 16
    while x < c["x_front"] - 10:
        w, H = halfwidth(x), ridge(x)
        ze = H - w * TAN
        z0, z1 = c["Z_T"] + 4.0, c["Z_T"] + ze - 3.0         # Fußband 4 mm, Traufband 3 mm
        h = z1 - z0
        b = min(0.5 * h, c["wall_r"] * 2)
        inport = c["port_win"][0] - b < x < c["port_win"][1] + b
        if h >= 10 and not keep_out_x(x, b / 2) and not inport:
            for sgn in (1, -1):
                yb = ywin(sgn, w)
                P = [V(x - b / 2, yb, (z0 + z1) / 2), V(x, yb, z0), V(x + b / 2, yb, (z0 + z1) / 2), V(x, yb, z1)]
                out.append(Part.Face(Part.makePolygon(P + [P[0]])).extrude(V(0, 14, 0)))
        x += b + c["rib"] + 0.4 if h >= 10 else 4.0
    # Pi-Anschlussfenster: Rechteck mit Spitzbogen oben
    x0, x1 = c["port_win"]
    for sgn in (1, -1):
        w = min(halfwidth(x0), halfwidth(x1)); ze = ridge((x0 + x1) / 2) - halfwidth((x0 + x1) / 2) * TAN
        z0, z1 = c["Z_T"] + 3.0, c["Z_T"] + ze - 4.0
        yb = ywin(sgn, w)
        box = Part.makeBox(x1 - x0, 14, z1 - z0 - (x1 - x0) / 2 * 0.6, V(x0, yb, z0))
        zt = z0 + (z1 - z0 - (x1 - x0) / 2 * 0.6)
        tri = Part.Face(Part.makePolygon([V(x0, yb, zt), V(x1, yb, zt), V((x0 + x1) / 2, yb, z1), V(x0, yb, zt)])).extrude(V(0, 14, 0))
        out += [box, tri]
    return out


def notches():
    """Kabeldurchlässe unten in den Seitenwänden (spitzbogig)."""
    out = []
    for x, wd in C["notch"]:
        if wd <= 0:
            continue
        for sgn in (1, -1):
            w = halfwidth(x)
            yb = ywin(sgn, w)
            z0 = C["Z_T"] - 1
            h = 9.0
            box = Part.makeBox(wd, 14, h + 1, V(x - wd / 2, yb, z0))
            tri = Part.Face(Part.makePolygon([V(x - wd / 2, yb, z0 + h + 1), V(x + wd / 2, yb, z0 + h + 1),
                                              V(x, yb, z0 + h + 1 + wd * 0.5), V(x - wd / 2, yb, z0 + h + 1)])).extrude(V(0, 14, 0))
            out += [box, tri]
    return out


def run_freecad():
    doc = App.ActiveDocument if App.ActiveDocument and App.ActiveDocument.Name.startswith("SLARC") else App.newDocument("SLARC_Cover")
    g = build()
    for n, s in (("Cover_Front", g["front"]), ("Cover_Rear", g["rear"])):
        o = doc.addObject("Part::Feature", n); o.Shape = s
        if App.GuiUp:
            o.ViewObject.ShapeColor = (0.08, 0.08, 0.08)
    doc.recompute()
    if App.GuiUp:
        import FreeCADGui as Gui
        Gui.activeDocument().activeView().viewIsometric(); Gui.SendMsgToActiveView("ViewFit")
    print("Panzer erzeugt: vorn %.0f cm3, hinten %.0f cm3" % (g["front"].Volume / 1000, g["rear"].Volume / 1000))
    return g


if __name__ != "__slarc_lib__":
    run_freecad()
