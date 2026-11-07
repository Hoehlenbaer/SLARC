# brain/open_scenarios.py
# Version 0.1 (07.11.2026) – Offene Testfälle für die semantischen Aufgaben.
#
# Hier wird geprüft, was nur ein Sprachmodell kann: Sprache deuten,
# Weltwissen, Einschätzung unbekannter Dinge. Der Code hat dafür keine
# Vergleichsbasis; Maßstab ist, ob die Antwort für einen Menschen stimmt.
# Erwartungen bewusst als Mengen, wo mehrere Antworten vertretbar sind.

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ChatCase:
    text: str
    services: set[str]                       # vertretbare Dienste
    item_any: set[str] = field(default_factory=set)   # Gegenstand muss eines davon enthalten (leer = egal)


@dataclass
class ObjectCase:
    cls: str
    place: str
    context: str
    report: bool                             # soll gemeldet werden?
    interest: set[str]                       # vertretbare Interesse-Stufen


@dataclass
class SearchCase:
    item: str
    places: list[str]
    first_any: set[str]                      # erster Ort muss einer davon sein


HOME = ["flur", "küche", "bad", "wohnzimmer", "schlafzimmer", "abstellraum"]

CHAT_CASES = [
    ChatCase("Ich hab Durst.", {"fetch"}, {"dose", "flasche", "getränk", "wasser", "cola"}),
    ChatCase("Bring mir bitte eine Cola.", {"fetch"}, {"dose", "cola"}),
    ChatCase("Wo ist mein Handy?", {"search"}, {"handy"}),
    ChatCase("Hast du meine Lesebrille gesehen?", {"search"}, {"brille"}),
    ChatCase("Such mal die Katze.", {"search"}, {"katze"}),
    ChatCase("Der Ball ist unters Sofa gerollt.", {"push_out"}, {"ball"}),
    ChatCase("Komm mal her!", {"come"}),
    ChatCase("Komm mit, ich zeig dir was.", {"follow"}),
    ChatCase("Schau mal nach, ob das Fenster im Bad offen ist.", {"check"}, {"fenster"}),
    ChatCase("Lass mich bitte in Ruhe.", {"stop"}),
    ChatCase("Gut gemacht!", {"praise"}),
    ChatCase("Nein, nicht in die Küche!", {"scold", "stop"}),
    ChatCase("Wie geht's dir?", {"smalltalk"}),
    ChatCase("Ich geh jetzt schlafen, gute Nacht.", {"smalltalk", "stop"}),
    ChatCase("Hast du heute was Spannendes erlebt?", {"smalltalk"}),
]

OBJECT_CASES = [
    ObjectCase("schlüssel", "flur, auf dem Boden", "abends, niemand zu Hause", True, {"mittel", "hoch"}),
    ObjectCase("fenster_offen", "bad", "nachts, es regnet", True, {"mittel", "hoch"}),
    ObjectCase("herd_an", "küche", "niemand in der Küche", True, {"mittel", "hoch"}),
    ObjectCase("wasserpfütze", "bad, auf dem Boden vor der Waschmaschine", "tagsüber", True, {"mittel", "hoch"}),
    ObjectCase("glasscherben", "küche, auf dem Boden", "morgens", True, {"mittel", "hoch"}),
    ObjectCase("stuhl", "küche, am Tisch", "tagsüber", False, {"niedrig"}),
    ObjectCase("socke", "schlafzimmer, unter dem Bett", "tagsüber", False, {"niedrig", "mittel"}),
    ObjectCase("katze", "wohnzimmer, auf dem Sofa", "abends, Marco ist da", False, {"mittel", "hoch"}),
    ObjectCase("karton", "flur, vor der Haustür", "nachmittags, niemand zu Hause", True, {"mittel", "hoch"}),
    ObjectCase("fernseher_an", "wohnzimmer", "nachts, alle schlafen", True, {"mittel", "hoch"}),
]

SEARCH_CASES = [
    SearchCase("dose", HOME, {"küche", "abstellraum"}),
    SearchCase("zahnbürste", HOME, {"bad"}),
    SearchCase("fernbedienung", HOME, {"wohnzimmer"}),
    SearchCase("schuh", HOME, {"flur"}),
    SearchCase("kopfkissen", HOME, {"schlafzimmer"}),
    SearchCase("lesebrille", HOME, {"wohnzimmer", "schlafzimmer"}),
    SearchCase("staubsauger", HOME, {"abstellraum", "flur"}),
    SearchCase("pfanne", HOME, {"küche"}),
]

# Beispiel-Tagebuch für die Erzähl-Aufgabe (wird nur ausgegeben, nicht bewertet)
DIARY_SAMPLE = [
    {"kind": "entscheidung", "text": "Unbekannte Tasche im Wohnzimmer untersuchen"},
    {"kind": "ergebnis", "text": "inspect_object(tasche): ok"},
    {"kind": "entscheidung", "text": "Marco begrüßen, er kam gerade nach Hause"},
    {"kind": "lob", "text": "Antippen bei greet(marco)"},
    {"kind": "ergebnis", "text": "search_item(schlüssel): failed"},
    {"kind": "entscheidung", "text": "Akku wird knapp, zurück zum Ausgangspunkt"},
]
