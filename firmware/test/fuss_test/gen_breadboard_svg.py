# Erzeugt fuss_test_breadboard.svg – Breadboard-Skizze für den Fußschalter-Test
# Aufruf: python gen_breadboard_svg.py (schreibt fuss_test_breadboard.svg in den aktuellen Ordner)
W, H = 980, 700
o = []
def add(s): o.append(s)
def T(x, y, s, size=13, anchor="start", w="normal", fill="#1d1d1d"):
    add(f'<text x="{x}" y="{y}" font-size="{size}" text-anchor="{anchor}" font-weight="{w}" fill="{fill}">{s}</text>')

add(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="Arial, Helvetica, sans-serif">')
add(f'<rect width="{W}" height="{H}" fill="#f7f7f2"/>')
T(20, 32, "SLARC · Fußschalter-Test mit Arduino Uno", 20, w="bold")
T(20, 54, "D2 mit INPUT_PULLUP, Schalter nach GND (0 = Kontakt) · LED an D8 über 330 Ω · Board-LED D13 zeigt dasselbe", 13, fill="#444")

# ---------------- Arduino Uno
ux, uy, uw, uh = 30, 110, 300, 230
add(f'<rect x="{ux}" y="{uy}" width="{uw}" height="{uh}" rx="10" fill="#1f7a8c" stroke="#145566" stroke-width="2"/>')
add(f'<rect x="{ux-14}" y="{uy+40}" width="40" height="44" fill="#b9bec4" stroke="#7d848b"/>')  # USB
T(ux+5, uy+100, "USB", 11, fill="#fff")
T(ux+uw/2+20, uy+150, "Arduino Uno", 20, "middle", "bold", "#fff")
# obere Buchsenleiste
hdr = ["SCL", "SDA", "AREF", "GND", "13", "12", "11", "10", "9", "8", "", "7", "6", "5", "4", "3", "2", "1", "0"]
pin = {}
px0, pstep, py = ux + 52, 13, uy + 14
add(f'<rect x="{px0-8}" y="{py-8}" width="{pstep*len(hdr)+3}" height="16" fill="#222" rx="2"/>')
for i, n in enumerate(hdr):
    if not n: continue
    x = px0 + i * pstep
    add(f'<rect x="{x-3.5}" y="{py-3.5}" width="7" height="7" fill="#555"/>')
    add(f'<text x="{x}" y="{py+24}" font-size="9" fill="#fff" text-anchor="end" transform="rotate(-90 {x} {py+24})" dx="-0">{n}</text>')
    pin[n] = (x, py)
# Board-LED "L" an D13
lx, ly = px0 + 4 * pstep, uy + 70
add(f'<rect x="{lx-6}" y="{ly-4}" width="12" height="8" fill="#ffd34d" stroke="#a88400"/>')
T(lx + 10, ly + 4, "L (D13)", 10, fill="#fff")

# ---------------- Breadboard
bx, by = 400, 90
cols, cs = 30, 17
bw = cols * cs + 30
add(f'<rect x="{bx}" y="{by}" width="{bw}" height="330" rx="8" fill="#fbfbfb" stroke="#c8c8c0" stroke-width="2"/>')
def hx(c): return bx + 22 + (c - 1) * cs
rail_minus, rail_plus = by + 18, by + 34
rows = {r: by + 66 + i * cs for i, r in enumerate("abcde")}
rows.update({r: by + 66 + 5 * cs + 26 + i * cs for i, r in enumerate("fghij")})
add(f'<line x1="{bx+10}" y1="{rail_minus-9}" x2="{bx+bw-10}" y2="{rail_minus-9}" stroke="#2b6cd6" stroke-width="2"/>')
add(f'<line x1="{bx+10}" y1="{rail_plus+9}" x2="{bx+bw-10}" y2="{rail_plus+9}" stroke="#d62b2b" stroke-width="2"/>')
T(bx + 4, rail_minus + 4, "−", 14, "end", "bold", "#2b6cd6")
T(bx + 4, rail_plus + 4, "+", 14, "end", "bold", "#d62b2b")
for c in range(1, cols + 1):
    for y in (rail_minus, rail_plus):
        if c % 6: add(f'<rect x="{hx(c)-3}" y="{y-3}" width="6" height="6" fill="#bbb"/>')
    for r, y in rows.items():
        add(f'<rect x="{hx(c)-3}" y="{y-3}" width="6" height="6" fill="#bbb"/>')
    if c % 5 == 0 or c == 1:
        T(hx(c), rows["a"] - 12, str(c), 9, "middle", fill="#888")
for r, y in rows.items():
    T(bx + 10, y + 3, r, 9, "middle", fill="#888")
gy = (rows["e"] + rows["f"]) / 2
add(f'<rect x="{bx+16}" y="{gy-5}" width="{bw-32}" height="10" fill="#ecece6"/>')
T(bx + bw / 2, by + 322, "Rail − = GND (vom Uno)  ·  Rail + bleibt frei  ·  Spalten a–e sind je Spalte verbunden", 10, "middle", fill="#666")

def hole(c, r): return (hx(c), rows[r] if r in rows else {"-": rail_minus, "+": rail_plus}[r])
def wire(p, q, color, mid=None, w=4):
    (x1, y1), (x2, y2) = p, q
    if mid:
        d = f"M{x1},{y1} C{mid[0]},{mid[1]} {mid[2]},{mid[3]} {x2},{y2}"
    else:
        d = f"M{x1},{y1} L{x2},{y2}"
    add(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{w}" stroke-linecap="round" opacity=".9"/>')
    for x, y in ((x1, y1), (x2, y2)):
        add(f'<circle cx="{x}" cy="{y}" r="3.5" fill="{color}" stroke="#222" stroke-width=".8"/>')

# ---------------- Mikroschalter (Spalten 4/6/8, Reihe e)
cCOM, cNO, cNC = 4, 6, 8  # NO ist der mittlere Pin (Marco, 18.11.2026)
sx0, sx1 = hx(min(cCOM, cNO, cNC)) - 14, hx(max(cCOM, cNO, cNC)) + 14
sy, sh = rows["c"] - 9, rows["d"] - rows["c"] + 14
add(f'<rect x="{sx0}" y="{sy}" width="{sx1-sx0}" height="{sh}" rx="3" fill="#2e2e2e"/>')
add(f'<path d="M{sx0+4},{sy+2} L{sx1-6},{sy-8}" stroke="#9aa" stroke-width="3" stroke-linecap="round"/>')  # Hebel
T((sx0 + sx1) / 2, sy + sh / 2 + 4, "Mikroschalter", 10, "middle", fill="#fff")
for c in (cCOM, cNC, cNO):
    add(f'<line x1="{hx(c)}" y1="{sy+sh}" x2="{hx(c)}" y2="{rows["e"]}" stroke="#999" stroke-width="2.5"/>')
for c, n, col in ((cCOM, "COM", "#1d1d1d"), (cNC, "NC", "#888"), (cNO, "NO", "#1d1d1d")):
    T(hx(c), gy + 4, n, 9, "middle", "bold", col)

# ---------------- Widerstand 330 Ω (Reihe c, Spalte 15 -> 19) und LED (Reihe e, Anode 19, Kathode 21)
cR1, cA, cK = 15, 19, 21
ry = rows["b"]
add(f'<line x1="{hx(cR1)}" y1="{ry}" x2="{hx(cA)}" y2="{ry}" stroke="#999" stroke-width="2"/>')
rmx = (hx(cR1) + hx(cA)) / 2
add(f'<rect x="{rmx-20}" y="{ry-7}" width="40" height="14" rx="6" fill="#e8cfa0" stroke="#a5865a"/>')
for i, col in enumerate(("#f57c00", "#f57c00", "#6d4c41", "#c9a400")):  # 330 Ω: orange orange braun gold
    add(f'<rect x="{rmx-13+i*7}" y="{ry-7}" width="3" height="14" fill="{col}"/>')
T(rmx, ry + 22, "330 Ω", 10, "middle", "bold")
ly2 = rows["d"] - 4
add(f'<line x1="{hx(cA)}" y1="{ly2+14}" x2="{hx(cA)}" y2="{rows["e"]}" stroke="#999" stroke-width="2"/>')
add(f'<line x1="{hx(cK)}" y1="{ly2+14}" x2="{hx(cK)}" y2="{rows["e"]}" stroke="#999" stroke-width="2"/>')
lmx = (hx(cA) + hx(cK)) / 2
add(f'<path d="M{lmx-12},{ly2+14} L{lmx-12},{ly2} A12,12 0 0 1 {lmx+12},{ly2} L{lmx+12},{ly2+14} Z" fill="#e53935" stroke="#9e1c1a"/>')
T(hx(cA), gy + 4, "A+", 9, "middle", "bold")
T(hx(cK), gy + 4, "K−", 9, "middle", "bold")
add(f'<rect x="{hx(cK)+14}" y="{ly2-6}" width="172" height="20" rx="3" fill="#fff" stroke="#ccc"/>')
T(hx(cK) + 20, ly2 + 8, "LED rot (langes Bein = Anode)", 10, "start", "bold")
T(lmx, rows["e"] + 0 - 60 - 10 + 0, "", 1)

# ---------------- Drähte
gnd, d2, d8 = pin["GND"], pin["2"], pin["8"]
wire(gnd, hole(1, "-"), "#111", mid=(gnd[0], gnd[1] - 70, hole(1, "-")[0] - 80, hole(1, "-")[1] - 60))
wire(hole(cCOM, "-"), hole(cCOM, "a"), "#111")
wire(d2, hole(cNO, "a"), "#2b6cd6", mid=(d2[0], d2[1] - 60, hole(cNO, "a")[0], hole(cNO, "a")[1] - 110))
wire(d8, hole(cR1, "a"), "#e0a800", mid=(d8[0], d8[1] - 95, hole(cR1, "a")[0], hole(cR1, "a")[1] - 120))
wire(hole(cK, "a"), hole(cK, "-"), "#111")

# ---------------- Legende / Schaltplan
lx0, ly0 = 30, 470
add(f'<rect x="{lx0}" y="{ly0}" width="330" height="200" rx="8" fill="#fff" stroke="#ccc"/>')
T(lx0 + 12, ly0 + 24, "Verbindungen", 14, w="bold")
lines = [("#111", "GND → Rail −, Rail − → COM, Kathode → Rail −"),
         ("#2b6cd6", "D2 → NO (Mitte, Spalte 6)"),
         ("#e0a800", "D8 → 330 Ω (Spalte 15)"),
         ("#999", "330 Ω (Reihe b) → LED-Anode (Spalte 19)")]
for i, (c, s) in enumerate(lines):
    y = ly0 + 50 + i * 24
    add(f'<line x1="{lx0+14}" y1="{y-4}" x2="{lx0+40}" y2="{y-4}" stroke="{c}" stroke-width="5" stroke-linecap="round"/>')
    T(lx0 + 50, y, s, 12)
T(lx0 + 12, ly0 + 158, "NC (äußerer Pin) bleibt frei. Bei den verwendeten Schaltern", 11, fill="#555")
T(lx0 + 12, ly0 + 174, "ist NO der mittlere Pin. COM–NO schließt beim Drücken.", 11, fill="#555")
T(lx0 + 12, ly0 + 190, "Ohne externe LED zeigt die Board-LED L (D13) den Zustand.", 11, fill="#555")

# Schaltplan
sx, sy0 = 470, 470
add(f'<rect x="{sx}" y="{sy0}" width="480" height="200" rx="8" fill="#fff" stroke="#ccc"/>')
T(sx + 12, sy0 + 24, "Schaltplan", 14, w="bold")
def L(x1, y1, x2, y2, c="#222", w=2): add(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{c}" stroke-width="{w}"/>')
def gnd_sym(x, y):
    L(x, y, x, y + 10); L(x - 10, y + 10, x + 10, y + 10); L(x - 6, y + 14, x + 6, y + 14); L(x - 2, y + 18, x + 2, y + 18)
# Zweig 1: interner Pull-up -> D2 -> Schalter -> GND
x1 = sx + 120
T(x1, sy0 + 50, "5 V", 11, "middle")
L(x1, sy0 + 54, x1, sy0 + 64)
add(f'<rect x="{x1-6}" y="{sy0+64}" width="12" height="30" fill="none" stroke="#222" stroke-width="2" stroke-dasharray="3 2"/>')
T(x1 + 12, sy0 + 84, "~35 kΩ intern (INPUT_PULLUP)", 10)
L(x1, sy0 + 94, x1, sy0 + 112)
add(f'<circle cx="{x1}" cy="{sy0+112}" r="3" fill="#222"/>')
L(x1 - 50, sy0 + 112, x1, sy0 + 112, "#2b6cd6"); T(x1 - 54, sy0 + 116, "D2", 11, "end", "bold")
L(x1, sy0 + 112, x1, sy0 + 128)
L(x1, sy0 + 128, x1 + 12, sy0 + 146)  # offener Kontakt
add(f'<circle cx="{x1}" cy="{sy0+128}" r="2.5" fill="#fff" stroke="#222"/>')
add(f'<circle cx="{x1}" cy="{sy0+150}" r="2.5" fill="#fff" stroke="#222"/>')
T(x1 + 16, sy0 + 142, "NO–COM", 10)
L(x1, sy0 + 152, x1, sy0 + 162); gnd_sym(x1, sy0 + 162)
# Zweig 2: D8 -> 330 -> LED -> GND
x2 = sx + 340
L(x2 - 60, sy0 + 60, x2, sy0 + 60, "#e0a800"); T(x2 - 64, sy0 + 64, "D8", 11, "end", "bold")
L(x2, sy0 + 60, x2, sy0 + 70)
add(f'<rect x="{x2-6}" y="{sy0+70}" width="12" height="30" fill="none" stroke="#222" stroke-width="2"/>')
T(x2 + 12, sy0 + 90, "330 Ω", 10)
L(x2, sy0 + 100, x2, sy0 + 116)
add(f'<path d="M{x2-9},{sy0+116} L{x2+9},{sy0+116} L{x2},{sy0+132} Z" fill="#e53935" stroke="#222"/>')
L(x2 - 9, sy0 + 132, x2 + 9, sy0 + 132)
T(x2 + 14, sy0 + 128, "LED", 10)
L(x2, sy0 + 132, x2, sy0 + 162); gnd_sym(x2, sy0 + 162)
T(sx + 470, sy0 + 192, "~10 mA bei roter LED", 10, "end", fill="#555")

add('</svg>')
open("fuss_test_breadboard.svg", "w", encoding="utf-8").write("\n".join(o))
print("ok")
