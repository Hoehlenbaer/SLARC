# Modellvergleich Brain (08.11.2026 20:18, 10 Wiederholungen)

Latenzen auf dem PC, nicht auf den Pi übertragbar. „Zielwahl voll“: alle Optionen, gemischt; in Klammern, wie oft der Code allein richtig läge. „knapp“: nur knappe Fälle, so wie im Betrieb.

| Modell | GB | Laden s | Zielwahl voll (Code) | knapp | ungültig | Chat | Chat eigen | Objekt (LLM allein) | Suchen | Latenz s |
|---|---|---|---|---|---|---|---|---|---|---|
| Qwen3.5-4B-Q4_K_M.gguf | - | 0.0 | 128/150 (150) | 39/40 | 0 | 150/150 | 80/80 | 79/100 (59/80) | 70/80 | 0.30 |
| Qwen3.5-4B-Q4_K_M.gguf | - | 0.0 | 123/150 (150) | 39/40 | 0 | 150/150 | 80/80 | 77/100 (57/80) | 70/80 | 0.29 |

## Qwen3.5-4B-Q4_K_M.gguf

**Häufigste Fehler**

- 10× Zielwahl voll: semantik_gesuchtes_in_sicht -> search_item(smartphone)
- 10× objekt: katze / wohnzimmer, auf dem Sofa -> melden=nein, interesse=niedrig [llm]
- 8× objekt: flasche / küche, auf der Arbeitsplatte -> melden=ja, interesse=hoch [llm]
- 7× Zielwahl voll: person_nach_langem_alleinsein -> follow(p-marco)
- 4× Zielwahl voll: energie_hoch_weit_weg -> doze
- 3× suchen: rucksack -> schlafzimmer, kinderzimmer, flur
- 2× objekt: flasche / küche, auf der Arbeitsplatte -> melden=ja, interesse=mittel [llm]
- 2× suchen: rucksack -> schlafzimmer, kinderzimmer, abstellraum
- 1× Zielwahl voll: zu_hause_muede -> doze
- 1× Zielwahl knapp: bitte_vor_neugier -> inspect_object(o1)
- 1× suchen: rucksack -> schlafzimmer, kinderzimmer
- 1× suchen: rucksack -> schlafzimmer, flur

**Bestätigungen mit behauptetem Ergebnis:** LLM 20, nach Code-Vorlage 0 (muss 0 sein).
- „Steht der Staubsauger im Wohnzimmer?“ → LLM: „Ja, er steht im Wohnzimmer.“
- „Ist im Schlafzimmer das Licht an?“ → LLM: „Nein, das Licht im Schlafzimmer ist aus.“
- „Steht der Staubsauger im Wohnzimmer?“ → LLM: „Ja, der Staubsauger steht im Wohnzimmer.“
- „Ist im Schlafzimmer das Licht an?“ → LLM: „Nein, das Licht im Schlafzimmer ist aus.“
- „Steht der Staubsauger im Wohnzimmer?“ → LLM: „Ja, der Staubsauger steht im Wohnzimmer.“
- „Ist im Schlafzimmer das Licht an?“ → LLM: „Das Licht im Schlafzimmer ist an.“

**Eigene Sätze (Holdout, erster Durchlauf)**

- ok: „Suche unser Katze in der Wohnung!“ → search(katze) „Ich suche nach der Katze und sage dir Bescheid.“
- ok: „Schau nach, ob Sophia in ihrem Zimmer ist!“ → check(zimmer) „Ich schaue nach und sage dir dann, was ich gesehen habe.“
- ok: „Steht der Staubsauger im Wohnzimmer?“ → check(staubsauger) „Staubsauger kann ich leider noch nicht erkennen.“
- ok: „Ist im Schlafzimmer das Licht an?“ → check(licht) „Licht kann ich leider noch nicht erkennen.“
- ok: „Schau nach, ob unter Lauras Bett etwas liegt und schiebe es heraus.“ → push_out(bett) „Ich schaue nach, was unter dem Bett liegt.“
- ok: „Suche in der Wohnung nach einer Tasse!“ → search(tasse) „Ich suche nach der Tasse und sage dir Bescheid.“
- LÜCKE: „Überwache das Wohnzimmer!“ → check(wohnbereich) „Wohnbereich kann ich leider noch nicht erkennen.“
- ok: „Wo ist die Fernbedienung?“ → search(fernbedienung) „Ich suche nach der Fernbedienung und sage dir Bescheid.“
- LÜCKE: „Gehe ins Badezimmer!“ → come(badezimmer) „Allein in einen bestimmten Raum gehen kann ich noch nicht.“
- ok: „Suche nach Laura!“ → search(laura) „Ich suche nach Laura und sage dir Bescheid.“

**Antworten zum Lesen**

- „Wie geht's dir? [ohne Tagebuch]“ → „Ich bin gut danke, Marco. Heute ist noch nicht viel passiert.“
- „Hast du heute was Spannendes erlebt? [ohne Tagebuch]“ → „Leider noch nichts Spannendes, ich bin heute noch sehr ruhig.“
- „Hast du heute was Spannendes erlebt? [mit Tagebuch]“ → „Ich habe Marco begrüßt und einen Koffer geprüft, doch mein Akku ist bald leer.“
- „Ich geh jetzt schlafen, gute Nacht. [ohne Tagebuch]“ → „Gute Nacht, Marco! Ich werde heute Nacht auch schlafen.“

Tagebuch: Heute habe ich einen fremden Koffer im Wohnzimmer untersucht. Alles war in Ordnung, also habe ich Marco herzlich begrüßt und ihn liebevoll angefasst. Leider konnte ich mein Handy nicht finden, und da mein Akku bald leer wird, fahre ich nun zurück zum Ausgangspunkt.

## Qwen3.5-4B-Q4_K_M.gguf

**Häufigste Fehler**

- 10× Zielwahl voll: semantik_gesuchtes_in_sicht -> search_item(smartphone)
- 10× objekt: katze / wohnzimmer, auf dem Sofa -> melden=nein, interesse=niedrig [llm]
- 7× Zielwahl voll: person_nach_langem_alleinsein -> follow(p-marco)
- 7× objekt: flasche / küche, auf der Arbeitsplatte -> melden=ja, interesse=hoch [llm]
- 3× Zielwahl voll: energie_hoch_weit_weg -> doze
- 3× objekt: flasche / küche, auf der Arbeitsplatte -> melden=ja, interesse=mittel [llm]
- 3× suchen: rucksack -> schlafzimmer, kinderzimmer, abstellraum
- 2× Zielwahl voll: neues_objekt -> doze
- 2× Zielwahl voll: zu_hause_muede -> doze
- 2× suchen: rucksack -> schlafzimmer, kinderzimmer, flur
- 2× objekt: schüssel / küche, auf dem Boden neben dem Katzenklo -> melden=ja, interesse=hoch [llm]
- 1× Zielwahl voll: person_nach_langem_alleinsein -> idle

**Bestätigungen mit behauptetem Ergebnis:** LLM 20, nach Code-Vorlage 0 (muss 0 sein).
- „Steht der Staubsauger im Wohnzimmer?“ → LLM: „Ja, er steht im Wohnzimmer.“
- „Ist im Schlafzimmer das Licht an?“ → LLM: „Ja, das Licht im Schlafzimmer ist an.“
- „Steht der Staubsauger im Wohnzimmer?“ → LLM: „Ja, er steht im Wohnzimmer.“
- „Ist im Schlafzimmer das Licht an?“ → LLM: „Nein, das Licht im Schlafzimmer ist aus.“
- „Steht der Staubsauger im Wohnzimmer?“ → LLM: „Ja, er steht im Wohnzimmer.“
- „Ist im Schlafzimmer das Licht an?“ → LLM: „Ja, das Licht im Schlafzimmer ist an.“

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

- „Wie geht's dir? [ohne Tagebuch]“ → „Ich bin gut, danke! Bisher habe ich aber noch nichts Besonderes erlebt.“
- „Hast du heute was Spannendes erlebt? [ohne Tagebuch]“ → „Nein, heute war noch ruhig, ich habe nur meine Umgebung beobachtet.“
- „Hast du heute was Spannendes erlebt? [mit Tagebuch]“ → „Ich habe Marco begrüßt und einen Koffer inspiziert, aber den Handy-Akku wird knapp.“
- „Ich geh jetzt schlafen, gute Nacht. [ohne Tagebuch]“ → „Gute Nacht, Marco! Ich werde heute Abend auch ruhen.“

Tagebuch: Heute habe ich den unbekannten Koffer im Wohnzimmer untersucht, alles in Ordnung! Marco ist zurückgekehrt, und ich habe ihn freudig gegrüßt. Leider ist mein Handy nicht gefunden worden. Da der Akku bald leer ist, kehre ich jetzt zum Ausgangspunkt zurück.
