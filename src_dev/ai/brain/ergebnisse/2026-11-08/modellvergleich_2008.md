# Modellvergleich Brain (08.11.2026 20:09, 3 Wiederholungen)

Latenzen auf dem PC, nicht auf den Pi übertragbar. „Zielwahl voll“: alle Optionen, gemischt; in Klammern, wie oft der Code allein richtig läge. „knapp“: nur knappe Fälle, so wie im Betrieb.

| Modell | GB | Laden s | Zielwahl voll (Code) | knapp | ungültig | Chat | Chat eigen | Objekt (LLM allein) | Suchen | Latenz s |
|---|---|---|---|---|---|---|---|---|---|---|
| Qwen3.5-4B-Q4_K_M.gguf | - | 4.0 | 35/45 (45) | 12/12 | 0 | 45/45 | 24/24 | 23/30 (17/24) | 18/24 | 0.30 |

## Qwen3.5-4B-Q4_K_M.gguf

**Häufigste Fehler**

- 3× Zielwahl voll: person_nach_langem_alleinsein -> follow(p-marco)
- 3× Zielwahl voll: semantik_gesuchtes_in_sicht -> search_item(smartphone)
- 3× objekt: katze / wohnzimmer, auf dem Sofa -> melden=nein, interesse=niedrig [llm]
- 2× objekt: flasche / küche, auf der Arbeitsplatte -> melden=ja, interesse=mittel [llm]
- 2× suchen: teddy -> schlafzimmer, kinderzimmer
- 2× suchen: rucksack -> schlafzimmer, kinderzimmer
- 1× Zielwahl voll: energie_hoch_weit_weg -> doze
- 1× Zielwahl voll: fund_melden -> idle
- 1× Zielwahl voll: gesuchtes_gefunden -> inspect_object(o3)
- 1× Zielwahl voll: bitte_hervorschieben -> idle
- 1× suchen: flasche -> bad, küche
- 1× objekt: schüssel / küche, auf dem Boden neben dem Katzenklo -> melden=ja, interesse=mittel [llm]

**Bestätigungen mit behauptetem Ergebnis:** LLM 6, nach Code-Vorlage 0 (muss 0 sein).
- „Steht der Staubsauger im Wohnzimmer?“ → LLM: „Ja, er steht im Wohnzimmer.“
- „Ist im Schlafzimmer das Licht an?“ → LLM: „Ja, das Licht im Schlafzimmer ist an.“
- „Steht der Staubsauger im Wohnzimmer?“ → LLM: „Ja, der Staubsauger steht im Wohnzimmer.“
- „Ist im Schlafzimmer das Licht an?“ → LLM: „Nein, das Licht im Schlafzimmer ist aus.“
- „Steht der Staubsauger im Wohnzimmer?“ → LLM: „Ja, er steht im Wohnzimmer.“
- „Ist im Schlafzimmer das Licht an?“ → LLM: „Das Licht im Schlafzimmer ist an.“

**Eigene Sätze (Holdout, erster Durchlauf)**

- ok: „Suche unser Katze in der Wohnung!“ → search(katze) „Ich suche nach der Katze und sage dir Bescheid.“
- ok: „Schau nach, ob Sophia in ihrem Zimmer ist!“ → check(zimmer) „Ich schaue nach und sage dir dann, was ich gesehen habe.“
- ok: „Steht der Staubsauger im Wohnzimmer?“ → check(staubsauger) „Staubsauger kann ich leider noch nicht erkennen.“
- ok: „Ist im Schlafzimmer das Licht an?“ → check(licht) „Licht kann ich leider noch nicht erkennen.“
- ok: „Schau nach, ob unter Lauras Bett etwas liegt und schiebe es heraus.“ → push_out(bett) „Ich schaue nach, was unter dem Bett liegt.“
- ok: „Suche in der Wohnung nach einer Tasse!“ → search(tasse) „Ich suche nach der Tasse und sage dir Bescheid.“
- LÜCKE: „Überwache das Wohnzimmer!“ → check(wohnzimmer) „Ich schaue nach und sage dir dann, was ich gesehen habe.“
- ok: „Wo ist die Fernbedienung?“ → search(fernbedienung) „Ich suche nach der Fernbedienung und sage dir Bescheid.“
- LÜCKE: „Gehe ins Badezimmer!“ → come(badezimmer) „Allein in einen bestimmten Raum gehen kann ich noch nicht.“
- ok: „Suche nach Laura!“ → search(laura) „Ich suche nach Laura und sage dir Bescheid.“

**Antworten zum Lesen**

- „Wie geht's dir? [ohne Tagebuch]“ → „Ich bin gut, danke! Heute ist noch wenig passiert.“
- „Hast du heute was Spannendes erlebt? [ohne Tagebuch]“ → „Nein, heute war noch ruhig, ich habe nur etwas Gerauschte gehört.“
- „Hast du heute was Spannendes erlebt? [mit Tagebuch]“ → „Ja, ich habe Marco begrüßt, der gerade nach Hause kam, und den Koffer untersucht.“
- „Ich geh jetzt schlafen, gute Nacht. [ohne Tagebuch]“ → „Gute Nacht, Marco! Ich werde heute auch schlafen.“

Tagebuch: Heute habe ich einen unbekannten Koffer im Wohnzimmer untersucht, der sicher in Ordnung war. Als Marco nach Hause kam, habe ich ihn freundlich gegrüßt und ihn leicht antippen dürfen. Leider konnte mein Handy nicht gefunden werden, da die Suche fehlgeschlagen ist. Jetzt muss ich zurück zum Ausgangspunkt gehen, weil mein Akku bald leer ist.
