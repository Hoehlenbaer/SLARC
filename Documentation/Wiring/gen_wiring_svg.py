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
    pinl = ["GPB0", "GPB1", "GPB2", "GPB3", "GPB4", "GPB5", "GPB6", "GPB7", "VDD", "VSS", "nc", "SCL", "SDA", "nc",
            "A0", "A1", "A2", "RST", "INTB", "INTA", "GPA0", "GPA1", "GPA2", "GPA3", "GPA4", "GPA5", "GPA6", "GPA7"]
    b.dip(4, 7, 2, 14, "", pinl)
    b.bar("3V3", (11, 1), (11, 13)); b.bar("GND", (0, 18), (17, 18))
    b.trace("GND", [(7, 13), (7, 18)])                    # A0..A2 -> GND (Adresse 0x20)
    b.trace("3V3", [(7, 12), (11, 12)])                   # RESET -> 3V3
    legs = [("FR", 13, 1), ("MR", 13, 6), ("RR", 13, 11), ("FL", 16, 1), ("ML", 16, 6), ("RL", 16, 11)]
    gpa = {"FR": 4, "FL": 5, "MR": 6, "ML": 7, "RR": 8, "RL": 9}   # Zeile: GPA5..GPA0
    for n, c, r in legs:
        b.header([(c, r, "", "GND"), (c, r + 1, "", "DATA"), (c, r + 2, "", "SW")], n, "left")
    b.trace("DATA", [(14, 2), (14, 16)])
    for n, c, r in legs:
        b.trace("DATA", [(c, r + 1), (14, r + 1)])
        b.trace("GND", [(c, r), (12 if c == 13 else 17, r)])
    b.trace("GND", [(12, 1), (12, 18)]); b.trace("GND", [(17, 1), (17, 18)])
    for n, row in gpa.items():
        b.trace("SW", [(7, row), (10, row)])
        b.res((10, row), (11, row), "", standing=True)
    x, y = b.xy(10, 3.2); b.over.append(T(x, y, "R1–R6 10k", "btxt", "middle"))
    for n, c, r in legs:
        tr = r + 3
        b.wire("SW", (9, gpa[n]), (c, tr), via=[(12.4, tr)] if c == 13 else [(12.4, tr)])
    b.header([(1, 2, "GND", "GND"), (1, 3, "3V3", "3V3"), (1, 4, "SCL", "I2C"), (1, 5, "SDA", "I2C")], "J1 I²C", "left")
    b.wire("I2C", (1, 4), (4, 13), via=[(2.3, 4), (2.3, 13)]); b.wire("I2C", (1, 5), (4, 14), via=[(1.7, 5), (1.7, 14)])
    b.wire("3V3", (1, 3), (11, 1), via=[(2.9, 3), (2.9, 0.4), (11, 0.4)])
    b.wire("GND", (1, 2), (0, 18), via=[(0.4, 2), (0.4, 18)])
    b.cap((3, 10), (3, 11), "C1", pol=False, big=False)
    b.trace("3V3", [(3, 10), (4, 10)]); b.trace("GND", [(3, 11), (4, 11)])
    b.wire("3V3", (3, 10), (2.9, 3), via=[(2.9, 10)])
    b.wire("GND", (3, 11), (3, 18), via=[(3, 11)])
    b.header([(1, 20, "GND", "GND"), (1, 21, "DATA", "DATA")], "J2 von H5", "right")
    b.header([(7, 20, "GND", "GND"), (7, 21, "INTA", "INT")], "J3 → IO34", "right")
    b.wire("GND", (1, 20), (1, 18)); b.wire("GND", (7, 20), (7, 18.6), via=[(7.5, 20), (7.5, 18.6)])
    b.wire("DATA", (1, 21), (14, 16), via=[(1, 22.6), (14, 22.6)])
    b.wire("INT", (7, 21), (8, 10), via=[(8.6, 21), (8.6, 10)])
    b.note(["U1 MCP23017 (DIP-28 in Fassung) an I²C",
            "  des ESP32 (IO32/33)",
            "  Adresse 0x20 (A0–A2 auf GND), RST an 3,3 V",
            "C1 100 nF dicht an VDD/VSS",
            "GPA0 RL · GPA1 RR · GPA2 ML",
            "GPA3 MR · GPA4 FL · GPA5 FR",
            "R1–R6 10k (stehend) von GPA nach 3,3 V",
            "INTA → IO34 (IOCON: Push-Pull, aktiv low)",
            "Bank B frei für Status-LEDs",
            "Datenstern: J2 (von H5) → Spalte 14",
            "  → DATA-Pin aller 6 Beinstecker",
            "Beinstecker XH3: GND · DATA · SW",
            "Unterseite: GND Zeile 18, Spalte 12+17",
            "  3V3 Spalte 11",
            "Drahtbrücken enden im Nachbarloch des",
            "  Pins, Lötbrücke zum Pin",
            "Befestigung: Eckbohrungen M2 auf",
            "  gedrucktem Träger am Modulplatz MCP"])
    return b

# ======================================================================= Platine C: Power
def board_power():
    b = Board("Platine C · Power-Verteiler", 18, 24, "Lochraster 5×7 cm", p=26)
    rows = {"12V": 2, "12VL": 8, "12VR": 14, "GND": 21}
    for net, r in rows.items():
        b.bar(net, (0, r), (17, r))
    def padrow(net, r, items):
        for c, t in items:
            b.pad(c, r, net)
            x, y = b.xy(c, r)
            w = 5.4 * len(t) + 6
            b.over.append(f'<rect x="{x-w/2}" y="{y+8}" width="{w}" height="12" rx="2" fill="#163626" opacity=".9"/>')
            b.over.append(T(x, y + 17.5, t, "bsmall", "middle"))
    padrow("12V", 2, [(1, "F1"), (3, "F1"), (5, "F1"), (8, "K1"), (10, "K2"), (12, "K3"), (15, "Trb")])
    padrow("12VL", 8, [(1, "K2"), (3, "K2"), (8, "FL"), (11, "ML"), (14, "RL")])
    padrow("12VR", 14, [(1, "K3"), (3, "K3"), (8, "FR"), (11, "MR"), (14, "RR")])
    padrow("GND", 21, [(0, "P−"), (1, "P−"), (2, "P−"), (4, "FL"), (5, "ML"), (6, "RL"), (8, "FR"), (9, "MR"), (10, "RR"),
                      (12, "Trb"), (14, "DC"), (16, "Rel")])
    b.note(["Sammelschienen auf der Unterseite:",
            "  1,5 mm² Cu massiv (NYM-Rest),",
            "  auf ganzer Länge verlötet",
            "Zeile 2  12 V Haupt (dauernd)",
            "  F1 = von der 30-A-Sicherung,",
            "    3 Löcher für 3× AWG20 (oder AWG14)",
            "  K1/K2/K3 = zu COM am Relaismodul",
            "  Trb = Treiber XH-Eingang",
            "Zeile 8  12 V Servos links (von K2 NO)",
            "  2 Einspeiselöcher = 2× AWG20",
            "Zeile 14 12 V Servos rechts (von K3 NO)",
            "Zeile 21 GND",
            "  P− = BMS-Ausgang, 3 Löcher",
            "  DC = DC-DC IN−, Rel = Relaismodul",
            "Je Bein ein Paar AWG20 (12 V + GND)",
            "Jede Ader in ein eigenes Loch"])
    return b

# ======================================================================= Platine D: Relais-Adapter
def board_relay():
    b = Board("Platine D · Relais-Adapter", 7, 17, "Streifen aus Lochraster 2×8 cm", p=28)
    pins = [(0, 0, "GND", "GND")] + [(0, i, f"IN{i}", "CTL") for i in range(1, 9)] + [(0, 9, "VCC", "5V")]
    b.header(pins, "", "out", kind="hdr")
    x, y = b.xy(0, -0.9); b.over.append(T(x - 10, y, "Buchse → Relaismodul", "small", "start"))
    for i in (1, 2, 3):
        b.trace("CTL", [(0, i), (2, i)])
    b.dio((2, 1), (6, 1), "D1 1N4148"); b.dio((2, 2), (6, 2), "D2"); b.dio((2, 3), (6, 3), "D3")
    b.trace("CTL", [(6, 2), (6, 3)])
    # Q1 BC547: C B E
    b.header([(2, 6, "C", "CTL"), (3, 6, "B", "CTL"), (4, 6, "E", "GND")], "Q1 BC547", "bottom", kind="comp")
    b.wire("CTL", (2, 6), (1, 1), via=[(1.5, 6), (1.5, 1.5)])
    b.trace("CTL", [(3, 6), (3, 7)])
    b.res((3, 7), (3, 11), "R1 4k7")
    hdr = [(6, 12, "IO16", "CTL"), (6, 13, "IO27", "CTL"), (6, 14, "GPIO26", "CTL"), (6, 15, "GND", "GND")]
    b.header(hdr, "J1 Steuerung (XH4)", "left")
    b.wire("CTL", (6, 1), (6, 12), via=[(6.5, 1), (6.5, 11.5)])
    b.wire("CTL", (6, 3), (6, 13), via=[(5.5, 3.5), (5.5, 12.5), (6, 12.6)])
    b.wire("CTL", (3, 11), (6, 14), via=[(3, 14)])
    b.wire("GND", (4, 6), (6, 15), via=[(4.5, 6), (4.5, 15)])
    b.trace("5V", [(0, 9), (0, 16)]); b.pad(0, 16, "5V", "5 V", "end", -0.9)
    b.pad(1, 16, "GND"); b.wire("GND", (1, 16), (6, 15), via=[(1, 15.6), (5.4, 15.6)])
    b.wire("GND", (0, 0), (1, 16), via=[(0.5, 0), (0.5, 16.5), (1, 16.5)])
    b.note(["IN1 = K1  12 V → DC-DC (Pi)",
            "   ESP IO16 low  ODER  Pi GPIO26 high",
            "IN2 = K2  Servos links,  IN3 = K3 rechts",
            "   beide über IO27 (low = an)",
            "Eingänge aktiv-low (Optokoppler)",
            "Dioden: Kathode (Ring) zum ESP32",
            "Q1 statt Diode für den Pi: ein",
            "   ausgeschalteter Pi zieht IN1 sonst",
            "   über seinen Pin nach unten",
            "5 V + GND vom Treiber (40-pol., Pin 2/6)",
            "Reihenfolge der Modul-Stiftleiste",
            "   vor dem Löten prüfen"])
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
    box("pwr", 380, 40, 150, 200, "C Power-Verteiler", "12 V Haupt\n12 V links (K2)\n12 V rechts (K3)\nGND", "boxnew")
    box("rel", 380, 290, 150, 96, "Relaismodul 8-fach", "K1 12 V → DC-DC\nK2 Servos links\nK3 Servos rechts")
    box("adp", 380, 420, 150, 58, "D Relais-Adapter", "3 Dioden + BC547", "boxnew")
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
    ln("12V", [(530, 330), (560, 330), (560, 200), (530, 200)], lab="K2/K3 NO", lpos=(482, 282))
    ln("12V", [(530, 60), (600, 60)], lab="12 V", lpos=(545, 54))
    # Servo-Speisung zu Beinen
    for n, y in (("FR", 40), ("MR", 140), ("RR", 240), ("FL", 360), ("ML", 460), ("RL", 560)):
        yy = 205 if n[1] == "R" else 222
        xx = 845 if n[1] == "R" else 852
        ln("12V", [(530, yy), (xx, yy), (xx, y + 30), (870, y + 30)])
    o.append(T(808, 216, "je Bein 1 Paar AWG20", "labs", "end"))
    # Daten
    ln("DATA", [(700, 190), (700, 250)], lab="DATA", lpos=(672, 244))
    ln("I2C", [(750, 190), (750, 250)], lab="I²C", lpos=(732, 244))
    ln("INT", [(780, 250), (780, 190)])
    for n, y in (("FR", 40), ("MR", 140), ("RR", 240), ("FL", 360), ("ML", 460), ("RL", 560)):
        ln("DATA", [(800, 300), (830, 300), (830, y + 55), (870, y + 55)])
    o.append(T(796, 372, "je Bein XH3: GND · DATA · SW", "labs", "end"))
    ln("CTL", [(640, 190), (640, 230), (560, 230), (560, 450), (530, 450)], lab="IO16/27", lpos=(536, 470))
    ln("5V", [(610, 190), (610, 215), (545, 215), (545, 420)])
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


