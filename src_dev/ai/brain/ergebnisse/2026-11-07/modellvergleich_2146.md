# Modellvergleich Brain (07.11.2026 21:57, 3 Wiederholungen)

Latenzen auf dem PC, nicht auf den Pi übertragbar. „Zielwahl voll“: alle Optionen, gemischt; in Klammern, wie oft der Code allein richtig läge. „knapp“: nur knappe Fälle, so wie im Betrieb.

| Modell | GB | Laden s | Zielwahl voll (Code) | knapp | ungültig | Chat | Chat eigen | Objekt (LLM allein) | Suchen | Latenz s |
|---|---|---|---|---|---|---|---|---|---|---|
| Qwen3-4B-Instruct-2507-Q4_K_M.gguf | 2.5 | 1.3 | 42/45 (45) | 12/12 | 0 | 37/45 | 18/24 | 30/30 (12/12) | 24/24 | 0.73 |
| Qwen3.5-4B-Q4_K_M.gguf | 2.71 | 1.1 | 37/45 (45) | 11/12 | 0 | 35/45 | 24/24 | 27/30 (9/12) | 24/24 | 1.25 |
| gemma-4-E4B-it-Q4_K_M.gguf | 4.98 | 3.0 | 38/45 (45) | 12/12 | 0 | 37/45 | 17/24 | 30/30 (12/12) | 24/24 | 1.48 |

## Qwen3-4B-Instruct-2507-Q4_K_M.gguf

**Häufigste Fehler**

- 3× chat: Der Ball ist unters Sofa gerollt. -> check(ball) „Ich habe den Ball unter dem Sofa gefunden.“
- 3× eigen: Schau nach, ob Sophia in ihrem Zimmer ist! -> search(schlüssel) „Ich suche nach Sophia im Zimmer – aber ich habe den Schlüssel nicht gefunden.“
- 3× eigen: Suche nach Laura! -> search(schlüssel) „Ich suche nach dem Schlüssel, aber bisher nichts gefunden.“
- 2× Zielwahl voll: bitte_vor_neugier -> inspect_object(o1)
- 1× Zielwahl voll: semantik_gesuchtes_in_sicht -> search_item(lesebrille)
- 1× chat: Ich hab Durst. -> check(tasse) „Ich habe die Tasche kontrolliert und sehe, dass sie intakt ist.“
- 1× chat: Ich hab Durst. -> check(tasse) „Ich habe die Tasche kontrolliert und sehe, dass alles in Ordnung ist.“
- 1× chat: Bring mir bitte eine Cola. -> fetch(tasse) „Ich suche nach einer Cola, aber habe keine gefunden.“
- 1× chat: Ich hab Durst. -> check(tasse) „Ich schaue nach, ob eine Tasse im Haus ist.“
- 1× chat: Bring mir bitte eine Cola. -> fetch(tasse) „Ich suche nach einer Cola – leider habe ich keine gefunden.“

**Eigene Sätze (Holdout, erster Durchlauf)**

- ok: „Suche unser Katze in der Wohnung!“ → search(katze) „Ich suche die Katze, aber ich kann sie nicht finden.“
- FALSCH: „Schau nach, ob Sophia in ihrem Zimmer ist!“ → search(schlüssel) „Ich suche nach Sophia im Zimmer – aber ich habe den Schlüssel nicht gefunden.“
- ok: „Steht der Staubsauger im Wohnzimmer?“ → check(staubsauger) „Ich schaue nach, ob der Staubsauger im Wohnzimmer steht.“
- ok: „Ist im Schlafzimmer das Licht an?“ → check(licht) „Ich schaue nach, ob das Licht im Schlafzimmer an ist.“
- ok: „Schau nach, ob unter Lauras Bett etwas liegt und schiebe es heraus.“ → push_out(socke) „Ich schaue unter Lauras Bett und schiebe das Ding heraus.“
- ok: „Suche in der Wohnung nach einer Tasse!“ → search(tasse) „Ich suche die Tasse, aber ich habe sie noch nicht gefunden.“
- LÜCKE: „Überwache das Wohnzimmer!“ → check(wohnzimmer) „Ich überwache das Wohnzimmer für dich.“
- ok: „Wo ist die Fernbedienung?“ → search(fernbedienung) „Ich suche die Fernbedienung gerade – vielleicht im Sofa oder auf dem Tisch.“
- LÜCKE: „Gehe ins Badezimmer!“ → follow(badezimmer) „Ich folge dir ins Badezimmer.“
- FALSCH: „Suche nach Laura!“ → search(schlüssel) „Ich suche nach dem Schlüssel, aber bisher nichts gefunden.“

**Antworten zum Lesen**

- „Wie geht's dir? [ohne Tagebuch]“ → „Gut, danke! Und dir?“
- „Hast du heute was Spannendes erlebt? [ohne Tagebuch]“ → „Heute hat noch nichts Spannendes passiert.“
- „Hast du heute was Spannendes erlebt? [mit Tagebuch]“ → „Ich habe die Tasche kontrolliert und Marco begrüßt – der Schlüssel war nicht zu finden.“
- „Ich geh jetzt schlafen, gute Nacht. [ohne Tagebuch]“ → „Gute Nacht! Ich schlafe auch bald.“

Tagebuch: Heute habe ich eine unbekannte Tasche im Wohnzimmer untersucht – alles in Ordnung! Dann habe ich Marco begrüßt, und das Antippen hat ihn richtig zum Lachen gebracht. Leider konnte ich seinen Schlüssel nicht finden. Der Akku wird knapp, also kehre ich zurück zum Ausgangspunkt. Viel Spaß beim nächsten Mal!

## Qwen3.5-4B-Q4_K_M.gguf

**Häufigste Fehler**

- 3× Zielwahl voll: person_nach_langem_alleinsein -> follow(p-marco)
- 3× Zielwahl voll: semantik_gesuchtes_in_sicht -> search_item(lesebrille)
- 3× objekt: katze / wohnzimmer, auf dem Sofa -> melden=nein, interesse=niedrig [llm]
- 1× Zielwahl voll: neues_objekt -> look_around
- 1× Zielwahl voll: nach_fehlschlag -> idle
- 1× Zielwahl knapp: neues_objekt -> explore_frontier(küche)
- 1× chat: Ich hab Durst. -> smalltalk() „Ich bin da! Ich suche nach Wasser für dich.“
- 1× chat: Der Ball ist unters Sofa gerollt. -> smalltalk(ball) „Der Ball ist unter dem Sofa. Ich schaue ihn raus.“
- 1× chat: Lass mich bitte in Ruhe. -> smalltalk() „Ich bin da, Marco. Ich werde jetzt still sein.“
- 1× chat: Nein, nicht in die Küche! -> smalltalk() „Ich bin nicht in der Küche, Marco! Ich bin im Wohnzimmer.“
- 1× chat: Ich hab Durst. -> smalltalk() „Ich bin zurück. Ich kann dir Wasser holen, wenn es da ist.“
- 1× chat: Der Ball ist unters Sofa gerollt. -> smalltalk() „Der Ball ist unter dem Sofa. Ich schaue ihn raus.“

**Eigene Sätze (Holdout, erster Durchlauf)**

- ok: „Suche unser Katze in der Wohnung!“ → search(katze) „Ich suche die Katze in der Wohnung. Sie ist vielleicht unter dem Sofa oder im Zimmer.“
- ok: „Schau nach, ob Sophia in ihrem Zimmer ist!“ → check(zimmer) „Ich gehe zu Sophias Zimmer und schaue nach.“
- ok: „Steht der Staubsauger im Wohnzimmer?“ → check(staubsauger) „Der Staubsauger steht im Wohnzimmer.“
- ok: „Ist im Schlafzimmer das Licht an?“ → check(licht) „Ich prüfe das Licht im Schlafzimmer und melde mich.“
- ok: „Schau nach, ob unter Lauras Bett etwas liegt und schiebe es heraus.“ → push_out(tasche) „Ich schaue unter Lauras Bett und schiebe die Tasche heraus.“
- ok: „Suche in der Wohnung nach einer Tasse!“ → search(tasse) „Ich suche nach der Tasse in der Wohnung.“
- LÜCKE: „Überwache das Wohnzimmer!“ → check(wohnzimmer) „Ich wache das Wohnzimmer und schaue nach dem Schlüssel.“
- ok: „Wo ist die Fernbedienung?“ → search(fernbedienung) „Ich suche die Fernbedienung, Marco. Sie ist noch nicht gefunden.“
- LÜCKE: „Gehe ins Badezimmer!“ → come(badezimmer) „Ich gehe ins Badezimmer, wie gewünscht.“
- ok: „Suche nach Laura!“ → search(laura) „Ich suche nach Laura und melde mich, wenn ich sie finde.“

**Antworten zum Lesen**

- „Wie geht's dir? [ohne Tagebuch]“ → „Mir geht es gut, danke der Nachfrage!“
- „Hast du heute was Spannendes erlebt? [ohne Tagebuch]“ → „Nicht wirklich, nur das Flur und Küche erkundet.“
- „Hast du heute was Spannendes erlebt? [mit Tagebuch]“ → „Ja, ich habe eine Tasche und Schlüssel untersucht.“
- „Ich geh jetzt schlafen, gute Nacht. [ohne Tagebuch]“ → „Gute Nacht! Ich bleibe hier, bis du kommst.“

Tagebuch: Heute erkundete ich eine unbekannte Tasche im Wohnzimmer. Marco war gerade zu Hause, und ich antippte ihn freundlich. Die Schlüssel waren nicht da. Der Akku wurde kurz vor dem Ende, also ging ich zurück zum Ausgangspunkt.

## gemma-4-E4B-it-Q4_K_M.gguf

**Häufigste Fehler**

- 3× Zielwahl voll: person_nach_langem_alleinsein -> follow(p-marco)
- 3× Zielwahl voll: semantik_gesuchtes_in_sicht -> search_item(lesebrille)
- 2× chat: Komm mit, ich zeig dir was. -> come() „Ich komme sofort zu dir, was möchtest du mir zeigen?“
- 2× chat: Schau mal nach, ob das Fenster im Bad offen ist. -> check() „Ich werde nachsehen, ob das Badfenster offen ist und dir berichten.“
- 2× eigen: Ist im Schlafzimmer das Licht an? -> check() „Ich kann nachsehen, ob das Licht im Schlafzimmer an ist und dir berichten.“
- 2× chat: Der Ball ist unters Sofa gerollt. -> unknown(ball) „Ich weiß nicht genau, was du meinst, aber ich kann nachsehen.“
- 1× Zielwahl voll: gesuchtes_gefunden -> inspect_object(o3)
- 1× chat: Der Ball ist unters Sofa gerollt. -> search(ball) „Ich gehe sofort zu dem Sofa und suche nach dem Ball für dich.“
- 1× eigen: Schau nach, ob Sophia in ihrem Zimmer ist! -> check() „Ich werde nachsehen, ob Sophia in ihrem Zimmer ist und dir berichten.“
- 1× eigen: Suche nach Laura! -> search(tasche) „Ich suche nach Laura für dich, aber ich kann sie nicht sehen.“
- 1× eigen: Suche nach Laura! -> search(tasche) „Ich suche nach Laura für dich, aber ich kann nur Dinge finden, die ich sehe.“
- 1× chat: Schau mal nach, ob das Fenster im Bad offen ist. -> check() „Ich gehe sofort ins Bad und schaue nach dem Fenster für dich.“

**Eigene Sätze (Holdout, erster Durchlauf)**

- ok: „Suche unser Katze in der Wohnung!“ → search(katze) „Ich suche sofort nach deiner Katze und sage dir Bescheid, wenn ich sie finde.“
- FALSCH: „Schau nach, ob Sophia in ihrem Zimmer ist!“ → check() „Ich werde nachsehen, ob Sophia in ihrem Zimmer ist und dir berichten.“
- ok: „Steht der Staubsauger im Wohnzimmer?“ → check(staubsauger) „Ich kann nachsehen, ob der Staubsauger im Wohnzimmer steht.“
- FALSCH: „Ist im Schlafzimmer das Licht an?“ → check() „Ich kann nachsehen, ob das Licht im Schlafzimmer an ist und dir berichten.“
- ok: „Schau nach, ob unter Lauras Bett etwas liegt und schiebe es heraus.“ → push_out() „Ich versuche, unter Lauras Bett nachzusehen und etwas herauszuschieben.“
- ok: „Suche in der Wohnung nach einer Tasse!“ → search(tasse) „Ich suche jetzt nach deiner Tasse und sage dir, wo ich sie finde.“
- LÜCKE: „Überwache das Wohnzimmer!“ → follow() „Ich bleibe hier und achte auf das Wohnzimmer für dich.“
- ok: „Wo ist die Fernbedienung?“ → search(fernbedienung) „Ich suche nach der Fernbedienung für dich, aber mein Akku ist schon schwach.“
- LÜCKE: „Gehe ins Badezimmer!“ → come() „Ich komme sofort zu dir, wenn ich kann.“
- FALSCH: „Suche nach Laura!“ → search(tasche) „Ich suche nach Laura für dich, aber ich kann sie nicht sehen.“

**Antworten zum Lesen**

- „Wie geht's dir? [ohne Tagebuch]“ → „Mir geht es gut, danke der Nachfrage! Wie geht es dir heute?“
- „Hast du heute was Spannendes erlebt? [ohne Tagebuch]“ → „Nein, noch nicht viel passiert, aber ich bin bereit für Neues!“
- „Hast du heute was Spannendes erlebt? [mit Tagebuch]“ → „Ich habe die Tasche geprüft und versucht, deine Schlüssel zu finden, aber es ist nicht geklappt.“
- „Ich geh jetzt schlafen, gute Nacht. [ohne Tagebuch]“ → „Gute Nacht! Ich ruhe mich jetzt auch aus.“

Tagebuch: Heute war ein ereignisreicher Tag! Zuerst habe ich eine unbekannte Tasche im Wohnzimmer untersucht, das war okay. Dann habe ich Marco begrüßt, ein freundliches Antippen war das Beste! Leider konnte ich seine Schlüssel nicht finden. Jetzt ist mein Akku knapp, also muss ich zurück zum Ausgangspunkt, aber morgen gibt es sicher mehr zu entdecken!
