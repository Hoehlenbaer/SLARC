# brain/semantic.py
# Version 0.6 (08.11.2026) – Semantische Aufgaben für das LLM.
# V0.6: Bestätigungen für Aufträge (search, check, fetch, push_out, follow, come) baut der
#       Code aus Vorlagen; die LLM-Antwort bleibt nur in llm_reply. Grund: Qwen3.5-4B
#       antwortete auf „Steht der Staubsauger im Wohnzimmer?“ mit „Ja, der Staubsauger
#       steht im Wohnzimmer.“ (Lauf 08.11.2026), also mit erfundenem Ergebnis.
#       item_problem() gilt auch für check (Räume ausgenommen); claims_result() erkennt
#       Antworten, die ein Ergebnis behaupten (Heuristik, für die Testsuite). Bekannte
#       Personennamen (persons) gelten nicht als unerkennbar.
# V0.5: Gegenstandsliste inkl. Außenklassen (SLARC soll auch draußen laufen).
# V0.4: Gegenstandsliste im Chat-Prompt und Regeln aus perception_classes.py (echte
#       Klassen); item_problem() erkennt Bitten um Dinge, die SLARC nicht sehen kann.
# V0.3: Chat zweistufig. Stufe 1 deutet die Nachricht OHNE Tagebuch (Lauf 07.11.: mit
#       Tagebuch wurde "Suche nach Laura" zu search(schlüssel), Chat Qwen3 42->37/45);
#       die Antwort ist nur eine Bestätigung. Stufe 2 nur bei Smalltalk: Antwort MIT
#       Tagebuch (talk_reply). Few-Shot mit erfundenem Ausflug entfernt.
# V0.2: assess_object fragt das LLM nur für unbekannte Klassen (Gefahren, Meldenswertes
#       und Möbel per Regel); Chat bekommt die letzten Tagebuch-Einträge (ERLEBT),
#       damit Smalltalk nichts erfindet; Few-Shot für Verabschiedung.
#
# Ergebnis des ersten Tests (07.11.2026, Qwen3-4B Q4): Als Entscheider ist das
# LLM schlechter als die Code-Auswahl (36/45 gegen 42/45, Regel "Energie hoch"
# 0/3). Deshalb bekommt es hier die Fragen, die der Code nicht beantworten kann
# (Konzept Abschnitt 2, Punkt 5):
#   interpret_chat  Was will der Mensch? -> Dienst + Gegenstand + kurze Antwort
#   assess_object   Was ist das, lohnt es sich anzusehen, soll ich es melden?
#   search_places   Wo liegt so etwas wahrscheinlich? (Weltwissen)
#   narrate         Tagebuch erzählen
# Jede Aufgabe hat eigenen Systemprompt, Few-Shot und GBNF. Die Antworten werden
# vom Code geprüft und in Bitten (Request) bzw. Gewichte übersetzt; Sicherheit
# und Handlungswahl bleiben beim Code.

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Optional

from .behaviors import HAZARDS
from .perception_classes import DETECTABLE, REPORTABLE, ROUTINE, normalize_item
from .datatypes import Request

# ---------------------------------------------------------------- Grammatik-Bausteine
WS = 'ws ::= " "?\n'


def _str(name: str, lo: int, hi: int) -> str:
    return f'{name} ::= "\\"" [^"\\\\\\n]{{{lo},{hi}}} "\\""\n'


def _enum(name: str, values) -> str:
    return f"{name} ::= " + " | ".join(f'"\\"{v}\\""' for v in values) + "\n"


def _obj(fields: list[tuple[str, str]]) -> str:
    """root ::= {"a": ra, "b": rb, ...} in fester Reihenfolge."""
    parts = []
    for i, (key, rule) in enumerate(fields):
        sep = '"," ws ' if i else ""
        parts.append(f'{sep}"\\"{key}\\":" ws {rule}')
    return 'root ::= "{" ws ' + " ws ".join(parts) + ' ws "}"\n'


def _messages(system: str, shots: list[tuple[str, str]], user: str) -> list[dict]:
    m = [{"role": "system", "content": system}]
    for u, a in shots:
        m += [{"role": "user", "content": u}, {"role": "assistant", "content": a}]
    m.append({"role": "user", "content": user})
    return m


PERSONA = ("Du bist SLARC, ein sechsbeiniger Roboter, der in einer Wohnung lebt. "
           "Du bist kein Assistent, sondern ein kleines, neugieriges Wesen, das Menschen gern hilft.")

# Gegenstände, die die Perzeption erkennen kann (perception_classes.py).
KNOWN_ITEMS = DETECTABLE

# ================================================================= 1. Chat deuten
CHAT_SERVICES = {
    "search": "einen Gegenstand suchen und melden, wo er ist",
    "fetch": "etwas holen und bringen",
    "follow": "mitkommen, folgen",
    "come": "zur Person kommen",
    "push_out": "etwas unter einem Möbel hervorschieben",
    "check": "nachsehen, ob etwas so ist (z. B. Fenster offen), und berichten",
    "stop": "aufhören, in Ruhe lassen, still sein",
    "praise": "Lob",
    "scold": "Tadel, Unzufriedenheit",
    "smalltalk": "Plaudern, Frage an mich, keine Aufgabe",
    "unknown": "unverständlich",
}

CHAT_SYSTEM = (
    "AUFGABE: chat\n" + PERSONA + "\n"
    "Ein Mensch schreibt dir. Erkenne, was er von dir will.\n"
    "Mögliche Dienste:\n" + "\n".join(f"- {k}: {v}" for k, v in CHAT_SERVICES.items()) + "\n"
    "Gegenstand: das Ding oder der Ort, um den es geht, kurz und klein geschrieben, sonst leer. "
    "Wenn es passt, nimm einen dieser Namen, sonst das Wort des Menschen: " + ", ".join(KNOWN_ITEMS) + ".\n"
    "Antwort: ein kurzer, freundlicher Satz von dir in der Ich-Form, höchstens 20 Wörter. "
    "Bei einer Bitte ist das nur eine Bestätigung, bevor du handelst: Behaupte kein Ergebnis "
    "(nicht \"gefunden\", nicht \"nicht gefunden\"). Versprich nichts, was du nicht kannst.\n"
    "Eine Verabschiedung oder ein Gute-Nacht-Gruß ist smalltalk, keine Aufforderung zu kommen.\n"
    'Antworte nur mit JSON: {"dienst": "...", "gegenstand": "...", "antwort": "..."}'
)
CHAT_SHOTS = [
    ("Marco: Wo hab ich nur mein Portemonnaie hingelegt?",
     '{"dienst": "search", "gegenstand": "geldbörse", "antwort": "Ich schaue mich um und sage dir Bescheid, wenn ich es sehe."}'),
    ("Marco: Super gemacht, Kleiner!",
     '{"dienst": "praise", "gegenstand": "", "antwort": "Danke, das freut mich!"}'),
    ("Marco: Bist du müde?",
     '{"dienst": "smalltalk", "gegenstand": "", "antwort": "Ein bisschen, aber für einen kleinen Ausflug reicht es noch."}'),
    ("Marco: Ich bin dann mal weg, bis später!",
     '{"dienst": "smalltalk", "gegenstand": "", "antwort": "Bis später! Ich passe hier auf."}'),
]
CHAT_GBNF = (_obj([("dienst", "dienst"), ("gegenstand", "item"), ("antwort", "text")])
             + _enum("dienst", CHAT_SERVICES) + _str("item", 0, 40) + _str("text", 1, 160) + WS)

# Dienste aus dem Chat, die als Bitte ins Menü gehen (behaviors.SERVICES)
CHAT_TO_REQUEST = {"search": "search", "fetch": "fetch", "follow": "follow",
                   "come": "follow", "push_out": "push_out"}


@dataclass
class ChatResult:
    service: Optional[str]
    item: str = ""
    reply: str = ""
    raw: str = ""
    latency_s: float = 0.0          # beide Stufen zusammen
    error: str = ""
    talk: bool = False              # Antwort aus Stufe 2 (mit Tagebuch)
    llm_reply: str = ""             # [V0.6] Antwort des LLM aus Stufe 1, ungeprüft (nur Log/Test)


# ---------------------------------------------------------------- [V0.6] ehrliche Bestätigungen
# Geschlecht der erkennbaren Klassen für Artikel in den Vorlagen (m, f, n).
GENUS = {"person": "f", "fahrrad": "n", "auto": "n", "motorrad": "n", "bus": "m", "lkw": "m",
         "ampel": "f", "hydrant": "m", "stoppschild": "n", "parkuhr": "f", "bank": "f", "vogel": "m",
         "katze": "f", "hund": "m", "rucksack": "m", "regenschirm": "m", "handtasche": "f",
         "koffer": "m", "flasche": "f", "tasse": "f", "schüssel": "f", "stuhl": "m", "sofa": "n",
         "topfpflanze": "f", "bett": "n", "esstisch": "m", "toilette": "f", "fernseher": "m",
         "laptop": "m", "fernbedienung": "f", "tastatur": "f", "handy": "n", "mikrowelle": "f",
         "ofen": "m", "waschbecken": "n", "kühlschrank": "m", "buch": "n", "uhr": "f", "vase": "f",
         "teddy": "m"}
_ART = {"dat": {"m": "dem", "n": "dem", "f": "der"}, "akk": {"m": "den", "n": "das", "f": "die"}}

# Räume und Orte: bei check kein "kann ich nicht erkennen" (es geht um den Ort, nicht ein Ding)
ROOM_WORDS = ("zimmer", "küche", "bad", "flur", "diele", "keller", "balkon", "garten", "terrasse",
              "abstellraum", "wohnung", "garage", "dachboden", "treppe")


def _np(item: str, case: str) -> str:
    """'katze' -> 'der Katze' (Dativ); unbekannte Wörter und Namen ohne Artikel."""
    cls = normalize_item(item) or ""
    word = (cls or item or "").strip()
    if not word:
        return "es" if case == "akk" else "dem"
    g = GENUS.get(cls)
    return f"{_ART[case][g]} {word.capitalize()}" if g else word.capitalize()


def confirmation(res: "ChatResult") -> Optional[str]:
    """Bestätigung eines Auftrags aus einer Vorlage; None für Dienste ohne Auftrag."""
    svc, item = res.service, res.item
    if svc == "search":
        return f"Ich suche nach {_np(item, 'dat')} und sage dir Bescheid." if item else "Ich suche und sage dir Bescheid."
    if svc == "check":
        return "Ich schaue nach und sage dir dann, was ich gesehen habe."
    if svc == "fetch":
        return f"Ich versuche, {_np(item, 'akk')} zu holen." if item else "Ich versuche es zu holen."
    if svc == "push_out":
        return f"Ich schaue nach, was unter {_np(item, 'dat')} liegt." if item else "Ich schaue nach, was da liegt."
    if svc == "follow":
        return "Ich komme mit."
    if svc == "come":
        return "Ich komme zu dir."
    return None


_CLAIM = [re.compile(p) for p in (
    r"^\s*(ja|nein|doch)\b", r"\bgefunden\b", r"\bnicht (da|hier|zu sehen)\b",
    r"\b(steht|liegt|ist|sind|brennt)\b[^,.]*\b(im|in der|in dem|auf dem|auf der|unter dem|unter der|an|aus|offen|zu|da)\b")]


def claims_result(reply: str) -> bool:
    """Behauptet die Antwort ein Ergebnis, das SLARC noch nicht haben kann? Heuristik:
    Ja/Nein am Anfang, 'gefunden', 'steht/liegt/ist … im/an/offen'. Indirekte Fragen
    ('ich schaue, ob …') zählen nicht."""
    t = (reply or "").lower()
    if not t:
        return False
    if any(p.search(t) for p in _CLAIM[:3]):
        return True
    return " ob " not in f" {t} " and bool(_CLAIM[3].search(t))


# Stufe 2: Smalltalk-Antwort mit Tagebuch. Beispiele bewusst mit Inhalten, die nicht im
# Test-Tagebuch vorkommen, und eines mit leerem Tagebuch.
TALK_SYSTEM = (
    "AUFGABE: plaudern\n" + PERSONA + "\n"
    "Ein Mensch plaudert mit dir. Unter ERLEBT steht, was du heute wirklich getan hast. "
    "Antworte in einem kurzen, freundlichen Satz in der Ich-Form, höchstens 25 Wörter. "
    "Erzähle von Erlebnissen nur, was unter ERLEBT steht. Steht dort \"noch nichts\", "
    "erfinde nichts und sag ehrlich, dass noch nicht viel passiert ist.\n"
    'Antworte nur mit JSON: {"antwort": "..."}'
)
TALK_SHOTS = [
    ("ERLEBT: noch nichts\nMarco: Na, was hast du heute gemacht?",
     '{"antwort": "Bisher noch nicht viel, ich habe gerade erst angefangen."}'),
    ("ERLEBT: Abstellraum erkundet; Eimer im Abstellraum untersucht\nMarco: Erzähl mal, wie war dein Tag?",
     '{"antwort": "Ich war im Abstellraum und habe mir einen Eimer genau angesehen."}'),
]
TALK_GBNF = _obj([("antwort", "text")]) + _str("text", 1, 180) + WS


def _erlebt(diary: Optional[list[dict]], n: int = 5) -> str:
    """Kurze Zusammenfassung der letzten Entscheidungen und Ergebnisse fürs Chat-Prompt."""
    if not diary:
        return "noch nichts"
    items = [e.get("text", "") for e in diary if e.get("kind") in ("entscheidung", "ergebnis", "lob")]
    return "; ".join(items[-n:]) or "noch nichts"


def talk_reply(backend, text: str, sender: str = "Marco",
               diary: Optional[list[dict]] = None) -> tuple[str, float, str]:
    """Stufe 2: Smalltalk-Antwort mit Tagebuch. Rückgabe: Antwort, Latenz, Fehler."""
    user = f"ERLEBT: {_erlebt(diary)}\n{sender}: {text}"
    g = backend.generate(_messages(TALK_SYSTEM, TALK_SHOTS, user), TALK_GBNF, 80, temperature=0.4)
    if g.error:
        return "", g.latency_s, g.error
    try:
        return json.loads(g.raw)["antwort"].strip(), g.latency_s, ""
    except (json.JSONDecodeError, KeyError) as e:
        return "", g.latency_s, str(e)


def interpret_chat(backend, text: str, sender: str = "Marco",
                   diary: Optional[list[dict]] = None, persons: tuple = ()) -> ChatResult:
    """Stufe 1 ohne Tagebuch; bei Smalltalk Stufe 2 mit Tagebuch für die Antwort."""
    g = backend.generate(_messages(CHAT_SYSTEM, CHAT_SHOTS, f"{sender}: {text}"), CHAT_GBNF, 100)
    if g.error:
        return ChatResult(None, raw=g.raw, latency_s=g.latency_s, error=g.error)
    try:
        d = json.loads(g.raw)
        svc = d["dienst"] if d.get("dienst") in CHAT_SERVICES else None
        res = ChatResult(svc, d.get("gegenstand", "").strip().lower(), d.get("antwort", "").strip(),
                         g.raw, g.latency_s, "" if svc else "dienst ungültig")
        res.llm_reply = res.reply
        safe = item_problem(res, persons) or confirmation(res)   # [V0.6] Code statt LLM
        if safe:
            res.reply = safe
    except (json.JSONDecodeError, KeyError) as e:
        return ChatResult(None, raw=g.raw, latency_s=g.latency_s, error=str(e))
    if svc == "smalltalk":
        reply, lat, err = talk_reply(backend, text, sender, diary)
        res.latency_s += lat
        if reply and not err:          # sonst bleibt die Antwort aus Stufe 1
            res.reply, res.talk = reply, True
    return res



def item_problem(res: ChatResult, persons: tuple = ()) -> Optional[str]:
    """Antwort, wenn SLARC das Gewünschte nicht erkennen kann, sonst None.
    Ehrlich ablehnen statt endlos suchen."""
    if not res.item or normalize_item(res.item) is not None:
        return None
    if res.item in {p.lower() for p in persons}:     # [V0.6] bekannte Namen: Personensuche
        return None
    if res.service in ("search", "fetch", "push_out"):
        return f"{res.item.capitalize()} kann ich leider noch nicht erkennen."
    if res.service == "check" and not any(w in res.item for w in ROOM_WORDS):    # [V0.6]
        return f"{res.item.capitalize()} kann ich leider noch nicht erkennen."
    return None


def to_request(res: ChatResult, text: str, sender: str, sender_pid: Optional[str],
               now: float) -> Optional[Request]:
    """Chat-Ergebnis -> Bitte fürs Menü. praise/scold/stop behandelt der Arbiter direkt.
    Gegenstände werden auf Klassennamen abgebildet ("smartphone" -> "handy")."""
    svc = CHAT_TO_REQUEST.get(res.service or "")
    if svc is None:
        return None
    arg = sender_pid if svc == "follow" else (normalize_item(res.item) or res.item or None)
    return Request(rid=f"chat-{int(now)}", text=text, service=svc, arg=arg,
                   from_person=sender, t_created=now)


# ================================================================= 2. Objekt einschätzen
OBJECT_SYSTEM = (
    "AUFGABE: objekt\n" + PERSONA + "\n"
    "Du siehst einen Gegenstand. Schätze ein:\n"
    "- interesse: wie spannend ist es für dich, ihn anzusehen (niedrig, mittel, hoch)?\n"
    "- melden: sollst du den Menschen davon erzählen (ja, nein)? Melde Dinge, die jemand "
    "vermissen könnte, die gefährlich sind oder die nicht so sind, wie sie sein sollten. "
    "Alltägliches, das an seinem Platz ist, meldest du nicht.\n"
    "Erst kurz begründen, dann einschätzen.\n"
    'Antworte nur mit JSON: {"grund": "...", "interesse": "...", "melden": "..."}'
)
OBJECT_SHOTS = [
    ("GEGENSTAND: geldbörse\nORT: flur, auf dem Boden\nZEIT: tagsüber, niemand zu Hause",
     '{"grund": "Eine Geldbörse auf dem Boden hat jemand verloren.", "interesse": "mittel", "melden": "ja"}'),
    ("GEGENSTAND: sofa\nORT: wohnzimmer\nZEIT: abends, Marco ist da",
     '{"grund": "Das Sofa steht immer dort.", "interesse": "niedrig", "melden": "nein"}'),
]
LEVELS3 = ("niedrig", "mittel", "hoch")
OBJECT_GBNF = (_obj([("grund", "text"), ("interesse", "lvl"), ("melden", "yn")])
               + _str("text", 1, 160) + _enum("lvl", LEVELS3) + _enum("yn", ("ja", "nein")) + WS)


@dataclass
class ObjectAssessment:
    interest: Optional[str]
    report: Optional[bool]
    reason: str = ""
    raw: str = ""
    latency_s: float = 0.0
    error: str = ""
    source: str = "llm"          # "regel" oder "llm"


def rule_assessment(cls: str) -> Optional[ObjectAssessment]:
    """Bekannte Klassen entscheidet der Code; das LLM nur den offenen Rest."""
    if cls in HAZARDS:
        return ObjectAssessment("hoch", True, "Gefahr (Regel)", source="regel")
    if cls in REPORTABLE:
        return ObjectAssessment("mittel", True, "meldenswert (Regel)", source="regel")
    if cls in ROUTINE:
        return ObjectAssessment("niedrig", False, "Alltägliches (Regel)", source="regel")
    return None


def assess_object(backend, cls: str, place: str, context: str = "",
                  use_rules: bool = True) -> ObjectAssessment:
    if use_rules:
        r = rule_assessment(cls)
        if r is not None:
            return r
    user = f"GEGENSTAND: {cls}\nORT: {place}" + (f"\nZEIT: {context}" if context else "")
    g = backend.generate(_messages(OBJECT_SYSTEM, OBJECT_SHOTS, user), OBJECT_GBNF, 100)
    if g.error:
        return ObjectAssessment(None, None, raw=g.raw, latency_s=g.latency_s, error=g.error)
    try:
        d = json.loads(g.raw)
        return ObjectAssessment(d["interesse"], d["melden"] == "ja", d.get("grund", ""), g.raw, g.latency_s)
    except (json.JSONDecodeError, KeyError) as e:
        return ObjectAssessment(None, None, raw=g.raw, latency_s=g.latency_s, error=str(e))


# ================================================================= 3. Wo suchen?
SEARCH_SYSTEM = (
    "AUFGABE: suchen\n" + PERSONA + "\n"
    "Du sollst einen Gegenstand finden. Wähle aus den bekannten Orten die, an denen er am "
    "wahrscheinlichsten liegt, den wahrscheinlichsten zuerst (ein bis drei Orte). "
    "Nutze dein Wissen darüber, wo Menschen solche Dinge aufbewahren oder liegen lassen.\n"
    'Antworte nur mit JSON: {"grund": "...", "orte": ["...", "..."]}'
)
SEARCH_SHOTS = [
    ("GEGENSTAND: handtuch\nORTE: flur, küche, bad, wohnzimmer",
     '{"grund": "Handtücher hängen meist im Bad, manchmal in der Küche.", "orte": ["bad", "küche"]}'),
]


def search_gbnf(places: list[str]) -> str:
    return (_obj([("grund", "text"), ("orte", "orte")])
            + 'orte ::= "[" ws ort ("," ws ort)? ("," ws ort)? ws "]"\n'
            + _enum("ort", places) + _str("text", 1, 160) + WS)


@dataclass
class SearchPlan:
    places: list[str] = field(default_factory=list)
    reason: str = ""
    raw: str = ""
    latency_s: float = 0.0
    error: str = ""


def search_places(backend, item: str, places: list[str]) -> SearchPlan:
    user = f"GEGENSTAND: {item}\nORTE: {', '.join(places)}"
    g = backend.generate(_messages(SEARCH_SYSTEM, SEARCH_SHOTS, user), search_gbnf(places), 100)
    if g.error:
        return SearchPlan(raw=g.raw, latency_s=g.latency_s, error=g.error)
    try:
        d = json.loads(g.raw)
        seen, out = set(), []
        for p in d["orte"]:          # Doppelte entfernen, Reihenfolge behalten
            if p in places and p not in seen:
                seen.add(p)
                out.append(p)
        return SearchPlan(out, d.get("grund", ""), g.raw, g.latency_s)
    except (json.JSONDecodeError, KeyError) as e:
        return SearchPlan(raw=g.raw, latency_s=g.latency_s, error=str(e))


# ================================================================= 4. Tagebuch
NARRATE_SYSTEM = (
    "AUFGABE: tagebuch\n" + PERSONA + "\n"
    "Erzähle in der Ich-Form und in wenigen Sätzen, was du erlebt hast. Nur was in den "
    "Einträgen steht, nichts dazuerfinden. Freundlich, ein bisschen verspielt, höchstens 80 Wörter.\n"
    'Antworte nur mit JSON: {"text": "..."}'
)
NARRATE_GBNF = _obj([("text", "text")]) + _str("text", 1, 600) + WS


def narrate(backend, entries: list[dict]) -> tuple[str, float, str]:
    """entries: Tagebuch-Einträge aus Memory.diary (kind, text, …). Rückgabe: Text, Latenz, Fehler."""
    lines = [f"- {e.get('kind', '')}: {e.get('text', '')}" for e in entries[-15:]]
    g = backend.generate(_messages(NARRATE_SYSTEM, [], "EINTRÄGE\n" + "\n".join(lines)),
                         NARRATE_GBNF, 220, temperature=0.5)
    if g.error:
        return "", g.latency_s, g.error
    try:
        return json.loads(g.raw)["text"].strip(), g.latency_s, ""
    except (json.JSONDecodeError, KeyError) as e:
        return "", g.latency_s, str(e)
