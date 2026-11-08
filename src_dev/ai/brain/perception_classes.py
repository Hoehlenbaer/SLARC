# brain/perception_classes.py
# Version 0.2 (08.11.2026) – Was die Perzeption wirklich erkennen kann.
# V0.2: Außenklassen gelten als erkennbar (SLARC soll auch draußen laufen); DETECTABLE
#       statt INDOOR für Chat und Synonyme. Bäume erkennt die Detektion vermutlich als
#       "topfpflanze" (bewusst so akzeptiert, Marco 08.11.2026).
#
# Einzige Quelle für Klassen im Brain. Grundlage: FusedHexapodModel V5.0,
# Detektion mit 40 COCO-Klassen + "unbekannt" (ROBOT_CAT_IDS in
# Documentation/Models/FusedHexapodModel/FusedHexapodModel_V5_0-Phase-1.py),
# Segmentierung mit 6 geometrischen Klassen.
#
# Nicht erkennbar (Stand V5.0): Türen, Fenster, Treppen als Objekt (nur
# geometrisch als STEP), Dosen, Schlüssel, Brillen, Geldbörsen, Zustände wie
# "Herd an" oder "Licht an", Identität von Personen.
# Ändert sich die Detektion, wird nur diese Datei angepasst.

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# Art der Klasse
LANDMARK = "anker"        # steht fest, eignet sich zur Orientierung und zum Erkennen des Raums
FURNITURE = "moebel"      # Möbel, wird aber verschoben (Stuhl)
ITEM = "ding"             # tragbar
LIVING = "lebewesen"
OUTDOOR = "draussen"      # vor allem draußen; dort auch Anker zur Orientierung (Bank, Hydrant, Ampel)
UNKNOWN = "unbekannt"


@dataclass(frozen=True)
class DetClass:
    idx: int                  # Ausgabe-Index der Detektion
    coco_id: Optional[int]
    en: str
    de: str                   # Name im Brain (klein, ohne Leerzeichen)
    kind: str
    reportable: bool = False  # vermisst man so etwas, lohnt eine Meldung des Fundorts
    rooms: tuple = ()         # wo so etwas typischerweise ist (Suchhilfe ohne LLM)


DET_CLASSES = [
    DetClass(0, 1, "person", "person", LIVING, False, ("wohnzimmer", "küche")),
    DetClass(1, 2, "bicycle", "fahrrad", OUTDOOR),
    DetClass(2, 3, "car", "auto", OUTDOOR),
    DetClass(3, 4, "motorcycle", "motorrad", OUTDOOR),
    DetClass(4, 6, "bus", "bus", OUTDOOR),
    DetClass(5, 8, "truck", "lkw", OUTDOOR),
    DetClass(6, 10, "traffic light", "ampel", OUTDOOR),
    DetClass(7, 11, "fire hydrant", "hydrant", OUTDOOR),
    DetClass(8, 13, "stop sign", "stoppschild", OUTDOOR),
    DetClass(9, 14, "parking meter", "parkuhr", OUTDOOR),
    DetClass(10, 15, "bench", "bank", OUTDOOR),
    DetClass(11, 16, "bird", "vogel", LIVING),
    DetClass(12, 17, "cat", "katze", LIVING),
    DetClass(13, 18, "dog", "hund", LIVING),
    DetClass(14, 27, "backpack", "rucksack", ITEM, True, ("flur", "kinderzimmer")),
    DetClass(15, 28, "umbrella", "regenschirm", ITEM, False, ("flur",)),
    DetClass(16, 31, "handbag", "handtasche", ITEM, True, ("flur", "schlafzimmer")),
    DetClass(17, 33, "suitcase", "koffer", ITEM, False, ("abstellraum", "schlafzimmer")),
    DetClass(18, 44, "bottle", "flasche", ITEM, False, ("küche", "abstellraum")),
    DetClass(19, 47, "cup", "tasse", ITEM, False, ("küche", "wohnzimmer")),
    DetClass(20, 51, "bowl", "schüssel", ITEM, False, ("küche",)),
    DetClass(21, 62, "chair", "stuhl", FURNITURE, False, ("küche", "wohnzimmer")),
    DetClass(22, 63, "couch", "sofa", LANDMARK, False, ("wohnzimmer",)),
    DetClass(23, 64, "potted plant", "topfpflanze", LANDMARK, False, ("wohnzimmer",)),
    DetClass(24, 65, "bed", "bett", LANDMARK, False, ("schlafzimmer", "kinderzimmer")),
    DetClass(25, 67, "dining table", "esstisch", LANDMARK, False, ("küche", "wohnzimmer")),
    DetClass(26, 70, "toilet", "toilette", LANDMARK, False, ("bad",)),
    DetClass(27, 72, "tv", "fernseher", LANDMARK, False, ("wohnzimmer",)),
    DetClass(28, 73, "laptop", "laptop", ITEM, True, ("wohnzimmer", "kinderzimmer")),
    DetClass(29, 75, "remote", "fernbedienung", ITEM, True, ("wohnzimmer",)),
    DetClass(30, 76, "keyboard", "tastatur", ITEM, False, ("kinderzimmer", "wohnzimmer")),
    DetClass(31, 77, "cell phone", "handy", ITEM, True, ("wohnzimmer", "küche", "schlafzimmer")),
    DetClass(32, 78, "microwave", "mikrowelle", LANDMARK, False, ("küche",)),
    DetClass(33, 79, "oven", "ofen", LANDMARK, False, ("küche",)),
    DetClass(34, 81, "sink", "waschbecken", LANDMARK, False, ("küche", "bad")),
    DetClass(35, 82, "refrigerator", "kühlschrank", LANDMARK, False, ("küche",)),
    DetClass(36, 84, "book", "buch", ITEM, False, ("wohnzimmer", "schlafzimmer", "kinderzimmer")),
    DetClass(37, 85, "clock", "uhr", LANDMARK, False, ()),
    DetClass(38, 86, "vase", "vase", ITEM, False, ("wohnzimmer",)),
    DetClass(39, 88, "teddy bear", "teddy", ITEM, False, ("kinderzimmer",)),
    DetClass(40, None, "unknown", "unbekannt", UNKNOWN),
]

BY_DE = {c.de: c for c in DET_CLASSES}

# Umgangssprache -> Klassenname (nur Fälle, die eindeutig dieselbe Klasse meinen)
SYNONYMS = {
    "smartphone": "handy", "telefon": "handy", "mobiltelefon": "handy",
    "tv": "fernseher", "glotze": "fernseher", "couch": "sofa",
    "becher": "tasse", "kaffeetasse": "tasse", "tasche": "handtasche",
    "kuscheltier": "teddy", "teddybär": "teddy", "plüschtier": "teddy",
    "pflanze": "topfpflanze", "blume": "topfpflanze", "notebook": "laptop",
    "schulranzen": "rucksack", "ranzen": "rucksack", "schirm": "regenschirm",
    "napf": "schüssel", "tisch": "esstisch", "klo": "toilette", "wc": "toilette",
    "mieze": "katze", "kater": "katze", "mensch": "person",
    "rad": "fahrrad", "velo": "fahrrad", "wagen": "auto", "pkw": "auto", "parkbank": "bank",
    "baum": "topfpflanze", "busch": "topfpflanze", "strauch": "topfpflanze",
}

DETECTABLE = [c.de for c in DET_CLASSES if c.kind != UNKNOWN]
INDOOR = [c.de for c in DET_CLASSES if c.kind not in (OUTDOOR, UNKNOWN)]
REPORTABLE = {c.de for c in DET_CLASSES if c.reportable}
ROUTINE = {c.de for c in DET_CLASSES if c.kind in (LANDMARK, FURNITURE)}
SEARCHABLE = {c.de for c in DET_CLASSES if c.kind in (ITEM, LIVING)}

# Räume an festen Dingen erkennen (Anker -> Raum). Nur eindeutige Anker.
ROOM_ANCHORS = {"toilette": "bad", "kühlschrank": "küche", "ofen": "küche", "mikrowelle": "küche",
                "bett": "schlafzimmer", "sofa": "wohnzimmer", "fernseher": "wohnzimmer"}


def normalize_item(text: Optional[str]) -> Optional[str]:
    """Freier Gegenstandsname -> Klassenname, oder None, wenn SLARC so etwas nicht erkennen kann."""
    if not text:
        return None
    t = text.lower().strip().replace("_", " ")
    for prefix in ("mein ", "meine ", "meinen ", "die ", "der ", "das ", "den ", "eine ", "ein ", "einen ", "unsere ", "unser "):
        if t.startswith(prefix):
            t = t[len(prefix):]
    t = t.replace(" ", "")
    if t in BY_DE and BY_DE[t].kind != UNKNOWN:
        return t
    if t in SYNONYMS:
        return SYNONYMS[t]
    # Teilwort: "lesebrille" -> nichts, "fernsehfernbedienung" -> fernbedienung
    for de in DETECTABLE:
        if len(de) >= 4 and de in t:
            return de
    return None


def is_detectable(text: Optional[str]) -> bool:
    return normalize_item(text) is not None


def typical_rooms(item: str) -> tuple:
    c = BY_DE.get(normalize_item(item) or "")
    return c.rooms if c else ()
