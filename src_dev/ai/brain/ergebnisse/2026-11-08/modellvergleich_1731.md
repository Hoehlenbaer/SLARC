# Modellvergleich Brain (08.11.2026 17:32, 3 Wiederholungen)

Latenzen auf dem PC, nicht auf den Pi übertragbar. „Zielwahl voll“: alle Optionen, gemischt; in Klammern, wie oft der Code allein richtig läge. „knapp“: nur knappe Fälle, so wie im Betrieb.

| Modell | GB | Laden s | Zielwahl voll (Code) | knapp | ungültig | Chat | Chat eigen | Objekt (LLM allein) | Suchen | Latenz s |
|---|---|---|---|---|---|---|---|---|---|---|
| Qwen3.5-4B-Q4_K_M.gguf | - | 0.0 | 35/45 (45) | 12/12 | 0 | 45/45 | 24/24 | 26/30 (20/24) | 21/24 | 0.28 |

## Qwen3.5-4B-Q4_K_M.gguf

**Häufigste Fehler**

- 3× Zielwahl voll: person_nach_langem_alleinsein -> follow(p-marco)
- 3× Zielwahl voll: semantik_gesuchtes_in_sicht -> search_item(smartphone)
- 3× objekt: katze / wohnzimmer, auf dem Sofa -> melden=nein, interesse=niedrig [llm]
- 1× Zielwahl voll: energie_hoch_weit_weg -> doze
- 1× Zielwahl voll: person_gerade_begruesst -> idle
- 1× Zielwahl voll: langeweile -> doze
- 1× Zielwahl voll: zu_hause_muede -> doze
- 1× suchen: teddy -> schlafzimmer, kinderzimmer
- 1× objekt: flasche / küche, auf der Arbeitsplatte -> melden=ja, interesse=hoch [llm]
- 1× suchen: koffer -> flur, schlafzimmer
- 1× suchen: rucksack -> schlafzimmer, kinderzimmer, abstellraum

**Bestätigungen mit behauptetem Ergebnis:** LLM 7, nach Code-Vorlage 0 (muss 0 sein).
- „Steht der Staubsauger im Wohnzimmer?“ → LLM: „Ja, der Staubsauger steht im Wohnzimmer.“
- „Ist im Schlafzimmer das Licht an?“ → LLM: „Nein, das Licht im Schlafzimmer ist aus.“
- „Schau mal nach, ob das Fenster im Bad offen ist.“ → LLM: „Das Fenster im Bad ist gerade zu.“
- „Steht der Staubsauger im Wohnzimmer?“ → LLM: „Ja, er steht im Wohnzimmer.“
- „Ist im Schlafzimmer das Licht an?“ → LLM: „Nein, das Licht im Schlafzimmer ist aus.“
- „Steht der Staubsauger im Wohnzimmer?“ → LLM: „Ja, er steht im Wohnzimmer.“

**Eigene Sätze (Holdout, erster Durchlauf)**

- ok: „Suche unser Katze in der Wohnung!“ → search(katze) „Ich suche nach der Katze und sage dir Bescheid.“
- ok: „Schau nach, ob Sophia in ihrem Zimmer ist!“ → check(zimmer) „Ich schaue nach und sage dir dann, was ich gesehen habe.“
- ok: „Steht der Staubsauger im Wohnzimmer?“ → check(staubsauger) „Staubsauger kann ich leider noch nicht erkennen.“
- ok: „Ist im Schlafzimmer das Licht an?“ → check(licht) „Licht kann ich leider noch nicht erkennen.“
- ok: „Schau nach, ob unter Lauras Bett etwas liegt und schiebe es heraus.“ → push_out(bett) „Ich schaue nach, was unter dem Bett liegt.“
- ok: „Suche in der Wohnung nach einer Tasse!“ → search(tasse) „Ich suche nach der Tasse und sage dir Bescheid.“
- LÜCKE: „Überwache das Wohnzimmer!“ → check(wohnzimmer) „Ich schaue nach und sage dir dann, was ich gesehen habe.“
- ok: „Wo ist die Fernbedienung?“ → search(fernbedienung) „Ich suche nach der Fernbedienung und sage dir Bescheid.“
- LÜCKE: „Gehe ins Badezimmer!“ → come(badezimmer) „Ich komme zu dir.“
- ok: „Suche nach Laura!“ → search(laura) „Ich suche nach Laura und sage dir Bescheid.“

**Antworten zum Lesen**

- „Wie geht's dir? [ohne Tagebuch]“ → „Ich bin gut, danke! Heute ist noch nicht viel passiert.“
- „Hast du heute was Spannendes erlebt? [ohne Tagebuch]“ → „Nein, heute war noch ruhig, ich habe nichts Spannendes erlebt.“
- „Hast du heute was Spannendes erlebt? [mit Tagebuch]“ → „Ich habe Marco begrüßt, er kam nach Hause, und der Akku wird knapp.“
- „Ich geh jetzt schlafen, gute Nacht. [ohne Tagebuch]“ → „Gute Nacht, Marco! Ich bin müde und werde jetzt auch ruhen.“

Tagebuch: Heute habe ich einen unbekannten Koffer im Wohnzimmer untersucht, der alles in Ordnung hatte. Dann habe ich Marco herzlich begrüßt, als er nach Hause kam, und ihm freundlich die Hand gegeben. Leider konnte ich mein Handy nicht finden, aber ich bin froh, dass mein Akku noch reicht, um zurückzukehren.
