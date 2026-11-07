# brain/behaviors.py
# Version 0.3 (07.11.2026) – Verhaltenskatalog, Menübau und Code-Auswahl.
# V0.3: Gefahren (HAZARDS) immer melden, unabhängig von Energie und LLM;
#       ROUTINE-Klassen (Möbel) gelten als nicht meldenswert.
# V0.2: Bitte <-> Fund im Code verknüpft, Energie "hoch" filtert das Menü,
#       close_options() für knappe Fälle (nur diese gehen ans LLM).
#
# Der Code baut aus Beobachtung, Bedürfnissen und Gedächtnis ein Menü
# machbarer Ziele (Konzept Abschnitt 5). Das LLM wählt daraus nur per
# Nummer; fällt es aus, wählt select_fallback() gewichtet zufällig.
# Sicherheits-Veto (safety.py) filtert vorher.

from __future__ import annotations

import math
import random
from typing import Optional

from .datatypes import Observation, Option
from .memory import Memory
from .needs import NeedsState
from .safety import SafetyState

# Dienste für "Nützlichkeit" (Konzept 4.3). Nur diese darf das LLM wählen.
SERVICES = {
    "search": "Gegenstand suchen und melden",
    "report": "Auffälliges melden",
    "greet": "Menschen begrüßen",
    "follow": "Menschen begleiten",
    "push_out": "Dinge unter Möbeln hervorschieben",
    "fetch": "kleine Dinge holen und bringen",
}
SERVICES_ENABLED = {"search", "report", "greet", "follow", "push_out"}   # fetch erst mit Meilenstein Dose

# Klassen, deren Fund gemeldet wird (Annahme, an die 41 Detektionsklassen anpassen)
REPORTABLE = {"schlüssel", "handy", "geldbörse", "brille", "fernbedienung",
              "fenster_offen", "tür_offen", "licht_an", "dose"}
# Gefahren: immer und sofort melden, per Regel (Modellvergleich 07.11.: Qwen3.5 und
# Gemma meldeten den eingeschalteten Herd 3/3 nicht). Annahme, an die Detektion anpassen.
HAZARDS = {"herd_an", "bügeleisen_an", "wasserpfütze", "glasscherben", "rauch", "feuer"}
# Alltägliches am festen Platz: nicht melden, kaum interessant (Annahme)
ROUTINE = {"stuhl", "tisch", "sofa", "bett", "schrank", "regal", "lampe", "tür", "fenster",
           "teppich", "pflanze", "fernseher", "kühlschrank", "waschmaschine"}
REPORT_REPEAT_S = 3600.0        # dasselbe Objekt frühestens nach 1 h wieder melden
HAZARD_REPEAT_S = 600.0         # Gefahr alle 10 min erneut, solange sie besteht
GREET_REPEAT_S = 600.0          # dieselbe Person frühestens nach 10 min wieder begrüßen
ENERGY_EXEMPT = {"return_home", "rest", "retreat", "idle"}
ENERGY_FILTER_LEVEL = 3         # ab "hoch" nur noch ENERGY_EXEMPT im Menü (Test 07.11.: LLM ignorierte Regel 3)
CLOSE_MARGIN = 0.15             # knapp = Nutzen höchstens so weit unter dem besten
CLOSE_MAX = 3
MATCH_BONUS = 0.15              # Fund passt zu offener Bitte: vor der weiteren Suche
MENU_MAX = 7                    # mehr Optionen überfordern ein 4B-Modell (Annahme, testen)
INSPECT_MAX = 2
FRONTIER_MAX = 2

# Stimmungen: Ausgabe des LLM -> Ausdrucksparameter für den ESP32 (Konzept 6).
# Höhe relativ zur Stehhöhe, Tempo relativ, Idle-Amplitude 0…1, LED-Farbe.
MOODS = {
    "ruhig":      {"height": 0.0,  "speed": 0.8, "idle": 0.3, "led": "warmweiss"},
    "neugierig":  {"height": 0.1,  "speed": 0.7, "idle": 0.6, "led": "cyan"},
    "eifrig":     {"height": 0.1,  "speed": 1.0, "idle": 0.5, "led": "gruen"},
    "gesellig":   {"height": 0.05, "speed": 0.9, "idle": 0.7, "led": "gelb"},
    "verspielt":  {"height": 0.05, "speed": 1.0, "idle": 0.9, "led": "magenta"},
    "vorsichtig": {"height": -0.2, "speed": 0.5, "idle": 0.2, "led": "orange"},
    "aengstlich": {"height": -0.3, "speed": 0.4, "idle": 0.1, "led": "violett"},
    "muede":      {"height": -0.25, "speed": 0.5, "idle": 0.1, "led": "blau_dunkel"},
}


def _w(mem: Memory, service: Optional[str]) -> float:
    return mem.weight(service)


def _norm(s: str) -> str:
    return s.lower().replace("_", " ").replace("-", " ").strip()


def matches(cls: str, wanted: Optional[str]) -> bool:
    """Passt eine erkannte Klasse zum gesuchten Gegenstand? Einfacher Teilwort-
    Vergleich ("brille" passt zu "lesebrille"). Synonyme ("Cola" -> "dose") liefert
    später semantic.normalize_item() über das LLM."""
    if not wanted:
        return False
    a, b = _norm(cls), _norm(wanted)
    if len(a) < 3 or len(b) < 3:
        return a == b
    return a in b or b in a


def build_options(obs: Observation, needs: NeedsState, mem: Memory,
                  safety: SafetyState) -> list[Option]:
    """Machbare Ziele mit Code-Bewertung, nach Nutzen sortiert, höchstens MENU_MAX."""
    if safety.stop:
        return []
    now = obs.t
    v = needs.values
    unease = v["unbehagen"]
    opts: list[Option] = []

    def add(o: Option) -> None:
        if safety.allows(o.behavior):
            opts.append(o)

    # --- Grundverhalten ---
    add(Option("idle", None, "Stehen bleiben und abwarten", 0.1))
    add(Option("look_around", None, "Sich umsehen", 0.15 + 0.3 * v["neugier"] + 0.2 * unease))

    # --- Neugier ---
    for area in obs.frontier[:FRONTIER_MAX]:
        h = mem.habituation(f"area:{area}", now)
        # etwas unter "Objekt untersuchen": ein konkretes neues Ding zieht stärker als eine Fläche
        u = 0.8 * v["neugier"] * (1 - unease) * (1 - 0.5 * h)
        add(Option("explore_frontier", area, f"Unbekanntes erkunden: {area}", u))

    novel = []
    for o in obs.objects:
        if not o.reachable:
            continue
        h = mem.habituation(f"obj:{o.oid}", now)
        if h < 0.7:
            novel.append((h, o))
    novel.sort(key=lambda x: (x[0], x[1].dist_m))
    for h, o in novel[:INSPECT_MAX]:
        state = "unbekannt" if h < 0.1 else "kaum bekannt"
        if o.moved:
            state += ", hat sich bewegt"
        where = f"{o.place}, {o.dist_m:.0f} m"
        if unease >= 0.4:
            # Konflikt Neugier gegen Unbehagen: vorsichtig annähern
            u = v["neugier"] * (1 - h) * 0.8
            add(Option("approach_avoid", o.oid, f"Vorsichtig an {o.cls} herantasten ({where}, {state})", u))
        else:
            u = v["neugier"] * (1 - h) * (1 - unease)
            add(Option("inspect_object", o.oid, f"{o.cls.capitalize()} untersuchen ({where}, {state})", u))

    # --- Bitten von Menschen (Nützlichkeit) ---
    for r in obs.requests:
        if r.service not in SERVICES_ENABLED:
            continue
        who = f" für {r.from_person}" if r.from_person else ""
        u = (0.5 + 0.5 * v["nuetzlichkeit"]) * _w(mem, r.service)
        if r.service == "search":
            found = [o for o in obs.objects if matches(o.cls, r.arg)]
            for o in found:
                # das Gesuchte ist schon im Bild: melden statt weitersuchen
                add(Option("report", o.oid, f"Melden: {o.cls} gefunden ({o.place}) – passt zur Bitte{who} ({r.arg})",
                           u + MATCH_BONUS, "search"))
            add(Option("search_item", r.arg, f"Bitte{who}: {r.arg} suchen", u * (0.7 if found else 1.0), "search"))
        elif r.service == "push_out":
            add(Option("push_out", r.arg, f"Bitte{who}: {r.arg} hervorschieben", u, "push_out"))
        elif r.service == "follow":
            add(Option("follow", r.arg, f"Bitte{who}: mitkommen", u, "follow"))

    # --- Gefahren: immer melden (Regel, nicht gedämpft, nicht gefiltert) ---
    for o in obs.objects:
        if o.cls in HAZARDS and now - mem.reported.get(o.oid, -1e9) > HAZARD_REPEAT_S:
            add(Option("report", o.oid, f"GEFAHR melden: {o.cls} ({o.place})", 1.0, "hazard"))

    # --- Meldenswertes (Nützlichkeit) ---
    for o in obs.objects:
        if any(x.behavior == "report" and x.arg == o.oid for x in opts):
            continue    # schon als Treffer zu einer Bitte im Menü
        if o.cls in REPORTABLE and now - mem.reported.get(o.oid, -1e9) > REPORT_REPEAT_S:
            u = (0.3 + 0.6 * v["nuetzlichkeit"]) * _w(mem, "report")
            add(Option("report", o.oid, f"Melden: {o.cls} gefunden ({o.place})", u, "report"))

    # --- Gesellschaft ---
    for p in obs.persons:
        name = p.name or "unbekannte Person"
        if now - mem.last_greet.get(p.pid, -1e9) > GREET_REPEAT_S:
            u = (0.2 + 0.8 * v["gesellschaft"]) * _w(mem, "greet")
            add(Option("greet", p.pid, f"{name} begrüßen ({p.dist_m:.0f} m)", u, "greet"))
        if not any(r.service == "follow" and r.arg == p.pid for r in obs.requests):
            u = 0.6 * v["gesellschaft"] * _w(mem, "follow")
            add(Option("follow", p.pid, f"{name} begleiten", u, "follow"))

    # --- Energie ---
    if not obs.at_home and obs.home_dist_m is not None and needs.levels["energie"] >= 1:
        add(Option("return_home", None, f"Zum Ausgangspunkt zurück ({obs.home_dist_m:.0f} m)", v["energie"]))
    if obs.at_home:
        add(Option("rest", None, "Hinlegen und ausruhen", 0.1 + 0.9 * v["energie"]))

    # --- Sicherheit ---
    if unease >= 0.5:
        add(Option("retreat", None, "Vorsichtig zurückziehen", unease))

    # Müdigkeit dämpft alles außer Heimweg, Ruhe, Rückzug und Abwarten (Regel 3 auch für die Code-Auswahl)
    damp = 1.0 - 0.6 * v["energie"]
    for o in opts:
        if o.behavior not in ENERGY_EXEMPT and o.service != "hazard":
            o.utility *= damp

    if needs.levels["energie"] >= ENERGY_FILTER_LEVEL:
        opts = [o for o in opts if o.behavior in ENERGY_EXEMPT or o.service == "hazard"]

    opts.sort(key=lambda o: o.utility, reverse=True)
    menu = opts[:MENU_MAX]
    # Heimweg nie aus dem Menü fallen lassen, wenn Energie spürbar ist
    home = next((o for o in opts if o.behavior == "return_home"), None)
    if home and home not in menu:
        menu[-1] = home
    return menu


def close_options(menu: list[Option], margin: float = CLOSE_MARGIN,
                  k: int = CLOSE_MAX) -> list[Option]:
    """Die knappen Fälle: Optionen nahe am besten Nutzen (Menü ist sortiert).
    Nur wenn hier mehr als eine übrig bleibt, lohnt sich das LLM als Schiedsrichter."""
    if not menu:
        return []
    best = max(o.utility for o in menu)
    close = [o for o in menu if o.utility >= best - margin]
    close.sort(key=lambda o: o.utility, reverse=True)
    return close[:k]


def select_fallback(menu: list[Option], rng: Optional[random.Random] = None,
                    temperature: float = 0.1) -> Optional[Option]:
    """Code-Auswahl ohne LLM: Softmax über den Nutzen. Bei fast gleichwertigen
    Optionen nicht immer dieselbe (Konzept 6, Zufall)."""
    if not menu:
        return None
    rng = rng or random
    m = max(o.utility for o in menu)
    ws = [math.exp((o.utility - m) / temperature) for o in menu]
    return rng.choices(menu, weights=ws, k=1)[0]
