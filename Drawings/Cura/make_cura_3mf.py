# -*- coding: utf-8 -*-
"""
SLARC – Cura-Projekte (3MF) pro Druckteil erzeugen.   V1.5 (Quelle: Stückliste)
Drucker: Anycubic Kobra Plus, Cura 5.13 (setting_version 27).

Ablauf:
- Teile, Material, Füllung, Wände, Ausrichtung kommen aus Drawings/Macros/SLARC_Stueckliste.xlsx, Blatt
  Druckteile. Erzeugt werden nur Zeilen mit STL-Datei (Spalte N). Spalte O: Fläche, die aufs Bett kommt
  (-Z = wie modelliert, +Z = Oberseite, ±X, ±Y = Seitenflächen, siehe ORIENT).
  In Spalte M (Stützen / Besonderes) werden "Brim N mm" und "Tree Support" erkannt.
- Vorlage pro Material (templates/AKP_template_<MAT>.3mf) = von Marco in Cura gespeichertes Projekt
  (Drucker, Startcode, Material). Daraus werden nur Modell und Profil ersetzt.
- Ein Profil pro Material ("PLA SLARC", "PETG SLARC") mit den Basiswerten aus BASE
  (entspricht Blatt Druckeinstellungen).
- Füllung, Wände, Stützen stehen als "Einstellungen pro Modell" am Objekt (in Cura 5.13 geprüft, 2026-11-01).
  Brim ist in Cura nur global einstellbar -> steht als Benutzeränderung im Projekt, nicht im Profil.
- Vorhandene 3MF, die nicht von diesem Skript stammen (von Hand in Cura gespeichert), werden nicht
  überschrieben, außer mit --force.
Ausgabe: Drawings/STL files/AKP_<STL-Name>.3mf

Aufruf:  python make_cura_3mf.py               (alle Teile mit STL-Datei)
         python make_cura_3mf.py Cap Base      (nur Teile, deren STL-Name den Text enthält)
         python make_cura_3mf.py --force Cap   (auch von Hand gespeicherte Projekte überschreiben)
Benötigt: numpy, openpyxl.
Beim Öffnen in Cura für das Profil "neu erstellen" bzw. später "aktualisieren" wählen.

V1.5
- TPU-Vorlage (Marco, 11.11.2026). In der Vorlage ist als Material noch eSUN PETG eingestellt; deshalb setzt
  das TPU-Profil Rückzug (1.5 mm, 25 mm/s), Lüfter (60 %), Bett (50 °C) und Temperaturen (220 °C) selbst.
  Schichthöhe 0.2 fest (Vorlage: 0.1 adaptiv, erste Schicht 0.4), alle gleichzeitig statt einzeln.

V1.4
- PETG-Temperaturen aus dem Temperaturturm der Anycubic-PETG-Rolle (Marco, 10.11.2026): 250–240 °C starke Fäden,
  235 grenzwertig, 230–220 sauber; Schichthaftung auch bei 220 zäh (Bruch nur an den Kerben zwischen den Stufen).
  Jetzt 230 / erste Schicht 235 / Ende 225 statt 235 / 240 / 230 aus der Vorlage.

V1.3
- V1.2 zurückgenommen: Stützen wieder nur vom Druckbett. Tree Support führt die Äste um die untere Gabelwange
  herum bis zur oberen (in Cura geprüft, Marco 03.11.2026). So entstehen keine Stützen auf der Innenseite der
  unteren Wange, und die liegt am Servo an.
- Neue Stücklisten-Spalte P "Cura-Extras": beliebige Einstellungen pro Modell als "key=value; key=value"
  (Cura-Schlüssel, z. B. support_top_distance=0.2).

V1.2
- "Tree Support" setzt zusätzlich Stützen "überall" (support_type = everywhere, global als Benutzeränderung):
  bei den Beinteilen muss die obere Gabelwange von der unteren aus gestützt werden, nicht nur vom Bett.

V1.1
- Quelle ist die Stückliste statt der PARTS-Tabelle im Skript. ASCII-STL. Schutz für von Hand gespeicherte
  Projekte. Brim über Benutzeränderungen. PETG mit Brückeneinstellungen, erste Schicht 120 % (wie Blatt
  Druckeinstellungen).
- Ausrichtung als Bettfläche (-Z, +Z, ±X, ±Y) statt none/flip_x, damit auch seitlich liegende Teile gehen.
"""
import os, re, struct, sys, zipfile
import numpy as np
import openpyxl

HERE = os.path.dirname(os.path.abspath(__file__))
STL_DIR = os.path.join(HERE, "..", "STL files")
BOM = os.path.join(HERE, "..", "Macros", "SLARC_Stueckliste.xlsx")
MARK = "<!-- SLARC make_cura_3mf -->"
TPL = {"PLA": os.path.join(HERE, "templates", "AKP_template_PLA.3mf"),      # eSUN PLA+ Black
       "PETG": os.path.join(HERE, "templates", "AKP_template_PETG.3mf"),    # eSUN PETG Black
       "TPU": os.path.join(HERE, "templates", "AKP_template_TPU.3mf")}      # V1.5 (Material in der Vorlage: PETG!)

# Basiswerte je Material: (global, extruder, Einträge der Vorlage, die entfernt werden)
# PLA: Temperaturen, Bett, Lüfter, Rückzug kommen aus dem Material (eSUN PLA+: 210 °C, 60 °C, 100 %, 3 mm).
# PETG: Bett 80, Lüfter 40 %, Rückzug 4,5 mm aus Marcos Profil (Vorlage); Temperaturen V1.4 aus dem Temperaturturm.
COMMON_G = {"layer_height": "0.2", "layer_height_0": "0.2", "adhesion_type": "skirt",
            "print_sequence": "all_at_once", "support_enable": "False", "support_structure": "tree",
            "support_type": "buildplate", "retraction_combing": "noskin"}
COMMON_E = {"wall_line_width": "0.42", "hole_xy_offset": "0.15", "xy_offset_layer_0": "-0.1",
            "initial_layer_line_width_factor": "120", "brim_width": "8", "infill_pattern": "gyroid"}
BASE = {
    "PLA": (COMMON_G,
            dict(COMMON_E, top_thickness="1.0", bottom_thickness="0.8", infill_sparse_density="20",
                 wall_line_count="3"),
            ("top_bottom_thickness", "material_print_temperature", "material_print_temperature_layer_0",
             "material_final_print_temperature")),
    "PETG": (COMMON_G,
             dict(COMMON_E, top_bottom_thickness="1.0", infill_sparse_density="40", wall_line_count="4",
                  material_print_temperature="230.0", material_print_temperature_layer_0="235.0",
                  material_final_print_temperature="225.0",
                  bridge_settings_enabled="True", bridge_wall_speed="20", bridge_skin_speed="25",
                  bridge_fan_speed="100", bridge_skin_material_flow="100", bridge_enable_more_layers="True"),
             ()),
    # V1.5: TPU 95A, Bowden: wenig und langsamer Rückzug, Combing überall (weniger Rückzüge)
    "TPU": (dict(COMMON_G, retraction_combing="all", adaptive_layer_height_enabled="False",
                 material_bed_temperature="50"),
            dict(COMMON_E, infill_sparse_density="20", wall_line_count="5",
                 material_print_temperature="220.0", material_print_temperature_layer_0="220.0",
                 material_final_print_temperature="215.0", retraction_amount="1.5", retraction_speed="25",
                 cool_fan_enabled="True", cool_fan_speed="60.0", cool_fan_speed_min="60.0", cool_fan_speed_max="60.0"),
            ()),
}

# Druckausrichtung: welche Fläche des STL (Makro-Koordinaten) aufs Bett kommt. Drehung um 90° bzw. 180°.
ORIENT = {"-Z": np.eye(3),                                                    # wie modelliert
          "+Z": np.array([[1, 0, 0], [0, -1, 0], [0, 0, -1]], float),         # Oberseite aufs Bett (180° um X)
          "+X": np.array([[0, 0, 1], [0, 1, 0], [-1, 0, 0]], float),          # +X-Fläche aufs Bett (90° um Y)
          "-X": np.array([[0, 0, -1], [0, 1, 0], [1, 0, 0]], float),
          "+Y": np.array([[1, 0, 0], [0, 0, 1], [0, -1, 0]], float),          # +Y-Fläche aufs Bett (90° um X)
          "-Y": np.array([[1, 0, 0], [0, 0, -1], [0, 1, 0]], float)}


def parts_from_bom():
    """Blatt Druckteile -> {STL-Name: (Material, Ausrichtung, Einstellungen pro Modell, Brim-Breite oder None)}"""
    ws = openpyxl.load_workbook(BOM)["Druckteile"]
    hdr = {str(c.value).split(" ")[0]: c.column for c in ws[1] if c.value}
    get = lambda r, name: ws.cell(r, hdr[name]).value
    out = {}
    for r in range(2, ws.max_row + 1):
        stl = get(r, "STL-Datei")
        if not stl:
            continue
        mat = str(get(r, "Material")).split(" ")[0]
        orient = str(get(r, "Cura-Ausrichtung") or "-Z").strip().upper()
        if orient not in ORIENT:
            raise ValueError("Zeile %d: unbekannte Ausrichtung %r" % (r, orient))
        obj = {}
        m = re.search(r"(\d+)", str(get(r, "Füllung") or ""))
        if m:
            obj["infill_sparse_density"] = m.group(1)
        if get(r, "Wände"):
            obj["wall_line_count"] = str(int(get(r, "Wände")))
        note = str(get(r, "Stützen") or "")
        if "tree support" in note.lower():
            obj["support_enable"] = "True"
        if "Cura-Extras" in hdr:                         # V1.3: freie Einstellungen pro Modell "key=value; key=value"
            for kv in str(get(r, "Cura-Extras") or "").split(";"):
                if "=" in kv:
                    k, v = (x.strip() for x in kv.split("=", 1))
                    obj[k] = v
        m = re.search(r"Brim\s+(\d+)", note)
        out[str(stl).replace(".stl", "")] = (mat, orient, obj, m.group(1) if m else None, "support_enable" in obj)
    return out


def read_stl(p):
    b = open(p, "rb").read()
    n = struct.unpack("<I", b[80:84])[0] if len(b) >= 84 else 0
    if len(b) != 84 + 50 * n:                                # ASCII-STL
        v = re.findall(rb"vertex\s+(\S+)\s+(\S+)\s+(\S+)", b)
        return np.array(v, float).reshape(-1, 3, 3)
    a = np.frombuffer(b[84:84 + n * 50], dtype=np.dtype([("n", "<3f4"), ("v", "<9f4"), ("a", "<u2")]))
    return a["v"].reshape(-1, 3, 3).astype(float)


def model_xml(tris, name, obj):
    v = tris.reshape(-1, 3)
    uv, idx = np.unique(np.round(v, 5), axis=0, return_inverse=True)
    idx = idx.reshape(-1, 3)
    meta = "".join('<metadata name="cura:%s" preserve="true">%s</metadata>' % kv for kv in obj.items())
    out = ['<?xml version="1.0"?>\n' + MARK + '\n<model unit="millimeter" '
           'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" '
           'xmlns:cura="http://software.ultimaker.com/xml/cura/3mf/2015/10" xml:lang="en-US">\n<resources>\n'
           '<object id="1" name="%s" type="model"><metadatagroup>'
           '<metadata name="cura:drop_to_buildplate">True</metadata>'
           '<metadata name="cura:print_order">0</metadata>%s</metadatagroup><mesh><vertices>\n' % (name, meta)]
    out += ['<vertex x="%.5f" y="%.5f" z="%.5f" />\n' % tuple(p) for p in uv]
    out.append('</vertices><triangles>\n')
    out += ['<triangle v1="%d" v2="%d" v3="%d" />\n' % (a, b, c) for a, b, c in idx if a != b and b != c and a != c]
    out.append('</triangles></mesh></object>\n</resources>\n'      # Bettmitte Kobra Plus 300 x 300
               '<build><item objectid="1" transform="1 0 0 0 1 0 0 0 1 150 150 0" /></build>\n'
               '<metadata name="Application">UltiMaker Cura</metadata>\n</model>\n')
    return "".join(out)


def set_vals(txt, name, vals, dels=()):
    if name:
        txt = re.sub(r"(?m)^name = .*$", "name = " + name, txt, count=1)
    head, body = txt.split("[values]\n", 1)
    keys = set(vals) | set(dels)
    lines = [l for l in body.splitlines() if l.strip() and l.split(" = ")[0] not in keys]
    lines += ["%s = %s" % kv for kv in vals.items()]
    return head + "[values]\n" + "\n".join(sorted(lines)) + "\n\n"


def make(stl_name, part, force=False):
    mat, orient, obj, brim, tree = part
    if mat not in TPL:
        print("%-40s übersprungen: keine Cura-Vorlage für %s" % (stl_name, mat)); return
    out = os.path.join(STL_DIR, "AKP_%s.3mf" % stl_name)
    if os.path.exists(out) and not force:
        with zipfile.ZipFile(out) as z:
            if MARK.encode() not in z.read("3D/3dmodel.model")[:200]:
                print("%-40s übersprungen: von Hand gespeichertes Projekt (--force zum Überschreiben)" % stl_name)
                return
    g_vals, e_vals, e_del = BASE[mat]
    g_user, e_user = ({"adhesion_type": "brim"}, {"brim_width": brim}) if brim else ({}, {})
    t = read_stl(os.path.join(STL_DIR, stl_name + ".stl")) @ ORIENT[orient].T
    flat = t.reshape(-1, 3)
    c = (flat.max(0) + flat.min(0)) / 2
    t = t - np.array([c[0], c[1], flat[:, 2].min()])
    with zipfile.ZipFile(TPL[mat]) as zin, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
        for it in zin.infolist():
            n = it.filename
            if n.startswith("Metadata/thumbnail"):
                continue                                     # altes Vorschaubild weg, Cura erzeugt neu
            d = zin.read(n)
            if n == "3D/3dmodel.model":
                d = model_xml(t, stl_name + ".stl", obj).encode()
            elif n == "_rels/.rels":
                d = re.sub(rb'<Relationship Target="/Metadata/thumbnail.png"[^>]*/>', b"", d)
            elif n.startswith("Cura/") and n.endswith(".inst.cfg"):
                ext = b"\nposition = " in d or b"\nextruder = " in d
                if b"type = quality_changes" in d:
                    d = set_vals(d.decode(), "%s SLARC" % mat, e_vals if ext else g_vals,
                                 e_del if ext else ()).encode()
                elif b"type = user" in d:                    # Benutzeränderungen: nur Brim
                    d = set_vals(d.decode(), None, e_user if ext else g_user, ("adhesion_type", "brim_width", "support_type")).encode()
            zout.writestr(it, d)
    print("%-40s %-4s %-3s Höhe %5.1f mm  Brim %-3s %s" % (os.path.basename(out), mat, orient,
                                                           t[:, :, 2].max(), brim or "-", obj))


if __name__ == "__main__":
    args = sys.argv[1:]
    force = "--force" in args
    sel = [a for a in args if a != "--force"]
    for name, part in parts_from_bom().items():
        if not sel or any(s in name for s in sel):
            make(name, part, force)
