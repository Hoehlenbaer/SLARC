# -*- coding: utf-8 -*-
"""
SLARC – Gesamtmodell: beide bestückten Baseplates + sechs Beine.   V1
FreeCAD 0.21 / 1.0 – Makro ausführen.

Benötigt im selben Ordner (oder MACRO_DIR):
    slarc_baseplates_v2.py, slarc_leg_freecad_vN.py (neueste Version wird automatisch genommen)
STEP-Modelle (ST3215, Pi 5, Treiber, Relais, IMX296) werden in STEP_DIR gesucht
(leer = Makro-Ordner).

Ablauf: Die beiden Makros werden in EIN Dokument "SLARC" ausgeführt, die doppelten Coxa-Servos der
Baseplate und die Coxa-Aufnahme des Einzelbeins (Body_Mount) werden entfernt bzw. ausgeblendet, dann
werden die Beine an die Coxa-Positionen aus slarc_sim_V10 gesetzt.

LEG_MODE
  "links"        – ein Bein (Spreadsheet "Params") + 5 App::Links. Schnell; alle Beine haben dieselbe Pose.
  "independent"  – sechs vollständige Beine mit eigenem Spreadsheet P_FR, P_FL, ... -> Gelenkwinkel je Bein
                   einzeln einstellbar (POSES unten oder später im Spreadsheet). Dauert deutlich länger.
MIRROR_LEFT = True: die linken Beine (FL, ML, RL) werden gespiegelt gebaut (Bein-Makro ab V9, Option MIRROR).
Im Modus "links" entstehen dafür zwei Master-Beine (FR rechts, FL links gespiegelt), die übrigen sind Verknüpfungen.
Beide teilen das Spreadsheet "Params" – die Pose ist spiegelbildlich gleich.
"""
import os
import re
import FreeCAD as App

MACRO_DIR = r""          # leer = Ordner dieses Makros bzw. FreeCAD-Makro-Ordner
STEP_DIR = r""           # leer = MACRO_DIR
LEG_MODE = "links"       # "links" oder "independent"
MIRROR_LEFT = True       # linke Beine gespiegelt (benötigt Bein-Makro >= V9)
COVER = True             # Rückenpanzer (slarc_cover_v1.py) mit einsetzen, falls vorhanden
LEG_FILE = ""            # leer = neueste slarc_leg_freecad_vN.py im Makro-Ordner (z.B. v8), sonst Dateiname

COXA = [("FR", 200.0, -75.0, -30.0), ("FL", 200.0, 75.0, 30.0),
        ("MR", 0.0, -115.0, -90.0), ("ML", 0.0, 115.0, 90.0),
        ("RR", -200.0, -75.0, -150.0), ("RL", -200.0, 75.0, 150.0)]
# Nur LEG_MODE "independent": (q_coxa, q_femur, q_tibia) je Bein; None = Default aus dem Bein-Makro
POSES = {"FR": None, "FL": None, "MR": None, "ML": None, "RR": None, "RL": None}

V = App.Vector


def _dir():
    if MACRO_DIR:
        return MACRO_DIR
    try:
        return os.path.dirname(os.path.abspath(__file__))
    except NameError:
        return App.getUserMacroDir(True)


MDIR = _dir()
SDIR = STEP_DIR or MDIR
BASE_SRC = os.path.join(MDIR, "slarc_baseplates_v2.py")
def _newest_leg():
    import glob
    cands = glob.glob(os.path.join(MDIR, "slarc_leg_freecad_v*.py"))
    def ver(p):
        m = re.search(r"_v(\d+)\.py$", p)
        return int(m.group(1)) if m else -1
    cands = [c for c in cands if ver(c) >= 0]
    return max(cands, key=ver) if cands else os.path.join(MDIR, "slarc_leg_freecad_v8.py")


LEG_SRC = LEG_FILE and os.path.join(MDIR, LEG_FILE) or _newest_leg()
print("Bein-Makro:", os.path.basename(LEG_SRC))
for p in (BASE_SRC, LEG_SRC):
    if not os.path.isfile(p):
        raise FileNotFoundError("Makro fehlt: " + p)

asm = App.newDocument("SLARC")
_orig_new = App.newDocument
App.newDocument = lambda *a, **k: asm          # Untermakros bauen in dieses Dokument


def _run(path, replace=()):
    src = open(path, encoding="utf-8").read()
    for a, b in replace:
        if a not in src:
            raise RuntimeError("Ersetzung nicht gefunden in %s: %s" % (os.path.basename(path), a))
        src = src.replace(a, b)
    ns = {"__name__": "__slarc_sub__", "__file__": path}
    exec(compile(src, path, "exec"), ns)
    return ns


try:
    # ------------------------------------------------ Baseplates (inkl. Elektronik, Kamera, Batterie)
    _run(BASE_SRC, [('STEP_DIR = r""', 'STEP_DIR = r"%s"' % SDIR)])
    for n, *_ in COXA:                      # Coxa-Servos kommen mit den Beinen
        o = asm.getObject("ST3215_" + n)
        if o:
            asm.removeObject(o.Name)

    # ------------------------------------------------ Beine
    step_rep = ('SERVO_STEP = r""', 'SERVO_STEP = r"%s"' % os.path.join(SDIR, "ST3215.step"))
    legs = []
    def mir_rep(n, y):
        if MIRROR_LEFT and y > 0:
            return [("MIRROR = False", "MIRROR = True")]
        return []

    if LEG_MODE == "independent":
        for n, x, y, yaw in COXA:
            sh = "P_" + n
            ns = _run(LEG_SRC, mir_rep(n, y) + [step_rep,
                                ('"Params." + m.group(1)', '"%s." + m.group(1)' % sh),
                                ('addObject("Spreadsheet::Sheet", "Params")', 'addObject("Spreadsheet::Sheet", "%s")' % sh)])
            leg = ns["leg"]; leg.Label = "Leg_" + n
            if POSES.get(n):
                s = asm.getObject(sh)
                for alias, val in zip(("q_coxa", "q_femur", "q_tibia"), POSES[n]):
                    s.set(alias, str(val))
            legs.append(leg)
    else:
        masters = {}
        for n, x, y, yaw in COXA:
            side = "L" if (MIRROR_LEFT and y > 0) else "R"
            if side not in masters:
                ns = _run(LEG_SRC, mir_rep(n, y) + [step_rep])
                masters[side] = ns["leg"]; ns["leg"].Label = "Leg_" + n
                legs.append(ns["leg"])
            else:
                lk = asm.addObject("App::Link", "Leg_" + n)
                lk.LinkedObject = masters[side]
                legs.append(lk)
    COVER_SRC = os.path.join(MDIR, "slarc_cover_v1.py")
    if COVER and os.path.isfile(COVER_SRC):
        App.setActiveDocument(asm.Name)
        _run(COVER_SRC)
finally:
    App.newDocument = _orig_new

# Body_Mount (Coxa-Aufnahme des Einzelbein-Modells) wird durch die Baseplates ersetzt
for o in asm.Objects:
    if o.Name.startswith("Body_Mount"):
        o.Visibility = False
        if App.GuiUp:
            o.ViewObject.Visibility = False

for leg, (n, x, y, yaw) in zip(legs, COXA):
    leg.Placement = App.Placement(V(x, y, 0), App.Rotation(V(0, 0, 1), yaw))

asm.recompute()
if App.GuiUp:
    import FreeCADGui as Gui
    Gui.activeDocument().activeView().viewIsometric()
    Gui.SendMsgToActiveView("ViewFit")
print("SLARC-Gesamtmodell erzeugt (%s). Gelenkwinkel: Spreadsheet %s"
      % (LEG_MODE, "Params (alle Beine)" if LEG_MODE == "links" else "P_FR ... P_RL"))
