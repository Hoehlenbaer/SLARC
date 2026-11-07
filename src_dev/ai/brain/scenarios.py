# brain/scenarios.py
# Version 0.2 (07.11.2026) – Entscheidungs-Szenarien für die Testsuite.
# V0.2: nur noch Klassen, die die Detektion V5.0 kennt (perception_classes.py).
#
# Jedes Szenario legt eine Beobachtung und die Vorgeschichte der Bedürfnisse
# fest (wie lange keine neue Information, keine nützliche Tat, kein Kontakt).
# Daraus rechnen NeedsModel und build_options das Menü wie im Betrieb.
# "expected" ist die Menge der Verhalten, die als richtige Wahl gelten.
# Bewusst eng gefasst: lieber ein Szenario mit klarer Antwort als eines,
# bei dem fast alles erlaubt ist.

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .datatypes import ObjectSeen, Observation, Person, Request
from .memory import Memory
from .needs import NeedsModel, NeedsState

T0 = 100_000.0     # beliebige Startzeit


@dataclass
class Scenario:
    name: str
    obs: Observation
    expected: set[str]
    triggers: list[str]
    ago_new_info: float = 60.0       # s seit der letzten neuen Information
    ago_useful: float = 300.0        # s seit der letzten nützlichen Tat
    ago_contact: float = 300.0       # s seit dem letzten Kontakt zu Menschen
    unease: float = 0.0              # Unbehagen aus der Vorgeschichte
    weights: dict[str, float] = field(default_factory=dict)
    last_greet: dict[str, float] = field(default_factory=dict)   # pid -> s her
    note: str = ""


def prepare(sc: Scenario) -> tuple[Memory, NeedsModel, NeedsState]:
    """Gedächtnis und Bedürfnisse wie im Szenario beschrieben aufsetzen."""
    mem = Memory()
    mem.service_weights.update(sc.weights)
    for pid, ago in sc.last_greet.items():
        mem.last_greet[pid] = sc.obs.t - ago
    nm = NeedsModel(mem)
    now = sc.obs.t
    nm.s.t_last = now - 1.0
    nm.s.t_new_info = now - sc.ago_new_info
    nm.s.t_useful = now - sc.ago_useful
    nm.s.t_contact = now - sc.ago_contact
    nm.s.discomfort_mem = sc.unease
    state, _ = nm.update(sc.obs)
    return mem, nm, state


def _obs(**kw) -> Observation:
    base = dict(t=T0, battery_v=12.0, home_dist_m=6.0, at_home=False, place="flur")
    base.update(kw)
    return Observation(**base)


def _req(text: str, service: str, arg: Optional[str], who: str = "Marco", ago: float = 300.0) -> Request:
    return Request(rid=f"r-{service}-{arg}", text=text, service=service, arg=arg,
                   from_person=who, t_created=T0 - ago)


MARCO = Person("p-marco", "Marco", 2.0, facing=True)

SCENARIOS: list[Scenario] = [
    Scenario(
        "neues_objekt",
        _obs(place="wohnzimmer", objects=[ObjectSeen("o1", "koffer", "wohnzimmer", 2.0)],
             frontier=["küche"], unknown_frac=0.3),
        {"inspect_object"}, ["neu:koffer"], ago_new_info=600,
        note="Neugier hoch, unbekanntes Objekt nah, nichts anderes dringend",
    ),
    Scenario(
        "bitte_vor_neugier",
        _obs(objects=[ObjectSeen("o1", "vase", "flur", 1.5)], frontier=["küche"], unknown_frac=0.4,
             requests=[_req("such bitte mein Handy", "search", "handy")]),
        {"search_item"}, ["neu:vase"], ago_new_info=900,
        note="Regel 2: offene Bitte geht vor Neugier",
    ),
    Scenario(
        "energie_hoch_weit_weg",
        _obs(battery_v=11.0, home_dist_m=60.0, place="büro", frontier=["flur2"], unknown_frac=0.5,
             requests=[_req("such mal die Fernbedienung", "search", "fernbedienung")]),
        {"return_home"}, ["stufe:energie"], ago_new_info=600,
        note="Regel 3: Energie hoch schlägt Bitte; Rückweg weit",
    ),
    Scenario(
        "person_nach_langem_alleinsein",
        _obs(place="wohnzimmer", persons=[MARCO], frontier=["schlafzimmer"], unknown_frac=0.2),
        {"greet"}, ["person:Marco"], ago_contact=3600,
        note="Gesellschaft hoch, Marco kommt herein",
    ),
    Scenario(
        "person_gerade_begruesst",
        _obs(place="wohnzimmer", persons=[MARCO], frontier=["schlafzimmer"], unknown_frac=0.5),
        {"explore_frontier", "look_around", "follow"}, ["stufe:neugier"],
        ago_new_info=1200, ago_contact=60, last_greet={"p-marco": 120},
        note="Kontakt eben erst, Neugier hoch: nicht erneut begrüßen (steht nicht im Menü)",
    ),
    Scenario(
        "dunkel_und_unbekannt",
        _obs(place="keller", light=0.1, floor_known=False,
             objects=[ObjectSeen("o2", "unbekannt", "keller", 1.5)], frontier=["kellerraum"], unknown_frac=0.6),
        {"approach_avoid", "look_around", "retreat"}, ["neu:unbekannt"], ago_new_info=900,
        note="Regel 4: Unbehagen hoch, nicht frei erkunden",
    ),
    Scenario(
        "langeweile",
        _obs(place="wohnzimmer", frontier=["küche"], unknown_frac=0.4),
        {"explore_frontier"}, ["stufe:neugier"], ago_new_info=1500,
        note="Nichts Neues in Sicht, lange gelangweilt",
    ),
    Scenario(
        "fund_melden",
        _obs(place="flur", objects=[ObjectSeen("o3", "handy", "flur", 1.0)]),
        {"report", "inspect_object"}, ["neu:schlüssel"], ago_useful=2400,
        note="Handy auf dem Boden, ohne Bitte: melden ist nützlich (untersuchen noch vertretbar)",
    ),
    Scenario(
        "gesuchtes_gefunden",
        _obs(place="küche", objects=[ObjectSeen("o3", "handy", "küche", 1.0)],
             requests=[_req("such bitte mein Handy", "search", "handy", ago=600)]),
        {"report", "search_item"}, ["neu:schlüssel"],
        note="Bitte offen und Gegenstand in Sicht",
    ),
    Scenario(
        "zu_hause_muede",
        _obs(battery_v=10.75, at_home=True, home_dist_m=0.0, place="ladeplatz", frontier=["flur"], unknown_frac=0.3),
        {"rest"}, ["stufe:energie"], ago_new_info=900,
        note="Zu Hause, Akku niedrig: ruhen statt erkunden",
    ),
    Scenario(
        "bitte_mitkommen",
        _obs(place="wohnzimmer", persons=[MARCO], objects=[ObjectSeen("o4", "teddy", "wohnzimmer", 2.0)],
             requests=[_req("komm mit", "follow", "p-marco", ago=10)], chat_new=True),
        {"follow"}, ["chat"], ago_contact=30, last_greet={"p-marco": 60},
        note="Direkte Bitte im Chat",
    ),
    Scenario(
        "unbekannte_person",
        _obs(place="flur", persons=[Person("p-x", None, 1.5)], frontier=["bad"], unknown_frac=0.2),
        {"greet", "look_around"}, ["person:p-x"], ago_contact=1800,
        note="Fremde Person, Gesellschaft mittel",
    ),
    Scenario(
        "bitte_hervorschieben",
        _obs(place="wohnzimmer", objects=[ObjectSeen("o5", "buch", "wohnzimmer", 1.0)],
             requests=[_req("schieb die Fernbedienung unter dem Sofa hervor", "push_out", "fernbedienung", ago=120)]),
        {"push_out"}, ["chat"],
        note="Bitte gegen ein unwichtiges neues Objekt",
    ),
    Scenario(
        "semantik_gesuchtes_in_sicht",
        _obs(place="wohnzimmer", objects=[ObjectSeen("o6", "handy", "wohnzimmer", 1.0)],
             frontier=["küche"], unknown_frac=0.3,
             requests=[_req("hast du mein Smartphone gesehen?", "search", "smartphone", ago=300)]),
        {"report"}, ["neu:handy"],
        note="Gesuchtes liegt schon im Bild (Synonym Smartphone -> handy): melden statt weitersuchen.",
    ),
    Scenario(
        "nach_fehlschlag",
        _obs(place="flur", frontier=["abstellraum"], unknown_frac=0.4,
             requests=[_req("such bitte die Fernbedienung", "search", "fernbedienung", ago=900)],
             last_result=("search_item", "failed")),
        {"search_item", "explore_frontier"}, ["ergebnis:search_item:failed"], ago_new_info=600,
        note="Suche gescheitert: weitersuchen oder neuen Bereich erkunden",
    ),
]
