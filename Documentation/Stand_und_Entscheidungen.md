# SLARC – Stand und Entscheidungen (Mechanik, Elektronik, Simulation)

Stand: 25.10.2026. Zusammenfassung aus dem CAD-, Hardware- und Sim-Chat (Oktober 2026). Quelle der Wahrheit für Code und CAD ist das Repo **Hoehlenbaer/SLARC** (`master`). Dieses Dokument hält Entscheidungen, Begründungen und Messwerte fest, die nicht direkt im Code stehen.

---

## 1. Wo liegt was im Repo

| Inhalt | Pfad |
|---|---|
| FreeCAD-Makros, STEP der Kaufteile, Stückliste, Gesamtmodell `SLARC.FCStd` | `Drawings/Macros/` |
| Bein-Makro (aktuell V9.1) | `Drawings/Macros/slarc_leg_freecad_v9.py` |
| Baseplates (V2.7) | `Drawings/Macros/slarc_baseplates_v2.py` |
| Kamerahalter (V1.5.x, Dateiname bleibt v1_4) | `Drawings/Macros/slarc_stereo_mount_v1_4.py` |
| Rückenpanzer (V1.1) | `Drawings/Macros/slarc_cover_v1.py` |
| Gesamtmodell-Makro | `Drawings/Macros/slarc_assembly_v1.py` (Schalter `LEG_MODE`, `MIRROR_LEFT`, `COVER`, `POSES`) |
| Stückliste | `Drawings/Macros/SLARC_Stueckliste.xlsx` (Marco pflegt Preise/Status – nur direkt in der Datei ändern, nicht neu erzeugen) |
| Verkabelung, Lochraster-Layouts | `Documentation/Wiring/` (README + SVG, Generator `gen_wiring_svg.py`) |
| Simulation (aktuell V10.17) | `utilities/Motion_development/slarc_sim/slarc_sim_V10.py` |
| CAD-URDF + Meshes + Doku | `utilities/Motion_development/slarc_sim/urdf/` |
| STL-Exporte und Cura-Projekte `AKP_*.3mf` | `Drawings/STL files/` |
| Cura-Generator + Vorlagen (Quelle: Stückliste, Blatt Druckteile) | `Drawings/Cura/` |

Arbeitsweise mit Claude: jede Änderung auf eigenem Branch + PR, Marco merged. Nach dem Merge Branch löschen. Zu Beginn einer Sitzung frischen `master` holen. Mehrere offene PRs, die dieselbe Binärdatei (Stückliste) ändern, werden in einem PR zusammengeführt (Konflikte in .xlsx lassen sich auf GitHub nicht lösen). Auf einen Branch nur weiter pushen, solange sein PR nachweislich noch offen ist – sonst neuer Branch/PR vom aktuellen master.

---

## 2. Bein (Makro V9.4)

**Standardparameter (von Marco festgelegt):** Coxa 60 mm, Femur 150 mm, Tibia-Sehne 175 mm (Knieachse → Fußspitze), Knick 38,6° nach unten, Fußsegment 140 mm → Segment 1 (`tib_a`) = 42,2 mm. Standardpose im Makro: q_femur −15°, q_tibia 100°.

**Aufbau / Entscheidungen**
- Doppelte Lagerung: obere Gabelwange auf dem Horn, untere auf der servoeigenen Rückscheibe.
- Servo komplett eingehaust, von oben eingesetzt, unten 2× Blechschraube 2×5 (nur axial belastet).
- Gabelsteg Femur/Tibia 6 mm, Rampen zum Träger.
- **Femur und Tibia sind Rohre** (20 × 28 mm, Wand 2 mm, innen hohl): biegesteif genug (~3 MPa bei 3 Nm), leicht, Hohlraum führt Fußschalterkabel und Kabelbinder. Cura: 5 Wandlinien, Brückeneinstellungen an (Decke 16 mm).
- **Kabelführung:** Kabelbinder-Schlitzpaare (4 × 2 mm, 10 mm Abstand), Binder unter dem 8-mm-Steg durch den Hohlraum. Femur 3 Stellen (Servokabel), Tibia 1 Stelle am Fußsegment. Schalterkabel innen, Austritt hinter dem Knie. Am Gelenk lose Schlaufe.
- TPU-Fuß 95A mit Mikroschalter, Druck mit Öffnung nach unten ohne Stützen.
- **V9.1 (Fase 6 mm):** erste Berührung bei ±117° (vorher ±109°).
- Linke Beine gespiegelt → **Drehrichtung der gespiegelten Femur-/Tibia-Servos in der Firmware umkehren.**
- Schrauben: M3×8 oben (Horn), M3×6 unten (Rückscheibe) – nicht länger.
- **ST3215-Dummy** (`Drawings/STL files/ST3215_Dummy.stl`) für die Coxa-Positionen, seitlich liegend drucken.

**Gelenkgrenzen (mechanisch)**
| Gelenk | Anschlag | Grenze in Sim/IK |
|---|---|---|
| Coxa | ±95° (Freischnitt Baseplate) | ±90° (URDF ±95°) |
| Femur | ±117° (V9.1) | ±112° |
| Tibia | ±117° (V9.1) | ±112° |

---
- **Servo-Tasche (V9.2, 05.11.2026):** Erster Druck (Coxa, PETG): Der Femur-Servo ging nur mit Druck in die Tasche und schwer heraus. Ursache: Die Hüllmaße im Makro waren gerundet (24,7 statt 24,78 mm). Mit fit 0,2 blieben so je Seite nur 0,16 mm Spiel. Jetzt Maße aus dem STEP (24,78 × 45,25) und eigenes Spiel `fit_srv` = 0,3 mm je Seite. Die Schaltertasche behält `fit` = 0,2. Die Gabelpassung zum Horn ist gut (leichtes Spiel). Messung alte Tasche: 24,86 mm statt 25,10 mm im Modell (oben und unten gleich). Der Drucker macht große Taschen in PETG also je Seite etwa 0,12 mm enger; die Lochkorrektur von Cura greift bei großen Öffnungen nicht. Die neue Tasche wird damit etwa 25,14 mm breit, also etwa 0,18 mm Spiel je Seite zum Servo (24,78 laut STEP). Gemessener Servo: 24,6–24,9 mm, am breitesten in der Mitte an der Trennfuge der Gehäuseschalen (fühlbarer Grat). Dort war die alte Tasche (24,86) schon zu eng. Die neue lässt an der Fuge etwa 0,12 mm je Seite.
- **Tropfenbohrungen (V9.3, 05.11.2026):** In der Coxa liegen die Schraubenlöcher der Femur-Servo-Laschen beim Druck waagerecht. Cura setzte Stützen in die Senkungen (Ø4,4, 3,3 tief), die man ausbohren musste. Jetzt als Tropfen mit 45°-Spitze nach oben, unter dem Stützwinkel von 50°. Das ist für das rechte und das gespiegelte Bein geprüft (Schnitt durch die STL). Senkrechte Bohrungen bleiben rund. Laschen: Die Senkung berührte die Laschenkante tangential (Wand 0, in Cura als Fehlerfläche sichtbar, Marco). Jetzt endet die Lasche 0,6 mm weiter vorn (tab_x 29,9) und ist unterhalb des Servos um 3 mm verlängert (tab_ext). Femur gegen Coxa geprüft: frei bis ±115°, wie bisher.
- **Spitzdach im Hohlprofil (V9.4, 06.11.2026):** Die Decke der Hohlräume von Femur und Tibia war eine 16-mm-Brücke. Cura legte die erste Brückenschicht längs, und die Linienrichtung ändert daran nichts, sobald die Brückeneinstellungen an sind. Marco: Eine Deckschicht, die nicht richtig trägt, schwächt das Biegemoment des Glieds. Deshalb jetzt ein 45°-Spitzdach im Hohlraum (8 mm hoch), das ohne Brücke und ohne Stütze druckt. Kosten: Femur +5,3 cm³, Tibia +6,5 cm³, für 6 Beine etwa +71 cm³, rund 50 g bei 40 % Füllung. Für rechtes und gespiegeltes Bein mit Schnitten geprüft.
- **Gabelmontage:** Die obere Wange (ohne Bund) kommt auf das Servohorn. Die untere Wange mit dem 1-mm-Distanzbund kommt auf die Rückseitenscheibe (passive Lagerung), Bund zum Servo.

## 3. Baseplates (V2.7)

- Obere Platte: Pi 5 + Hailo-8 (x 115), Waveshare General Driver (x 42,5), Stereo-Kamerahalter vorn (Front x 182). Untere Platte: Akku-Fach, BMS, 8-fach-Relais quer.
- Coxa-Servos zwischen den Platten, Freischnitte ±95°. Platten zweiteilig (Teilung x = −40); hinterer Teil der oberen Platte kopfüber gedruckt → dort nur Bohrungen.
- **DC-DC 12 → 5 V / 5 A (Fulree)** oben hinten bei (−115, −35).
- **Modulplätze** (2× M3, Abstand 42 mm): MCP bei (−115, +35) → Hub-Platine B auf gedrucktem Träger (Eckbohrungen der 5×7 messen); Reserve bei (−115, 0).
- Säulen: an 6 Säulen M3×50 in Gewindeeinsätze der Panzersäulen; bei x = −40 M3×45 + Mutter.
- **Akku (ZEEE 3S 9000 mAh, 100C, 99,9 Wh):** Kabelabgänge seitlich an der Stirnseite (~38 mm auseinander), Stirnseite nach hinten. Tasche 2 mm, Schienen, Anschlag vorn, obere Platte 4,1 mm darüber, 2 Klettgurte, Ausbau nach hinten über 4-mm-Rampe.
- **Akkustecker-Halter (V2.6, verlegt V2.13):** linke Seite bei x −140, Stecköffnungen nach außen, 8 mm hinter der Plattenkante (vorher hinten links). Die Akku-Kabel kommen von außen in die Öffnungen. Deans reicht, der Balancer (~45 mm) braucht eine Verlängerung. Deans (Stifte Robot-Seite) + Balancer-Adapter zum BMS. Daly: erst B−, dann Balancer.
- **Akku-Riegel (V2.7):** ein gedruckter Bajonett-Stift Ø8 mittig (x −171, y 0), von unten bis in die obere Platte, keine Aufbauten auf der unteren Platte. Hochdrücken, 90° drehen (Rille quer = zu). Moosgummi unter dem Kopf. Kein Zukaufteil.
- **Servo-Wiege (V2.13, 02.11.2026):** Marco beim Prüfstand-Deckel: Bisher hielten nur die 0,9-mm-Tasche oben und die vier 2x5-Blechschrauben im Servogehäuse das Stall-Moment um die Coxa-Achse (2,94 Nm). Jetzt auf der unteren Platte je eine Wiege: Seitenwangen 5 mm und hinterer Anschlag 4 mm, 0,2 mm Spiel, bis z −4. Die volle Gehäusebreite ±12,4 liegt nur zwischen z −27 und −2 an (aus ST3215.step). Bei Stall drückt das Gehäuse auf eine Wange, etwa 110 N mit Hebel ~27 mm. Biegespannung am Wangenfuß ~22 MPa bei voller Stall-Last. Für PETG quer zu den Schichten ist das knapp, aber im Normalbetrieb deutlich weniger. Die Wangen enden vorn am Freischnitt der Gabel. Bein-Platinen FR/FL dafür nach y ∓21,5. Untere Platte vorn +42 cm³. Für RR/RL wurden Taster und Akkustecker-Halter an die Seiten verlegt (x −140), jetzt haben alle sechs Coxas eine Wiege. Ausgleich: Fenster in der oberen Platte unter Pi und Treiber (−13,5 cm³). Netto +49 cm³, etwa +53 g. Keine Löcher unter dem Akku und unter dem Relaismodul, weil die Bauchseite Bodenkontakt hat (LiPo bzw. offene 12-V-Lötstellen).

---

## 4. Kamerahalter (V1.5.2)

- 2× IMX296 mit M12 2,8 mm, Baseline 65 mm (Trigger-Platine 20 × 22 mm dazwischen). Mindestdistanz ≈ 12 cm.
- **ICM20948** oben mittig, 2 Kernlöcher M2,5 im Abstand 13,6 mm; Bunde hinter der Front, mit Steg bis zur Frontfläche → stehen beim Druck auf dem Bett.
- **V1.5:** obere Rahmenecken R6, Laschenenden halbrund, Kehlen R2,5 (min. Wand 1,76 mm).
- **Objektiv ZH3019-14** als Kontrollkörper (Spitze bei x 199,7). Sturzprüfung: mit Beinen in Stehpose treffen die Objektive bei keiner ebenen Anprallrichtung zuerst; Restrisiko nur bei schmalen Hindernissen zwischen den Vorderbeinen. Kein Schutzbügel.
- Druck PETG: Front aufs Bett, 0,2 mm, 235/80 °C, 4 Wände, keine Stützen. Gegen hochziehende Ecken: Brim 6–8 mm, Lüfter erst ab Schicht 4 und max. 30–40 %, Bett 85 °C.

---

## 5. Rückenpanzer (V1.2)

- Käferform, Satteldach 40° mit Firstkamm, Wabengitter; ~170 g, Wand 2,4 mm, **PETG**.
- Selbstaufrichten muss über eine Beinbewegung kommen (noch zu entwickeln).
- **V1.2 (02.11.2026):** Marco hat Stellen gefunden, an denen der Drucker ins Leere drucken müsste. Per Schichtanalyse der STL bestätigt: 0,2-mm-Schichten, Überhang bis 50°, Stege unter 0,84 mm zählen nicht. Ursachen und Lösung:
  - Seitenrauten, die die Kabeldurchlässe bei x −95 und 30 anschnitten, ließen dünne Stege stehen. Jetzt mindestens 4 mm Abstand (`notch_gap`).
  - Dachwaben in der hinteren Kuppel (x < ca. −135): Dort fällt das Dach auch in X, die Wabenspitze zeigt nicht mehr bergauf, und die Decke der Wabe hängt frei. Dort jetzt keine Waben mehr (`hex_slope`).
  - Ergebnis: Ohne Stützen druckbar, übrig sind nur die Decken der M3-Querbohrungen im Teilungsspant (Ø3,4, kurze Brücke). Masse +6,6 cm³, etwa +7 g.

---

## 6. Elektronik – Entscheidungen

- **Fußkontakte über MCP23017-E-Modul** (Breakout, ~7,30 €, billiger als der DIP-Chip) auf dem Hub, I²C des ESP32 (IO32/33), Adresse 0x20, 10-kΩ-Pull-ups nach 3,3 V, ITA → **IO34**. Zuordnung: PA0 RR, PA1 RL, PA2 MR, PA3 ML, PA4 FR, PA5 FL. Bank B frei.
- **LEDs:** WS2812 an **IO4**, 5 V vom Treiber (bis ~10 LEDs) oder DC-DC.
- **GPIOs am Treiber:** IO16 (K1, Open-Drain), IO27 (K2…K7), IO34 (ITA), IO4 (LEDs). Frei: IO35 (nur Eingang), IO5 (Strapping).
- **Puffer SN74LVC1G125 ist bereits auf dem Treiberboard** → H5/H6 am selben Bustreiber.
- **IMU:** Balance auf dem ESP32 mit QMI8658C. ICM20948 für SLAM/VIO auf dem Pi (I²C1, INT → GPIO24), Zeitbezug über Trigger-Rückführung (GPIO23).
- **Magnetometer:** nur im Stillstand als schwache Stütze.
- Firmware ESP32 noch nicht im Repo. `config.h`: Gelenkgrenzen, `JOINT_DIR = −1` für gespiegelte Servos, Fußkontakt-Zuordnung, Relais aktiv-low, IO16 Open-Drain.

### 6a. Verkabelung (Plan in `Documentation/Wiring`, PR #20)

- **Energiepfad:** Akku + → F1 30 A → Power-Board (Platine C, 2 Sammelschienen 1,5 mm² Cu: 12 V, GND). Akku − → BMS B−, P− → GND. AWG14 (oder 3× AWG20) für den Hauptpfad.
- **Ein Relais je Bein (Marcos Einwand):** Relaismodul 8× SRD-05VDC-SL-C (10 A). K1 = 12 V → DC-DC (Pi), **K2…K7 = je ein Bein** (FR MR RR FL ML RL), K8 frei. Ein Bein max. 8,1 A < 10 A; eine Seite (~15 A Spitze) wäre für ein Relais zu viel. Bein-Relais nur bei abgeschaltetem Drehmoment schalten.
- **Relais-Ansteuerung:** Jumper JD-VCC–VCC gezogen: VCC (Optokoppler) 3,3 V, JD-VCC (Spulen) 5 V vom Treiber → Eingänge direkt an 3,3-V-Logik, keine Dioden. IO16 (Open-Drain) → IN1; Pi hält K1 über GPIO26 → 4,7 kΩ → BC547 (direkt ginge nicht: ein ausgeschalteter Pi zöge IN1 herunter). IO27 → IN2…IN7 gemeinsam (~12 mA). Später möglich: Beine einzeln über MCP PB0–5. Relais-Adapter = Platine D.
- **Servo-Strom sternförmig:** je Bein 12 V von Kx NO und GND vom Power-Board (je 1× AWG20) zur Bein-Platine (Platine A, ½ 3×7 cm, 470 µF), dort Servos einzeln.
- **Daten:** H5 → nur DATA + GND → Hub (Platine B) → Datenstern zu 6 Beinen, Signalkabel XH3 GND · DATA · SW.
- **AWG20 passt nicht in XH-/Dupont-Crimps** → gesteckte Signalleitungen AWG24, AWG20 nur gelötet/Strom.
- **Pi 5 V:** je Pol 2× AWG20; bei GPIO-Speisung `PSU_MAX_CURRENT=5000`.
- **Ablauf:** Akku stecken → ESP32 läuft → K1 (Pi bootet) → Pi hält K1 → K2…K7 (Beine) → Drehmoment ein. Akku nach Betrieb abziehen.
- **Inbetriebnahme:** Servo-IDs vorher einzeln vergeben (alle neu = ID 1). Pinfolge Servokabel, H5-DATA-Pin, Relais-Eingangsleiste vor dem Löten messen.

---

## 7. Masse und Lasten

- **Gesamtmasse laut CAD ≈ 3,79 kg**. Rumpf 2,26 kg; je Bein: Coxa-Link 77 g, Femur 102 g, Tibia 58 g, Fuß 17 g.
- **`G_RADIUS` = 0,18 m:** Femur-Last im Tripod −26 %.
- Stehpose bei 0,18 (Servowinkel): FR 0,3/−24,9/90,7 · FL −0,5/−24,4/90,5 · MR 0,8/−21,6/89,3 · ML −0,9/−20,6/89,0 · RR 0,6/−17,8/87,8 · RL −0,3/−17,3/87,5. FreeCAD: q_femur −21, q_tibia 89.

**Tripod auf der Ebene, Femur in der Standphase (`vx` 0,4):**
| G_RADIUS | Femur Median | Femur Mittel | an Stall-Grenze | längste Phase |
|---|---|---|---|---|
| 0,229 | 1,00 Nm | 1,03 Nm | 8,5 % | 25 ms |
| 0,20 | 0,81 Nm | 0,84 Nm | 6,4 % | 17 ms |
| **0,18** | **0,72 Nm** | **0,76 Nm** | **6,0 %** | **17 ms** |
| 0,16 | 0,73 Nm | 0,74 Nm | 5,0 % | 17 ms |

---

## 8. Simulation V10.17

- Geometrie aus dem CAD (`LEG_*`): Coxa 0,060; Femurachse 0,017025 m unter Coxa; Femur 0,150; Ersatz-Tibia 0,1592 m / 29,07°; Fußkugel r 0,016.
- CAD-URDF mit Meshes, Massen, Trägheiten; Fallback Primitiv-URDF.
- Gelenkgrenzen in der IK per Bisektion, Zähler `lim_hits`.
- Klettern bleibt an der Stufenkante hängen – Kletterparameter neu optimieren.
- Headless-Sim in Claude-Sitzungen möglich (PyBullet aus conda-forge).

---

## 9. Perzeption (unverändert)

- FusedHexapodModel V5.0, 3 HEFs, **1+3+1 Kontexte, 16,5 FPS**.
- INT8-Check: EPE FP32 1,134 px / INT8 1,121 px.
- Schwäche Himmel → Nachtraining mit echten SLARC-Bildern.

### 9a. High-Level-Brain (07.11.2026, Konzept in `Documentation/Brain_Konzept.md`)

- SLARC folgt Bedürfnissen (Energie, Neugier, Nützlichkeit, Gesellschaft, Sicherheit) statt klarer Aufträge. Grund: Aufträge wie "laufe nach Norden" sind im Prinzip eine Sprachfernsteuerung.
- Bedürfnisse und Sicherheitsgrenzen laufen als Code auf dem Pi. Das LLM wählt nur bei Ereignissen ein Ziel aus einem vom Code erzeugten Menü. Grund: Ein 4B-Modell wägt Zahlen nicht zuverlässig ab.
- Akku knapp → Rückkehr zum Ausgangspunkt. Die Schwelle berücksichtigt den Rückweg.
- Denk-Zustand: Während das LLM rechnet, pausieren Perzeption und Motion auf dem Pi. Der ESP32 hält Reflexe aktiv und zeigt eine Denk-Pose.
- Pi 5 hat 8 GB RAM. Modell vorerst Qwen3-4B-Instruct-2507 Q4_K_M über llama.cpp. Qwen3.5-4B/2B und Gemma 4 E2B/E4B werden mit einer eigenen Testsuite auf dem Pi verglichen.
- Erste Umsetzung in `src_dev/ai/brain/` (V0.1): Bedürfnismodell, Sicherheits-Veto, Menü, Arbiter, Prompt mit GBNF, Testsuite.
- Erster Modelltest (07.11.2026, Qwen3-4B Q4, PC/GPU): Als Entscheider schlechter als der Code (36/45 gegen 42/45), Regel "Energie hoch" 0/3 eingehalten. Daher (fest): Handlungswahl beim Code, LLM nur für knappe Fälle und semantische Aufgaben (Chat deuten, Objekte einschätzen, Suchorte, Tagebuch). Energie ab "hoch" ist jetzt eine Regel. Details: `Brain_Konzept.md`, Abschnitt 15.
- Interaktion zunächst ohne Audio: Web-Chat, Handy-Meldungen, Körpersprache, LEDs, Antippen als Lob. Audio später über USB, weil I²S mit dem Kameratrigger an GPIO18 kollidiert.

---

## 10. Offene Punkte

1. Kletterparameter mit V10.17 neu optimieren, dann grafisch prüfen.
2. Aufricht-Bewegung aus der Rückenlage entwickeln.
3. Firmware: Gelenkgrenzen, Drehrichtungen, Fußkontakte, Relais-Sequenz, WS2812.
4. Träger für den Hub am Modulplatz MCP – Eckbohrungen der 5×7-Platine messen.
5. Lage von Bein-Platinen, Power-Board und Relais-Adapter im CAD prüfen, Halter vorsehen.
6. Echte Massen wiegen → URDF/Stückliste.
7. Testdrucke: Kamerahalter V1.5.x, dann Bein und Panzer.
8. Steckermaße und echte Akkulänge messen → `conn`/`lat`.
9. PR #20 (Verkabelung) mergen.
10. Sprache der Doku (notiert 01.11.2026): Im Moment sind Doku, Kommentare und Stückliste gemischt Deutsch/Englisch. In der finalen Version soll die ganze Doku auf Englisch sein (inkl. Stückliste und Code-Kommentare). Bis dahin gilt die Regel aus `CLAUDE.md` (Deutsch, `README.md` Englisch).
11. Akku-Kabel zum Steckerhalter (linke Seite, x −140), gemessen 02.11.2026: Deans reicht, Balancer nur ~45 mm → Verlängerung JST-XH 4-pol. (3S) 1:1, bleibt am Akku. Mit Schrumpfschlauch oder Klebeband sichern.
