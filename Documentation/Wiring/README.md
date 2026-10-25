# SLARC – Verkabelung

Stand 25.10.2026. Plan für Energie, Servo-Bus, Fußkontakte, Relais und Sensorik, dazu vier Lochraster-Platinen zum Selberbauen. Die Layouts sind für die AZ-Delivery-Lochrasterplatinen (2,54 mm, durchkontaktiert) gezeichnet. Die SVGs erzeugt `gen_wiring_svg.py` (`python gen_wiring_svg.py . file`).

![Blockschaltbild](block.svg)

## Grundentscheidungen

- **Akku → BMS → Verteiler.** Akku-Plus über die 30-A-Flachsicherung F1 auf das Power-Board (Platine C). Akku-Minus auf B− des Daly-BMS, dessen P− auf die GND-Schiene. Der Balancer hängt über den Adapter im Steckerhalter am BMS. Geladen wird extern, der Akku kommt dafür raus.
- **Ein Relais je Bein.** Das Relaismodul (8× SRD-05VDC-SL-C, 10 A je Kontakt) schaltet:
  - K1: 12 V auf den DC-DC-Wandler, also den Pi.
  - K2…K7: je ein Bein (FR, MR, RR, FL, ML, RL).
  - K8: frei.

  Ein Bein zieht im Mittel ~1,7 A und höchstens 8,1 A (3 × 2,7 A Stall). Das liegt unter den 10 A eines Kontakts. Eine ganze Seite (~15 A Spitze) wäre für ein Relais zu viel.
- **Steuerung durch den ESP32.** Der ESP32 läuft dauernd, sobald der Akku steckt.
  - IO16 schaltet K1, IO27 schaltet K2…K7 gemeinsam.
  - So kann er den Servos im Notfall die Spannung nehmen, auch wenn der Bus nicht mehr antwortet.
  - Der Pi hält K1 zusätzlich selbst über einen Transistor, damit er sauber herunterfahren kann.
- **Relaismodul mit getrennter Versorgung.** Der Jumper JD-VCC–VCC wird gezogen.
  - Optokoppler-Seite (VCC): 3,3 V.
  - Spulen (JD-VCC): 5 V vom Treiber.

  Damit sperrt ein 3,3-V-High den Eingang sicher, und es braucht keine Dioden.
- **Servo-Strom sternförmig.** Jede Bein-Platine (A) bekommt 12 V von ihrem Relais und GND vom Power-Board, je eine Ader AWG20. Auf der Bein-Platine geht jeder Servo einzeln ab, ohne Daisy-Chain durch die Servos. So fließt durch die dünnen Servokabel nur der Strom eines Servos.
- **Daten getrennt vom Strom.** Am Treiber wird von H5 nur DATA und GND abgegriffen.
  - Auf dem Hub (B) verteilt sich DATA sternförmig auf die sechs Beine.
  - H5 und H6 hängen auf dem Treiber am selben Bustreiber (SN74LVC1G125), deshalb genügt H5.
  - GND läuft in jedem Signalkabel mit. So hat DATA eine saubere Masse, auch wenn auf den Stromleitungen ein paar Zehntel Volt abfallen.
- **Fußkontakte am MCP23017-Modul auf dem Hub.** Jeder Fußschalter läuft mit zwei Adern das Bein hoch zur Bein-Platine. Von dort geht er im 3-adrigen Signalkabel (GND · DATA · SW) zum Hub. Dort sitzt ein 10-kΩ-Pull-up nach 3,3 V.
- **Pi-Versorgung kurz und doppelt.** Vom DC-DC-Ausgang laufen je Pol 2× AWG20 zum Pi, über die USB-C-Buchse oder die 5-V-Pins der GPIO-Leiste.
- **Strommessung am Treiber.** Das INA219 auf dem Treiber misst nur noch den Strom des Treibers. Die Akkuspannung sieht es weiterhin.

## Strombudget und Querschnitte

| Verbraucher | Mittel | Spitze | Leitung |
|---|---|---|---|
| 18 Servos gesamt (Tripod) | ~10 A | 20–30 A | – |
| je Bein (3 Servos, über ein Relais) | ~1,7 A | 8,1 A (3× 2,7 A Stall) | 12 V: Kx NO → Bein, GND: Power-Board → Bein, je 1× AWG20 |
| Pi 5 + Hailo-8 (5 V) | 2–3 A | ~5 A | je Pol 2× AWG20, ≤ 25 cm (≈ 40 mV Abfall) |
| DC-DC-Eingang (12 V, über K1) | ~1,3 A | ~2,5 A | AWG20 |
| Treiber (12 V) | 0,15 A | 0,5 A | mitgeliefertes XH-Kabel oder AWG22 |
| Relaisspulen (5 V vom Treiber) | bis 7× 72 mA ≈ 0,5 A | – | AWG24 |
| Akku → F1 → Power-Board, Akku− → BMS → GND | ~12 A | 30 A | **AWG14** (oder 3× AWG20 parallel), ≤ 30 cm |

Laufzeit grob: 9 Ah bei ~12 A Mittel ergibt 40–45 min Gehen.

Kurzschlussschutz: Ein Kurzschluss löst die Kurzschlussabschaltung des BMS im Mikrosekundenbereich aus, F1 sichert dahinter. Die kurzen AWG20-Abgänge brauchen deshalb keine eigene Sicherung.

Die Bein-Relais nur schalten, wenn das Drehmoment der Servos aus ist. Beim Einschalten lädt der 470-µF-Kondensator kurz über den Kontakt, unter Last schalten verschleißt die Kontakte.

**AWG20 und Steckverbinder.** Für Datenleitungen ist AWG20 elektrisch mehr als genug. Es passt aber nicht in XH- oder Dupont-Crimpkontakte, die nehmen höchstens AWG22. Deshalb gilt:

- Gelötete Verbindungen und alle Stromleitungen: AWG20.
- Gesteckte Signalleitungen (Hub ↔ Beine, I²C, INT, Relais): AWG24.

## Leitungsliste

| Nr | Von | Nach | Adern | Querschnitt | Verbindung |
|---|---|---|---|---|---|
| L1 | Deans + (Steckerhalter) | F1 → Power-Board 12 V | 1 | AWG14 | gelötet / Flachsicherungshalter |
| L2 | Deans − | BMS B− | 1 | AWG14 (BMS-Litze) | gelötet |
| L3 | BMS P− | Power-Board GND | 1 | AWG14 | gelötet, 3 Löcher |
| L4 | Balancer-Adapter (Steckerhalter) | BMS Balance | 4 | BMS-Kabel | Stecker; erst B−, dann Balancer |
| L5 | Power-Board 12 V | K1…K7 COM | je 1 | AWG20 | Schraubklemme Relais |
| L6 | K2…K7 NO | Bein-Platine FR, MR, RR, FL, ML, RL (12 V) | je 1 | AWG20 | Schraubklemme / gelötet |
| L7 | Power-Board GND | Bein-Platine je Bein (GND) | je 1 | AWG20 | beidseitig gelötet |
| L8 | K1 NO / Power-Board GND | DC-DC IN+ / IN− | 2 | AWG20 | gelötet |
| L9 | DC-DC OUT+ / OUT− | Pi 5 (USB-C-Pigtail oder Pin 2+4 / 6+9) | 2 + 2 | AWG20 | gelötet / Dupont |
| L10 | Power-Board 12 V + GND | Treiber XH-Eingang | 2 | AWG20 / XH-Kabel | XH2 |
| L11 | Treiber H5 (DATA, GND) | Hub J2 | 2 | Servokabel 5264 | 5264 / XH2 |
| L12 | Treiber I²C (GND, 3V3, SCL, SDA) | Kopfleiste MCP23017-Modul | 4 | AWG24 | Dupont |
| L13 | MCP23017-Modul ITA | Treiber IO34 | 1 + GND | AWG24 | Dupont / Encoder-Stecker A |
| L14 | Hub J-FR … J-RL | Bein-Platine J4 | 3 je Bein | AWG24 | XH3 / XH3 |
| L15 | Fußschalter | Bein-Platine J5 | 2 | AWG24 | im Bein geführt, XH2 |
| L16 | Coxa-/Femur-/Tibia-Servo | Bein-Platine | 3 je Servo | Servokabel | 5264 auf Stiftleiste |
| L17 | Treiber IO16, IO27, GND, 3V3 | Relais-Adapter J1 | 4 | AWG24 | XH5 / Dupont |
| L18 | Pi GPIO26 (Pin 37) | Relais-Adapter J1 | 1 | AWG24 | Dupont |
| L19 | Treiber 40-pol. 5 V (Pin 2) / GND (Pin 6) | Relaismodul JD-VCC / GND (3-pol. Leiste) | 2 | AWG24 | Dupont |
| L20 | Treiber IO4 + 5 V + GND | WS2812-Streifen (optional) | 3 | AWG24 | 3-pol. Servostecker |
| L21 | Pi I²C1 (Pin 1, 3, 5, 9) + GPIO24 (Pin 18) | ICM-20948 | 5 | AWG24 | Dupont |
| L22 | Pi GPIO18 (Pin 12) / GPIO23 (Pin 16) | Trigger-Platine (Ausgang / Rückführung) | 2 + GND | Dupont | Dupont |
| L23 | Pi CAM0 / CAM1 | IMX296 links / rechts | FPC | – | CSI-Kabel 200 mm |
| L24 | Pi ↔ ESP32 | UART | 3 oder USB | AWG24 / USB-C | USB-C (CP2102) oder GPIO14/15 an die 40-pol. Leiste |
| L25 | Ein/Aus-Taster (hinten rechts) | Hub J6 | 2 | AWG24 | XH2 / angelötet |
| L26 | Hub J7 (IO35, GND) | Treiber IO35 (Encoder-Stecker A) | 2 | AWG24 | XH2 / PH2.0 |

## Pinbelegung

**ESP32 (Waveshare General Driver)**

| Pin | Funktion | Richtung |
|---|---|---|
| IO18 / IO19 | Servo-Bus (UART1, intern über SN74LVC1G125/126) | – |
| IO32 / IO33 | I²C: Board-IMU QMI8658C/AK09918C + MCP23017 (0x20) | – |
| IO34 | MCP23017 INTA | Eingang |
| IO16 | K1 Pi-Versorgung, **low = an**, als Open-Drain betreiben | Ausgang |
| IO27 | K2…K7 Bein-Versorgung, **low = an** (~12 mA Senke) | Ausgang |
| IO4 | WS2812-Daten | Ausgang |
| IO35 | Ein/Aus-Taster (low = gedrückt, 10 kΩ Pull-up auf dem Hub), Wecken aus dem Deep Sleep | Eingang |
| IO5 | frei (Strapping-Pin, beim Booten nicht low ziehen) | – |

IO16 als Open-Drain (`OUTPUT_OPEN_DRAIN`): IN1 hängt auch am Transistor des Pi. Ein Push-Pull-High des ESP32 gegen den durchgeschalteten Transistor wäre ein Kurzschluss.

**Raspberry Pi 5**

| GPIO (Pin) | Funktion |
|---|---|
| GPIO2 / GPIO3 (3 / 5) | I²C1 → ICM-20948 |
| GPIO24 (18) | ICM-20948 INT |
| GPIO18 (12) | PWM Kameratrigger (wie im Trigger-Setup; mit `config.txt` abgleichen) |
| GPIO23 (16) | Trigger-Rückführung (Zeitstempel) |
| GPIO26 (37) | K1 halten, **high = halten** |
| GPIO14 / GPIO15 (8 / 10) | UART zum ESP32, falls nicht über USB |
| 5 V (2, 4), GND (6, 9) | Versorgung, wenn nicht über USB-C |

Bei Versorgung über die GPIO-5-V-Pins oder ein Netzteil ohne USB-PD: `PSU_MAX_CURRENT=5000` in der EEPROM-Konfiguration setzen (`sudo rpi-eeprom-config -e`). Sonst begrenzt der Pi die USB-Ports und warnt.

**MCP23017-Modul (Hub)**

| Pin | Funktion |
|---|---|
| PA0 | Fußschalter RR |
| PA1 | Fußschalter RL |
| PA2 | Fußschalter MR |
| PA3 | Fußschalter ML |
| PA4 | Fußschalter FR |
| PA5 | Fußschalter FL |
| PB0…PB7 | frei für Status-LEDs, je LED 330 Ω Vorwiderstand, insgesamt höchstens ~125 mA |

Die Reihenfolge folgt der Leiterführung auf der Platine, die Firmware bildet sie auf die Beine ab.

## Platinen

Allgemein:

- **Unterseite:** Schienen aus Draht, satt verzinnt. Sie sind breit und halbtransparent gezeichnet.
- **Oberseite:** Drahtbrücken, als farbige Linien gezeichnet. Jede Drahtbrücke endet im Nachbarloch des Pins und wird dort mit einer Lötbrücke angeschlossen.
- **Farben:** rot 12 V, schwarz GND, gelb DATA, blau Fußschalter, grün I²C, lila 3,3 V, orange 5 V, magenta Relaissteuerung, türkis INT.
- **Vor dem Löten prüfen:**
  - die Pinfolge am Servokabel (GND / 12 V / DATA)
  - an H5, welcher Pin DATA ist: Er liegt im Ruhezustand bei 3,3–5 V, der Versorgungspin bei Akkuspannung.
  - die Reihenfolge der Eingangsleiste am Relaismodul

### A – Bein-Verteiler (6×)

![Platine A](board_a_bein.svg)

Eine halbe 3×7-cm-Platine (10 × 11 Löcher), aus jeder 3×7 entstehen zwei Bein-Platinen.

- **Bestückung:** drei 3-polige Stiftleisten für Coxa, Femur und Tibia, C1 470 µF / 25 V, XH3 J4 zum Hub, XH2 J5 für den Fußschalter.
- **Einspeisung:** 12 V (vom Bein-Relais) und GND (vom Power-Board) von unten direkt an die Schienen löten.
- **Montage (Baseplates V2.8):** zwischen den Platten auf der unteren Platte, je zwei M2-Bunde am Lochende (2× M2x5) und ein Stützstift am freien Ende. Lage: FR/FL bei x 183, y ∓25 (vor dem Relaismodul), MR/ML bei x 0, y ∓60 (neben den Mittel-Servos), RR/RL bei x −100, y ∓55 (neben dem Akku, außerhalb des Ausziehwegs). Die hinteren Platinen sitzen ~100 mm von der Coxa-Achse, dort reichen die Servokabel eventuell nicht – vorher messen.

### B – Hub (1×)

![Platine B](board_b_hub.svg)

5×7 cm mit dem MCP23017-Modul (Breakout).

- **Modul:** Die seitliche 20-polige Stiftleiste wird in Spalte 8 eingelötet, das Modul liegt über der linken Hälfte der Platine. Alternativ steckt es in einer Buchsenleiste.
- **Kopfleiste des Moduls:** Dort kommen I²C (VCC 3,3 V, GND, SCL, SDA) vom Treiber und ITA zum IO34 direkt per Dupont an.
- **Was das Modul schon mitbringt:** RST-Pull-up (10 kΩ) und I²C-Pull-ups (4,7 kΩ). Mit den Pull-ups auf dem Treiber parallel ist das unkritisch.
- **Adresse:** Die Lötbrücken A0–A2 müssen auf GND stehen, das ergibt 0x20. Bitte nachsehen.
- **Pull-ups für die Füße:** sechs 10-kΩ-Widerstände, stehend, von PA0–5 nach 3,3 V. Die 3,3 V kommen vom VCC-Pin des Moduls.
- **Datenstern:** Spalte 14 auf der Unterseite verbindet J2 (von H5) mit den DATA-Pins aller sechs Beinstecker.
- **Ein/Aus-Taster:** J6 (Taster), R7 10 kΩ nach 3,3 V, J7 führt IO35 und GND zum Treiber.
- **Montage (Baseplates V2.8):** auf dem gedruckten Hub-Träger (2× M3 auf den Modulplatz MCP, 4× M2x5 in die Eckbohrungen 66 × 46). Die Platine liegt bei x −150…−80, y −5…45 und überdeckt den Reserveplatz MUX. Die Modulseite zeigt nach außen, wo der Panzer niedrig ist (dort nur ~10 mm Bauhöhe): I²C- und INT-Leitungen direkt in die Kopfleisten-Löcher des Moduls löten, keine Stiftleiste. Die XH-Stecker der Beine liegen innen.

### C – Power-Verteiler (1×)

![Platine C](board_c_power.svg)

Die halbe Länge einer 5×7-Platine reicht. Zwei Sammelschienen auf der Unterseite aus 1,5 mm² Kupfer massiv, zum Beispiel ein Rest NYM-Leitung, auf ganzer Länge verlötet:

- 12 V Haupt (dauernd): F1 rein, je eine Ader zu K1…K7 COM und zum Treiber.
- GND: P− rein, je eine Ader zu den sechs Beinen, zum Treiber und zum DC-DC.

Jede Ader kommt in ein eigenes Loch. **Montage (Baseplates V2.8):** auf der gedruckten Power-Brücke über dem BMS (x 30…80). Die Brücke liegt auf zwei Hülsen, die über die Säulen bei (60, ±45) geschoben werden; Platine mit 2× M2x5 am Lochende, Auflage am anderen Ende. Unter dem Deck bleiben 4,5 mm für den BMS-Gurt.

### D – Relais-Adapter (1×)

![Platine D](board_d_relais.svg)

Ein Streifen aus der 2×8-cm-Platine. Die Eingangsstifte des Relaismoduls sitzen an der Vorderkante (x 142,6) und zeigen nach oben, darüber sind nur ~16 mm bis zur oberen Platte. Deshalb steckt der Adapter mit einer **gewinkelten** 10-poligen Buchsenleiste auf den Stiften und liegt flach vor dem Modul (x 147…165, zwischen Relais und den vorderen Bein-Platinen).

- **Jumper ziehen:** Am Modul wird der Jumper JD-VCC–VCC entfernt.
  - VCC (Optokoppler) bekommt 3,3 V über den Adapter.
  - JD-VCC (Spulen) bekommt 5 V vom Treiber an der 3-poligen Leiste.

  Die Eingänge sind aktiv-low und hängen direkt an der 3,3-V-Logik.
- **IN1 (K1):** ESP32 IO16 als Open-Drain und parallel der BC547 des Pi (GPIO26 → 4,7 kΩ → Basis).
- **Warum der Pi einen Transistor braucht:** Direkt am Pin ginge es nicht. Ein ausgeschalteter Pi zöge IN1 über die Schutzdiode seines Pins nach unten, und K1 würde einschalten.
- **IN2…IN7 (K2…K7):** in Spalte 1 gebrückt und gemeinsam an IO27. IN8 bleibt frei.
- **Später möglich:** Die Bein-Relais einzeln über PB0–5 des MCP23017 schalten, etwa um die Beine nacheinander einzuschalten oder ein Bein stromlos zu machen. Dafür die Brücke in Spalte 1 auftrennen.

## Ablauf Ein / Aus

Der Akku bleibt dauerhaft eingesteckt (Deans und Balancer). Ein/Aus macht ein Taster hinten rechts (Baseplates V2.10, versenkt hinter der Plattenkante) zusammen mit dem Deep Sleep des ESP32. Der Taster liegt über J6 auf dem Hub, R7 10 kΩ zieht IO35 auf 3,3 V, Druck = low.

1. **Aus-Zustand:** ESP32 im Deep Sleep, Wecken über IO35 (ext0, low). Alle Relais offen, Pi und Beine stromlos. Ruhestrom des Treibers vor dem Festlegen messen (erwartet 5–15 mA).
2. **Taster drücken:** ESP32 wacht auf und zieht IO16 low. K1 zieht an, der DC-DC startet, der Pi bootet (`POWER_OFF_ON_HALT=0` ist gesetzt).
3. Der Pi setzt GPIO26 high: K1 hält jetzt auch ohne den ESP32.
4. ESP32 zieht IO27 low: Die Beine bekommen Strom, die Servos sind dabei noch ohne Drehmoment. Danach schaltet der ESP32 das Drehmoment ein.
5. **Ausschalten, Taster kurz oder Befehl vom Webinterface des Pi:** Beine ablegen, Drehmoment aus, IO27 high. Shutdown an den Pi, auf Bestätigung warten (Zeitlimit ~30 s). IO16 loslassen, K1 fällt mit GPIO26. Dann Deep Sleep.
6. **Taster 5 s halten:** Notaus. Der ESP32 lässt sofort alle Relais los und geht in den Deep Sleep.

Lagerung über Wochen: hinten Deans und Balancer abziehen, beide sind bei geschlossenem Panzer erreichbar. Der Schalter auf dem Treiber liegt unter dem Panzer und bleibt auf Ein.

## Inbetriebnahme

1. Jede Platine vor dem ersten Einschalten durchmessen: kein Durchgang zwischen 12 V und GND und zwischen 3,3 V und GND.
2. **Servo-IDs vergeben, bevor ein Servo an den Bus kommt.** Neue ST3215 haben alle ID 1. Jeden Servo einzeln am Treiber anschließen und umnummerieren, zum Beispiel FR 11/12/13 … RL 61/62/63.
3. Nur Treiber, Relaismodul und Relais-Adapter: IO16 und IO27 toggeln, die Relais müssen hörbar klicken. Mit IO27 high müssen alle Bein-Relais sicher abfallen.
4. DC-DC an K1, am Ausgang 5,0–5,25 V messen, erst dann den Pi anschließen.
5. Hub: Im I²C-Scan des ESP32 erscheint 0x20. Jeden Fußschalter drücken und das passende PA-Bit prüfen.
6. Ein Bein komplett, dann alle.

## Offen

- Länge der Servokabel zu den hinteren Bein-Platinen prüfen.
- Trigger-Platine (20 × 22 mm) ist eigenständig und hier nur verdrahtet.
