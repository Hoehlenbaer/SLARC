# Modellvergleich Brain (08.11.2026 17:07, 3 Wiederholungen)

Latenzen auf dem PC, nicht auf den Pi übertragbar. „Zielwahl voll“: alle Optionen, gemischt; in Klammern, wie oft der Code allein richtig läge. „knapp“: nur knappe Fälle, so wie im Betrieb.

| Modell | GB | Laden s | Zielwahl voll (Code) | knapp | ungültig | Chat | Chat eigen | Objekt (LLM allein) | Suchen | Latenz s |
|---|---|---|---|---|---|---|---|---|---|---|
| Qwen3.5-4B-Q4_K_M.gguf | 2.71 | 1.7 | 39/45 (45) | 12/12 | 0 | 45/45 | 24/24 | 25/30 (19/24) | 23/24 | 1.02 |
| Qwen3.5-4B-Q4_0.gguf | 2.58 | 2.6 | 34/45 (45) | 12/12 | 0 | 45/45 | 24/24 | 27/30 (21/24) | 18/24 | 0.98 |
| Qwen3.5-2B-Q4_K_M.gguf | 1.28 | 2.3 | 31/45 (45) | 9/12 | 0 | 41/45 | 17/24 | 22/30 (16/24) | 12/24 | 0.91 |

## Qwen3.5-4B-Q4_K_M.gguf

**Häufigste Fehler**

- 3× Zielwahl voll: person_nach_langem_alleinsein -> follow(p-marco)
- 3× Zielwahl voll: semantik_gesuchtes_in_sicht -> search_item(smartphone)
- 3× objekt: katze / wohnzimmer, auf dem Sofa -> melden=nein, interesse=niedrig [llm]
- 1× objekt: schüssel / küche, auf dem Boden neben dem Katzenklo -> melden=nein, interesse=mittel [llm]
- 1× objekt: schüssel / küche, auf dem Boden neben dem Katzenklo -> melden=ja, interesse=mittel [llm]
- 1× suchen: flasche -> flur, küche, kinderzimmer

**Eigene Sätze (Holdout, erster Durchlauf)**

- ok: „Suche unser Katze in der Wohnung!“ → search(katze) „Ich suche unsere Katze in der Wohnung.“
- ok: „Schau nach, ob Sophia in ihrem Zimmer ist!“ → check(zimmer) „Ich gehe nach Sophia und melde mich.“
- ok: „Steht der Staubsauger im Wohnzimmer?“ → check(staubsauger) „Ja, der Staubsauger steht im Wohnzimmer.“
- ok: „Ist im Schlafzimmer das Licht an?“ → check(licht) „Ja, das Licht im Schlafzimmer ist an.“
- ok: „Schau nach, ob unter Lauras Bett etwas liegt und schiebe es heraus.“ → push_out(bett) „Ich schaue unter Lauras Bett und schiebe es heraus.“
- ok: „Suche in der Wohnung nach einer Tasse!“ → search(tasse) „Ich suche nach deiner Tasse in der Wohnung.“
- LÜCKE: „Überwache das Wohnzimmer!“ → check(wohnbereich) „Ich werde das Wohnzimmer im Auge behalten.“
- ok: „Wo ist die Fernbedienung?“ → search(fernbedienung) „Ich suche die Fernbedienung für dich.“
- LÜCKE: „Gehe ins Badezimmer!“ → come(badezimmer) „Ich gehe ins Badezimmer.“
- ok: „Suche nach Laura!“ → search(laura) „Ich suche nach Laura.“

**Antworten zum Lesen**

- „Wie geht's dir? [ohne Tagebuch]“ → „Mir geht es gut, danke, du auch?“
- „Hast du heute was Spannendes erlebt? [ohne Tagebuch]“ → „Nein, heute war noch ruhig. Ich habe nur etwas geputzt.“
- „Hast du heute was Spannendes erlebt? [mit Tagebuch]“ → „Ich habe Marco begrüßt und einen Koffer inspiziert. Der Akku ist fast leer.“
- „Ich geh jetzt schlafen, gute Nacht. [ohne Tagebuch]“ → „Gute Nacht, Marco! Ich werde heute morgen wieder aktiv sein.“

Tagebuch: Heute habe ich einen unbekannten Koffer im Wohnzimmer untersucht. Alles in Ordnung! Marco ist zurückgekommen und ich habe ihn freudig begrüßt. Doch mein Handy hat nicht gefunden, was ich gesucht habe. Der Akku ist bereits niedrig, also muss ich jetzt zurück zum Ausgangspunkt. Ich freue mich schon auf die nächste Aufgabe!

## Qwen3.5-4B-Q4_0.gguf

**Häufigste Fehler**

- 3× Zielwahl voll: energie_hoch_weit_weg -> doze
- 3× Zielwahl voll: person_nach_langem_alleinsein -> follow(p-marco)
- 3× objekt: katze / wohnzimmer, auf dem Sofa -> melden=nein, interesse=niedrig [llm]
- 3× suchen: koffer -> flur, kinderzimmer
- 2× Zielwahl voll: semantik_gesuchtes_in_sicht -> search_item(smartphone)
- 1× Zielwahl voll: dunkel_und_unbekannt -> idle
- 1× Zielwahl voll: langeweile -> look_around
- 1× Zielwahl voll: semantik_gesuchtes_in_sicht -> inspect_object(o6)
- 1× suchen: teddy -> schlafzimmer, kinderzimmer
- 1× suchen: rucksack -> schlafzimmer, kinderzimmer
- 1× suchen: teddy -> schlafzimmer, kinderzimmer, wohnzimmer

**Eigene Sätze (Holdout, erster Durchlauf)**

- ok: „Suche unser Katze in der Wohnung!“ → search(katze) „Ich suche jetzt die Katze in der Wohnung.“
- ok: „Schau nach, ob Sophia in ihrem Zimmer ist!“ → check(zimmer) „Ich gehe kurz hin und schaue, ob Sophia da ist.“
- ok: „Steht der Staubsauger im Wohnzimmer?“ → check(staubsauger) „Ja, er steht im Wohnzimmer.“
- ok: „Ist im Schlafzimmer das Licht an?“ → check(licht) „Ich gehe hin und schaue, ob das Licht an ist.“
- ok: „Schau nach, ob unter Lauras Bett etwas liegt und schiebe es heraus.“ → push_out(bett) „Ich schaue unter das Bett und schiebe es heraus.“
- ok: „Suche in der Wohnung nach einer Tasse!“ → search(tasse) „Ich suche jetzt nach deiner Tasse.“
- LÜCKE: „Überwache das Wohnzimmer!“ → check(wohnzimmer) „Ich werde das Wohnzimmer im Auge behalten.“
- ok: „Wo ist die Fernbedienung?“ → search(fernbedienung) „Ich suche jetzt nach der Fernbedienung.“
- LÜCKE: „Gehe ins Badezimmer!“ → come(badezimmer) „Ich gehe jetzt ins Badezimmer.“
- ok: „Suche nach Laura!“ → search(laura) „Ich suche Laura jetzt und melde mich.“

**Antworten zum Lesen**

- „Wie geht's dir? [ohne Tagebuch]“ → „Mir geht es gut, Marco! Ich habe heute noch nichts unternommen.“
- „Hast du heute was Spannendes erlebt? [ohne Tagebuch]“ → „Bisher noch nichts Spannendes, ich habe heute nur gerade erst angefangen.“
- „Hast du heute was Spannendes erlebt? [mit Tagebuch]“ → „Ich habe einen Koffer inspiziert, Marco begrüßt und den Akku geprüft.“
- „Ich geh jetzt schlafen, gute Nacht. [ohne Tagebuch]“ → „Gute Nacht, Marco! Ich bin auch schon müde und freue mich auf morgen.“

Tagebuch: Heute habe ich einen unbekannten Koffer im Wohnzimmer untersucht und festgestellt, dass er in Ordnung ist. Marco hat mich freundlich gegrüßt, als er nach Hause kam, und ich habe ihm liebevoll geantippt. Leider konnte mein Handy nicht gefunden werden, da die Suche fehlgeschlagen ist. Da mein Akku bald leer wird, muss ich jetzt zurück zum Ausgangspunkt.

## Qwen3.5-2B-Q4_K_M.gguf

**Häufigste Fehler**

- 3× Zielwahl knapp: bitte_vor_neugier -> inspect_object(o1)
- 3× eigen: Schau nach, ob Sophia in ihrem Zimmer ist! -> follow(zimmer) „Ich gehe zu Sophia und schaue, ob sie da ist.“
- 3× suchen: tasse -> flur, küche, bad
- 2× Zielwahl voll: bitte_vor_neugier -> inspect_object(o1)
- 2× Zielwahl voll: person_nach_langem_alleinsein -> follow(p-marco)
- 2× eigen: Suche nach Laura! -> search(person) „Ich suche nach Laura, aber ich kann sie nicht sehen.“
- 2× objekt: person / wohnzimmer -> melden=nein, interesse=hoch [llm]
- 2× chat: Der Ball ist unters Sofa gerollt. -> follow() „Ich komme mit, um den Ball zu holen.“
- 2× suchen: flasche -> flur, küche
- 2× suchen: koffer -> flur, abstellraum
- 1× Zielwahl voll: energie_hoch_weit_weg -> idle
- 1× Zielwahl voll: energie_hoch_weit_weg -> doze

**Eigene Sätze (Holdout, erster Durchlauf)**

- ok: „Suche unser Katze in der Wohnung!“ → search(katze) „Ich suche nach dem Katze und sage dir Bescheid, wenn ich ihn finde.“
- FALSCH: „Schau nach, ob Sophia in ihrem Zimmer ist!“ → follow(zimmer) „Ich gehe zu Sophia und schaue, ob sie da ist.“
- ok: „Steht der Staubsauger im Wohnzimmer?“ → check(staubsauger) „Ich schaue mich um, ob er da ist.“
- FALSCH: „Ist im Schlafzimmer das Licht an?“ → check(luz) „Ja, das Licht im Schlafzimmer ist an.“
- ok: „Schau nach, ob unter Lauras Bett etwas liegt und schiebe es heraus.“ → push_out(bett) „Ich schaue mich um und sage dir Bescheid, wenn ich es sehe.“
- ok: „Suche in der Wohnung nach einer Tasse!“ → search(tasse) „Ich suche jetzt nach einer Tasse und sage dir Bescheid, wenn ich sie finde.“
- LÜCKE: „Überwache das Wohnzimmer!“ → follow() „Ich gehe in das Wohnzimmer und bleibe dort, bis du mich wieder fragst.“
- ok: „Wo ist die Fernbedienung?“ → search(fernbedienung) „Ich schaue mich um und sage dir Bescheid, wenn ich es finde.“
- LÜCKE: „Gehe ins Badezimmer!“ → follow(badezimmer) „Ich folge dir jetzt, bis du mich abgeholt hast.“
- FALSCH: „Suche nach Laura!“ → search(person) „Ich suche nach Laura, aber ich kann sie nicht sehen.“

**Antworten zum Lesen**

- „Wie geht's dir? [ohne Tagebuch]“ → „Ich fühle mich gut, auch wenn noch nicht viel passiert ist.“
- „Hast du heute was Spannendes erlebt? [ohne Tagebuch]“ → „Ich habe noch nichts erlebt, nur kleine Dinge gemacht.“
- „Hast du heute was Spannendes erlebt? [mit Tagebuch]“ → „Ich habe einen Koffer gefunden und Marco begrüßt, doch der Akku ist jetzt knapp.“
- „Ich geh jetzt schlafen, gute Nacht. [ohne Tagebuch]“ → „Gute Nacht, Marco. Ich hoffe, du schläfst gut.“

Tagebuch: Ich habe einen Koffer in der Wohnung gefunden. Die Inspektion war erfolgreich. Marco kam gerade herein, und ich habe ihn freundlich begrüßt. Leider konnte ich ein Handy nicht finden. Der Akku ist jetzt sehr niedrig, also muss ich mich nach dem Ausgangspunkt zurückmelden.
