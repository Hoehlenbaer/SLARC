# SLARC – Konzept High-Level-Brain

Stand: 07.11.2026, Entwurf V0.1. Ergebnis aus dem Brain-Chat. Ersetzt das Prinzip "klare Aufgabe → Behavior-Tree-JSON" (`src_dev/ai/exploration_manager_V4.py`) durch ein System, das eigenen Bedürfnissen folgt.

Kennzeichnung wie in `Hardware_Interfaces.md`: **(fest)** entschieden, **(Annahme)** Startwert, **(offen)** noch zu entscheiden.

---

## 1. Ziel

SLARC soll sich selbstständig bewegen und entscheiden und dabei wie ein Lebewesen wirken, nicht wie eine Sprachfernsteuerung. Bisher braucht er Aufträge wie "Laufe nach Norden, bis der Akku leer ist". Künftig handelt er aus Bedürfnissen heraus: Neugier, Wunsch nützlich zu sein, Energiebedarf, dazu ein Sicherheitsempfinden. Menschen können Bitten äußern, die er in diese Bedürfnisse einordnet.

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

- **Eingänge:** Akkuspannung unter Last (Treiber-INA219), daraus Ladezustand; geschätzter Energiebedarf für den Rückweg zum Ausgangspunkt aus Weglänge (SLAM) und mittlerem Verbrauch je Meter.
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

### 4.4 Sicherheit

Zwei getrennte Teile:

- **Harte Grenzen (Code, Veto):** Kippwinkel, Treppenkante ohne Kletterfreigabe, Akku unter 9,9 V, Mensch näher als ein Mindestabstand bei Bewegung, Servo-Übertemperatur, Fußkontakt-Widersprüche. Verletzt ein Ziel eine Grenze, wird es gar nicht erst ins Menü aufgenommen oder abgebrochen.
- **Unbehagen (Bedürfnis):** steigt bei Dunkelheit, unbekanntem Untergrund, Enge, schnell bewegten Objekten, kurz nach einem Sturz oder Rutschen. Es senkt die Bereitschaft für Neugier-Verhalten und erzeugt Zögern.
- **Ausdruck:** geduckt, breiter Stand, langsamer, bei Schreck kurzer Rückzug.

### 4.5 Konflikte

Liegen zwei Bedürfnisse nahe beieinander, entscheidet nicht der Größere hart. Typisch ist Neugier gegen Unbehagen bei einem unbekannten Objekt: annähern, zurückweichen, wieder annähern. Dieses sichtbare Zögern wirkt stark lebendig und wird als eigenes Verhalten modelliert.

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
| `greet(person)` | Nützlichkeit | Person erkannt | hinwenden, kurz aufrichten, LED |
| `follow(person)` | Nützlichkeit | Bitte oder Einladung | Abstand halten |
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

Kurz und in Stufen, keine Fließkommazahlen. Der Systemprompt bleibt gleich und wird gecacht; nur dieser Teil ist neu.

```
ZUSTAND
Energie: leicht (Rückweg 12 m)
Neugier: hoch
Nützlichkeit: mittel
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
{"ziel": 2, "begruendung": "Marco sucht seinen Schlüssel; die Tasche liegt auf dem Weg, ich schaue sie dabei an.", "stimmung": "eifrig"}
```

- `ziel`: nur Nummern aus dem Menü.
- `begruendung`: ein Satz, geht ins Tagebuch.
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
8. Weiteres Bedürfnis "Gesellschaft" (Nähe zu Menschen suchen)? Entscheidung offen.
9. Audio-Hardware (Stufe 2/3) im Hardware-Chat.
