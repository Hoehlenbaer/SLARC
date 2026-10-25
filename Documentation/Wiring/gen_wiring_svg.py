# -*- coding: utf-8 -*-
"""SVG-Generator: Lochraster-Layouts + Blockschaltbild für die SLARC-Verkabelung."""
import html, json, sys
P = 18           # px pro Rasterschritt (2,54 mm)
M = 40           # Rand

NET = {"12V": "n12", "12VL": "n12", "12VR": "n12", "GND": "ngnd", "DATA": "ndata", "SW": "nsw",
       "I2C": "ni2c", "3V3": "n33", "5V": "n5", "CTL": "nctl", "INT": "nint"}

FILE_STYLE = """
svg{font-family:'IBM Plex Sans','Segoe UI',Arial,sans-serif}
.bg{fill:#f7f8f4}.board{fill:#2f6b4a}.boardedge{fill:none;stroke:#1f4a33;stroke-width:2}
.pad{fill:#c9b37a;stroke:#8a7440;stroke-width:.8}.padhole{fill:#2a2a2a}
.txt{fill:#1d2320;font-size:11px}.small{fill:#1d2320;font-size:9.5px}.title{fill:#1d2320;font-size:14px;font-weight:600}
.btxt{fill:#f2f5ef;font-size:9px}.bsmall{fill:#e9efe6;font-size:8px}
.comp{fill:#e8e3d3;stroke:#3a3a3a;stroke-width:1}.hdr{fill:#f1f1ee;stroke:#3a3a3a;stroke-width:1}
.ic{fill:#26292b;stroke:#111;stroke-width:1}.ictxt{fill:#e8e8e8;font-size:8px}
.res{fill:#d8c39b;stroke:#6b5a37;stroke-width:1}.dio{fill:#c84b2f;stroke:#7a2b18;stroke-width:1}.band{fill:#1e1e1e}
.cap{fill:#2b4e8c;stroke:#162a4d;stroke-width:1}
.n12{stroke:#d1362f}.ngnd{stroke:#1f1f1f}.ndata{stroke:#d9a400}.nsw{stroke:#2f6fdb}.ni2c{stroke:#1b9a6b}
.n33{stroke:#9b59b6}.n5{stroke:#e07b00}.nctl{stroke:#c2187a}.nint{stroke:#0aa1b8}
.f12{fill:#d1362f}.fgnd{fill:#1f1f1f}.fdata{fill:#d9a400}.fsw{fill:#2f6fdb}.fi2c{fill:#1b9a6b}.f33{fill:#9b59b6}.f5{fill:#e07b00}.fctl{fill:#c2187a}.fint{fill:#0aa1b8}
.bar{stroke-width:7;stroke-linecap:round;opacity:.55}.trace{stroke-width:3.2;stroke-linecap:round;opacity:.7}
.wire{stroke-width:2.6;fill:none;stroke-linecap:round}.drill{fill:none;stroke:#fff;stroke-width:1.4;stroke-dasharray:3 2}
.box{fill:#ffffff;stroke:#2c3a33;stroke-width:1.3}.box2{fill:#eef3ec;stroke:#2c3a33;stroke-width:1.3}.boxnew{fill:#fff6dc;stroke:#a7781a;stroke-width:1.6}
.lab{fill:#1d2320;font-size:11px}.labb{fill:#1d2320;font-size:12px;font-weight:600}.labs{fill:#4b5a52;font-size:9.5px}
.ln{fill:none;stroke-width:2.2}.lnth{fill:none;stroke-width:4}.dash{stroke-dasharray:5 3}
"""

def T(x, y, s, cls="txt", anchor="start", rot=None):
    r = f' transform="rotate({rot} {x:.1f} {y:.1f})"' if rot else ""
    return f'<text x="{x:.1f}" y="{y:.1f}" class="{cls}" text-anchor="{anchor}"{r}>{html.escape(s)}</text>'

class Board:
    def __init__(s, name, cols, rows, sub="", p=18):
        s.name, s.cols, s.rows, s.sub, s.p = name, cols, rows, sub, p
        s.under, s.over, s.labels, s.used = [], [], [], set()
        s.extra_r = 230   # Platz rechts für Legende/Labels

    def xy(s, c, r):
        P = s.p
        return M + 40 + c * s.p + s.p / 2, M + 22 + r * s.p + s.p / 2

    # Unterseite
    def bar(s, net, a, b, label=None, side="left"):
        (x1, y1), (x2, y2) = s.xy(*a), s.xy(*b)
        s.under.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" class="bar {NET[net]}"/>')
    def trace(s, net, pts):
        d = " ".join(f"{s.xy(*p)[0]},{s.xy(*p)[1]}" for p in pts)
        s.under.append(f'<polyline points="{d}" class="trace {NET[net]}" fill="none"/>')
    # Oberseite
    def wire(s, net, a, b, via=None):
        pts = [a] + (via or []) + [b]
        d = " ".join(f"{s.xy(*p)[0]},{s.xy(*p)[1]}" for p in pts)
        s.over.append(f'<polyline points="{d}" class="wire {NET[net]}"/>')
    def header(s, pins, label, lpos="left", kind="hdr"):
        cs = [p[0] for p in pins]; rs = [p[1] for p in pins]
        x0, y0 = s.xy(min(cs), min(rs)); x1, y1 = s.xy(max(cs), max(rs))
        s.over.append(f'<rect x="{x0-s.p*0.48}" y="{y0-s.p*0.48}" width="{x1-x0+s.p*0.96}" height="{y1-y0+s.p*0.96}" rx="2" class="{kind}" opacity=".85"/>')
        for c, r, pl, net in pins:
            x, y = s.xy(c, r)
            s.over.append(f'<rect x="{x-3.2}" y="{y-3.2}" width="6.4" height="6.4" class="f{NET[net][1:]}"/>')
            s.used.add((c, r))
            if pl:
                if lpos == "left":
                    s.over.append(T(x0 - s.p * 0.6, y + 3, pl, "bsmall", "end"))
                elif lpos == "out":
                    s.over.append(T(x0 - s.p * 0.25, y + 3, pl, "small", "end"))
                elif lpos == "right":
                    s.over.append(T(x1 + s.p * 0.6, y + 3, pl, "bsmall", "start"))
                elif lpos == "top":
                    s.over.append(T(x, y0 - s.p * 0.62, pl, "bsmall", "middle"))
                else:
                    s.over.append(T(x, y1 + s.p * 0.95, pl, "bsmall", "middle"))
        s.lab_at(label, (x0 + x1) / 2 + (s.p * 0.9 if lpos == "right" else 0), y0 - s.p * 0.62 - (10 if lpos == "top" else 0))
    def lab_at(s, label, x, y, cls="btxt"):
        if label:
            w = 5.6 * len(label) + 8
            s.over.append(f'<rect x="{x-w/2}" y="{y-10}" width="{w}" height="13" rx="3" fill="#163626" opacity=".85"/>')
            s.over.append(T(x, y, label, cls, "middle"))
    def pad(s, c, r, net, label=None, anchor="end", dx=-0.65):
        x, y = s.xy(c, r)
        s.over.append(f'<circle cx="{x}" cy="{y}" r="4.6" class="f{NET[net][1:]}" stroke="#fff" stroke-width="1.2"/>')
        s.used.add((c, r))
        if label: s.over.append(T(x + dx * s.p, y + 3, label, "small" if c == 0 else "btxt", anchor))
    def res(s, a, b, label, standing=False):
        (x1, y1), (x2, y2) = s.xy(*a), s.xy(*b)
        s.used |= {a, b}
        s.over.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#777" stroke-width="1.6"/>')
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        if standing:
            s.over.append(f'<circle cx="{x1}" cy="{y1}" r="6" class="res"/>')
        else:
            horiz = abs(x2 - x1) > abs(y2 - y1)
            w, h = (22, 8) if horiz else (8, 22)
            s.over.append(f'<rect x="{mx-w/2}" y="{my-h/2}" width="{w}" height="{h}" rx="3" class="res"/>')
        s.over.append(T(mx, my - 7 if abs(x2-x1) > abs(y2-y1) else my, label, "btxt", "middle") if not standing else T(x1 - 9, y1 + 3, label, "btxt", "end"))
    def dio(s, a, k, label):
        (x1, y1), (x2, y2) = s.xy(*a), s.xy(*k)
        s.used |= {a, k}
        s.over.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#777" stroke-width="1.6"/>')
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        s.over.append(f'<rect x="{mx-11}" y="{my-4.5}" width="22" height="9" rx="2" class="dio"/>')
        s.over.append(f'<rect x="{mx+6}" y="{my-4.5}" width="3" height="9" class="band"/>')
        s.over.append(T(mx, my - 8, label, "btxt", "middle"))
    def cap(s, a, b, label, pol=True, big=True):
        (x1, y1), (x2, y2) = s.xy(*a), s.xy(*b)
        s.used |= {a, b}
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        r = s.p * 0.98 if big else 5
        if big:
            s.over.append(f'<circle cx="{mx}" cy="{my}" r="{r}" class="cap" opacity=".9"/>')
            s.over.append(T(x1 + 7, y1 + 3, "+", "btxt"))
        else:
            s.over.append(f'<rect x="{min(x1,x2)-3}" y="{min(y1,y2)-3}" width="{abs(x2-x1)+6}" height="{abs(y2-y1)+6}" rx="3" class="cap"/>')
        s.over.append(T(mx + r + 4, my + 3, label, "btxt"))
    def dip(s, cl, cr, r0, n, label, pinl):
        x0, y0 = s.xy(cl, r0); x1, y1 = s.xy(cr, r0 + n - 1)
        s.over.append(f'<rect x="{x0+3}" y="{y0-s.p*0.5}" width="{x1-x0-6}" height="{y1-y0+s.p}" rx="2" class="ic"/>')
        s.over.append(f'<circle cx="{(x0+x1)/2}" cy="{y0-s.p*0.5}" r="4" fill="#555"/>')
        s.over.append(T((x0 + x1) / 2, y0 - s.p * 0.5 - 6, label, "small", "middle"))
        for i in range(n):
            for c, idx, anc, dx in ((cl, i, "end", -0.55), (cr, 2 * n - 1 - i, "start", 0.55)):
                x, y = s.xy(c, r0 + i)
                s.over.append(f'<rect x="{x-3}" y="{y-3}" width="6" height="6" fill="#bbb"/>')
                s.used.add((c, r0 + i))
                t = pinl[idx]
                s.over.append(T(x + (8 if anc == "end" else -8), y + 3, t, "ictxt", "start" if anc == "end" else "end"))
    def drill(s, c, r, label):
        x, y = s.xy(c, r)
        s.over.append(f'<circle cx="{x}" cy="{y}" r="7" class="drill"/>')
        if label: s.over.append(T(x, y + 18, label, "bsmall", "middle"))
    def note(s, text_lines):
        s.notes = text_lines

    def svg(s, mode="file"):
        W = M * 2 + 40 + s.cols * s.p + s.extra_r
        H = M * 2 + 22 + s.rows * s.p + 10
        out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" class="pcb" role="img" aria-label="{html.escape(s.name)}">']
        if mode == "file":
            out.append(f"<style>{FILE_STYLE}</style><rect width='{W}' height='{H}' class='bg'/>")
        out.append(T(M, 20, s.name + (" – " + s.sub if s.sub else ""), "title"))
        bx, by = M + 40, M + 22
        out.append(f'<rect x="{bx}" y="{by}" width="{s.cols*s.p}" height="{s.rows*s.p}" rx="4" class="board"/>')
        for c in range(s.cols):
            for r in range(s.rows):
                x, y = s.xy(c, r)
                out.append(f'<circle cx="{x}" cy="{y}" r="3.3" class="pad"/><circle cx="{x}" cy="{y}" r="1.2" class="padhole"/>')
        out.append(f'<rect x="{bx}" y="{by}" width="{s.cols*s.p}" height="{s.rows*s.p}" rx="4" class="boardedge"/>')
        # Raster-Beschriftung
        for c in range(0, s.cols, 2):
            x, _ = s.xy(c, 0); out.append(T(x, by - 4, str(c), "small", "middle"))
        for r in range(0, s.rows, 2):
            _, y = s.xy(0, r); out.append(T(bx - 34, y + 3, str(r), "small", "end"))
        out += s.under + s.over
        # Notizen rechts
        nx = M + 40 + s.cols * s.p + 18; ny = M + 34
        for i, line in enumerate(getattr(s, "notes", [])):
            out.append(T(nx, ny + i * 15, line, "small"))
        out.append("</svg>")
        return "\n".join(out)

# ======================================================================= Platine A: Bein
def board_leg():
    b = Board("Platine A · Bein-Verteiler (6×)", 10, 11, "½ Lochraster 3×7 cm", p=30)
    b.bar("GND", (0, 1), (9, 1)); b.bar("12V", (0, 2), (9, 2))
    b.trace("DATA", [(3, 3), (8, 3)])
    b.pad(0, 1, "GND", "GND", "end"); b.pad(0, 2, "12V", "12 V", "end")
    b.trace("GND", [(1, 0), (1, 1)])
    b.cap((1, 2), (1, 0), "C1")
    for c, lab in ((4, "Coxa"), (6, "Femur"), (8, "Tibia")):
        b.header([(c, 1, "", "GND"), (c, 2, "", "12V"), (c, 3, "", "DATA")], lab, "left")
    b.header([(2, 6, "GND", "GND"), (2, 7, "DATA", "DATA"), (2, 8, "SW", "SW")], "J4 Hub", "left")
    b.header([(6, 8, "SW", "SW"), (6, 9, "GND", "GND")], "J5 Fuß", "right")
    b.wire("GND", (2, 6), (5, 1), via=[(5, 6)])
    b.wire("DATA", (2, 7), (3, 3), via=[(3, 7)])
    b.wire("SW", (2, 8), (6, 8))
    b.wire("GND", (6, 9), (9, 1), via=[(9, 9)])
    b.note(["Unterseite (breit):",
            "  Zeile 1 GND, Zeile 2 12 V – blanker",
            "  Cu-Draht 0,8 mm, satt verzinnt",
            "  Zeile 3 DATA – dünner Draht",
            "Oberseite (Linien): Drahtbrücken",
            "Coxa/Femur/Tibia: Stiftleiste 3-pol.",
            "  2,54 (5264-Servostecker passt)",
            "  Pinfolge am Servokabel prüfen!",
            "C1: 470 µF / 25 V stehend, + an 12 V,",
            "  ragt links über den Rand",
            "Einspeisung je Bein: 1 Paar AWG20",
            "  vom Power-Board, von unten anlöten",
            "J4 (XH3) GND · DATA · SW zum Hub",
            "J5 (XH2) Mikroschalter im Fuß"])
    return b

def board_hub():
    b = Board("Platine B · Hub (Fußkontakte + Datenstern)", 18, 24, "Lochraster 5×7 cm", p=24)
    # MCP23017-Modul liegt über Spalte 1..8, seitliche Stiftleiste in Spalte 8 (Zeile 3..22)
    x0, y0 = b.xy(1.4, 1.2); x1, y1 = b.xy(8.45, 22.5)
    b.over.append(f'<rect x="{x0}" y="{y0}" width="{x1-x0}" height="{y1-y0}" rx="3" fill="#3f9a4e" stroke="#1f5e2c" stroke-width="1.2" opacity=".55"/>')
    xm, ym = b.xy(4.6, 8); b.over.append(T(xm, ym, "MCP23017-Modul", "btxt", "middle"))
    xm, ym = b.xy(4.6, 9); b.over.append(T(xm, ym, "liegt auf der", "btxt", "middle"))
    xm, ym = b.xy(4.6, 10); b.over.append(T(xm, ym, "Stiftleiste", "btxt", "middle"))
    xm, ym = b.xy(4.6, 1.9); b.over.append(T(xm, ym, "Kopfleiste: VCC GND SCL SDA RST ITA ITB", "bsmall", "middle"))
    names = ["VCC", "GND"] + [f"PB{i}" for i in range(7, -1, -1)] + ["VCC", "GND"] + [f"PA{i}" for i in range(8)]
    nets = {"VCC": "3V3", "GND": "GND"}
    b.header([(8, 3 + i, n, nets.get(n, "SW" if n in ("PA0", "PA1", "PA2", "PA3", "PA4", "PA5") else "CTL")) for i, n in enumerate(names)], "", "left")
    b.bar("3V3", (11, 13), (11, 20)); b.trace("3V3", [(8, 13), (11, 13)])
    b.trace("GND", [(8, 14), (10, 14)]); b.wire("GND", (10, 14), (12, 14))
    legs = [("FR", 13, 1), ("MR", 13, 6), ("RR", 13, 11), ("FL", 16, 1), ("ML", 16, 6), ("RL", 16, 11)]
    pa = {"RR": 15, "RL": 16, "MR": 17, "ML": 18, "FR": 19, "FL": 20}      # Zeile von PA0..PA5
    for n, c, r in legs:
        b.header([(c, r, "", "GND"), (c, r + 1, "", "DATA"), (c, r + 2, "", "SW")], n, "left")
    b.trace("DATA", [(14, 2), (14, 18)])
    for n, c, r in legs:
        b.trace("DATA", [(c, r + 1), (14, r + 1)])
        b.trace("GND", [(c, r), (12 if c == 13 else 17, r)])
    b.trace("GND", [(12, 1), (12, 23)]); b.trace("GND", [(17, 1), (17, 23)]); b.trace("GND", [(12, 23), (17, 23)])
    for n, row in pa.items():
        b.trace("SW", [(8, row), (10, row)])
        b.res((10, row), (11, row), "", standing=True)
    x, y = b.xy(10.5, 21.3); b.over.append(T(x, y, "R1–R6 10k", "btxt", "middle"))
    for n, c, r in legs:
        b.wire("SW", (9, pa[n]), (c, r + 3), via=[(12.5, r + 3)])
    b.header([(13, 17, "GND", "GND"), (13, 18, "DATA", "DATA")], "J2 von H5", "right")
    b.trace("DATA", [(13, 18), (14, 18)]); b.trace("GND", [(13, 17), (12, 17)])
    b.note(["MCP23017-Modul (Breakout) mit der seitlichen",
            "  20-pol. Stiftleiste in Spalte 8 eingelötet",
            "  (oder in eine Buchsenleiste gesteckt)",
            "I²C + INT direkt an die Kopfleiste des Moduls:",
            "  VCC 3,3 V · GND · SCL · SDA → Treiber-I²C",
            "  ITA → IO34 (Dupont)",
            "Adresse 0x20: A0–A2 auf GND (Modul-Brücken",
            "  prüfen), RST hat das Modul schon (10k)",
            "PA0 RR · PA1 RL · PA2 MR · PA3 ML",
            "PA4 FR · PA5 FL",
            "R1–R6 10k (stehend) von PA nach 3,3 V",
            "Datenstern: J2 (von H5) → Spalte 14",
            "  → DATA-Pin aller 6 Beinstecker (XH3)",
            "Unterseite: GND Spalte 12+17 + Zeile 23,",
            "  3V3 Spalte 11 (vom Modul-VCC, Zeile 13)",
            "Bank B (PB0–7) frei für Status-LEDs",
            "Befestigung: Eckbohrungen M2 auf",
            "  gedrucktem Träger am Modulplatz MCP"])
    return b

def board_power():
    b = Board("Platine C · Power-Verteiler", 18, 14, "Lochraster 5×7 cm (halbe Länge reicht)", p=26)
    rows = {"12V": 3, "GND": 10}
    for net, r in rows.items():
        b.bar(net, (0, r), (17, r))
    def padrow(net, r, items):
        for c, t in items:
            b.pad(c, r, net)
            x, y = b.xy(c, r)
            w = 5.4 * len(t) + 6
            b.over.append(f'<rect x="{x-w/2}" y="{y+8}" width="{w}" height="12" rx="2" fill="#163626" opacity=".9"/>')
            b.over.append(T(x, y + 17.5, t, "bsmall", "middle"))
    padrow("12V", 3, [(0, "F1"), (1, "F1"), (2, "F1"), (4, "K1"), (6, "K2"), (8, "K3"), (10, "K4"), (12, "K5"), (14, "K6"), (16, "K7"), (17, "Trb")])
    padrow("GND", 10, [(0, "P−"), (1, "P−"), (2, "P−"), (4, "FR"), (5, "MR"), (6, "RR"), (8, "FL"), (9, "ML"), (10, "RL"),
                      (12, "Trb"), (14, "DC")])
    b.note(["Zwei Sammelschienen auf der Unterseite:",
            "  1,5 mm² Cu massiv (NYM-Rest),",
            "  auf ganzer Länge verlötet",
            "Zeile 3  12 V Haupt (dauernd)",
            "  F1 = von der 30-A-Sicherung,",
            "    3 Löcher für 3× AWG20 (oder AWG14)",
            "  K1…K7 = je 1× AWG20 zu COM am Relais",
            "  Trb = Treiber XH-Eingang",
            "Zeile 10 GND",
            "  P− = BMS-Ausgang, 3 Löcher",
            "  je Bein 1× AWG20 (GND der Bein-Platine)",
            "  Trb = Treiber, DC = DC-DC IN−",
            "12 V der Beine kommt von Kx NO,",
            "  nicht vom Power-Board",
            "Jede Ader in ein eigenes Loch"])
    return b

# ======================================================================= Platine D: Relais-Adapter
def board_relay():
    b = Board("Platine D · Relais-Adapter", 7, 14, "Streifen aus Lochraster 2×8 cm", p=28)
    pins = [(0, 0, "GND", "GND")] + [(0, i, f"IN{i}", "CTL") for i in range(1, 9)] + [(0, 9, "VCC", "33")]
    pins[-1] = (0, 9, "VCC", "3V3")
    b.header(pins, "", "out", kind="hdr")
    x, y = b.xy(0, -0.9); b.over.append(T(x - 10, y, "Buchse → Eingangsleiste Relaismodul", "small", "start"))
    b.trace("CTL", [(0, 2), (1, 2), (1, 7), (0, 7)])          # IN2..IN7 gebrückt (Spalte 1)
    for i in range(3, 7): b.trace("CTL", [(0, i), (1, i)])
    b.trace("CTL", [(0, 1), (2, 1)])                          # IN1-Knoten
    b.header([(2, 3, "C", "CTL"), (3, 3, "B", "CTL"), (4, 3, "E", "GND")], "Q1 BC547", "bottom", kind="comp")
    b.wire("CTL", (2, 3), (2, 1))
    b.trace("CTL", [(3, 3), (3, 4)])
    b.res((3, 4), (3, 8), "R1 4k7")
    hdr = [(6, 9, "IO16", "CTL"), (6, 10, "IO27", "CTL"), (6, 11, "GPIO26", "CTL"), (6, 12, "GND", "GND"), (6, 13, "3V3", "3V3")]
    b.header(hdr, "J1 Steuerung", "left")
    b.wire("CTL", (2, 1), (6, 9), via=[(5.5, 1), (5.5, 8.5), (6, 8.5)])
    b.wire("CTL", (1, 7), (6, 10), via=[(1, 10)])
    b.wire("CTL", (3, 8), (6, 11), via=[(3, 11)])
    b.wire("GND", (4, 3), (6, 12), via=[(4.6, 3), (4.6, 12)])
    b.wire("GND", (0, 0), (6, 12), via=[(0.5, 0), (0.5, 12.6), (6, 12.6)])
    b.wire("3V3", (0, 9), (6, 13), via=[(0.5, 9.4), (0.5, 13), (6, 13)]) if False else b.wire("3V3", (0, 9), (6, 13), via=[(-0.3, 9), (-0.3, 13.5), (6, 13.5)])
    b.note(["Modul: Jumper JD-VCC–VCC ziehen!",
            "  VCC (Optokoppler) = 3,3 V über J1",
            "  JD-VCC (Spulen) = 5 V vom Treiber,",
            "  GND an der 3-pol. Leiste",
            "Eingänge aktiv-low, direkt an 3,3-V-Logik",
            "IN1 = K1 12 V → DC-DC (Pi)",
            "  ESP IO16 (Open-Drain) ODER Pi GPIO26",
            "  über Q1 (high = halten)",
            "IN2…IN7 = K2…K7 je ein Bein",
            "  FR MR RR FL ML RL, alle an IO27",
            "  (low = an, ~12 mA Senke)",
            "IN8 = K8 frei",
            "Q1 statt Direktanschluss für den Pi:",
            "  ein ausgeschalteter Pi zöge IN1 über",
            "  seinen Pin nach unten",
            "Reihenfolge der Modul-Leiste prüfen"])
    return b

# ======================================================================= Blockschaltbild
def block():
    W, H = 1080, 700
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" class="pcb" role="img" aria-label="Blockschaltbild SLARC">']
    boxes = {}
    def box(k, x, y, w, h, title, sub="", cls="box"):
        boxes[k] = (x, y, w, h)
        o.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" class="{cls}"/>')
        o.append(T(x + 8, y + 17, title, "labb"))
        for i, line in enumerate(sub.split("\n") if sub else []):
            o.append(T(x + 8, y + 32 + i * 13, line, "labs"))
    def ln(net, pts, thick=False, dash=False, lab=None, lpos=None):
        d = " ".join(f"{x},{y}" for x, y in pts)
        o.append(f'<polyline points="{d}" class="{"lnth" if thick else "ln"} {NET[net]}{" dash" if dash else ""}"/>')
        if lab:
            x, y = lpos or pts[len(pts)//2]
            o.append(T(x, y, lab, "labs"))
    # Energie (links)
    box("bat", 20, 40, 150, 62, "LiPo 3S 9000 mAh", "Deans-Buchse + Balancer")
    box("hold", 20, 140, 150, 50, "Steckerhalter", "Deans-Stifte · Balancer-Adapter", "box2")
    box("fuse", 220, 40, 110, 44, "F1 30 A", "Flachsicherung")
    box("bms", 220, 140, 110, 62, "BMS Daly 3S", "B− · P− · Balance")
    box("pwr", 380, 40, 150, 200, "C Power-Verteiler", "12 V Haupt (dauernd)\nGND\n2 Sammelschienen", "boxnew")
    box("rel", 380, 290, 150, 96, "Relaismodul 8-fach", "K1 12 V → DC-DC (Pi)\nK2…K7 je ein Bein\nK8 frei · je 10 A")
    box("adp", 380, 420, 150, 58, "D Relais-Adapter", "BC547 für den Pi", "boxnew")
    box("dcdc", 220, 290, 110, 56, "DC-DC 12→5 V", "Fulree 5 A")
    box("pi", 20, 420, 300, 120, "Raspberry Pi 5 + Hailo-8", "GPIO26 Halten · GPIO18 PWM Trigger\nGPIO23 Trigger zurück · GPIO24 IMU-INT\nI²C1 (GPIO2/3) · CSI 0/1 · UART")
    box("imu", 20, 580, 140, 48, "ICM-20948", "I²C + INT")
    box("trg", 180, 580, 140, 48, "Trigger-Platine", "→ XTR beider IMX296")
    box("cam", 180, 645, 140, 40, "2× IMX296", "")
    # Treiber + Hub
    box("drv", 600, 40, 200, 150, "Waveshare General Driver", "ESP32 · XH 12 V Eingang\nH5 Servo-Bus (DATA)\nI²C IO32/33 · IO34 INT\nIO16 · IO27 · IO4\n40-pol.: 5 V / GND")
    box("hub", 600, 250, 200, 100, "B Hub", "MCP23017 (Fußkontakte)\nDatenstern 1 → 6\n10k Pull-ups", "boxnew")
    box("led", 600, 400, 200, 44, "WS2812-Streifen (opt.)", "Daten IO4")
    # Beine
    for i, (n, y) in enumerate((("FR", 40), ("MR", 140), ("RR", 240), ("FL", 360), ("ML", 460), ("RL", 560))):
        box("leg" + n, 870, y, 190, 80, f"A Bein {n}", "3× ST3215 (Coxa/Femur/Tibia)\nFußschalter\n470 µF", "boxnew")
    # Leitungen Energie
    ln("12V", [(170, 60), (220, 60)], True); ln("12V", [(330, 60), (380, 60)], True)
    ln("GND", [(170, 90), (195, 90), (195, 160), (220, 160)], True, lab="B−", lpos=(176, 128))
    ln("GND", [(330, 180), (355, 180), (355, 220), (380, 220)], True, lab="P−", lpos=(338, 210))
    ln("CTL", [(95, 102), (95, 140)], lab="Balance", lpos=(100, 125))
    ln("CTL", [(170, 175), (220, 190)], dash=True)
    # 12 V zu Relais / DC-DC
    ln("12V", [(410, 240), (410, 290)], lab="COM", lpos=(414, 270)); ln("12V", [(440, 240), (440, 290)]); ln("12V", [(470, 240), (470, 290)])
    ln("12V", [(380, 320), (330, 320)], lab="K1", lpos=(345, 314))
    ln("5V", [(275, 346), (275, 420)], True, lab="5 V / 5 A", lpos=(280, 390))
    o.append(T(482, 282, "7× COM", "labs"))
    ln("12V", [(530, 60), (600, 60)], lab="12 V", lpos=(545, 54))
    # Servo-Speisung zu Beinen
    for n, y in (("FR", 40), ("MR", 140), ("RR", 240), ("FL", 360), ("ML", 460), ("RL", 560)):
        ln("12V", [(530, 362), (852, 362), (852, y + 30), (870, y + 30)])
        ln("GND", [(530, 225), (845, 225), (845, y + 22), (870, y + 22)])
    o.append(T(842, 218, "GND je Bein", "labs", "end")); o.append(T(842, 357, "12 V je Bein von K2…K7 NO", "labs", "end"))
    # Daten
    ln("DATA", [(700, 190), (700, 250)], lab="DATA", lpos=(672, 244))
    ln("I2C", [(750, 190), (750, 250)], lab="I²C", lpos=(732, 244))
    ln("INT", [(780, 250), (780, 190)])
    for n, y in (("FR", 40), ("MR", 140), ("RR", 240), ("FL", 360), ("ML", 460), ("RL", 560)):
        ln("DATA", [(800, 300), (830, 300), (830, y + 55), (870, y + 55)])
    o.append(T(796, 388, "je Bein XH3: GND · DATA · SW", "labs", "end"))
    ln("CTL", [(640, 190), (640, 238), (560, 238), (560, 450), (530, 450)], lab="IO16/27, 3,3 V", lpos=(536, 470))
    ln("5V", [(610, 190), (610, 232), (545, 232), (545, 290)])
    o.append(T(550, 284, "5 V Spulen", "labs"))
    ln("CTL", [(455, 420), (455, 386)])
    ln("CTL", [(320, 440), (380, 440)], lab="GPIO26", lpos=(330, 434))
    ln("DATA", [(800, 175), (815, 175), (815, 422), (800, 422)], dash=True)
    o.append(T(810, 410, "IO4", "labs", "end"))
    ln("DATA", [(320, 500), (580, 500), (580, 120), (600, 120)], dash=True, lab="UART", lpos=(586, 300))
    ln("I2C", [(90, 540), (90, 580)]); ln("CTL", [(250, 540), (250, 580)]); ln("DATA", [(250, 628), (250, 645)])
    o.append("</svg>")
    return "\n".join(o)


if __name__ == "__main__":
    out = sys.argv[1]; mode = sys.argv[2] if len(sys.argv) > 2 else "file"
    for fn, f in (("board_a_bein", board_leg), ("board_b_hub", board_hub), ("board_c_power", board_power), ("board_d_relais", board_relay)):
        open(f"{out}/{fn}.svg", "w", encoding="utf-8").write(f().svg(mode))
    open(f"{out}/block.svg", "w", encoding="utf-8").write(block().replace('class="pcb" role="img"', 'class="pcb" role="img"') if mode != "file" else block().replace('aria-label="Blockschaltbild SLARC">', 'aria-label="Blockschaltbild SLARC"><style>' + FILE_STYLE + '</style><rect width="1080" height="700" class="bg"/>', 1))
    print("ok")


