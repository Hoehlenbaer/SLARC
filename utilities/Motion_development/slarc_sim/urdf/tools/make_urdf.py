import FreeCAD as App, Part, Mesh, MeshPart, math, json, os, traceback
OUT = "/tmp/claude-0/urdf/slarc_urdf"
os.makedirs(OUT + "/meshes", exist_ok=True)
log = open("/tmp/claude-0/run/make_urdf.txt", "w")
def w(s): log.write(s + "\n"); log.flush()
V = App.Vector
try:
    d = App.openDocument("/home/claude/slarc/Drawings/Macros/SLARC.FCStd")
    sheets = [o for o in d.Objects if o.TypeId == "Spreadsheet::Sheet"]
    for s in sheets:
        for k in ("q_coxa", "q_femur", "q_tibia"):
            s.set(k, "0")
        s.recompute()
    for o in d.Objects: o.touch()
    d.recompute(None, True, True)
    S = sheets[0]
    P = {k: float(S.get(k).Value if hasattr(S.get(k), "Value") else S.get(k)) for k in
         ("coxa_len", "femur_len", "tibia_len", "tib_bend", "foot_seg", "foot_r", "zc", "tib_a", "tib_delta", "link_w", "link_h")}
    w("params %s" % P)
    zc = P["zc"]
    FEM = V(P["coxa_len"], 0, zc)
    TIB = V(P["coxa_len"] + P["femur_len"], 0, zc)
    b = math.radians(P["tib_bend"]); rc = P["foot_seg"] - P["foot_r"]
    BALL_T = V(P["tib_a"] + rc * math.cos(b), 0, -rc * math.sin(b))       # Kugelmitte im Tibia-Frame
    TIP_T = V(P["tib_a"] + P["foot_seg"] * math.cos(b), 0, -P["foot_seg"] * math.sin(b))
    FOOT = TIB + BALL_T

    RHO = {"petg": 1.27 * 0.8, "pla": 1.24 * 1.0, "tpu": 1.21 * 0.8}      # g/cm3 effektiv (gedruckt)
    SERVO_G = 55.0

    def top(o):
        p = o.getParentGeoFeatureGroup()
        while p is not None and p.getParentGeoFeatureGroup() is not None:
            p = p.getParentGeoFeatureGroup()
        return p

    def chain(o):
        n = []; p = o.getParentGeoFeatureGroup()
        while p is not None:
            n.append(p.Name.rstrip("0123456789")); p = p.getParentGeoFeatureGroup()
        return n

    LEAF = {"Coxa_Part": "petg", "Femur_Part": "petg", "Tibia_Part": "petg", "Foot_TPU": "tpu", "Microswitch": "sw",
            "ST3215_Coxa": "servo", "ST3215_Femur": "servo", "ST3215_Tibia": "servo",
            "Deco_Femur_A": "pla", "Deco_Femur_B": "pla", "Deco_Tibia_A": "pla", "Deco_Tibia_B": "pla"}

    # --------------------------------------------------- Massen-Hilfen
    def box_props(bb, m):
        c = V((bb.XMin + bb.XMax) / 2, (bb.YMin + bb.YMax) / 2, (bb.ZMin + bb.ZMax) / 2)
        a, bq, cc = bb.XLength, bb.YLength, bb.ZLength
        I = [[m * (bq * bq + cc * cc) / 12, 0, 0], [0, m * (a * a + cc * cc) / 12, 0], [0, 0, m * (a * a + bq * bq) / 12]]
        return m, c, I

    def solid_props(sh, rho):
        """Masse [g], Schwerpunkt [mm], Trägheit um den Schwerpunkt [g mm2]."""
        sols = sh.Solids
        M = 0; C = V(); parts = []
        for s in sols:
            m = s.Volume / 1000 * rho
            parts.append((m, s.CenterOfMass, s.MatrixOfInertia, s.Volume))
            M += m; C += s.CenterOfMass * m
        C = C * (1 / M)
        I = [[0] * 3 for _ in range(3)]
        for m, c, Mi, vol in parts:
            k = m / vol           # MatrixOfInertia gilt für Dichte 1 (Volumen-Einheit)
            A = [[Mi.A11, Mi.A12, Mi.A13], [Mi.A21, Mi.A22, Mi.A23], [Mi.A31, Mi.A32, Mi.A33]]
            r = c - C; rr = [r.x, r.y, r.z]
            for i in range(3):
                for j in range(3):
                    I[i][j] += k * A[i][j] + m * ((r.Length ** 2 if i == j else 0) - rr[i] * rr[j])
        return M, C, I

    def combine(items):
        M = sum(m for m, c, I in items); C = V()
        for m, c, I in items: C += c * m
        C = C * (1 / M); T = [[0] * 3 for _ in range(3)]
        for m, c, I in items:
            r = c - C; rr = [r.x, r.y, r.z]
            for i in range(3):
                for j in range(3):
                    T[i][j] += I[i][j] + m * ((r.Length ** 2 if i == j else 0) - rr[i] * rr[j])
        return M, C, T

    def gshape(o):
        s = o.Shape.copy(); s.Placement = o.getGlobalPlacement(); return s

    def export(shapes, fname, origin):
        comp = Part.makeCompound([s.copy() for s in shapes]); comp.translate(-origin)
        m = MeshPart.meshFromShape(Shape=comp, LinearDeflection=0.4, AngularDeflection=0.5)
        m.write(OUT + "/meshes/" + fname)
        return m.CountFacets

    # --------------------------------------------------- Beine (rechts = Leg, links = Leg001 gespiegelt)
    legs = {"R": d.getObject("Leg"), "L": d.getObject("Leg001")}
    LINKS = {}
    coxa_servo_local = None
    for side, L in legs.items():
        inv = L.Placement.inverse()
        groups = {"coxa": [], "femur": [], "tibia": [], "foot": [], "base": []}
        for o in d.Objects:
            base = o.Name.rstrip("0123456789")
            if base not in LEAF or top(o) is not L:
                continue
            ch = chain(o)
            sh = o.Shape.copy(); sh.Placement = inv.multiply(o.getGlobalPlacement())
            kind = LEAF[base]
            if "J3_Tibia" in ch:
                g = "foot" if base == "Foot_TPU" else "tibia"
            elif "J2_Femur" in ch:
                g = "femur"
            elif "J1_Coxa" in ch:
                g = "coxa"
            else:
                g = "base"
            groups[g].append((base, kind, sh))
        origins = {"coxa": V(), "femur": FEM, "tibia": TIB, "foot": FOOT}
        for g in ("coxa", "femur", "tibia", "foot"):
            items = []
            for base, kind, sh in groups[g]:
                if kind == "servo":
                    items.append(box_props(sh.BoundBox, SERVO_G))
                elif kind == "sw":
                    items.append(box_props(sh.BoundBox, 2.0))
                else:
                    items.append(solid_props(sh, RHO[kind]))
            M, C, I = combine(items)
            C = C - origins[g]
            nf = export([sh for _, _, sh in groups[g]], "%s_%s.stl" % (g, side), origins[g])
            bb = Part.makeCompound([sh for _, _, sh in groups[g]]).BoundBox
            bb_local = [bb.XMin - origins[g].x, bb.XMax - origins[g].x, bb.YMin - origins[g].y, bb.YMax - origins[g].y,
                        bb.ZMin - origins[g].z, bb.ZMax - origins[g].z]
            LINKS[(g, side)] = dict(m=M, c=[C.x, C.y, C.z], I=I, bb=bb_local, facets=nf,
                                    parts=[b0 for b0, _, _ in groups[g]])
            w("%s %s: %.1f g CoM %s parts %s facets %d" % (g, side, M, [round(v, 1) for v in (C.x, C.y, C.z)],
                                                           LINKS[(g, side)]["parts"], nf))
        if side == "R":
            coxa_servo_local = groups["base"]

    # --------------------------------------------------- Rumpf
    items = []; vis = []
    def add_solid(n, rho):
        o = d.getObject(n); sh = gshape(o); items.append(solid_props(sh, rho)); vis.append(sh)
    for n in ("Baseplate_Top_Front", "Baseplate_Top_Rear", "Baseplate_Bottom_Front", "Baseplate_Bottom_Rear", "Stereo_Mount"):
        add_solid(n, 1.27 * 0.85)
    for n in ("Cover_Front", "Cover_Rear"):
        add_solid(n, 1.27 * 0.9)
    BOXM = {"Battery_3S_9000": 600, "BMS_Daly_3S": 60, "DCDC_5V_Fulree": 40, "RaspberryPi5": 120, "GeneralDriver": 60,
            "Relay8": 90, "IMX296_L": 15, "IMX296_R": 15, "Modulplatz_MCP": 10, "Modulplatz_MUX": 10}
    for n, m in BOXM.items():
        o = d.getObject(n); sh = gshape(o); bb = sh.BoundBox
        if n == "RaspberryPi5":     # Pi + HAT + Kühler: Hülle bis 30 mm über Platte
            bb = App.BoundBox(bb.XMin, bb.YMin, bb.ZMin, bb.XMax, bb.YMax, 3.1 + 33)
        items.append(box_props(bb, m)); vis.append(sh)
    # Coxa-Servos (6x, aus der Beinlage in den Rumpf)
    for o in d.Objects:
        if o.TypeId in ("App::Part", "App::Link") and o.Label.startswith("Leg_"):
            pl = o.Placement
            for base, kind, sh in coxa_servo_local:
                s2 = sh.copy(); s2.Placement = pl.multiply(s2.Placement)
                items.append(box_props(s2.BoundBox, SERVO_G)); vis.append(s2)
    items.append(box_props(App.BoundBox(-190, -70, -35, 190, 70, 0), 200))   # Kabel, Schrauben, Kleinteile
    M, C, I = combine(items)
    LINKS[("base", "")] = dict(m=M, c=[C.x, C.y, C.z], I=I)
    w("base: %.1f g CoM %s" % (M, [round(v, 1) for v in (C.x, C.y, C.z)]))
    nf = export(vis, "base.stl", V()); w("base facets %d" % nf)
    # Kollisions-Hülle Panzer: Außenform (konvex)
    cf = "/home/claude/slarc/Drawings/Macros/slarc_cover_v1.py"
    cn = {"__name__": "__slarc_lib__", "__file__": cf}; exec(open(cf, encoding="utf-8").read(), cn)
    hull = cn["loft"](cn["C"]["x_rear"] + 0.5, cn["C"]["x_front"], 24)
    m = MeshPart.meshFromShape(Shape=hull, LinearDeflection=1.0, AngularDeflection=0.6); m.write(OUT + "/meshes/cover_hull.stl")
    w("cover hull bb %s" % hull.BoundBox)

    tot = LINKS[("base", "")]["m"] + 3 * sum(LINKS[(g, s)]["m"] for g in ("coxa", "femur", "tibia", "foot") for s in ("R", "L"))
    w("TOTAL %.0f g" % tot)
    geo = dict(P=P, FEM=[FEM.x, FEM.y, FEM.z], TIB=[TIB.x, TIB.y, TIB.z], BALL_T=[BALL_T.x, BALL_T.y, BALL_T.z],
               TIP_T=[TIP_T.x, TIP_T.y, TIP_T.z], cam_bb=list(d.getObject("Stereo_Mount").Shape.BoundBox.__getattribute__(a) for a in ("XMin", "XMax", "YMin", "YMax", "ZMin", "ZMax")))
    json.dump(dict(links={"%s_%s" % k: v for k, v in LINKS.items()}, geo=geo, total=tot), open("/tmp/claude-0/run/urdf_data.json", "w"), indent=1)
    w("done")
except Exception:
    w(traceback.format_exc())
log.close()
