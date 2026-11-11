# 2D-Simulation mit Karte (sim2d)

Stand 11.11.2026. Hintergrund und Datenformate: `Documentation/Brain_Konzept.md`, Abschnitt 18.

SLARC kennt die Wohnung anfangs nicht. Er baut mit der (simulierten) Kamera eine Belegungskarte auf,
verfolgt Objekte, erkundet Grenzen zum Unbekannten und navigiert mit A* auf der eigenen Karte.
Das Brain sieht nur das Blackboard. Jeder Lauf wird als HTML-Seite zum Abspielen gespeichert.

| Datei | Inhalt |
|---|---|
| `floorplan.py` | Grundriss: 7 Räume, Türen, Möbel, kleine Dinge (Wahrheit) |
| `world2d.py` | Körper (drehen, gehen), Kamera (Tiefe, Detektion, Verdeckung), Menschen, Katze, Akku |
| `bt2d.py` | Behavior-Tree-Blätter auf Karte und Blackboard |
| `day2d.py` | Tagesschleife, Aufzeichnung, HTML-Ausgabe |
| `viewer.html` | Abspielseite (Vorlage, Daten werden eingebettet) |

## Aufruf (aus `src_dev/ai`, conda-env `slarc-brain` oder venv `ai`)

```
python -m brain.sim2d.day2d                          # 3 h ohne LLM, ~15 s Rechenzeit
python -m brain.sim2d.day2d --hours 1 --html ~/slarc_tag.html
python -m brain.sim2d.day2d --server http://127.0.0.1:8081 --slots 4    # mit Qwen über llama-server
python -m brain.sim2d.day2d --needs --trees          # Stufenwechsel und Bäume im Protokoll
```

Die Seite landet ohne `--html` in `brain/ergebnisse/<Datum>/sim2d_<Uhrzeit>.html` und läuft ohne Server
direkt im Browser (unter WSL z. B. `explorer.exe sim2d_1840.html`).

## Viewer

- Karte: unbekannt (grau), frei (Farbe = Bereich), belegt (dunkel); darüber blass die wahren Wände und Dinge.
- SLARC als Pfeil mit Sichtkegel, gestrichelt der geplante A*-Weg, die Spur der letzten Minuten.
- Quadrate: verfolgte Objekte; Kreuz: fehlt; Magenta: verschoben. Kreise: Menschen (gefüllt = gerade gesehen).
- Kleine Kreise: Dinge, die die Detektion nur als „unbekannt“ kennt; gefüllt, sobald „Was ist das?“ einen Namen
  ergab („?“ = Vermutung, Rückfrage an den Menschen offen).
- Rechts: Verhalten und BT-Blatt, Akku, Bedürfnisse mit Stufe, Blackboard-Zahlen, Protokoll.
- Unten: Abspielen, Zeitregler, Geschwindigkeit (30× bis 300× Simulationszeit).
