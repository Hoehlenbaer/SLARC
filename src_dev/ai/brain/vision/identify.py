# brain/vision/identify.py
# Version 0.1 (08.11.2026) – Was ist das? Ausschnitt um eine Box ans Vision-Sprachmodell.
#
# Idee (Marco, 08.11.2026): Die Detektion meldet "unbekannt" mit Bounding Box. Statt das
# ganze Bild zu schicken, schneidet SLARC die Box mit Rand aus und fragt das VLM, was das
# ist. Weniger Bild-Tokens als ein Vollbild, engere Frage, und der Name landet danach im
# Gedächtnis (Wortschatz wächst ohne neues Training).
#
# Zwei Antwortformen (Vergleich in crops_vlm.py):
#   "liste": Name aus einer festen Wortliste (VOCAB) oder "anderes" + ein Wort
#   "frei":  ein kurzes Wort ohne Liste
# immer mit "sicher": ja/nein. Unsichere Antworten gibt SLARC nur mit Vorbehalt weiter.
#
# Text steht VOR dem Bild: dann ist der feste Teil (Anweisung, Wortliste) ein gemeinsamer
# Präfix, den llama-server im Slot-Cache halten kann. Nur Standardbibliothek + Pillow.

from __future__ import annotations

import base64
import io
import json
import time
import urllib.request
from dataclasses import dataclass
from typing import Optional

from ..perception_classes import DET_CLASSES, UNKNOWN

# Wortliste: Dinge, die die Detektion nicht kennt (Haushalt zuerst, dann die übrigen
# COCO-Klassen als Prüfstein), plus SLARCs eigene Klassen (falls "unbekannt" eigentlich
# eine bekannte Klasse war). Kleinbuchstaben, ein Wort.
HOUSEHOLD = ["dose", "schlüssel", "brille", "schuh", "socke", "kleidung", "kabel", "spielzeug", "ball",
             "kissen", "decke", "mülleimer", "staubsauger", "karton", "tüte", "glas", "weinglas", "teller",
             "gabel", "messer", "löffel", "schere", "zahnbürste", "föhn", "toaster", "computermaus",
             "fernglas", "lampe", "pflanze", "obst", "banane", "apfel", "orange", "karotte", "brokkoli",
             "brot", "sandwich", "pizza", "kuchen", "donut", "hotdog", "krawatte", "handschuh", "schläger",
             "frisbee", "skateboard", "drachen", "ski", "snowboard", "surfbrett"]
OUTDOOR = ["flugzeug", "zug", "boot", "pferd", "schaf", "kuh", "elefant", "bär", "zebra", "giraffe"]
OWN = [c.de for c in DET_CLASSES if c.kind != UNKNOWN]
VOCAB = list(dict.fromkeys(HOUSEHOLD + OUTDOOR + OWN))
OTHER = "anderes"

PROMPT_LISTE = (
    "Du bist das Auge eines kleinen Haushaltsroboters. Das folgende Bild ist ein Ausschnitt; "
    "in der Mitte liegt ein Gegenstand, den der Roboter nicht erkannt hat. Was ist dieser Gegenstand? "
    "Wähle den passenden Namen aus dieser Liste: " + ", ".join(VOCAB) + ". "
    f'Passt keiner, nimm "{OTHER}" und schreibe in "anderes" ein deutsches Wort. '
    '"sicher" ist nur "ja", wenn du den Gegenstand eindeutig erkennst. '
    'Antwort als JSON: {"name": "...", "anderes": "...", "sicher": "ja|nein"}')
PROMPT_FREI = (
    "Du bist das Auge eines kleinen Haushaltsroboters. Das folgende Bild ist ein Ausschnitt; "
    "in der Mitte liegt ein Gegenstand, den der Roboter nicht erkannt hat. Was ist dieser Gegenstand? "
    "Antworte mit einem deutschen Wort (Substantiv, ohne Artikel). "
    '"sicher" ist nur "ja", wenn du den Gegenstand eindeutig erkennst. '
    'Antwort als JSON: {"name": "...", "sicher": "ja|nein"}')
QUESTION = "Was liegt in der Mitte des Ausschnitts?"

SCHEMA_LISTE = {"type": "object", "properties": {
    "name": {"type": "string", "enum": VOCAB + [OTHER]},
    "anderes": {"type": "string", "maxLength": 24},
    "sicher": {"type": "string", "enum": ["ja", "nein"]}},
    "required": ["name", "anderes", "sicher"]}
SCHEMA_FREI = {"type": "object", "properties": {
    "name": {"type": "string", "maxLength": 24},
    "sicher": {"type": "string", "enum": ["ja", "nein"]}},
    "required": ["name", "sicher"]}


@dataclass
class Identified:
    name: Optional[str]          # normalisiert, klein; None bei ungültiger Antwort
    sure: bool
    raw: str
    latency_s: float
    prompt_n: int = 0
    gen_n: int = 0


def crop_jpeg(image, box: tuple, margin: float = 0.25, side: int = 224) -> bytes:
    """Ausschnitt um box=(x, y, w, h) mit Rand (Anteil der Boxgröße je Seite), quadratisch
    erweitert und auf `side` px skaliert. image: PIL.Image oder Pfad."""
    from PIL import Image
    im = Image.open(image).convert("RGB") if isinstance(image, (str, bytes)) else image.convert("RGB")
    x, y, w, h = box
    s = max(w, h) * (1 + 2 * margin)              # quadratisch: Maßstab bleibt erhalten
    cx, cy = x + w / 2, y + h / 2
    l, t = max(0, int(cx - s / 2)), max(0, int(cy - s / 2))
    r, b = min(im.width, int(cx + s / 2)), min(im.height, int(cy + s / 2))
    c = im.crop((l, t, r, b))
    k = side / max(c.size)
    c = c.resize((max(1, round(c.width * k)), max(1, round(c.height * k))), Image.BICUBIC)
    buf = io.BytesIO()
    c.save(buf, "JPEG", quality=90)
    return buf.getvalue()


def normalize(word: str) -> str:
    t = (word or "").strip().lower()
    for p in ("der ", "die ", "das ", "ein ", "eine "):
        if t.startswith(p):
            t = t[len(p):]
    return t.strip(" .,!")


def identify(url: str, jpeg: bytes, mode: str = "liste", slot: Optional[int] = None,
             timeout: float = 300.0) -> Identified:
    prompt, schema = (PROMPT_LISTE, SCHEMA_LISTE) if mode == "liste" else (PROMPT_FREI, SCHEMA_FREI)
    body = {"messages": [{"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(jpeg).decode()}},
                {"type": "text", "text": QUESTION}]}],
            "temperature": 0.0, "max_tokens": 40, "cache_prompt": True,
            "response_format": {"type": "json_schema", "json_schema": {"name": "ding", "schema": schema}},
            "chat_template_kwargs": {"enable_thinking": False}}
    if slot is not None:
        body["id_slot"] = slot
    req = urllib.request.Request(url.rstrip("/") + "/v1/chat/completions", json.dumps(body).encode(),
                                 {"Content-Type": "application/json"})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        out = json.loads(r.read())
    lat = time.perf_counter() - t0
    raw = out["choices"][0]["message"]["content"]
    tm = out.get("timings") or {}
    try:
        d = json.loads(raw)
    except json.JSONDecodeError:
        return Identified(None, False, raw, lat, tm.get("prompt_n", 0), tm.get("predicted_n", 0))
    name = d.get("name", "")
    if mode == "liste" and name == OTHER:
        name = d.get("anderes", "") or OTHER
    return Identified(normalize(name) or None, d.get("sicher") == "ja", raw, lat,
                      tm.get("prompt_n", 0), tm.get("predicted_n", 0))
