# SLARC – Hardware-Schnittstellen

Stand 25.10.2026 (Ein/Aus-Taster mit Deep Sleep ergänzt). Übergabe vom Hardware/Elektronik-Chat an die Chats für ESP32-Software, Pi-Software, Simulation und KI. Hier steht, was die Hardware liefert und was sie von der Software erwartet.

Was nicht hier steht, gilt nach Repo: Mechanik in den Makros unter `Drawings/Macros`, Verkabelung in `Documentation/Wiring`, Protokoll in `Documentation/SLARC Pi↔ESP32 Protokoll v0.1.pdf`.

Kennzeichnung im Text:
- **(fest)**: entschieden, gilt.
- **(Annahme)**: Startwert. Beim Aufbau messen und hier nachtragen.
- **(offen)**: Entscheidung steht noch aus.

---

## 1. Zuständigkeiten

| Chat | Besitzt | Liefert an |
|---|---|---|
| Hardware/Elektronik | CAD-Makros, Stückliste, Verkabelung, Lochraster-Platinen, CAD-URDF-Erzeugung, diese Datei | alle |
| ESP32-Software | Firmware (PlatformIO), Servo-Bus, Fußkontakte, Relais-Sequenz, Balance, Sicherheit | Pi-Software (Protokoll), Hardware (Kalibrierwerte) |
| Pi-Software | Protokoll-Seite Pi, Kameras/Trigger, ICM-20948, Missionsplanung, Inferenz-Pipeline | ESP32 (Befehle), KI (Daten) |
| Simulation | `slarc_sim_V10.py`, Gangarten, Klettern, Aufrichten, CMA-ES | ESP32 (Gait-Parameter, IK-Logik) |
| KI | FusedHexapodModel, Training, Hailo-Deploy | Pi-Software (HEFs, Pre-/Postprocessing) |

**Regeln für alle:**
- Jede Änderung auf einem eigenen Branch mit PR, Marco merged.
- Auf einen Branch nur weiter pushen, solange sein PR nachweislich offen ist.
- Mehrere PRs, die die Stückliste (`.xlsx`) ändern, in einem PR bündeln. Konflikte in Excel-Dateien lassen sich auf GitHub nicht lösen.
- Stückliste nur direkt in `SLARC_Stueckliste.xlsx` ändern. Marco pflegt dort Preise und Status.
- Wer eine Annahme dieser Datei durch eine Messung ersetzt, trägt sie hier ein, mit Datum.

---

## 2. Koordinaten und Konventionen (fest)

- **Körper-Frame:** X vorn, Y links, Z oben (REP-103). Ursprung in der Körpermitte. Z = 0 ist die Oberkante des Hüllmaßes der Coxa-Servos. Die obere Platte liegt bei z −0,9…3,1 mm, die untere bei −39…−35 mm.
- **Beinreihenfolge im Protokoll:** FR, MR, HR, FL, ML, HL. Im CAD und in der Verkabelung heißen die hinteren Beine RR/RL, das sind HR/HL.

**Coxa-Achsen** (x, y in mm, Grundausrichtung des Beins als Gierwinkel):

| Bein | x | y | Gier |
|---|---|---|---|
| FR | 200 | −75 | −30° |
| MR | 0 | −115 | −90° |
| HR | −200 | −75 | −150° |
| FL | 200 | 75 | 30° |
| ML | 0 | 115 | 90° |
| HL | −200 | 75 | 150° |

**Beingeometrie** (wie `LEG_*` in der Sim):

| Größe | Wert |
|---|---|
| Coxa (Coxa-Achse → Femurachse) | 60 mm |
| Femurachse unter der Coxa-Achse | 17,025 mm |
| Femur | 150 mm |
| Tibia als gerade Ersatz-Tibia (Knie → Fußkugelmitte) | 159,2 mm, 29,07° unter Segment 1 |
| Fußkugel | r 16 mm |

Gelenkwinkel Tibia = IK-Winkel der Ersatz-Tibia − 29,07°.

**Gelenkwinkel:**
- q = 0 heißt: Coxa radial in Grundausrichtung, Femur waagrecht, Tibia-Segment 1 in Verlängerung des Femurs.
- Coxa positiv um +Z, also gegen den Uhrzeigersinn von oben.
- Femur und Tibia: positiv = nach unten.
- Linke Beine sind gespiegelt gebaut. Femur- und Tibia-Servo sitzen dort um 180° gedreht. Die Bedeutung der Gelenkwinkel bleibt gleich, die Drehrichtung des Servos kehrt sich um.

**Gelenkgrenzen** (mechanischer Anschlag / Grenze für Software):

| Gelenk | Anschlag | Software |
|---|---|---|
| Coxa | ±95° | ±90° |
| Femur | ±117° | ±112° |
| Tibia | ±117° | ±112° |

- **Stehpose:** `G_RADIUS` = 0,18 m. Die Servowinkel dazu stehen im Projekt-Dokument, gemittelt etwa Femur −21°, Tibia 89°. Rumpf auf 128 mm.
- **Massen:** laut CAD-URDF 3,79 kg gesamt (`utilities/Motion_development/slarc_sim/urdf/`). Akku, Elektronik und Kabel sind geschätzt (Annahme), bitte wiegen.

---

## 3. Servos ST3215 (für ESP32 und Sim)

- **Bus:** halbduplex an UART1 des ESP32 (TX IO19, RX IO18), auf dem Treiber über SN74LVC1G125/126, DATA an H5. Werksbaudrate der ST3215 laut Feetech 1 Mbit/s (Annahme, am ersten Servo prüfen).
- **Kennwerte:** 12 V, Stall 2,94 Nm / 2,7 A, Leerlauf ~200 mA, 45 U/min. Position 0…4095 auf 360°, 2048 = Mitte.

**IDs** (fest, vergeben vor dem Anschluss an den Bus, jeder Servo einzeln, neue haben ID 1):

| Bein | Coxa | Femur | Tibia |
|---|---|---|---|
| FR | 11 | 12 | 13 |
| MR | 21 | 22 | 23 |
| HR | 31 | 32 | 33 |
| FL | 41 | 42 | 43 |
| ML | 51 | 52 | 53 |
| HL | 61 | 62 | 63 |

Die Zehnerstelle folgt der Protokoll-Reihenfolge.

**Drehrichtung und Nullpunkt** (offen, wird bei der Inbetriebnahme gemessen):
- Erwartet `dir = −1` für Femur und Tibia der linken Beine.
- Für die Coxa ergibt die Montage die Richtung.
- Nullpunkt-Offset je Servo, weil die Hornverzahnung den Winkel nicht exakt trifft.
- Die Firmware braucht eine Tabelle `{id: dir, offset_ticks}` mit einer Kalibrierroutine: Bein in die q = 0-Lehre oder an eine Referenzkante legen, Position speichern.

**Strom:**
- Jedes Bein hängt an einem eigenen Relais (K2…K7, 10 A Kontakt).
- Ein Bein zieht im Mittel ~1,7 A, höchstens 8,1 A.
- Die Bein-Relais nur bei abgeschaltetem Drehmoment schalten.

---

## 4. ESP32 (Waveshare General Driver)

| Pin | Funktion | Hinweis |
|---|---|---|
| IO18 / IO19 | Servo-Bus UART1 | fest |
| IO32 / IO33 | I²C (SDA/SCL laut Waveshare-Belegung prüfen) | Board-IMU, INA219, MCP23017 |
| IO34 | MCP23017 INTA | nur Eingang, kein interner Pull-up; INTA im IOCON als Push-Pull, aktiv low |
| IO16 | K1 (Pi-Versorgung), low = an | **als Open-Drain betreiben**, weil der Pi am selben Eingang über einen Transistor hält |
| IO27 | K2…K7 (alle Beine gemeinsam), low = an | ~12 mA Senke |
| IO4 | WS2812-Daten (optional) | 5 V vom Treiber |
| IO35 | Ein/Aus-Taster, low = gedrückt | 10 kΩ Pull-up auf dem Hub; RTC-fähig, weckt aus dem Deep Sleep (ext0) |
| IO5 | frei, Strapping-Pin | beim Booten nicht low ziehen |

**I²C-Geräte** (Annahme, mit einem I²C-Scan bestätigen und hier eintragen):

| Gerät | Adresse |
|---|---|
| MCP23017 (Hub) | 0x20 (A0–A2 auf GND) |
| QMI8658C (IMU) | 0x6B |
| AK09918C (Magnetometer) | 0x0C |
| INA219 | 0x40–0x45, Waveshare nutzt oft 0x42 |

Das INA219 misst nur den Strom des Treibers. Die Akkuspannung zeigt es trotzdem.

**Fußkontakte** (fest): MCP23017 Port A, Pull-up 10 kΩ nach 3,3 V. Mikroschalter schließt nach GND, also **0 = Kontakt**. Entprellen in der Firmware (Vorschlag 5–10 ms).

| Pin | Bein |
|---|---|
| PA0 | HR |
| PA1 | HL |
| PA2 | MR |
| PA3 | ML |
| PA4 | FR |
| PA5 | FL |

Port B ist frei für Status-LEDs.

**Ein- und Ausschalten** (fest, Deep-Sleep-Lösung):
- Der Akku bleibt eingesteckt. Ein Taster hinten rechts weckt den ESP32 aus dem Deep Sleep und löst auch das Ausschalten aus.
- Der Ruhestrom im Deep Sleep wird gemessen (Strom in der 12-V-Zuleitung des Treibers, erwartet 5–15 mA). Bei mehr als etwa 5 mA greift die Ausweichlösung: K8 als Selbsthaltung für den Treiber.

Ablauf:
1. Aus: Deep Sleep, alle Relais offen. Wecken über IO35 low.
2. IO16 low: K1 zieht an, der Pi bootet.
3. Der Pi setzt GPIO26 high und hält K1 damit selbst.
4. IO27 low: die Beine bekommen Strom, das Drehmoment ist noch aus.
5. Das Drehmoment einschalten.
6. Aus (Taster kurz oder Befehl vom Pi, z. B. aus einem Webinterface):
   1. Beine ablegen, Drehmoment aus, IO27 high.
   2. Shutdown an den Pi, auf Bestätigung warten (höchstens ~30 s).
   3. IO16 loslassen. K1 fällt, sobald GPIO26 abfällt.
   4. Deep Sleep.
7. Taster 5 s halten: Notaus, sofort alle Relais los, Deep Sleep.

Im Protokoll braucht es dafür einen Befehl „power off“ vom Pi zum ESP32 und eine Meldung „shutdown“ vom ESP32 an den Pi (mit Bestätigung).

Watchdog: Hängt die Firmware mit gezogenen Relais, muss der Task-Watchdog den ESP32 zurücksetzen. Nach einem Reset sind alle Relais offen.

**Sicherheit** (aus README/Protokoll):
- 100-Hz-Regelschleife, Heartbeat vom Pi alle 100 ms. Fehlt er länger als 300 ms während einer Bewegung, geht der ESP32 in `SAFE_STOP`.
- Notaus unabhängig vom Bus: IO27 high nimmt allen Beinen die Spannung. Danach liegt der Roboter auf dem Bauch.

**Akku:** 3S LiPo, 12,6 V voll, 11,1 V nominal. Vorschlag: Warnung bei 3,5 V/Zelle unter Last (10,5 V), Bewegung beenden bei 3,3 V/Zelle (9,9 V). Das BMS schaltet bei etwa 2,5–2,8 V/Zelle ab, das ist zu spät für den Akku.

---

## 5. Raspberry Pi 5

| GPIO (Pin) | Funktion |
|---|---|
| GPIO2 / GPIO3 (3 / 5) | I²C1 → ICM-20948 (Pimoroni, 0x68, alternativ 0x69) |
| GPIO24 (18) | ICM-20948 INT (Data Ready) |
| GPIO18 (12) | PWM Kameratrigger (siehe `Documentation/Setup HW trigger.txt`) |
| GPIO23 (16) | Trigger-Rückführung, Flanken-Zeitstempel (libgpiod v2) |
| GPIO26 (37) | K1 halten, high = halten (über BC547) |
| GPIO14 / GPIO15 (8 / 10) | UART zum ESP32, alternativ USB-C (CP2102) am Treiber (offen) |
| 5 V (2, 4), GND (6, 9) | Versorgung vom DC-DC, falls nicht über USB-C |

**Einstellungen:**
- `config.txt`: `POWER_OFF_ON_HALT=0`.
- Bei Versorgung ohne USB-PD in der EEPROM-Konfiguration `PSU_MAX_CURRENT=5000` (`sudo rpi-eeprom-config -e`).
- Kameras: CAM0 = links, CAM1 = rechts (fest, so verkabeln).

**Abschalten:**
- Der Pi erkennt das Ende über das Protokoll: ESP32-Heartbeat fehlt oder ein Shutdown-Befehl kommt.
- Er fährt herunter, setzt GPIO26 aber nicht aktiv auf low. GPIO26 fällt mit dem Ausschalten von selbst ab.

---

## 6. Kameras und IMU (für Pi-Software und KI)

**Kameras:**
- 2× IMX296 (Global Shutter, 1440 × 1080) mit M12-Objektiv ZH3019-14: 2,8 mm, F2.2, Bildwinkel D 148° / H 118°, Verzeichnung < −17 %.
- Baseline 65 mm, Hardware-Trigger.

**Einbaulage im Körper-Frame** aus dem CAD (Annahme, gilt bis zur Kalibrierung):

| Größe | Wert |
|---|---|
| Optische Achsen | parallel zu +X |
| Sensorebene | x ≈ 177,7 mm |
| Achsen | y = ±32,5 mm (links +), z = 37,2 mm |
| Objektivspitze | x 199,7 mm |
| ICM-20948 | auf dem Kamerahalter oben mittig, etwa x 173, y 0, z 62 mm; Achsen noch nicht festgelegt |

- Kamera-zu-Kamera und Kamera-zu-IMU kalibriert Kalibr. Die CAD-Werte dienen nur als Startwerte.
- Die Mindestdistanz der Stereo-Tiefe liegt bei ~12 cm (fx ≈ 357 px bei 640 × 480, 192 px Disparität).

**Was die Kameras sehen:**
- Die Füße der Vorderbeine.
- In Stehpose das Gelände ab etwa 12 cm vor dem Roboter.
- Kein Teil des Roboters im Bild, außer in Beinposen weit vorn. Die Panzerkante endet bei x 158, hinter dem Objektiv.

---

## 7. Für die Simulation

- **CAD-URDF:** `urdf/slarc_cad.urdf` ist die Referenz für Massen und Trägheiten. Neu erzeugen mit `tools/make_urdf.py` (FreeCAD), dann `gen_urdf.py`. Der Hardware-Chat erzeugt sie neu, wenn sich Masse oder Geometrie ändern.
- **Reale Grenzen, an die sich jede Gangart halten muss:**
  - Gelenkgrenzen wie oben.
  - Servo-Stall 2,94 Nm.
  - 45 U/min ≈ 4,7 rad/s.
  - Fußkontakt nur als binäres Signal mit Prellen.
  - IMU-Lage aus dem QMI8658C.
- **Coxa-Freigang:** Die Freischnitte der Platten erlauben ±95°. Darüber stößt die Gabel an die Platte.
- **Offen aus der Sim:**
  - Kletterparameter neu optimieren (V10.17 bleibt an der Stufenkante hängen).
  - Aufrichten aus der Rückenlage über den Panzerfirst (SLARC liegt dort auf First und Knie, etwa 3° gekippt).

---

## 8. Offene Hardware-Punkte, die andere betreffen

| Punkt | Betrifft | Stand |
|---|---|---|
| Pinfolge am Servo-Stecker (GND / 12 V / DATA), DATA-Pin an H5 | ESP32 | vor dem Löten messen |
| Servos sind bei BerryBase nicht lieferbar, ein Bein ist vorhanden | alle | Aufbau zunächst mit einem Bein und Servo-Dummys |
| Drehrichtung und Nullpunkt je Servo | ESP32, Sim | Kalibrierung |
| I²C-Adressen auf dem Treiber | ESP32 | Scan |
| UART Pi ↔ ESP32 über GPIO oder USB | ESP32, Pi | offen |
| Massen wiegen (Akku, Elektronik, Kabel) | Sim | offen |
| Ruhestrom des Treibers im Deep Sleep | ESP32, Hardware | messen, entscheidet Deep Sleep oder K8 |
| Taster beschaffen (12-mm-Einbautaster, Schließer) | Hardware | offen |
| Kabellänge der Servos zu den hinteren Bein-Platinen | Hardware | messen |

---

## 9. Wie man Änderungen an der Schnittstelle meldet

- **Ein Software-Chat braucht etwas von der Hardware**, zum Beispiel einen GPIO, ein Bauteil oder eine Montageänderung: Marco bringt die Anforderung in den Hardware-Chat. Der ändert Verkabelung, CAD oder Stückliste und diese Datei.
- **Ein Software-Chat legt etwas fest, das die Hardware betrifft**, zum Beispiel eine Baudrate, Kalibrierwerte oder eine Pinwahl: Er trägt es hier ein, im selben PR wie die Software.
- **Entscheidungen fürs Projekt** fasst jeder Chat zusätzlich im Projekt-Dokument „SLARC – Stand und Entscheidungen“ zusammen.
