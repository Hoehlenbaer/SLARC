# SLARC – Hinweise für Claude Code

Hexapod-Roboter (6 × 3 DOF, ST3215-Servos), Pi 5 + Hailo-8 für Perzeption und Planung, ESP32 (Waveshare General Driver) für Echtzeit-Regelung. Überblick auf Englisch in `README.md`.

## Kommunikation

- Antworten auf Deutsch, knapp, wenig Formatierung.
- Ehrlicher Widerspruch ist erwünscht. Annahmen und Unsicherheiten offen benennen, keine geschönten Ergebnisse.
- Code-Kommentare und Projekt-Doku auf Deutsch, `README.md` bleibt Englisch.

## Wo was läuft (wichtig)

| Umgebung | Was | Für Claude Code |
|---|---|---|
| Windows | FreeCAD: Makros in `Drawings/Macros/`, `SLARC.FCStd`, `utilities/Motion_development/slarc_sim/urdf/tools/make_urdf.py` | Nicht ausführbar, wenn FreeCAD fehlt. Prüfen mit `python -m py_compile`. Marco führt die Makros in FreeCAD aus. |
| WSL2 | PyBullet-Simulation, CMA-ES, Training (RTX 3080 Ti, PyTorch/ONNX), Hailo-DFC | Ausführbar. Sim headless mit `--no-gui`. |
| Raspberry Pi 5 | `src_stable/`, `src_dev/`, venvs unter `~/projects/slarc/venvs/` (`utilities/setup_venvs.sh`) | Nicht lokal starten, nur statisch prüfen. |
| ESP32 | Firmware in `firmware/esp32/` (PlatformIO, Arduino) | Bauen nur, wenn PlatformIO die Toolchain laden kann; sonst Syntaxprüfung mit g++ gegen Arduino-Stubs. Flashen macht Marco. |

- Makros finden Kaufteil-STEPs relativ zur eigenen Datei. Pfade in Makros nie hart auf Linux oder Windows setzen, sondern relativ zu `__file__` bilden.
- Zeilenenden: LF. Bestehende Dateien nicht umkonvertieren.

## Simulation (`utilities/Motion_development/slarc_sim/`)

- Aktuell `slarc_sim_V10.py` (V10.17). Dateiname bleibt, Version steht im Kopf und als `[V10.x]`-Tag an geänderten Stellen.
- Start headless, z. B. `python slarc_sim_V10.py --no-gui --auto 2400` (Frames geradeaus, dann Ende) oder `--hold N` für einen Stehtest. Optionen: `--help`. GUI über WSLg nur, wenn Marco es will.
- Grundregel: Controller nutzen nur, was der echte Roboter messen kann (Gelenkwinkel, Fuß-Mikroschalter, IMU). Markierungen `# PORTABLE` und `# SIM ONLY` beibehalten, damit der Port auf den ESP32 1:1 möglich bleibt.
- Beingeometrie steht einmal in `LEG_*`. Massen und Trägheiten kommen aus `urdf/slarc_cad.urdf` (Doku in `urdf/README.md`).
- CSV-Logs: `decimate=4` → 60 Hz effektiv; beim Einlesen `skiprows=1`, dann kommt der echte Header.
- Ergebnisse belegen, nicht schätzen. Zahlen aus Läufen mit Parametern angeben.

## Arbeitsweise mit Git

- Jede Änderung auf eigenem Branch mit PR. Nie direkt auf `master` pushen. Marco merged.
- Auf einen Branch nur weiter pushen, solange sein PR nachweislich offen ist. Sonst neuer Branch vom aktuellen `master`.
- Gezielte Änderungen statt Neuschreiben ganzer Dateien. Neue Version im Dateikopf vermerken.
- Alte Versionen (`slarc_sim_V2…V8.py`, `slarc_leg_freecad_v3…v8.py` usw.) und `Archive/` nicht ändern.
- `Drawings/Macros/SLARC_Stueckliste.xlsx`: nur gezielt in der Datei ändern (openpyxl, Formatierung erhalten), nie neu erzeugen. Marco pflegt dort Preise und Status. Mehrere Stücklisten-Änderungen in einem PR bündeln.
- Binärdateien (`SLARC.FCStd`, STEP, STL, HEF, Modelle) nur auf ausdrückliche Bitte ändern.

## Projektwissen

Vor Arbeiten an Hardware, Firmware-Schnittstellen, Geometrie oder Masse lesen:

- `Documentation/Hardware_Interfaces.md`: Koordinaten, Gelenkkonvention, Grenzen, Servo-IDs, Pins, Ein/Aus-Ablauf.
- `Documentation/Stand_und_Entscheidungen.md`: Entscheidungen mit Begründung, Messwerte, offene Punkte.
- `Documentation/Wiring/README.md`: Verkabelung und Lochraster-Platinen.

Wer eine Annahme durch eine Messung ersetzt oder eine Entscheidung ändert, trägt das im selben PR in diese Dateien ein, mit Datum.

## Große Ordner

`Archive/`, `Documentation/Models/` und die Deploy-Ordner unter `src_dev/ai/` sind groß (Modelle, Notebooks, PDFs). Nur gezielt hineinsehen, nicht pauschal durchsuchen.
