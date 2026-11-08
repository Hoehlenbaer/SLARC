# brain/vision/export_subset.py
# Version 0.1 (08.11.2026) – Kleine COCO-Auswahl zum Kopieren auf den Pi.
#
# Wählt N echte Innenraumbilder (mindestens ein Möbel oder Raum-Anker wie Sofa,
# Bett, Tisch, Toilette, Kühlschrank – nicht nur Regenschirm oder Handtasche) und
# schreibt sie mit einer passenden Mini-Annotation in einen Ordner:
#   <out>/val2017/*.jpg
#   <out>/annotations/instances_subset.json   (COCO-Format, nur diese Bilder)
# Damit laufen auf dem Pi sowohl bench_pi.py (Geschwindigkeit) als auch
# compare_vlm.py (Genauigkeit) auf denselben Bildern.
#
# Aufruf aus src_dev/ai (PC/WSL):
#   python -m brain.vision.export_subset --coco ~/datasets/coco -n 20 --out ~/vlm_pi_subset
# Danach z. B.:  scp -r ~/vlm_pi_subset <user>@<pi>:~/vlm_pi_subset

from __future__ import annotations

import argparse
import json
import os
import random
import shutil

from ..perception_classes import DET_CLASSES, FURNITURE, LANDMARK

ROOM_COCO_IDS = {c.coco_id for c in DET_CLASSES if c.kind in (LANDMARK, FURNITURE) and c.coco_id}


def main() -> None:
    ap = argparse.ArgumentParser(description="COCO-Innenraumbilder für den Pi exportieren")
    ap.add_argument("--coco", default=os.path.expanduser("~/datasets/coco"))
    ap.add_argument("-n", type=int, default=20)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default=os.path.expanduser("~/vlm_pi_subset"))
    a = ap.parse_args()

    with open(os.path.join(a.coco, "annotations", "instances_val2017.json"), encoding="utf-8") as f:
        d = json.load(f)
    room_imgs = {x["image_id"] for x in d["annotations"] if x["category_id"] in ROOM_COCO_IDS}
    ids = sorted(room_imgs)
    random.Random(a.seed).shuffle(ids)
    ids = set(ids[:a.n])

    os.makedirs(os.path.join(a.out, "val2017"), exist_ok=True)
    os.makedirs(os.path.join(a.out, "annotations"), exist_ok=True)
    images = [im for im in d["images"] if im["id"] in ids]
    for im in images:
        shutil.copy2(os.path.join(a.coco, "val2017", im["file_name"]), os.path.join(a.out, "val2017", im["file_name"]))
    sub = {"images": images, "annotations": [x for x in d["annotations"] if x["image_id"] in ids],
           "categories": d["categories"]}
    with open(os.path.join(a.out, "annotations", "instances_subset.json"), "w", encoding="utf-8") as f:
        json.dump(sub, f)
    size = sum(os.path.getsize(os.path.join(a.out, "val2017", im["file_name"])) for im in images)
    print(f"{len(images)} Bilder ({size / 1e6:.1f} MB) nach {a.out}")


if __name__ == "__main__":
    main()
