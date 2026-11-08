# brain/vision/crops_vlm.py
# Version 0.2 (08.11.2026) – Test: Ausschnitt um ein unbekanntes Objekt -> "Was ist das?"
# V0.2: --marks nein,ja (roter Rahmen) und --vocabs voll,haushalt als weitere Achsen.
#
# COCO hat 80 Klassen, SLARCs Detektion 40. Die übrigen 40 (Gabel, Schere, Banane,
# Zahnbürste …) sind für SLARC genau die "Unbekannten". Je Klasse bis zu k Boxen
# (Kante >= --min-px), Ausschnitt mit Rand (identify.crop_jpeg), Frage ans VLM
# (identify.identify), Vergleich mit dem COCO-Namen über erlaubte deutsche Wörter.
# Optional --known: dieselbe Probe für SLARCs eigene Klassen (Kontrolle).
#
# Kennzahlen je Server × Antwortform × Ausschnittgröße: Treffer gesamt und nur Haushalt,
# Anteil "sicher", Treffer bei sicher/unsicher (taugt "sicher" als Filter?), ungültig,
# Zeit und Prompt-Tokens je Frage. Dazu Treffer je Klasse und häufige Verwechslungen.
#
# Aufruf aus src_dev/ai (Server wie bei compare_vlm, mit --mmproj):
#   python -m brain.vision.crops_vlm --server 4B=http://127.0.0.1:8081 \
#       --coco-ann ~/datasets/coco/annotations/instances_val2017.json --coco-img ~/datasets/coco/val2017 \
#       -k 5 --sides 160,224,320 --modes liste,frei --known
# Bericht: brain/ergebnisse/<Datum>/vision_ausschnitt_<Uhrzeit>.md/.json

from __future__ import annotations

import argparse
import json
import os
import random
import statistics
import time
from collections import Counter, defaultdict

from ..perception_classes import normalize_item
from .compare_vlm import COCO2EN, ROBOT, check_server, out_paths
from .identify import crop_jpeg, identify

# COCO-Name -> erlaubte deutsche Antworten; auch als Wortende ("tennisschläger" endet auf
# "schläger"), aber nicht irgendwo im Wort ("flugzeug" zählt nicht als "zug")
EXPECT = {
    "airplane": {"flugzeug"}, "train": {"zug", "bahn", "lok"}, "boat": {"boot", "schiff"},
    "horse": {"pferd"}, "sheep": {"schaf"}, "cow": {"kuh", "rind"}, "elephant": {"elefant"},
    "bear": {"bär"}, "zebra": {"zebra"}, "giraffe": {"giraffe"},
    "tie": {"krawatte"}, "frisbee": {"frisbee", "scheibe"}, "skis": {"ski"}, "snowboard": {"snowboard"},
    "sports ball": {"ball"}, "kite": {"drachen"}, "baseball bat": {"schläger"},
    "baseball glove": {"handschuh"}, "skateboard": {"skateboard"}, "surfboard": {"surfbrett"},
    "tennis racket": {"schläger"}, "wine glass": {"weinglas", "glas"}, "fork": {"gabel"},
    "knife": {"messer"}, "spoon": {"löffel"}, "banana": {"banane", "obst"}, "apple": {"apfel", "obst"},
    "sandwich": {"sandwich", "brot", "brötchen", "toast"}, "orange": {"orange", "mandarine", "obst"},
    "broccoli": {"brokkoli", "gemüse"}, "carrot": {"karotte", "möhre", "gemüse"},
    "hot dog": {"hotdog", "würstchen", "wurst"}, "pizza": {"pizza"}, "donut": {"donut", "krapfen"},
    "cake": {"kuchen", "torte"}, "mouse": {"maus"}, "toaster": {"toaster"}, "scissors": {"schere"},
    "hair drier": {"föhn", "fön", "haartrockner"}, "toothbrush": {"zahnbürste"},
}
NOT_HOUSEHOLD = {"airplane", "train", "boat", "horse", "sheep", "cow", "elephant", "bear", "zebra", "giraffe",
                 "skis", "snowboard", "surfboard", "kite"}
EN2DE = {c.en: c.de for c in ROBOT}


def correct(coco_name: str, answer: str | None) -> bool:
    if not answer:
        return False
    if coco_name in EN2DE:                                    # Kontrolle: SLARCs eigene Klassen
        return normalize_item(answer) == EN2DE[coco_name]
    return any(answer == w or answer.endswith(w) for w in EXPECT.get(coco_name, ()))


def pick_boxes(ann_path: str, k: int, min_px: int, seed: int, known: bool) -> list[dict]:
    with open(ann_path, encoding="utf-8") as f:
        d = json.load(f)
    files = {im["id"]: im["file_name"] for im in d["images"]}
    names = {c["id"]: c["name"] for c in d["categories"]}
    by_cls = defaultdict(list)
    for a in d["annotations"]:
        name = names.get(a["category_id"])
        unknown = a["category_id"] not in COCO2EN
        if a.get("iscrowd") or not (unknown or known) or (unknown and name not in EXPECT):
            continue
        x, y, w, h = a["bbox"]
        if min(w, h) < min_px:
            continue
        by_cls[name].append({"cls": name, "file": files[a["image_id"]], "box": [x, y, w, h],
                             "unbekannt": unknown})
    rnd = random.Random(seed)
    out = []
    for name in sorted(by_cls):
        xs = by_cls[name]
        rnd.shuffle(xs)
        out += xs[:k]
    return out


def summarize(rows: list[dict]) -> dict:
    def acc(rs):
        return round(sum(r["ok"] for r in rs) / len(rs), 3) if rs else None
    unk = [r for r in rows if r["unbekannt"]]
    hh = [r for r in unk if r["cls"] not in NOT_HOUSEHOLD]
    sure = [r for r in unk if r["sicher"]]
    unsure = [r for r in unk if not r["sicher"]]
    lats = [r["latenz_s"] for r in rows]
    pns = [r["prompt_n"] for r in rows if r["prompt_n"]]
    return {"n_unbekannt": len(unk), "treffer_unbekannt": acc(unk), "treffer_haushalt": acc(hh),
            "n_bekannt": len(rows) - len(unk), "treffer_bekannt": acc([r for r in rows if not r["unbekannt"]]),
            "anteil_sicher": round(len(sure) / len(unk), 3) if unk else None,
            "treffer_wenn_sicher": acc(sure), "treffer_wenn_unsicher": acc(unsure),
            "ungueltig": sum(r["antwort"] is None for r in rows),
            "latenz_median_s": round(statistics.median(lats), 2) if lats else None,
            "prompt_tokens_median": int(statistics.median(pns)) if pns else None}


def main() -> None:
    ap = argparse.ArgumentParser(description="Was ist das? Ausschnitte unbekannter COCO-Objekte ans VLM")
    ap.add_argument("--server", action="append", default=[], help="NAME=URL, mehrfach")
    ap.add_argument("--coco-ann", required=True)
    ap.add_argument("--coco-img", required=True)
    ap.add_argument("-k", type=int, default=5, help="Boxen je Klasse")
    ap.add_argument("--min-px", type=int, default=32, help="kürzere Boxkante mindestens (Originalpixel)")
    ap.add_argument("--margin", type=float, default=0.25, help="Rand je Seite als Anteil der Boxgröße")
    ap.add_argument("--sides", default="224", help="Kantenlänge des Ausschnitts in px, kommagetrennt")
    ap.add_argument("--modes", default="liste,frei", help="liste und/oder frei")
    ap.add_argument("--marks", default="nein", help="nein und/oder ja: Box rot einrahmen")
    ap.add_argument("--vocabs", default="voll", help="voll und/oder haushalt (nur Antwortform liste)")
    ap.add_argument("--known", action="store_true", help="Kontrolle: auch SLARCs eigene Klassen")
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    try:
        import PIL  # noqa: F401
    except ImportError:
        raise SystemExit("Pillow fehlt (conda install -c conda-forge pillow).")
    servers = dict(x.split("=", 1) for x in (a.server or ["4B=http://127.0.0.1:8080"]))
    for url in servers.values():
        check_server(url)
    boxes = pick_boxes(a.coco_ann, a.k, a.min_px, a.seed, a.known)
    sides = [int(s) for s in a.sides.split(",") if s.strip()]
    modes = [m.strip() for m in a.modes.split(",") if m.strip()]
    marks = [m.strip() == "ja" for m in a.marks.split(",") if m.strip()]
    vocabs = [v.strip() for v in a.vocabs.split(",") if v.strip()]
    print(f"{len(boxes)} Ausschnitte ({sum(b['unbekannt'] for b in boxes)} unbekannt), Größen {sides}, Formen {modes}")

    res = {"boxen": len(boxes), "k": a.k, "min_px": a.min_px, "margin": a.margin, "seed": a.seed, "laeufe": {}}
    combos = [(m, v, mk, sd) for m in modes for v in (vocabs if m == "liste" else ["-"])
              for mk in marks for sd in sides]
    for sname, url in servers.items():
        for mode, vocab, mark, side in combos:
            key = f"{sname}|{mode}" + (f"-{vocab}" if mode == "liste" else "") + \
                  ("|rahmen" if mark else "") + f"|{side}"
            rows = []
            for i, b in enumerate(boxes, 1):
                jpg = crop_jpeg(os.path.join(a.coco_img, b["file"]), tuple(b["box"]), a.margin, side, mark)
                r = identify(url, jpg, mode, mark=mark, vocab=vocab if mode == "liste" else "voll")
                ok = correct(b["cls"], r.name)
                rows.append({**b, "antwort": r.name, "sicher": r.sure, "ok": ok,
                             "latenz_s": round(r.latency_s, 2), "prompt_n": r.prompt_n})
                print(f"[{key} {i}/{len(boxes)}] {'ok ' if ok else '-- '} {b['cls']:>14} -> {r.name} "
                      f"({'sicher' if r.sure else 'unsicher'}) {r.latency_s:.1f} s", flush=True)
            res["laeufe"][key] = {"summary": summarize(rows), "rows": rows}

    md, js = out_paths("vision_ausschnitt")
    lines = [f"# Was ist das? Ausschnitte ans VLM ({time.strftime('%d.%m.%Y %H:%M')})", "",
             f"{len(boxes)} Ausschnitte: je Klasse bis zu {a.k} COCO-Boxen mit kürzerer Kante ≥ {a.min_px} px, "
             f"Rand {a.margin:.0%} je Seite, quadratisch. „Unbekannt“ = die 40 COCO-Klassen, die SLARC nicht "
             "erkennt; „Haushalt“ = davon ohne Tiere/Fahrzeuge/Wintersport. Seed " + str(a.seed) + ".", "",
             "| Lauf | Treffer unbekannt | Haushalt | bekannt (Kontrolle) | sicher | Treffer wenn sicher | "
             "wenn unsicher | ungültig | Zeit (PC) | Prompt-Tokens |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for key, L in res["laeufe"].items():
        s = L["summary"]
        lines.append(f"| {key} | {s['treffer_unbekannt']} | {s['treffer_haushalt']} | {s['treffer_bekannt']} | "
                     f"{s['anteil_sicher']} | {s['treffer_wenn_sicher']} | {s['treffer_wenn_unsicher']} | "
                     f"{s['ungueltig']} | {s['latenz_median_s']} s | {s['prompt_tokens_median']} |")
    best = max(res["laeufe"], key=lambda k: res["laeufe"][k]["summary"]["treffer_unbekannt"] or 0)
    rows = res["laeufe"][best]["rows"]
    per = defaultdict(list)
    for r in rows:
        per[r["cls"]].append(r)
    lines += ["", f"**Je Klasse ({best})**", "", "| Klasse | Treffer | Antworten |", "|---|---|---|"]
    for cls in sorted(per, key=lambda c: (not per[c][0]["unbekannt"], c)):
        rs = per[cls]
        lines.append(f"| {cls}{'' if rs[0]['unbekannt'] else ' (bekannt)'} | {sum(r['ok'] for r in rs)}/{len(rs)} | "
                     + ", ".join(f"{r['antwort']}{'' if r['sicher'] else '?'}" for r in rs) + " |")
    conf = Counter((r["cls"], r["antwort"]) for r in rows if not r["ok"])
    lines += ["", "**Häufigste Verwechslungen:** " + ", ".join(f"{c} → {n} ({k})" for (c, n), k in conf.most_common(12)),
              "", "„?“ = Modell war unsicher."]
    with open(md, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    with open(js, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    print("\n" + "\n".join(lines[4:6 + len(res["laeufe"])]) + f"\n\nBericht: {md}")


if __name__ == "__main__":
    main()
