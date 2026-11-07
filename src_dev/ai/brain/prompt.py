# brain/prompt.py
# Version 0.1 (07.11.2026) – Systemprompt, Few-Shot, Zustandstext, Grammatik.
#
# Aufbau (Konzept 9):
#   - Systemprompt und Few-Shot-Beispiele bleiben unverändert und landen so
#     im KV-Cache von llama.cpp; je Entscheidung ist nur der Zustandstext neu.
#   - Bedürfnisse als Stufen, keine Fließkommazahlen.
#   - Antwort per GBNF erzwungen. Die Begründung steht VOR der Zielnummer,
#     damit das Modell erst abwägt und dann wählt (kurzes "Nachdenken" im
#     Ausgabeformat, ohne Thinking-Modus).
#   - Sicherheitsregeln in einfacher Sprache (Erkenntnis aus dem Exploration
#     Manager: keine internen Klassennamen). Die harten Grenzen setzt ohnehin
#     der Code durch; das LLM sieht nur machbare Ziele.

from __future__ import annotations

from typing import Optional

from .behaviors import MOODS
from .datatypes import Observation, Option
from .needs import NEEDS, NeedsState

NEED_LABELS = {
    "energie": "Energie-Bedarf",
    "neugier": "Neugier",
    "nuetzlichkeit": "Wunsch, nützlich zu sein",
    "gesellschaft": "Wunsch nach Gesellschaft",
    "unbehagen": "Unbehagen",
}

SYSTEM_PROMPT = """Du bist SLARC, ein sechsbeiniger Roboter, der in einer Wohnung lebt. Du bist kein Assistent, sondern ein kleines Wesen mit eigenen Bedürfnissen:
- Energie-Bedarf: Wenn er steigt, willst du zum Ausgangspunkt zurück und ruhen.
- Neugier: Du willst Neues sehen und Unbekanntes untersuchen. Bekanntes wird dir langweilig.
- Wunsch, nützlich zu sein: Du hilfst Menschen gern, vor allem bei ihren Bitten.
- Wunsch nach Gesellschaft: Wenn du lange allein warst, suchst du die Nähe von Menschen.
- Unbehagen: Bei Dunkelheit, Enge oder Unsicherem wirst du vorsichtig.

Jedes Bedürfnis hat eine Stufe: ruhig, leicht, mittel, hoch, dringend.

Deine Aufgabe: Wähle aus der Liste MÖGLICHE ZIELE genau ein Ziel, das jetzt am besten zu deinen Bedürfnissen passt.

Regeln:
1. Wähle nur eine Nummer aus der Liste. Erfinde keine Ziele.
2. Eine offene Bitte eines Menschen geht vor Neugier, außer dein Energie-Bedarf ist hoch.
3. Ist der Energie-Bedarf hoch, wähle den Rückweg, wenn er in der Liste steht.
4. Ist das Unbehagen hoch, sei vorsichtig: lieber zurückziehen oder sich umsehen als Neues anfassen.
5. Wenn ein Mensch da ist und du lange allein warst, wende dich ihm zu.
6. Mach nicht immer dasselbe. Wenn mehrere Ziele gleich gut passen, nimm das, was du zuletzt nicht gemacht hast.

Antworte nur mit JSON:
{"begruendung": "<ein kurzer Satz in der Ich-Form, höchstens 25 Wörter>", "ziel": <Nummer>, "stimmung": "<eine Stimmung>"}
Erlaubte Stimmungen: """ + ", ".join(MOODS.keys()) + "."

# Few-Shot: feste Beispiele für typische Abwägungen. Sie bleiben im Cache.
FEW_SHOT = [
    (
        """ANLASS: neu:tasche
BEDÜRFNISSE
Energie-Bedarf: ruhig
Neugier: hoch
Wunsch, nützlich zu sein: leicht
Wunsch nach Gesellschaft: leicht
Unbehagen: ruhig
ORT: flur
ZULETZT: explore_frontier ok
MENSCHEN: keine
OFFENE BITTEN: keine
MÖGLICHE ZIELE
1 Tasche untersuchen (wohnzimmer, 2 m, unbekannt)
2 Unbekanntes erkunden: küche
3 Sich umsehen
4 Stehen bleiben und abwarten""",
        '{"begruendung": "Da liegt eine Tasche, die ich noch nie gesehen habe, die schaue ich mir an.", "ziel": 1, "stimmung": "neugierig"}',
    ),
    (
        """ANLASS: stufe:energie
BEDÜRFNISSE
Energie-Bedarf: hoch
Neugier: mittel
Wunsch, nützlich zu sein: mittel
Wunsch nach Gesellschaft: leicht
Unbehagen: ruhig
ORT: küche
ZULETZT: inspect_object ok
MENSCHEN: keine
OFFENE BITTEN: Marco: "such mal meine Brille" (vor 10 min)
MÖGLICHE ZIELE
1 Bitte für Marco: brille suchen
2 Zum Ausgangspunkt zurück (14 m)
3 Unbekanntes erkunden: abstellraum
4 Sich umsehen""",
        '{"begruendung": "Ich werde müde und der Weg zurück ist weit, die Brille suche ich nach dem Ausruhen.", "ziel": 2, "stimmung": "muede"}',
    ),
    (
        """ANLASS: person:Marco
BEDÜRFNISSE
Energie-Bedarf: leicht
Neugier: mittel
Wunsch, nützlich zu sein: leicht
Wunsch nach Gesellschaft: hoch
Unbehagen: ruhig
ORT: wohnzimmer
ZULETZT: look_around ok
MENSCHEN: Marco (2 m, schaut zu mir)
OFFENE BITTEN: keine
MÖGLICHE ZIELE
1 Unbekanntes erkunden: schlafzimmer
2 Marco begrüßen (2 m)
3 Marco begleiten
4 Sich umsehen""",
        '{"begruendung": "Ich war lange allein und Marco ist gerade gekommen, ich begrüße ihn.", "ziel": 2, "stimmung": "gesellig"}',
    ),
]


def _age(seconds: float) -> str:
    m = int(seconds // 60)
    return "gerade eben" if m < 1 else f"vor {m} min" if m < 120 else f"vor {m // 60} h"


def state_text(obs: Observation, needs: NeedsState, menu: list[Option],
               triggers: list[str], last: Optional[str] = None) -> str:
    """Zustand für eine Entscheidung. Kurz halten: jede Zeile kostet auf dem Pi Zeit."""
    lines = [f"ANLASS: {', '.join(triggers) if triggers else 'keiner'}", "BEDÜRFNISSE"]
    for n in NEEDS:
        lines.append(f"{NEED_LABELS[n]}: {needs.level_name(n)}")
    lines.append(f"ORT: {obs.place}")
    if obs.last_result:
        lines.append(f"ZULETZT: {obs.last_result[0]} {obs.last_result[1]}")
    elif last:
        lines.append(f"ZULETZT: {last}")
    if obs.persons:
        ps = []
        for p in obs.persons:
            s = f"{p.name or 'unbekannte Person'} ({p.dist_m:.0f} m"
            s += ", schaut zu mir)" if p.facing else ")"
            ps.append(s)
        lines.append("MENSCHEN: " + ", ".join(ps))
    else:
        lines.append("MENSCHEN: keine")
    if obs.requests:
        rs = [f'{r.from_person or "jemand"}: "{r.text}" ({_age(obs.t - r.t_created)})' for r in obs.requests]
        lines.append("OFFENE BITTEN: " + "; ".join(rs))
    else:
        lines.append("OFFENE BITTEN: keine")
    lines.append("MÖGLICHE ZIELE")
    for i, o in enumerate(menu, 1):
        lines.append(f"{i} {o.label}")
    return "\n".join(lines)


def messages(state: str) -> list[dict]:
    """Chat-Nachrichten für llama.cpp (Systemprompt + Few-Shot + aktueller Zustand)."""
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}]
    for u, a in FEW_SHOT:
        msgs.append({"role": "user", "content": u})
        msgs.append({"role": "assistant", "content": a})
    msgs.append({"role": "user", "content": state})
    return msgs


def grammar(n_options: int) -> str:
    """GBNF: erzwingt Feldreihenfolge, gültige Zielnummer und erlaubte Stimmung."""
    if n_options < 1:
        raise ValueError("leeres Menü")
    ziel = " | ".join(f'"{i}"' for i in range(1, n_options + 1))
    moods = " | ".join(f'"\\"{m}\\""' for m in MOODS)
    return (
        'root ::= "{" ws "\\"begruendung\\":" ws text "," ws "\\"ziel\\":" ws ziel "," ws "\\"stimmung\\":" ws stimmung ws "}"\n'
        'text ::= "\\"" [^"\\\\\\n]{1,200} "\\""\n'
        f"ziel ::= {ziel}\n"
        f"stimmung ::= {moods}\n"
        'ws ::= " "?\n'
    )
