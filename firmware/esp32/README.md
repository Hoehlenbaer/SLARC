# SLARC – ESP32-Firmware (Waveshare General Driver for Robots)

Stand V0.1 (02.11.2026): Inbetriebnahme-Werkzeug. Noch keine Regelung, kein Pi-Protokoll. Pins, IDs, Grenzen und Drehrichtungen stehen in `include/config.h` (Quelle: `Documentation/Hardware_Interfaces.md`).

## Aufbau

| Datei | Inhalt |
|---|---|
| `platformio.ini` | Umgebung `slarc`, ESP32-WROOM-32, Arduino-Framework |
| `include/config.h` | Pins, Servo-IDs, `JOINT_DIR`, `JOINT_OFFSET`, Gelenkgrenzen, Fußkontakt-Bits, I²C-Adressen |
| `src/st3215.*` | Treiber für den STS-Bus (Ping, Read, Write, Position); erkennt ein Eigen-Echo des Bustreibers |
| `src/main.cpp` | Kommandozeile über USB-Seriell, 115200 Bd |

## Bauen und Flashen

Am einfachsten unter Windows mit VS Code und der PlatformIO-Erweiterung, Ordner `firmware/esp32` öffnen. Unter WSL2 braucht der USB-Port `usbipd-win`.

```
pio run                 # bauen
pio run -t upload       # flashen (USB-C am Treiber, CP2102)
pio device monitor      # Konsole, 115200 Bd
```

**Vor dem ersten Flashen die Werks-Firmware sichern** (siehe unten). `upload` überschreibt sie.

## Werks-Firmware sichern und wiederherstellen

Mit `esptool` (`pip install esptool`). Port unter Windows z. B. `COM5`, unter Linux `/dev/ttyUSB0`.

```
python -m esptool --port COM5 flash_id                                # Flash-Größe anzeigen (erwartet 4 MB)
python -m esptool --port COM5 --baud 460800 read_flash 0 ALL driver_werk.bin
python -m esptool --port COM5 --baud 460800 write_flash 0 driver_werk.bin   # wiederherstellen
```

`ALL` liest den ganzen Flash (esptool ≥ 4.6, sonst Größe angeben, z. B. `0x400000`). Das Abbild enthält Bootloader, Partitionstabelle, Programm und den NVS-Bereich (z. B. WLAN-Einstellungen). Die Datei nicht ins Repo legen (4 MB, Binärdatei). Kommt der ESP32 nicht in den Bootmodus: BOOT halten, EN kurz drücken.

## Befehle

`help` zeigt alle. Wichtig für die Inbetriebnahme:

| Befehl | Zweck |
|---|---|
| `i2c` | I²C-Scan, bestätigt SDA/SCL und Adressen |
| `scan` / `scan all` | Servos suchen, bei `all` über alle 8 STS-Baudraten |
| `setid <alt> <neu>` | ID vergeben, verweigert, wenn nicht genau ein Servo am Bus hängt |
| `info <id>` | Register: Baud, Grenzen, Ofs, Drehmoment, Position, Last, Spannung, Temperatur |
| `watch <id…>` | Position, Gelenkwinkel q und Last laufend |
| `calib <id>` | Gelenk in q = 0 halten → Wert für `JOINT_OFFSET` |
| `arm 1`, `goto <id> <grad>` | Gelenk langsam anfahren, nur innerhalb der Software-Grenzen |
| `feet`, `vbat`, `btn` | Fußkontakte, Spannung über INA219, Taster IO35 |
| `relay pi/legs on/off`, `off` | Relais K1 bzw. K2…K7; `off` nimmt Drehmoment und alle Relais weg |

## Ablauf Inbetriebnahme (ein Bein, Servo am Treiber)

1. Firmware sichern, dann flashen, Konsole öffnen.
2. `i2c`: Adressen in `Hardware_Interfaces.md` eintragen (QMI8658C, AK09918C, INA219, MCP23017).
3. Einen neuen Servo anschließen, `scan all`: Baudrate bestätigen (erwartet ID 1, 1 Mbit/s).
4. `setid 1 <ID>` laut Tabelle (FR: 11/12/13 …). Servo abziehen, nächsten anschließen.
5. Bein komplett anschließen, `scan`: alle drei IDs müssen antworten.
6. Drehmoment aus, Bein von Hand bewegen, `watch 11 12 13`: Drehrichtung prüfen (Femur/Tibia nach unten bzw. Coxa gegen den Uhrzeigersinn von oben → q steigt). Falsch → `JOINT_DIR` ändern.
7. Bein in die q = 0-Lage bringen, `calib <id>` je Gelenk → `JOINT_OFFSET`.
8. `arm 1`, `goto 12 -20` usw. mit kleinen Winkeln prüfen.

Gemessene Werte (Baudrate, Adressen, Drehrichtungen, Offsets) in `config.h` und `Hardware_Interfaces.md` eintragen, mit Datum.

## Bekannte Annahmen

- I²C an IO32/IO33, welcher Pin SDA ist, prüft der Scan.
- Ob der Bustreiber ein Echo der eigenen Sendung liefert, ist nicht bekannt. Der Treiber verkraftet beides, `scan` zeigt die Zahl erkannter Echos.
- Das Schreiben einer Zielposition schaltet bei STS-Servos das Drehmoment ein.
