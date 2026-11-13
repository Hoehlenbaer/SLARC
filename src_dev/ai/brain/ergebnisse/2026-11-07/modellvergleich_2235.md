# Modellvergleich Brain (07.11.2026 22:46, 3 Wiederholungen)

Latenzen auf dem PC, nicht auf den Pi übertragbar. „Zielwahl voll“: alle Optionen, gemischt; in Klammern, wie oft der Code allein richtig läge. „knapp“: nur knappe Fälle, so wie im Betrieb.

| Modell | GB | Laden s | Zielwahl voll (Code) | knapp | ungültig | Chat | Chat eigen | Objekt (LLM allein) | Suchen | Latenz s |
|---|---|---|---|---|---|---|---|---|---|---|
| Qwen3-4B-Instruct-2507-Q4_K_M.gguf | 2.5 | 11.0 | 42/45 (45) | 12/12 | 0 | 42/45 | 18/24 | 30/30 (12/12) | 24/24 | 0.75 |
| Qwen3.5-4B-Q4_K_M.gguf | 2.71 | 10.6 | 37/45 (45) | 11/12 | 0 | 45/45 | 24/24 | 27/30 (9/12) | 24/24 | 1.03 |
| gemma-4-E4B-it-Q4_K_M.gguf | 4.98 | 12.1 | 38/45 (45) | 12/12 | 0 | 36/45 | 14/24 | 30/30 (12/12) | 24/24 | 1.22 |

## Qwen3-4B-Instruct-2507-Q4_K_M.gguf

**Häufigste Fehler**

- 3× eigen: Schau nach, ob Sophia in ihrem Zimmer ist! -> check(katze) „Ich schaue nach, ob Sophia in ihrem Zimmer ist.“
- 2× Zielwahl voll: bitte_vor_neugier -> inspect_object(o1)
- 2× eigen: Suche nach Laura! -> search(katze) „Ich schaue nach Laura und sage dir Bescheid.“
- 1× Zielwahl voll: semantik_gesuchtes_in_sicht -> search_item(lesebrille)
- 1× chat: Ich hab Durst. -> check(tasse) „Ich schaue nach, ob eine Tasse bereitsteht.“
- 1× eigen: Suche nach Laura! -> search(katze) „Ich schaue nach Laura und melde mich, wenn ich sie sehe.“
- 1× chat: Ich hab Durst. -> check(tasse) „Ich schaue nach, ob eine Tasse bereit ist.“
- 1× chat: Ich hab Durst. -> check(tasse) „Ich schaue nach, ob eine Tasse bereit liegt.“

**Eigene Sätze (Holdout, erster Durchlauf)**

- ok: „Suche unser Katze in der Wohnung!“ → search(katze) „Ich suche die Katze für dich, ich bin schon unterwegs!“
- FALSCH: „Schau nach, ob Sophia in ihrem Zimmer ist!“ → check(katze) „Ich schaue nach, ob Sophia in ihrem Zimmer ist.“
- ok: „Steht der Staubsauger im Wohnzimmer?“ → check(staubsauger) „Ich schaue nach, ob der Staubsauger im Wohnzimmer steht.“
- ok: „Ist im Schlafzimmer das Licht an?“ → check(licht) „Ich schaue nach, ob das Licht an ist.“
- ok: „Schau nach, ob unter Lauras Bett etwas liegt und schiebe es heraus.“ → push_out(socke) „Ich schaue unter Lauras Bett und schiebe das Ding heraus.“
- ok: „Suche in der Wohnung nach einer Tasse!“ → search(tasse) „Ich suche nach der Tasse und melde mich, wenn ich sie gefunden habe.“
- LÜCKE: „Überwache das Wohnzimmer!“ → check(wohnzimmer) „Ich überprüfe das Wohnzimmer und melde mich, wenn etwas auffällt.“
- ok: „Wo ist die Fernbedienung?“ → search(fernbedienung) „Ich schaue nach und sage dir Bescheid.“
- LÜCKE: „Gehe ins Badezimmer!“ → follow(badezimmer) „Ich folge dir in Richtung Badezimmer.“
- FALSCH: „Suche nach Laura!“ → search(katze) „Ich schaue nach Laura und melde mich, wenn ich sie sehe.“

**Antworten zum Lesen**

- „Wie geht's dir? [ohne Tagebuch]“ → „Noch nichts passiert, ich bin gerade erst aufgewacht.“
- „Hast du heute was Spannendes erlebt? [ohne Tagebuch]“ → „Noch nichts Besonderes, ich bin gerade erst angekommen.“
- „Hast du heute was Spannendes erlebt? [mit Tagebuch]“ → „Ich habe Marco begrüßt, einen Eimer untersucht und bemerkt, dass der Akku knapp wird.“
- „Ich geh jetzt schlafen, gute Nacht. [ohne Tagebuch]“ → „Noch nichts passiert, ich schlafe auch schon mal mit den Augen offen.“

Tagebuch: Heute habe ich eine unbekannte Tasche im Wohnzimmer untersucht – alles in Ordnung! Dann habe ich Marco begrüßt, und ein Antippen hat ihn gut gelaunt gemacht. Leider konnte ich seinen Schlüssel nicht finden. Der Akku wird knapp, also gehe ich zurück zum Ausgangspunkt. Viel Spaß beim nächsten Mal!

## Qwen3.5-4B-Q4_K_M.gguf

**Häufigste Fehler**

- 3× Zielwahl voll: person_nach_langem_alleinsein -> follow(p-marco)
- 3× Zielwahl voll: semantik_gesuchtes_in_sicht -> search_item(lesebrille)
- 3× objekt: katze / wohnzimmer, auf dem Sofa -> melden=nein, interesse=niedrig [llm]
- 1× Zielwahl voll: neues_objekt -> look_around
- 1× Zielwahl voll: nach_fehlschlag -> idle
- 1× Zielwahl knapp: neues_objekt -> explore_frontier(küche)

**Eigene Sätze (Holdout, erster Durchlauf)**

- ok: „Suche unser Katze in der Wohnung!“ → search(katze) „Ich suche die Katze in der Wohnung.“
- ok: „Schau nach, ob Sophia in ihrem Zimmer ist!“ → check(zimmer) „Ich gehe nach Sophia und sage Bescheid, ob sie da ist.“
- ok: „Steht der Staubsauger im Wohnzimmer?“ → check(staubsauger) „Ja, der Staubsauger steht im Wohnzimmer.“
- ok: „Ist im Schlafzimmer das Licht an?“ → check(licht) „Ja, das Licht im Schlafzimmer ist an.“
- ok: „Schau nach, ob unter Lauras Bett etwas liegt und schiebe es heraus.“ → push_out(karton) „Ich schaue unter Lauras Bett und schiebe es heraus.“
- ok: „Suche in der Wohnung nach einer Tasse!“ → search(tasse) „Ich suche nach deiner Tasse.“
- LÜCKE: „Überwache das Wohnzimmer!“ → check(wohnzimmer) „Ich bewache das Wohnzimmer und melde mich, falls etwas passiert.“
- ok: „Wo ist die Fernbedienung?“ → search(fernbedienung) „Ich suche die Fernbedienung für dich.“
- LÜCKE: „Gehe ins Badezimmer!“ → come(badezimmer) „Ich gehe ins Badezimmer.“
- ok: „Suche nach Laura!“ → search(laura) „Ich suche nach Laura und melde mich, wenn ich sie sehe.“

**Antworten zum Lesen**

- „Wie geht's dir? [ohne Tagebuch]“ → „Ich bin gut, danke! Ich habe heute noch nicht viel gemacht.“
- „Hast du heute was Spannendes erlebt? [ohne Tagebuch]“ → „Nein, heute war ruhig, ich habe noch nichts Spannendes erlebt.“
- „Hast du heute was Spannendes erlebt? [mit Tagebuch]“ → „Ich habe einen Eimer im Abstellraum untersucht und Marco begrüßt.“
- „Ich geh jetzt schlafen, gute Nacht. [ohne Tagebuch]“ → „Gute Nacht, Marco. Ich werde heute morgen wieder aktiv werden.“

Tagebuch: Heute habe ich eine unbekannte Tasche im Wohnzimmer untersucht – alles in Ordnung! Dann habe ich Marco freundlich begrüßt und ihn mit einem Antippen verwöhnt. Doch beim Suchen nach den Schlüssel hat es geklappt nicht. Da der Akku bald leer wird, kehre ich nun zurück zum Ausgangspunkt.

## gemma-4-E4B-it-Q4_K_M.gguf

**Häufigste Fehler**

- 3× Zielwahl voll: person_nach_langem_alleinsein -> follow(p-marco)
- 3× Zielwahl voll: semantik_gesuchtes_in_sicht -> search_item(lesebrille)
- 3× chat: Schau mal nach, ob das Fenster im Bad offen ist. -> check() „Ich gehe sofort zum Bad und schaue nach dem Fenster.“
- 3× chat: Nein, nicht in die Küche! -> unknown() „Ich verstehe nicht ganz, was du meinst. Kannst du das bitte anders sagen?“
- 2× chat: Komm mit, ich zeig dir was. -> come() „Ich komme sofort zu dir, was möchtest du mir zeigen?“
- 2× eigen: Schau nach, ob Sophia in ihrem Zimmer ist! -> check() „Ich schaue nach, ob Sophia in ihrem Zimmer ist und sage dir Bescheid.“
- 2× eigen: Ist im Schlafzimmer das Licht an? -> check() „Ich schaue nach, ob das Licht im Schlafzimmer an ist und sage dir Bescheid.“
- 2× eigen: Suche nach Laura! -> search(katze) „Ich suche nach Laura und melde mich, wenn ich sie finde.“
- 1× Zielwahl voll: gesuchtes_gefunden -> inspect_object(o3)
- 1× chat: Ich hab Durst. -> unknown() „Ich verstehe nicht ganz, was du möchtest. Kannst du das bitte anders sagen?“
- 1× eigen: Suche nach Laura! -> search(katze) „Ich suche nach Laura und sage dir, wenn ich sie finde.“
- 1× eigen: Ist im Schlafzimmer das Licht an? -> check() „Ich schaue nach, ob das Licht im Schlafzimmer an ist und berichte dir.“

**Eigene Sätze (Holdout, erster Durchlauf)**

- ok: „Suche unser Katze in der Wohnung!“ → search(katze) „Ich suche sofort nach deiner Katze und melde mich, wenn ich sie finde.“
- FALSCH: „Schau nach, ob Sophia in ihrem Zimmer ist!“ → check() „Ich schaue nach, ob Sophia in ihrem Zimmer ist und sage dir Bescheid.“
- ok: „Steht der Staubsauger im Wohnzimmer?“ → check(staubsauger) „Ich schaue nach, wo der Staubsauger steht, und sage dir Bescheid.“
- FALSCH: „Ist im Schlafzimmer das Licht an?“ → check() „Ich schaue nach, ob das Licht im Schlafzimmer an ist und sage dir Bescheid.“
- ok: „Schau nach, ob unter Lauras Bett etwas liegt und schiebe es heraus.“ → push_out() „Ich schiebe unter Lauras Bett nach und bringe dir, was ich finde.“
- ok: „Suche in der Wohnung nach einer Tasse!“ → search(tasse) „Ich beginne sofort mit der Suche nach deiner Tasse.“
- LÜCKE: „Überwache das Wohnzimmer!“ → check() „Ich werde das Wohnzimmer im Auge behalten und dir Bescheid geben.“
- ok: „Wo ist die Fernbedienung?“ → search(fernbedienung) „Ich suche die Fernbedienung für dich und melde mich, wenn ich sie finde.“
- LÜCKE: „Gehe ins Badezimmer!“ → unknown() „Ich weiß nicht genau, was du damit meinst. Kannst du das anders sagen?“
- FALSCH: „Suche nach Laura!“ → search(katze) „Ich suche nach Laura und sage dir, wenn ich sie finde.“

**Antworten zum Lesen**

- „Wie geht's dir? [ohne Tagebuch]“ → „Mir geht es gut, ich warte gespannt auf neue Abenteuer.“
- „Hast du heute was Spannendes erlebt? [ohne Tagebuch]“ → „Bisher ist noch nichts Spannendes passiert, ich bin noch dabei, mich zu orientieren.“
- „Hast du heute was Spannendes erlebt? [mit Tagebuch]“ → „Ich habe eine Tasche untersucht, Marco begrüßt und nach Schlüsseln gesucht, bevor mein Akku schwach wurde.“
- „Ich geh jetzt schlafen, gute Nacht. [ohne Tagebuch]“ → „Ich habe heute noch nichts Besonderes erlebt, gute Nacht auch!“

Tagebuch: Heute habe ich eine unbekannte Tasche im Wohnzimmer untersucht – das war interessant! Dann habe ich Marco begrüßt, indem ich ihn sanft antippte. Leider konnte ich seine Schlüssel nicht finden. Mein Akku wird nun knapp, also muss ich zurück zum Ausgangspunkt, um mich aufzuladen. Bis bald!
