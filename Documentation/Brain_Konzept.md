# SLARC – Konzept High-Level-Brain

Stand: 08.11.2026, Entwurf V0.3 (V0.7: Pi-Messung Qwen3.5 Text und Bild, Abschnitt 17; V0.2: Bedürfnis Gesellschaft, erste Umsetzung in `src_dev/ai/brain/`; V0.3: neue Rollenverteilung Code/LLM nach dem ersten Modelltest, Abschnitt 15). Ergebnis aus dem Brain-Chat. Ersetzt das Prinzip "klare Aufgabe → Behavior-Tree-JSON" (`src_dev/ai/exploration_manager_V4.py`) durch ein System, das eigenen Bedürfnissen folgt.

Kennzeichnung wie in `Hardware_Interfaces.md`: **(fest)** entschieden, **(Annahme)** Startwert, **(offen)** noch zu entscheiden.

---

## 1. Ziel

SLARC soll sich selbstständig bewegen und entscheiden und dabei wie ein Lebewesen wirken, nicht wie eine Sprachfernsteuerung. Bisher braucht er Aufträge wie "Laufe nach Norden, bis der Akku leer ist". Künftig handelt er aus Bedürfnissen heraus: Neugier, Wunsch nützlich zu sein, Wunsch nach Gesellschaft, Energiebedarf, dazu ein Sicherheitsempfinden. Menschen können Bitten äußern, die er in diese Bedürfnisse einordnet.

---

## 2. Grundsätze

1. **Bedürfnisse sind Zahlen im Code, nicht Sätze im Prompt (fest).** Ein 4B-Modell wägt Zahlen nicht zuverlässig ab und behält keinen Zustand über Aufrufe hinweg. Das Bedürfnismodell läuft deterministisch auf dem Pi.
2. **Sicherheit entscheidet nie das LLM (fest).** Harte Grenzen setzt der Code durch, mit Vetorecht über jede Zielwahl. Das LLM sieht nur ein Unbehagens-Signal.
3. **Das LLM wird selten gefragt (fest).** Nur bei Ereignissen, Richtwert höchstens alle paar Minuten. Dazwischen laufen Verhalten und Behavior Tree ohne LLM.
4. **Lebendigkeit kommt aus Ausdruck und Variation, nicht aus Entscheidungsqualität.** Cozmo, Vector und Aibo wirkten lebendig ohne LLM. Der größte Hebel sind Körpersprache, Gewöhnung, Zögern und Zufall.
5. **Das LLM ist für das Semantische da:** Was ist hier interessant? Wo stehen wahrscheinlich Dosen? Was meint der Mensch? Und es erzählt im Tagebuch, was SLARC tut und warum.
6. **Architekturregel bleibt (fest):** Die Fortbewegung auf dem ESP32 nutzt keine Weltkoordinaten. Karte, Orte und Rückweg liegen nur auf dem Pi (SLAM).

---

## 3. Schichten

| Schicht | Wo | Takt | Aufgabe |
|---|---|---|---|
| Reflexe und Ausdruck | ESP32 | 100 Hz | Balance, Fußkontakte, Hochheben/Antippen erkennen, Idle-Bewegungen, Ausdrucksparameter des Gangs, Denk-Pose |
| Verhalten | Pi, `bt_executor` | 10 Hz | Ein Verhalten aus dem Katalog ausführen (Behavior Tree), Fehlschläge melden |
| Bedürfnisse und Gedächtnis | Pi | 1 Hz | Bedürfnisse aktualisieren, Verhalten vorschlagen, Sicherheits-Veto, Gedächtnis pflegen, LLM auslösen |
| Brain (LLM) | Pi, llama.cpp | ereignisgesteuert | Ziel aus einem Menü wählen, Sprache/Text deuten, Tagebuch |

Die Schnittstelle zum ESP32 bleibt das Protokoll (`SLARC Pi↔ESP32 Protokoll v0.1.pdf`). Für den Ausdruck sind dort Erweiterungen nötig (Abschnitt 6).

---

## 4. Bedürfnisse

Jedes Bedürfnis ist ein Wert 0…1, der im Takt von 1 Hz aus Messwerten und Zeit berechnet wird. Für das LLM wird er in Stufen übersetzt: **ruhig, leicht, mittel, hoch, dringend**. Alle Zeitkonstanten und Schwellen sind Annahmen und werden im Betrieb eingestellt.

### 4.1 Energie (fest: Rückkehr zum Ausgangspunkt)

- **Eingänge:** Akkuspannung unter Last (Treiber-INA219), daraus Ladezustand über eine stückweise lineare Zellkurve (Annahme, mit echter Entladekurve ersetzen); geschätzter Energiebedarf für den Rückweg zum Ausgangspunkt aus Weglänge (SLAM) und mittlerem Verbrauch je Meter.
- **Wert:** steigt, je kleiner die Reserve über dem Rückwegbedarf ist. Feste Schwellen in Volt reichen nicht: weit weg vom Start muss er früher umkehren.
- **Verhalten:** ab "hoch" bevorzugt er Ziele in Richtung Ausgangspunkt, bei "dringend" kehrt er ohne LLM zurück (Code-Regel, nicht verhandelbar). Am Ausgangspunkt legt er sich hin, meldet sich und fährt herunter.
- **Harte Grenzen** aus `Hardware_Interfaces.md`: Warnung 10,5 V unter Last, Bewegung beenden bei 9,9 V.
- **Ausdruck:** müde = tieferer Körper, langsamerer Gang, weniger Idle-Bewegung.

### 4.2 Neugier

- **Eingänge:** Anteil unerkundeter Fläche in der Nähe, neue oder lange nicht gesehene Objekte, Objekte, die sich bewegt haben (Movement Confidence aus dem Lokalisierungskonzept), Zeit seit der letzten neuen Information.
- **Gewöhnung:** jedes Objekt und jeder Ort hat einen Gewöhnungswert, der beim Betrachten steigt und langsam abklingt (Annahme: Halbwertszeit Stunden bis Tage). Bekanntes wird langweilig, Neues zieht an.
- **Verhalten:** erkunden, Objekt untersuchen (hinwenden, annähern, mit einem Vorderbein antasten), umsehen.
- **Ausdruck:** Körper zum Objekt geneigt, kurze Schritte, Pausen zum Hinsehen.

### 4.3 Nützlichkeit

- **Eingänge:** offene Bitten von Menschen, erkannte Gelegenheiten aus einer festen Liste von Diensten (Abschnitt 5), Zeit seit der letzten nützlichen Handlung.
- **Lernen durch Lob:** jeder Dienst hat ein Gewicht. Lob (Antippen des Panzers, "gut gemacht" im Chat) erhöht es dauerhaft, Tadel senkt es. So entstehen über Wochen Vorlieben, also eine Persönlichkeit.
- **Wichtig:** Das LLM darf nur Dienste aus der Liste wählen. Ohne feste Liste erfindet es welche.

### 4.4 Gesellschaft (fest, ergänzt 07.11.2026)

- **Eingänge:** Zeit seit dem letzten Kontakt zu einem Menschen, Menschen in der Nähe (≤ 2 m).
- **Wert:** steigt beim Alleinsein langsam (Annahme: ~63 % nach 20 min), sinkt in der Nähe eines Menschen schnell (Zeitkonstante ~1 min). Begrüßen und Begleiten zählen als Kontakt.
- **Verhalten:** Menschen begrüßen (dieselbe Person frühestens nach 10 min wieder), begleiten, sich in die Nähe begeben.
- **Ausdruck:** gesellig = leicht aufgerichtet, lebhafte Idle-Bewegung, gelbe LEDs.

### 4.5 Sicherheit

Zwei getrennte Teile:

- **Harte Grenzen (Code, Veto):** Kippwinkel, Treppenkante ohne Kletterfreigabe, Akku unter 9,9 V, Mensch näher als ein Mindestabstand bei Bewegung, Servo-Übertemperatur, Fußkontakt-Widersprüche. Verletzt ein Ziel eine Grenze, wird es gar nicht erst ins Menü aufgenommen oder abgebrochen.
- **Unbehagen (Bedürfnis):** steigt bei Dunkelheit, unbekanntem Untergrund, Enge, schnell bewegten Objekten, kurz nach einem Sturz oder Rutschen. Es senkt die Bereitschaft für Neugier-Verhalten und erzeugt Zögern.
- **Ausdruck:** geduckt, breiter Stand, langsamer, bei Schreck kurzer Rückzug.

### 4.6 Konflikte

Liegen zwei Bedürfnisse nahe beieinander, entscheidet nicht der Größere hart. Energie dämpft alle anderen Ziele außer Heimweg, Ruhe, Rückzug und Abwarten, damit auch die Code-Auswahl Regel 3 aus dem Prompt einhält. Typisch ist Neugier gegen Unbehagen bei einem unbekannten Objekt: annähern, zurückweichen, wieder annähern. Dieses sichtbare Zögern wirkt stark lebendig und wird als eigenes Verhalten modelliert.

---

## 5. Verhaltenskatalog (Annahme, erste Fassung)

| Verhalten | Bedürfnis | Voraussetzung | Ausdruck |
|---|---|---|---|
| `idle` | – | immer | Gewicht verlagern, "atmen", Fuß tippen |
| `look_around` | Neugier | steht | Körper dreht/neigt sich, Pausen |
| `explore_frontier` | Neugier | Karte hat Grenzen | normaler Gang, gelegentlich anhalten |
| `inspect_object(obj)` | Neugier | Objekt bekannt, erreichbar | hinwenden, annähern, antasten |
| `approach_avoid(obj)` | Neugier + Unbehagen | Konflikt | annähern, zurück, wieder |
| `search_item(klasse)` | Nützlichkeit | Klasse in der Detektion | systematisch absuchen |
| `report(text)` | Nützlichkeit | etwas Meldenswertes | anhalten, Vorderbein heben, Meldung senden |
| `greet(person)` | Gesellschaft, Nützlichkeit | Person erkannt | hinwenden, kurz aufrichten, LED |
| `follow(person)` | Gesellschaft, Nützlichkeit | Bitte oder Gesellschaft hoch | Abstand halten |
| `push_out(obj)` | Nützlichkeit | Objekt unter Möbel, flach genug | tief gehen, schieben |
| `fetch(obj)` | Nützlichkeit | Meilenstein Dose | später |
| `return_home` | Energie | Rückweg bekannt | müder Gang |
| `rest` | Energie | am Ausgangspunkt | hinlegen, LED dimmen |
| `retreat` | Sicherheit | Unbehagen hoch | geduckt zurück |
| `think` | – | LLM wird gefragt | Denk-Pose (siehe 8.2) |

Realistisch nach Machbarkeit: suchen und melden > begrüßen und begleiten > schieben > holen. "Aufräumen" (Dinge an ihren Platz) ist ohne Greifer kaum machbar und wird nicht versprochen.

---

## 6. Ausdruck

Der Ausdruck kommt zum großen Teil aus Parametern, die jedes Verhalten mitgibt:

- Körperhöhe, Neigung (Pitch/Roll), Blickrichtung des Körpers.
- Gangtempo und Schrittlänge, Pausen.
- Idle-Amplitude und -Frequenz (nie ganz still).
- Zufallsanteil: kein Ablauf wird exakt wiederholt; bei fast gleichwertigen Optionen nicht immer dieselbe.
- LEDs (WS2812 an IO4): Farbe und Puls für Stimmung und Aufmerksamkeit.
- Später Laute (Abschnitt 10).

**(offen)** Das Protokoll v0.1 braucht dafür einen Stream oder eine Konfig für "Stimmung" (Höhe, Tempo, Idle) und Aktionen für Gesten (Bein heben, Antasten, Denk-Pose). Das klärt der ESP32-Chat.

Reaktionen, die der ESP32 selbst erkennt und dem Pi meldet: Hochheben (IMU, alle Füße ohne Kontakt), Antippen des Panzers (IMU-Impuls im Stand), Rutschen.

---

## 7. Gedächtnis

Auf dem Pi, persistent (Annahme: SQLite oder JSON-Dateien):

- **Orte:** Ausgangspunkt, benannte Bereiche, Lieblingsorte (häufig mit Lob verbunden), Gefahrenorte.
- **Objekte:** Klasse, letzter Ort, Movement Confidence, Gewöhnungswert.
- **Menschen:** wiedererkannt (wenn die Perzeption das kann), letzte Begegnung, offene Bitten.
- **Gewichte der Dienste** (Lernen durch Lob).
- **Tagebuch:** kurze Einträge je Entscheidung und Ereignis. Das LLM formuliert daraus auf Nachfrage eine Erzählung. Das Erzählen trägt viel zum Eindruck eines Wesens bei.

---

## 8. Entscheidungszyklus

### 8.1 Ohne LLM (1 Hz)

1. Bedürfnisse aktualisieren.
2. Sicherheits-Veto prüfen; bei Verletzung sofort `retreat` oder Stopp.
3. Energie "dringend" → `return_home` (Regel).
4. Läuft ein Verhalten und ist es noch sinnvoll → weiter.
5. Sonst einfache Auswahl im Code (gewichtete Zufallswahl aus den passenden Verhalten), oder das LLM fragen, wenn ein Auslöser vorliegt.

### 8.2 Auslöser für das LLM und Denk-Zustand (fest)

Auslöser: ein Bedürfnis wechselt die Stufe nach oben, ein Ziel ist erreicht oder gescheitert, ein neues Objekt oder ein Mensch taucht auf, eine Nachricht aus dem Chat kommt an.

Während das LLM rechnet, geht SLARC in den **Denk-Zustand**: Perzeption und Motion auf dem Pi pausieren, damit das LLM alle Kerne hat. Der ESP32 bleibt aktiv (Balance, Fußkontakte, Hochheben) und zeigt eine Denk-Pose: wiegen, hinlegen oder eine andere Bewegung. Die Pause ist damit selbst Ausdruck. Sie darf nur selten kommen, sonst wirkt SLARC träge.

Liefert das LLM nicht in der Zeit (Annahme: 60 s) oder ungültig, entscheidet die Code-Auswahl aus 8.1.

---

## 9. Schnittstelle zum LLM

### 9.1 Eingabe (Beispiel)

Kurz und in Stufen, keine Fließkommazahlen. Der Systemprompt bleibt gleich und wird gecacht; nur dieser Teil ist neu. Stufenwechsel mit Hysterese (±0,05 um jede Grenze), damit ein Wert an der Grenze nicht zwischen zwei Stufen flackert und ständig das LLM auslöst.

```
ZUSTAND
Energie: leicht (Rückweg 12 m)
Neugier: hoch
Nützlichkeit: mittel
Gesellschaft: leicht
Unbehagen: ruhig
Ort: Flur, nahe Wohnzimmertür
ZULETZT: explore_frontier erfolgreich beendet
NEU GESEHEN: Tasche (Boden, Wohnzimmer, 2 m) — unbekannt
MENSCHEN: keiner
OFFENE BITTEN: "Schlüssel suchen" (vor 40 min, von Marco)
MÖGLICHE ZIELE
1 inspect_object(Tasche)
2 search_item(Schlüssel)
3 explore_frontier(Küche)
4 look_around
5 return_home
```

### 9.2 Ausgabe

Per Grammatik (llama.cpp GBNF) erzwungen:

```json
{"begruendung": "Marco sucht seinen Schlüssel; die Tasche liegt auf dem Weg, ich schaue sie dabei an.", "ziel": 2, "stimmung": "eifrig"}
```

- `begruendung`: ein Satz, geht ins Tagebuch. Steht **vor** der Zielnummer, damit das Modell erst abwägt und dann wählt.
- `ziel`: nur Nummern aus dem Menü.
- `stimmung`: aus fester Liste, steuert Ausdrucksparameter.

### 9.3 Regeln für den Prompt

- Sicherheitsregeln in einfacher Sprache, keine internen Klassennamen (Erkenntnis aus dem Exploration Manager).
- Persönlichkeit kurz beschreiben (Wesen, nicht Assistent), wenige Beispiele (Few-Shot) für typische Abwägungen.
- Temperatur niedrig (Annahme 0,3), Zufall kommt aus der Code-Auswahl.

---

## 10. Interaktion mit Menschen

SLARC hat bisher weder Lautsprecher noch Mikrofon. Aufbau in Stufen:

1. **Ohne neue Hardware (fest als erster Schritt):**
   - Web-Oberfläche auf dem Pi (ohnehin für "power off" vorgesehen): Text-Chat, Tagebuch, Bedürfnisse.
   - Meldungen aufs Handy (z. B. ntfy oder Telegram).
   - Körpersprache und LEDs.
   - Antippen des Panzers als Lob (IMU).
2. **Lautsprecher:** nicht-sprachliche Laute (Zirpen, Brummen, fragender Ton). Empfehlung, hier zu bleiben: Sprechen weckt Erwartungen an einen Assistenten, die ein 4B-Modell enttäuscht. Falls doch Sprache: Piper (deutsche Stimmen, läuft auf dem Pi).
3. **Mikrofon:** Wake-Word (openWakeWord), dann Spracherkennung (whisper.cpp tiny/base oder Vosk). Nur im Stand zuhören, beim Laufen übertönen die Servos alles.

**Hardware-Hinweis (an den Hardware-Chat):** I²S am Pi liegt auf GPIO18–21, GPIO18 ist der Kameratrigger. Daher Audio über USB (USB-Soundkarte mit Mini-Verstärker, USB-Mikrofon). Platz am Panzer vorsehen.

Das LLM bekommt in jeder Stufe Text; das Konzept ändert sich durch den Kanal nicht.

---

## 11. Modellwahl

- Pi 5 mit **8 GB RAM (fest)**. Ein 4B-Modell in Q4 (gut 2,5 GB) passt neben Perzeption und Rest, 9B nicht.
- **Aktuell:** Qwen3-4B-Instruct-2507 Q4_K_M über llama.cpp (llama-cpp-python), wie im bestehenden Code. Das Modell hat keinen Thinking-Modus; `/no_think` ist dafür vermutlich unnötig (prüfen).
- **Kandidaten (Annahme, messen):** Qwen3.5-4B und -2B (März 2026, hybride Attention), Gemma 4 E2B/E4B (April 2026, Function Calling). Ob E4B mit 8 GB auskommt, ist offen.
- **Vorgehen:** Entscheidungs-Testsuite mit festen Szenarien (Zustand → erwartetes Ziel oder Menge erlaubter Ziele) aufbauen und alle Kandidaten auf dem Pi damit messen: Trefferquote, ungültige Ausgaben, Zeit bis zur Antwort mit gecachtem Systemprompt.
- Grobe Erwartung für 4B Q4 auf dem Pi 5: Erzeugung im einstelligen Token/s-Bereich, eine Entscheidung 20–40 s. Für die oberste Schicht ausreichend.
- Ollama (`Documentation/How to create SLARC-brain model.odt`, Llama-3.2-3B) ist überholt. Weiter mit llama.cpp, weil sich die Ausgabe dort per Grammatik erzwingen lässt.

---

## 12. Bezug zum bestehenden Code

| Datei | Weiterverwendung |
|---|---|
| `src_dev/ai/exploration_manager_V4.py` | Modell-Laden, Normalisierung und Validierung übernehmen; Aufgabe wird von "Absicht → Policy" zu "Zustand → Zielwahl" |
| `src_dev/ai/mission_replanner_V1.py` | geht in der Zielwahl auf |
| `src_dev/ai/bt_executor.py` | führt die Verhalten aus Abschnitt 5 aus; `MockBlackboard` als Testumgebung für das Bedürfnismodell |
| `src_dev/ai/test_suite_V4.py` | Vorlage für die Entscheidungs-Testsuite |
| `src_dev/launch_all.py` | Brain-Prozess einhängen, Denk-Zustand mit Vision koordinieren |

---

## 13. Offene Punkte

1. Bedürfnismodell als Python-Modul mit Testumgebung (MockBlackboard), Zeitkonstanten einstellen.
2. Systemprompt und Few-Shot-Beispiele schreiben.
3. Entscheidungs-Testsuite und Modellvergleich auf dem Pi.
4. Protokoll-Erweiterung für Ausdruck und Denk-Pose (ESP32-Chat).
5. Erkennung von Antippen und Hochheben auf dem ESP32 (ESP32-Chat).
6. Web-Oberfläche mit Chat und Tagebuch (Pi-Software).
7. Liste der Dienste für "Nützlichkeit" mit Marco festlegen.
8. Audio-Hardware (Stufe 2/3) im Hardware-Chat.
9. Bitten aus dem Chat in Dienste übersetzen (eigener kleiner LLM-Aufruf oder Regeln). Bisher kommen Bitten schon strukturiert als `Request` an.
10. Brain-Prozess mit Denk-Zustand in `launch_all.py` einhängen; Simulation eines ganzen "Tages" mit dem MockBlackboard, um Abwechslung und Rhythmus zu beurteilen.
11. **Vision-Sprachmodell für seltene Bildfragen** (notiert 07.11.2026): Qwen3.5-4B nimmt laut Modellkarte auch Bilder, braucht dafür zusätzlich `mmproj-Qwen3.5-4B-f16.gguf` (~0,7 GB). Idee: Zustände, die die Detektion nicht kennt („Fenster offen?“, „Licht an?“, „Welcher Raum ist das?“), mit einem einzelnen Kamerabild fragen statt je eine Klasse zu trainieren. Offen: Unterstützung in llama-cpp-python (sonst `llama-server` über HTTP), Dauer je Bild auf dem Pi, Qualität. Erster Test auf dem PC mit Fotos aus der Wohnung. Werkzeug: `brain/vision/compare_vlm.py` (Qwen3.5-4B gegen ein größeres Modell, z. B. Qwen3.5-9B, auf COCO als Wahrheit und mit eigenen Fotos; Vorlage `questions_template.json`). Kein Vergleich mit dem YOLO-Head: der liefert Boxen, das VLM Antworten. Geschwindigkeit auf dem Pi: `brain/vision/bench_pi.py`, Anleitung in `brain/vision/README.md`. Erster Eindruck (PC, 10 COCO-Bilder, 07.11.2026): Precision 0,83, Recall 0,80, 0,32 s je Bild auf der GPU; erkannte Dosen im Kühlregal, die COCO nicht als Klasse kennt. 100 Bilder (PC, 08.11.2026, Seed 7, `--indoor`, 640 px): Precision 0,85, Recall 0,85, Recall für nicht kleine Objekte 0,90, keine ungültige Antwort, 0,32 s je Bild auf der GPU. Häufig übersehen: Handtasche, Stuhl, Schüssel; häufig zusätzlich genannt: Topfpflanze, Tasse, Stuhl, Flasche (teils vermutlich in COCO nur nicht annotiert, nicht geprüft). Einschränkung: `--indoor` lässt auch Straßenszenen mit Regenschirm durch. Messungen nach Bildgröße und auf dem Pi (08.11.2026): Abschnitt 17. Größenordnung: Bild-Encoder (mmproj, ~0,3 Mrd. Parameter) + 4 Mrd. Sprachmodell gegen ~5 Mio. für Backbone und YOLO-Head zusammen.
12. **Perzeption kennt keine Türen, Fenster, Dosen** (07.11.2026): Die Detektion V5.0 hat 40 COCO-Klassen + „unbekannt“ (`ROBOT_CAT_IDS` in `FusedHexapodModel_V5_0-Phase-1.py`), davon 10 Außenklassen (Auto, Ampel, Bank …). Die Außenklassen bleiben: SLARC soll auch draußen laufen, Bank, Hydrant und Ampel taugen dort als Anker, Bäume erkennt die Detektion vermutlich als „topfpflanze“, das ist so akzeptiert (Marco, 08.11.2026). Für Navigation an benennbaren Ankern innen und für den Meilenstein Dose fehlen Tür, Fenster, Dose; sie kommen zusätzlich dazu. Anforderung an den KI-Chat; Quellen z. B. ADE20K, Open Images.

---

## 14. Umsetzung V0.1 (`src_dev/ai/brain/`)

| Datei | Inhalt |
|---|---|
| `datatypes.py` | Beobachtung, Objekte, Personen, Bitten, Menü-Optionen |
| `memory.py` | Gewöhnung (Halbwertszeit 6 h), Gewichte der Dienste, Tagebuch, JSON-Persistenz |
| `needs.py` | Bedürfnismodell mit fünf Bedürfnissen und Stufen mit Hysterese |
| `safety.py` | harte Grenzen mit Veto |
| `behaviors.py` | Verhaltenskatalog, Menübau (höchstens 7 Ziele), Code-Auswahl (Softmax), Stimmungen → Ausdrucksparameter |
| `arbiter.py` | 1-Hz-Zyklus, Regeln, Auslöser, Abkühlzeit 2 min (Chat sofort), Lob durch Antippen |
| `prompt.py` | Systemprompt, drei Few-Shot-Beispiele, Zustandstext, GBNF-Grammatik |
| `llm.py` | llama.cpp-Anbindung mit Zeitlimit, Mock-Backend |
| `scenarios.py` | 15 Entscheidungs-Szenarien |
| `run_decision_suite.py` | Modellvergleich auf dem Pi |
| `tests/test_brain.py` | Unit-Tests (ohne Modell) |

**Aufrufe** (aus `src_dev/ai`):

```
python -m pytest brain/tests -q
python -m brain.run_decision_suite --mock
python -m brain.run_decision_suite --model Qwen3-4B-Instruct-2507-Q4_K_M.gguf --repeat 3 --out qwen3.json
```

**Prüfstand (07.11.2026):** Unit-Tests grün. Die Grammatik wurde mit dem llama.cpp-Parser (Qwen2-Vokabular) geprüft: Sie nimmt die Few-Shot-Antworten an und lehnt ungültige Nummern und erfundene Stimmungen ab. Erster Lauf mit echtem Modell: Abschnitt 15.

**Wichtig für die Bewertung:** Die Suite mischt die Menü-Reihenfolge standardmäßig und gibt als Vergleich an, wie oft die beste Code-Option schon richtig wäre. In 14 von 15 Szenarien trifft das der Code bereits. Das LLM lohnt sich also nur, wenn es mindestens gleich gut ist und die semantischen Fälle löst (`semantik_gesuchtes_in_sicht`: die gesuchte Lesebrille liegt schon im Bild). Dafür braucht es mehr semantische Szenarien.

---

## 15. Erster Modelltest und neue Rollenverteilung (07.11.2026, V0.3)

**Messung** (Marco, PC unter WSL, RTX 3080 Ti, Qwen3-4B-Instruct-2507 Q4_K_M, Menü gemischt, 15 Szenarien × 3):

| Größe | Wert |
|---|---|
| Treffer LLM | 36/45 |
| Treffer Code allein | 42/45 |
| ungültige Antworten | 0 |
| Wahl auf Position 1 | 20 % (liest das Menü, keine Positionsneigung) |
| Latenz Median / max (GPU) | 0,74 s / 1,06 s; Prompt ~1220 Tokens. Für den Pi nicht aussagekräftig |

Fehler des LLM:
- `energie_hoch_weit_weg` 0/3: wählt trotz Regel und passendem Few-Shot-Beispiel die Bitte ("Ich bin müde, aber die Bitte ist wichtig"). Sicherheitsrelevant.
- `bitte_vor_neugier` 1/3: untersucht lieber den Karton und begründet das nachträglich.
- `semantik_gesuchtes_in_sicht` 0/3: verbindet "Brille in Sicht" nicht mit der Bitte "Lesebrille".
- Begründungen meist natürlich, teils inhaltlich falsch ("Ich wollte lange allein sein") oder grammatisch holprig.

**Entscheidung (fest):** Die Handlungswahl liegt beim Code, wie die Aktionsauswahl bei Tieren nicht im sprachlichen Teil liegt (verhaltensbasierte Robotik, Drei-Schichten-Architektur). Das LLM bekommt die Fragen, die nur es beantworten kann.

**Umsetzung V0.2 des Brain:**
- Energie ab "hoch" ist eine Regel im Arbiter (heim bzw. ruhen); das Menü enthält dann nur Heimweg, Ruhe, Rückzug, Abwarten.
- Bitte und Fund verknüpft der Code (`matches()`, Teilwort: "brille" ↔ "lesebrille"). Das Menü bietet dann "Melden: … passt zur Bitte".
- Das LLM entscheidet nur noch knappe Fälle: höchstens 3 Optionen innerhalb 0,15 Nutzen vom besten (`close_options`). Eindeutige Fälle entscheidet der Code sofort, ohne Denk-Zustand.
- Neue semantische Aufgaben in `semantic.py`, je mit eigenem Prompt, Few-Shot und GBNF:
  - `interpret_chat`: Nachricht → Dienst (search, fetch, follow, come, push_out, check, stop, praise, scold, smalltalk, unknown), Gegenstand, kurze Antwort. Daraus macht `to_request()` eine Bitte fürs Menü.
  - `assess_object`: Interesse (niedrig/mittel/hoch) und ob gemeldet werden soll.
  - `search_places`: wahrscheinlichste Orte für einen Gegenstand aus den bekannten Orten.
  - `narrate`: Tagebuch erzählen.
- Testsuite dafür: `open_scenarios.py` (15 Chat-, 10 Objekt-, 8 Such-Fälle) und `run_open_suite.py`. Hier gibt es keine Code-Vergleichsbasis; Maßstab ist, ob die Antwort für einen Menschen stimmt.
- `run_decision_suite.py --close` prüft die Zielwahl so, wie sie jetzt im Betrieb läuft.

**Ehrliche Einschränkung:** Die 15 Entscheidungs-Szenarien hat der Code nach diesen Änderungen alle richtig. Das ist teilweise zirkulär, weil die Regeln aus genau diesen Fehlern abgeleitet sind. Neue Szenarien, die nicht zum Abstimmen benutzt wurden, sind nötig, bevor man daraus Schlüsse zieht.

**Offen:**
- Mehrere Aufgaben teilen sich ein Modell. Ohne Cache rechnet llama.cpp bei jedem Wechsel den Systemprompt neu (auf dem Pi ~1000 Tokens). Option `ram_cache_mb` (LlamaRAMCache) ist eingebaut, Speicherbedarf und Wirkung auf dem Pi messen.
- Chat-Ergebnisse `check`, `stop`, `praise`, `scold` im Arbiter verarbeiten; `fetch` erst mit dem Meilenstein Dose.
- Modellvergleich mit beiden Suiten: Qwen3.5-4B, Gemma 4 E4B. Werkzeug: `python -m brain.compare_models --gpu-layers -1` (alle `*.gguf` in `~/.models`, Bericht `modellvergleich.md`).

**Zweiter Lauf, semantische Aufgaben** (Marco, 07.11.2026, Qwen3-4B Q4, PC/GPU, 3 Wiederholungen): Chat 36/45, Objekt 26/30, Suchorte 24/24, Zielwahl knapp 12/12 (11 Szenarien eindeutig vom Code). Echte Fehler: „Gute Nacht“ → `come` (3/3), Stuhl am Tisch soll gemeldet werden (3/3), Smalltalk erfindet Erlebnisse („habe eine Katze gesehen“). Zwei Chat-Erwartungen waren zu eng (Cola → Flasche, Durst → Tasse) und wurden erweitert.

**Modellvergleich** (Marco, 07.11.2026, PC/GPU, 3 Wiederholungen; nur die im Betrieb relevanten Teile):

| Modell | GB | knapp | Chat | Objekt | Suchen | gesamt |
|---|---|---|---|---|---|---|
| Qwen3-4B-Instruct-2507 Q4_K_M | 2,5 | 12/12 | 42/45 | 26/30 | 24/24 | 104/111 |
| Qwen3.5-4B Q4_K_M | 2,7 | 11/12 | 45/45 | 24/30 | 24/24 | 104/111 |
| Gemma 4 E4B Q4_K_M | 5,0 | 12/12 | 33/45 | 27/30 | 24/24 | 96/111 |

Qwen3.5 und Gemma meldeten den eingeschalteten Herd 3/3 nicht. Qwen3.5 antwortet im Smalltalk am ehrlichsten. Gemma ist doppelt so groß und deutet Chat am schlechtesten. Bei 10 Objekt-Fällen sind Unterschiede von 2–3 Treffern Rauschen. **Entscheidung (vorläufig):** Qwen3-4B-Instruct-2507 bleibt (kleinstes Modell, schnellstes, kein Sicherheitsfehler).

**V0.3 des Brain:**
- Gefahren (`HAZARDS`: Herd an, Wasser auf dem Boden, Scherben, Rauch …) meldet der Code immer und sofort, vor Energie und LLM.
- `assess_object` fragt das LLM nur für unbekannte Klassen; Gefahren, Meldenswertes und Alltägliches (`ROUTINE`, Möbel) entscheidet eine Regel. Die Suite zählt Regel- und LLM-Fälle getrennt.
- Chat bekommt die letzten Tagebuch-Einträge (`ERLEBT`) und die Regel, nur davon zu erzählen. Neues Few-Shot für Verabschiedungen (bewusst anders formuliert als der Testfall „Gute Nacht“).

**Prompt-Größen** (Qwen-Tokenizer, ChatML):

| Aufgabe | gesamt | fester Teil (System + Beispiele) | neu je Aufruf |
|---|---|---|---|
| Zielwahl (7 Optionen) | 1236 | 1072 | 164 |
| Chat (mit Tagebuch) | 775 | 699 | 76 |
| Objekt | 368 | 334 | 34 |
| Suchorte | 247 | 208 | 39 |
| Tagebuch | 234 | 131 | 103 |

Auf dem Pi entscheidet der Cache: Ohne ihn wird bei jedem Wechsel der Aufgabe der feste Teil neu gerechnet (bis ~1100 Tokens), mit ihm nur 34–164 Tokens. Alle festen Teile zusammen sind ~2400 Tokens; bei Qwen3-4B (36 Schichten, 8 KV-Köpfe à 128, f16) sind das grob 150 kB je Token, also ~360 MB im RAM-Cache (Rechnung, nicht gemessen).

**Holdout (07.11.2026):** Marco hat zehn eigene Chat-Sätze geschrieben (`HOLDOUT_CHAT` in `open_scenarios.py`). Sie dienen nur zur Prüfung; Prompts und Beispiele werden nicht danach abgestimmt. Zwei Sätze zeigen fehlende Fähigkeiten, die getrennt ausgewiesen statt gewertet werden:
- „Überwache das Wohnzimmer!“: kein Dienst „überwachen“.
- „Gehe ins Badezimmer!“: kein Dienst „zu einem Ort gehen“.

Außerdem setzen mehrere Sätze voraus, dass SLARC Personen unterscheidet (Sophia, Laura) und weiß, welches Zimmer wem gehört. Die Perzeption kennt bisher nur „Person“; das Gedächtnis kennt keine Zimmer-Zuordnung (offen).

**Lauf V0.3** (Marco, 07.11.2026 21:46, PC/GPU, 3 Wiederholungen):

| Modell | Chat | Chat eigen (Holdout) | Objekt (LLM allein) | Suchen | knapp |
|---|---|---|---|---|---|
| Qwen3-4B-2507 | 37/45 | 18/24 | 30/30 (12/12) | 24/24 | 12/12 |
| Qwen3.5-4B | 35/45 | 24/24 | 27/30 (9/12) | 24/24 | 11/12 |
| Gemma 4 E4B | 37/45 | 17/24 | 30/30 (12/12) | 24/24 | 12/12 |

- Das Tagebuch im Chat-Prompt hat geschadet (Qwen3 42 → 37, Qwen3.5 45 → 35): „Suche nach Laura!“ wurde zu `search(schlüssel)`, Antworten behaupteten Ergebnisse („Ball gefunden“). Fehler im Vorgehen: zwei Änderungen auf einmal und Tagebuch auch bei Befehlen.
- Holdout: Qwen3.5 löst alle 8 wertbaren Sätze in allen Durchläufen. Bei den Lücken (überwachen, zu Ort gehen) presst jedes Modell die Bitte in einen vorhandenen Dienst, keines sagt „kann ich noch nicht“.
- Mit Gefahren per Regel spricht der unabgestimmte Test eher für Qwen3.5; dagegen stehen 10 Sätze als kleine Stichprobe und ~1,7× Latenz auf dem PC. Entscheidung nach dem nächsten Lauf und der Messung auf dem Pi.

**V0.4 (eine Änderung): Chat zweistufig.** Stufe 1 deutet die Nachricht ohne Tagebuch; die Antwort ist nur eine Bestätigung und darf kein Ergebnis behaupten. Stufe 2 (`talk_reply`) nur bei Smalltalk, mit Tagebuch. Das Few-Shot mit dem erfundenen Ausflug ist entfernt.

---

## 16. Echte Klassen, simulierte Wohnung und Behavior-Tree-Schicht (07.11.2026, V0.5)

**Klassen:** `perception_classes.py` ist die einzige Quelle für alles, was das Brain über Gegenstände weiß: die 41 Klassen der Detektion V5.0 mit deutschem Namen, Art (Anker, Möbel, Ding, Lebewesen, draußen, unbekannt), „meldenswert“ und typischen Räumen, dazu Synonyme („Smartphone“ → handy) und Raum-Anker (Toilette → Bad). Bitten um Dinge, die SLARC nicht sehen kann, beantwortet er ehrlich („Schlüssel kann ich leider noch nicht erkennen“). Die Gefahrenliste ist leer, weil die Detektion keine Gefahrenzustände kennt; der Mechanismus bleibt. Szenarien und Testfälle sind auf echte Klassen umgestellt; die Holdout-Sätze bleiben unverändert.

**Behavior-Tree-Schicht** (`sim/bt.py`): Der Arbiter wählt das Verhalten, `build_tree()` baut dafür einen festen py_trees-Teilbaum, der Runner tickt ihn bis SUCCESS/FAILURE, das Ergebnis geht als `last_result` zurück. Beispiel Suche: Räume nacheinander (zuerst wo zuletzt gesehen, dann typische Räume bzw. `search_places`, dann nach Entfernung), je Raum hingehen, umsehen, „sehe ich es?“, am Ende melden. Das LLM baut nie Bäume. Auf dem Roboter werden nur die Blätter ausgetauscht (Protokoll zum ESP32, SLAM, Perzeption).

**Simulierte Wohnung** (`sim/world.py`): sieben Räume als Graph, Gehen mit 0,12 m/s, Akku mit 15 W Grundlast + 0,2 Wh/m, Gegenstände nur aus echten Klassen, eine Katze, die umherzieht, zwei Personen mit Tagesplan (für SLARC namenlos), Chat-Drehbuch. Keine Physik.

**Aufruf** (aus `src_dev/ai`):
```
python -m brain.sim.day                      # ohne LLM, Chat per Stichwort
python -m brain.sim.day --trees --needs      # mit Bäumen und Bedürfnis-Stufen
python -m brain.sim.day --model Qwen3.5-4B-Q4_K_M.gguf --gpu-layers -1
```

**Was der erste simulierte Tag gezeigt hat** (3 h, ohne LLM) und was geändert wurde:
- Nach dem Erkunden wusste SLARC nichts mehr mit sich anzufangen: 725× Umsehen, 413× Abwarten. Ursache: Umsehen zählte als neue Information und setzte die Langeweile zurück. Neu: Umsehen wird im selben Raum langweilig, Rundgang (`wander`) zu lange nicht besuchten Räumen, Dösen (`doze`) als ruhige Beschäftigung. Räume gewöhnen mit 1 h Halbwertszeit ab, Objekte mit 6 h.
- Laufende Verhalten wurden von jedem neuen Objekt unterbrochen, teils wurde dieselbe Suche neu gestartet. Neu: Unterbrechung nur bei Chat oder einem um 0,2 besseren Ziel, dasselbe Ziel nie neu.
- Die Fernbedienung wurde stündlich erneut gemeldet. Neu: je Objekt und Ort nur einmal.
- Gesucht wurde ohne Gedächtnis (Fernbedienung um 00:04 gesehen, um 00:45 erst im Wohnzimmer gesucht). Neu: `last_seen`, Suche beginnt dort (88 s statt 247 s).
- Ergebnis danach: 125 von 180 min dösend, 6 Rundgänge, Suche direkt am letzten Fundort, keine doppelten Meldungen außer auf Nachfrage. Ob so viel Dösen gewollt ist, ist eine Einstellung (`DOZE_UTILITY`).
- Raum-Anker sind mehrdeutig: das Kinderzimmer mit Bett wird als Schlafzimmer erkannt. Zimmernamen müssen von Menschen kommen.
- Noch nicht gelaufen: Tag mit echtem LLM (`--model`).

**V0.6 nach dem Lauf mit Qwen3.5 (Marco, 07.11.2026):** SLARC döste 125 von 180 min, auch mit LLM; Gesellschaft stand über eine Stunde auf „dringend“, während Marco im Nebenraum saß. Das LLM begründete fast jede Wahl mit Müdigkeit (Energie war „ruhig“) und übernahm „der Weg zurück ist weit“ aus einem Few-Shot-Beispiel.
- Gesellschaft suchen (`seek_company`): ist niemand im Raum, dorthin, wo zuletzt Menschen waren, sonst Wohnzimmer/Küche. Ein Raum, in dem eben niemand war, 15 min nicht erneut (sonst Pendeln Wohnzimmer ↔ Küche).
- Liegen (Dösen, Ausruhen) mit 8 statt 15 W, weil die Servos kein Moment halten (Annahme, messen).
- Dösen sättigt (nach 20 min Dösen in der letzten Stunde nur noch ~37 % Reiz) und lockt mehr bei Energiebedarf.
- Ergebnis ohne LLM: Dösen 45 statt 125 min, Marco wird gesucht, gefunden, begrüßt und begleitet.
- Offen: Few-Shot im Entscheidungs-Prompt ohne konkrete Inhalte; nur Bedürfnisse ab „mittel“ als Grund.

## 17. Messung auf dem Pi 5: Text und Bild (08.11.2026, V0.7)

Aufbau: Pi 5 (8 GB, OS auf USB3-SSD), llama.cpp a691b23 als `llama-server`, `-t 4 -c 4096 -np 1 --cache-ram 0`, Perzeption und Motion aus. Werkzeug `brain/vision/run_pi_matrix.sh` (startet je Konfiguration einen Server, ruft `bench_pi.py` auf), 3 COCO-Bilder je Größe, Median. Keine Drosselung (`throttled=0x0`), Temperatur ≤ 67 °C. Rohdaten in `brain/ergebnisse/2026-11-08/` (`pi_matrix_1540.md`, `pi_bench_*`).

**Randbedingungen (gemessen)**

- `--cache-ram`: neuere llama-server halten zusätzlich einen Prompt-Cache im RAM, Standard 8192 MiB. Damit lief auf dem Pi der Swap voll (2 GB), und neue Bilder zeigten nur 4 Prompt-Tokens (vermutlich falsch wiederverwendete Zustände). Deshalb **(fest)** `--cache-ram 0`. Der Slot-Cache (`--cache-prompt`) bleibt.
- OpenBLAS: kein Unterschied (Zielwahl nach Wechsel 69,7 s mit, 70,0 s ohne BLAS; Bild 320 px je 17,4 s). llama.cpp rechnet Q4-Gewichte mit eigenen ARM-Kerneln. **(fest)** Build ohne BLAS.
- Architektur: Qwen3-4B-2507 ist mit Q4_K_M gleich schnell wie Qwen3.5-4B (Prompt ~19–21 tok/s). Die neue Architektur bremst also nicht.

**Ergebnisse** (Zeit für die ganze Anfrage; „Wechsel“ = fester Prompt-Teil neu gerechnet, „wiederholt“ = im Slot-Cache)

| Modell | mmproj | Bild ja/nein 320 / 448 px | Zielwahl Wechsel / wiederholt | Chat Wechsel / wiederholt | Prompt tok/s | Erzeugung tok/s | frei MB |
|---|---|---|---|---|---|---|---|
| Qwen3.5-4B Q4_K_M | F16 | 18,0 / 28,0 s | 72 / 14 s | 44 / 10 s | 19 | 2,8 | 3548 |
| Qwen3.5-4B Q4_K_M | Q8_0 | 10,6 / 15,6 s | 70 / 12 s | 43 / 8,6 s | 19 | 3,3 | 3810 |
| Qwen3.5-4B Q4_0 | Q8_0 | 9,5 / 13,5 s | 53 / 14 s | 32 / 9,3 s | 28 | 3,0 | 4021 |
| Qwen3.5-2B Q4_K_M | F16 | 12,5 / 20,6 s | 28 / 5,8 s | 18 / 5,2 s | 50 | 7,3 | 5159 |
| Qwen3.5-2B Q4_K_M | Q8_0 | 5,6 / 8,8 s | 28 / 5,8 s | 18 / 5,1 s | 50 | 7,3 | 5444 |
| Qwen3-4B-2507 Q4_K_M | – | – | 83 / 18 s | 46 / 9,5 s | 19 | 2,8 | 4321 |

**Genauigkeit Bild** (PC, 100 COCO-Bilder, Seed 7, alle Szenen, 08.11.2026; F16 und Q8_0 innerhalb ±0,01)

| Modell | Bildkante | Precision | Recall | F1 | Recall nicht klein | ungültig |
|---|---|---|---|---|---|---|
| Qwen3.5-4B | 640 px | 0,84 | 0,86 | 0,85 | 0,91 | 0 |
| Qwen3.5-4B | 448 px | 0,81 | 0,82 | 0,82 | 0,88 | 0 |
| Qwen3.5-4B | 320 px | 0,79 | 0,77–0,78 | 0,78 | 0,84–0,85 | 0 |
| Qwen3.5-2B | 640 px | 0,36–0,37 | 0,82–0,84 | 0,50–0,51 | 0,87–0,88 | 3–5 |

Das 2B nennt fast zwei von drei Klassen zu Unrecht (Flasche 18-mal, Tasse 15-mal, Schüssel 13-mal), es zählt eher die Liste auf, als hinzusehen. „Nicht klein“ ist in Originalpixeln gerechnet (≥ 32×32); bei 320 px Kante schrumpfen solche Objekte auf etwa die Hälfte.

**Folgerungen**

- **(fest)** mmproj Q8_0 statt F16: auf dem PC gleich genau, auf dem Pi halbiert es die Zeit des Bild-Encoders (4B: 18,0 → 10,6 s bei 320 px) und spart ~0,3 GB.
- **(fest)** Qwen3.5-2B nicht für Bildfragen (Precision 0,37). Für Text noch offen, Qualitätsvergleich mit `compare_models` steht aus. Auf dem Pi ist es 2,5-mal schneller (Zielwahl wiederholt 5,8 s).
- **(Annahme)** Bildfragen mit dem 4B bei 320 px als Standard (~10 s, Recall nicht klein 0,84), 448 px für Übersichtsfragen (~14–16 s). Nur als seltene Rückfrage im Denk-Zustand, keine laufende Wahrnehmung.
- Qualität auf dem PC (08.11.2026, `compare_models`, 3 Wiederholungen; `compare_vlm` 320 px):

  | Modell | Zielwahl knapp | Chat | Holdout | Objekt | Suchorte | Bild F1 320 px |
  |---|---|---|---|---|---|---|
  | Qwen3.5-4B Q4_K_M | 12/12 | 45/45 | 24/24 | 25/30 | 23/24 | 0,78 |
  | Qwen3.5-4B Q4_0 | 12/12 | 45/45 | 24/24 | 27/30 | 18/24 | 0,77 |
  | Qwen3.5-2B Q4_K_M | 9/12 | 41/45 | 17/24 | 22/30 | 12/24 | (0,51 bei 640 px) |

  Q4_0 verliert vor allem bei den Suchorten (Koffer dreimal Flur/Kinderzimmer) und gibt bei Bildern viermal eine leere Liste. Das 2B fällt auch bei Text ab (Holdout: „Sophia im Zimmer“ → follow, „Laura“ → person, einmal `check(luz)`).
- **(Annahme)** Qwen3.5-4B Q4_K_M mit mmproj Q8_0. Q4_0 spart nur ohne Cache Zeit (nach Wechsel 53 statt 70 s, mit Cache gleich), kostet aber Treffer. Kommt der Cache je Aufgabe nicht zustande, Q4_0 neu abwägen.
- **(offen)** Bestätigungen im Chat behaupten Ergebnisse: „Steht der Staubsauger im Wohnzimmer?“ → „Ja, der Staubsauger steht im Wohnzimmer.“, ebenso „Licht an?“. Beides kann SLARC gar nicht erkennen; `item_problem` griff nur bei `search`. Die Zählung im Holdout wertete nur den Dienst. Behoben in PR #64 (semantic V0.6): Bestätigungen für Aufträge aus Code-Vorlagen, `item_problem` auch für `check`, die Suite zählt behauptete Ergebnisse.
- **(offen)** Aufgabenwechsel kosten 30–70 s, das ist für den Betrieb zu langsam. Mit Cache sind es 9–14 s. Wege: mehrere Slots (`-np 4`, ein Slot je Aufgabe; Speicher messen) oder Slots je Aufgabe mit `--slot-save-path` sichern und laden. Umgesetzt in PR #64: `ServerBrain` (`brain/llm.py`) mit festem Slot je Aufgabe. Gemessen siehe unten (Slot je Aufgabe).
- **(offen)** Mit Cache bestimmt die Erzeugung die Zeit (~40 Tokens bei ~3 tok/s ≈ 12 s für die Zielwahl). Hebel: kürzere `begruendung` in der Ausgabe und kürzere Beispiele im Prompt (die ohnehin aufgeräumt werden müssen, Abschnitt 15).

**Slot je Aufgabe (Pi, 08.11.2026 17:48, `pi_matrix_1748.md`)**

Qwen3.5-4B Q4_K_M + mmproj Q8_0, ohne BLAS, `--cache-ram 0`, Text-Aufgaben mit den echten Grammatiken. `slots-1`: `-np 1 -c 4096`. `slots-4`: `-np 4 -c 12288` (3072 Tokens je Slot), `ServerBrain`-Zuordnung (Zielwahl 0, Chat 1, Objekt 2, Suchorte und Rest 3).

| Lauf | Zielwahl Wechsel / wiederholt | Chat | Objekt | Suchorte | frei MB |
|---|---|---|---|---|---|
| slots-1 | 71,7 / 12,6 s | 43,7 / 9,4 s | 29,0 / 12,0 s | 23,1 / 12,2 s | 3938 |
| slots-4 | 12,3 / 12,3 s | 8,9 / 8,8 s | 11,2 / 11,3 s | 11,5 / 11,4 s | 2909 |

Der Server-Log bestätigt „selected slot by id“ und nach dem ersten Lauf je Aufgabe nur noch 4 neue Prompt-Tokens. Aufgabenwechsel kosten damit nichts mehr; Preis rund 1 GB RAM.

- **(fest)** llama-server mit `-np 4 -c 12288` und `ServerBrain(n_slots=4)`.
- **(offen)** Beim Start muss jeder Slot einmal seinen festen Prompt rechnen (Zielwahl ~60 s, Chat ~35 s, Objekt ~17 s, Suchorte ~11 s, zusammen gut 2 min). Das gehört in den Start des Brain-Prozesses (vorwärmen, solange SLARC noch steht), nicht in die erste echte Anfrage.
- **(offen)** Mit Cache bestimmt allein die Erzeugung die Zeit: 28–38 Tokens bei ~3,1 tok/s = 9–12 s. Die Zielwahl erzeugt 38 Tokens, davon ist der größte Teil `begruendung`. Kürzere oder gestrichene Begründung würde die Denkpause auf ~3–5 s senken; ob die Trefferquote leidet, auf dem PC mit `compare_models` prüfen.
- **(offen)** 2,9 GB frei mit Modell und vier Slots, ohne Perzeption und Motion. Ob das neben dem vollen Stack reicht, ist ungemessen. Reserven: `-c 8192` (2048 je Slot, Zielwahl braucht ~1170) oder KV-Cache in q8_0.

