# brain/sprache.py
# Version 0.1 (11.11.2026) – Deutsche Textbausteine für Vorlagen (Artikel, Räume).  # PORTABLE
#
# Alle festen Sätze, die SLARC zu Menschen sagt (Bestätigungen, Meldungen, Rückfragen),
# baut der Code. Damit sie grammatisch stimmen, kennt dieses Modul Genus und Kasus der
# Wörter, die vorkommen: Klassen der Detektion, Haushaltsdinge aus „Was ist das?“, Räume.
# Anlass (Marco, 11.11.2026): „Im Raum schlafzimmer liegt etwas, ich glaube socke.“

from __future__ import annotations

GENUS = {
    # Klassen der Detektion (perception_classes)
    "person": "f", "fahrrad": "n", "auto": "n", "motorrad": "n", "bus": "m", "lkw": "m",
    "ampel": "f", "hydrant": "m", "stoppschild": "n", "parkuhr": "f", "bank": "f", "vogel": "m",
    "katze": "f", "hund": "m", "rucksack": "m", "regenschirm": "m", "handtasche": "f",
    "koffer": "m", "flasche": "f", "tasse": "f", "schüssel": "f", "stuhl": "m", "sofa": "n",
    "topfpflanze": "f", "bett": "n", "esstisch": "m", "toilette": "f", "fernseher": "m",
    "laptop": "m", "fernbedienung": "f", "tastatur": "f", "handy": "n", "mikrowelle": "f",
    "ofen": "m", "waschbecken": "n", "kühlschrank": "m", "buch": "n", "uhr": "f", "vase": "f",
    "teddy": "m",
    # Haushaltsdinge aus „Was ist das?“ (vision/identify.py) und häufige Antworten
    "dose": "f", "schlüssel": "m", "brille": "f", "schuh": "m", "socke": "f", "kleidung": "f",
    "kabel": "n", "ladekabel": "n", "spielzeug": "n", "ball": "m", "kissen": "n", "decke": "f",
    "mülleimer": "m", "staubsauger": "m", "karton": "m", "tüte": "f", "glas": "n", "weinglas": "n",
    "teller": "m", "gabel": "f", "messer": "n", "löffel": "m", "schere": "f", "zahnbürste": "f",
    "föhn": "m", "toaster": "m", "computermaus": "f", "fernglas": "n", "lampe": "f", "pflanze": "f",
    "obst": "n", "banane": "f", "apfel": "m", "orange": "f", "karotte": "f", "brokkoli": "m",
    "brot": "n", "sandwich": "n", "pizza": "f", "kuchen": "m", "donut": "m", "hotdog": "m",
    "krawatte": "f", "handschuh": "m", "schläger": "m", "frisbee": "n", "skateboard": "n",
    "drachen": "m", "geldbörse": "f", "portemonnaie": "n", "tasche": "f", "jacke": "f",
    # Räume
    "wohnzimmer": "n", "küche": "f", "bad": "n", "flur": "m", "abstellraum": "m",
    "schlafzimmer": "n", "kinderzimmer": "n", "diele": "f", "keller": "m", "balkon": "m",
    "garten": "m", "terrasse": "f", "garage": "f", "dachboden": "m", "treppe": "f",
}

_DEF = {"nom": {"m": "der", "f": "die", "n": "das"}, "akk": {"m": "den", "f": "die", "n": "das"},
        "dat": {"m": "dem", "f": "der", "n": "dem"}}
_INDEF = {"nom": {"m": "ein", "f": "eine", "n": "ein"}, "akk": {"m": "einen", "f": "eine", "n": "ein"},
          "dat": {"m": "einem", "f": "einer", "n": "einem"}}


def genus(word: str) -> str | None:
    """Genus aus der Liste, sonst aus der Endung (Komposita: letztes Glied zählt), sonst None."""
    w = (word or "").lower().strip()
    if w in GENUS:
        return GENUS[w]
    for k in sorted(GENUS, key=len, reverse=True):     # Komposita: „ladegerätkabel“ -> kabel
        if len(k) >= 4 and w.endswith(k):
            return GENUS[k]
    if w.endswith(("ung", "heit", "keit", "schaft", "ion", "e")):
        return "f"
    if w.endswith(("chen", "lein", "um")):
        return "n"
    return None


def noun(word: str, case: str = "nom", definite: bool = True) -> str:
    """'socke' -> 'die Socke' / 'eine Socke'; unbekanntes Genus (Namen): nur 'Laura'."""
    w = (word or "").strip()
    if not w:
        return "es"
    g = genus(w)
    name = w[0].upper() + w[1:]
    if g is None:
        return name
    return f"{(_DEF if definite else _INDEF)[case][g]} {name}"


def in_room(area: str | None) -> str:
    """'küche' -> 'in der Küche', 'flur' -> 'im Flur', None -> 'hier in der Nähe'."""
    if not area or area == "unbenannt":
        return "hier in der Nähe"
    g = genus(area) or ("n" if area.endswith("zimmer") else "m")
    name = area[0].upper() + area[1:]
    return f"in der {name}" if g == "f" else f"im {name}"


def cap(text: str) -> str:
    """Satzanfang groß, Rest unverändert (str.capitalize würde Nomen klein machen)."""
    return text[:1].upper() + text[1:] if text else text
