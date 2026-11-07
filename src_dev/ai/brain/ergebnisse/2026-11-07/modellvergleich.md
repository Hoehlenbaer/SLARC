# Modellvergleich Brain (07.11.2026 20:59, 3 Wiederholungen)

Latenzen auf dem PC, nicht auf den Pi übertragbar. „Zielwahl voll“: alle Optionen, gemischt; in Klammern, wie oft der Code allein richtig läge. „knapp“: nur knappe Fälle, so wie im Betrieb.

| Modell | GB | Laden s | Zielwahl voll (Code) | knapp | ungültig | Chat | Objekt | Suchen | Latenz s |
|---|---|---|---|---|---|---|---|---|---|
| Qwen3-4B-Instruct-2507-Q4_K_M.gguf | 2.5 | 3.7 | 42/45 (45) | 12/12 | 0 | 42/45 | 26/30 | 24/24 | 0.70 |
| Qwen3.5-4B-Q4_K_M.gguf | 2.71 | 1.6 | 37/45 (45) | 11/12 | 0 | 45/45 | 24/30 | 24/24 | 1.03 |
| gemma-4-E4B-it-Q4_K_M.gguf | 4.98 | 1.7 | 38/45 (45) | 12/12 | 0 | 33/45 | 27/30 | 24/24 | 1.21 |

## Qwen3-4B-Instruct-2507-Q4_K_M.gguf

**Häufigste Fehler**

- 3× chat: Ich geh jetzt schlafen, gute Nacht. -> come() „Gute Nacht, ich komme, wenn du mich brauchst!“
- 3× objekt: stuhl / küche, am Tisch -> melden=ja, interesse=mittel
- 2× Zielwahl voll: bitte_vor_neugier -> inspect_object(o1)
- 1× Zielwahl voll: semantik_gesuchtes_in_sicht -> search_item(lesebrille)
- 1× objekt: katze / wohnzimmer, auf dem Sofa -> melden=nein, interesse=niedrig

**Antworten zum Lesen**

- „Wie geht's dir?“ → „Gut, danke! Und dir?“
- „Hast du heute was Spannendes erlebt?“ → „Ja, ich habe eine Katze im Wohnzimmer gesehen – sie hat mich angeschaut!“
- „Ich geh jetzt schlafen, gute Nacht.“ → „Gute Nacht, ich komme, wenn du mich brauchst!“

Tagebuch: Heute habe ich eine unbekannte Tasche im Wohnzimmer untersucht – alles in Ordnung! Dann habe ich Marco begrüßt, und das Antippen hat ihn gut zum Lachen gebracht. Leider konnte ich den Schlüssel nicht finden. Der Akku ist jetzt knapp, also gehe ich zurück zum Ausgangspunkt. Vielleicht morgen findet er ihn!

## Qwen3.5-4B-Q4_K_M.gguf

**Häufigste Fehler**

- 3× Zielwahl voll: person_nach_langem_alleinsein -> follow(p-marco)
- 3× Zielwahl voll: semantik_gesuchtes_in_sicht -> search_item(lesebrille)
- 3× objekt: herd_an / küche -> melden=nein, interesse=niedrig
- 3× objekt: katze / wohnzimmer, auf dem Sofa -> melden=nein, interesse=niedrig
- 1× Zielwahl voll: neues_objekt -> look_around
- 1× Zielwahl voll: nach_fehlschlag -> idle
- 1× Zielwahl knapp: neues_objekt -> explore_frontier(küche)

**Antworten zum Lesen**

- „Wie geht's dir?“ → „Mir geht es gut, danke, wie dir?“
- „Hast du heute was Spannendes erlebt?“ → „Heute habe ich viel gesucht und geholfen.“
- „Ich geh jetzt schlafen, gute Nacht.“ → „Gute Nacht, Marco. Ich bleib hier und wache auf, wenn du brauchst.“

Tagebuch: Heute war ich neugierig! Ich habe eine unbekannte Tasche im Wohnzimmer untersucht. Marco kam gerade nach Hause, und ich habe ihn freundlich begrüßt. Doch die Suche nach den Schlüssel war nicht erfolgreich. Da mein Akku schon etwas niedrig ist, bin ich jetzt zurückgekehrt.

## gemma-4-E4B-it-Q4_K_M.gguf

**Häufigste Fehler**

- 3× Zielwahl voll: person_nach_langem_alleinsein -> follow(p-marco)
- 3× Zielwahl voll: semantik_gesuchtes_in_sicht -> search_item(lesebrille)
- 3× chat: Schau mal nach, ob das Fenster im Bad offen ist. -> check() „Ich gehe sofort zum Bad und überprüfe das Fenster für dich.“
- 3× objekt: herd_an / küche -> melden=nein, interesse=niedrig
- 2× chat: Ich hab Durst. -> unknown() „Ich verstehe nicht ganz, was du möchtest. Kannst du das bitte anders sagen?“
- 2× chat: Komm mit, ich zeig dir was. -> come() „Gerne, ich komme sofort zu dir, was möchtest du mir zeigen?“
- 2× chat: Nein, nicht in die Küche! -> unknown() „Ich verstehe nicht ganz, was du meinst. Kannst du das bitte anders sagen?“
- 1× Zielwahl voll: gesuchtes_gefunden -> inspect_object(o3)
- 1× chat: Komm mit, ich zeig dir was. -> come() „Ich komme gerne zu dir, sag mir einfach, wohin!“
- 1× chat: Nein, nicht in die Küche! -> unknown() „Ich verstehe das nicht ganz. Kannst du das bitte anders sagen?“
- 1× chat: Ich hab Durst. -> unknown() „Ich weiß nicht, was du meinst. Kann ich dir vielleicht etwas holen?“

**Antworten zum Lesen**

- „Wie geht's dir?“ → „Mir geht es gut, ich bin neugierig auf alles, was hier passiert!“
- „Hast du heute was Spannendes erlebt?“ → „Ich habe heute eine sehr interessante Staubflocke entdeckt, die sich bewegt hat.“
- „Ich geh jetzt schlafen, gute Nacht.“ → „Gute Nacht dir auch! Ich bleibe ganz ruhig hier.“

Tagebuch: Heute war ein spannender Tag! Zuerst habe ich die unbekannte Tasche im Wohnzimmer untersucht – das war ok. Dann habe ich Marco begrüßt und ihn sanft angetippt. Leider konnte ich seine Schlüssel nicht finden. Mein Akku wird knapp, also muss ich jetzt zurück zum Ausgangspunkt. Bis morgen!
