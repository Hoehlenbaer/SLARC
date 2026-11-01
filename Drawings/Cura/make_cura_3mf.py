# -*- coding: utf-8 -*-
"""
SLARC – Cura-Projekte (3MF) pro Druckteil erzeugen.   V1.0
Drucker: Anycubic Kobra Plus, Cura 5.13 (setting_version 27).

Ablauf:
- Vorlage pro Material (templates/AKP_template_<MAT>.3mf) = von Marco in Cura gespeichertes Projekt
  (Drucker, Startcode, Material). Daraus werden nur Modell und Profil ersetzt.
- Ein Profil pro Material ("PLA SLARC", "PETG SLARC") mit den Basiswerten aus BASE.
- Abweichungen pro Teil stehen als "Einstellungen pro Modell" am Objekt (in Cura 5.13 geprüft, 2026-11-01).
- Modell wird gedreht (ORIENT), mittig aufs Bett gesetzt.
Ausgabe: Drawings/STL files/AKP_<STL-Name>.3mf

Aufruf:  python make_cura_3mf.py            (alle Teile aus PARTS)
         python make_cura_3mf.py Cap Base   (nur Teile, deren STL-Name den Text enthält)
Beim Öffnen in Cura für das Profil "neu erstellen" bzw. beim zweiten Mal "aktualisieren" wählen.
"""
import os, re, struct, sys, zipfile
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
STL_DIR = os.path.join(HERE, "..", "STL files")
TPL = {"PLA": os.path.join(HERE, "templates", "AKP_template_PLA.3mf"),      # eSUN PLA+ Black
       "PETG": os.path.join(HERE, "templates", "AKP_template_PETG.3mf")}    # eSUN PETG Black

# Basiswerte je Material: (global, extruder, Einträge der Vorlage, die entfernt werden)
# PLA: Temperaturen, Bett, Lüfter, Rückzug kommen aus dem Material (eSUN PLA+: 210 °C, 60 °C, 100 %, 3 mm).
# PETG: Temperaturen 235/240/230 und Bett 80 aus Marcos Profil (Vorlage) bleiben.
COMMON_G = {"layer_height": "0.2", "layer_height_0": "0.2", "adhesion_type": "skirt",
            "print_sequence": "all_at_once", "support_enable": "False", "support_structure": "tree",
            "support_type": "buildplate"}
COMMON_E = {"wall_line_width": "0.42", "hole_xy_offset": "0.15", "xy_offset_layer_0": "-0.1",
            "brim_width": "5", "infill_pattern": "gyroid"}
BASE = {
    "PLA": (dict(COMMON_G, retraction_combing="noskin"),
            dict(COMMON_E, top_thickness="1.0", bottom_thickness="0.8", infill_sparse_density="20",
                 wall_line_count="3"),
            ("top_bottom_thickness", "material_print_temperature", "material_print_temperature_layer_0",
             "material_final_print_temperature")),
    "PETG": (dict(COMMON_G, retraction_combing="noskin"),
             dict(COMMON_E, top_bottom_thickness="1.0", infill_sparse_density="40", wall_line_count="4"),
             ()),
}

# Druckausrichtung: Drehung des STL (Makro-Koordinaten) vor dem Ablegen aufs Bett
ORIENT = {"none": np.eye(3),
          "flip_x": np.array([[1, 0, 0], [0, -1, 0], [0, 0, -1]], float)}   # Oberseite aufs Bett

# Teile: STL-Name -> (Material, Ausrichtung, Einstellungen pro Modell). Werte wie Stückliste/Druckteile.
PARTS = {
    "SLARC_Leg_Test_Stand_Base": ("PLA", "none", {"infill_sparse_density": "15", "wall_line_count": "3"}),
    "SLARC_Leg_Test_Stand_Cap": ("PLA", "flip_x", {"infill_sparse_density": "40", "wall_line_count": "4"}),
}


def read_stl(p):
    b = open(p, "rb").read()
    n = struct.unpack("<I", b[80:84])[0]
    if len(b) != 84 + 50 * n:
        raise ValueError("nur binäre STL: " + p)
    a = np.frombuffer(b[84:84 + n * 50], dtype=np.dtype([("n", "<3f4"), ("v", "<9f4"), ("a", "<u2")]))
    return a["v"].reshape(-1, 3, 3).astype(float)


def model_xml(tris, name, obj):
    v = tris.reshape(-1, 3)
    uv, idx = np.unique(np.round(v, 5), axis=0, return_inverse=True)
    idx = idx.reshape(-1, 3)
    meta = "".join('<metadata name="cura:%s" preserve="true">%s</metadata>' % kv for kv in obj.items())
    out = ['<?xml version="1.0"?>\n<model unit="millimeter" '
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


def set_vals(txt, name, vals, dels):
    txt = re.sub(r"(?m)^name = .*$", "name = " + name, txt, count=1)
    head, body = txt.split("[values]\n", 1)
    keys = set(vals) | set(dels)
    lines = [l for l in body.splitlines() if l.strip() and l.split(" = ")[0] not in keys]
    lines += ["%s = %s" % kv for kv in vals.items()]
    return head + "[values]\n" + "\n".join(sorted(lines)) + "\n\n"


def make(stl_name):
    mat, orient, obj = PARTS[stl_name]
    g_vals, e_vals, e_del = BASE[mat]
    t = read_stl(os.path.join(STL_DIR, stl_name + ".stl")) @ ORIENT[orient].T
    flat = t.reshape(-1, 3)
    c = (flat.max(0) + flat.min(0)) / 2
    t = t - np.array([c[0], c[1], flat[:, 2].min()])
    out = os.path.join(STL_DIR, "AKP_%s.3mf" % stl_name)
    with zipfile.ZipFile(TPL[mat]) as zin, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
        for it in zin.infolist():
            n = it.filename
            if n.startswith("Metadata/thumbnail"):
                continue                                   # altes Vorschaubild weg, Cura erzeugt neu
            d = zin.read(n)
            if n == "3D/3dmodel.model":
                d = model_xml(t, stl_name + ".stl", obj).encode()
            elif n == "_rels/.rels":
                d = re.sub(rb'<Relationship Target="/Metadata/thumbnail.png"[^>]*/>', b"", d)
            elif n.startswith("Cura/") and n.endswith(".inst.cfg") and b"type = quality_changes" in d:
                ext = "extruder" in n
                d = set_vals(d.decode(), "%s SLARC" % mat, e_vals if ext else g_vals, e_del if ext else ()).encode()
            zout.writestr(it, d)
    print("%-40s %-4s %-6s Höhe %5.1f mm  %s" % (os.path.basename(out), mat, orient, t[:, :, 2].max(), obj))


if __name__ == "__main__":
    sel = sys.argv[1:]
    for name in PARTS:
        if not sel or any(s in name for s in sel):
            make(name)
