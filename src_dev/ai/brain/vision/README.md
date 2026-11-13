# Vision-Sprachmodell (VLM) testen

Stand 13.11.2026 (Abschnitt 2: Setup über setup_venvs.sh). Hintergrund: `Documentation/Brain_Konzept.md`, Abschnitt 13, Punkt 11.

| Skript | Wo | Zweck |
|---|---|---|
| `compare_vlm.py` | PC oder Pi | Genauigkeit: welche der 40 Klassen sind im Bild (COCO als Wahrheit), Beschreibungen, Fragen an eigene Fotos; mehrere Modelle nebeneinander |
| `export_subset.py` | PC | kleine Auswahl echter Innenraumbilder + Mini-Annotation zum Kopieren auf den Pi |
| `bench_pi.py` | Pi | Geschwindigkeit: Bildfragen bei mehreren Bildgrößen und die Brain-Aufgaben ohne Bild |
| `identify.py` | Brain | Baustein: Ausschnitt um eine Box (mit Rand, quadratisch) ans VLM, „Was ist das?“, Antwort aus Wortliste oder frei, mit „sicher“ |
| `crops_vlm.py` | PC oder Pi | Test dazu: Boxen der 40 COCO-Klassen, die SLARC nicht kennt, als „Unbekannte“; Treffer je Antwortform und Ausschnittgröße |
| `run_pi_matrix.sh` | Pi | alle Modell-/mmproj-Varianten nacheinander mit `bench_pi`, Übersichtstabelle |

## 1. Bilder für den Pi (PC, WSL)

```
cd ~/SLARC/src_dev/ai
python -m brain.vision.export_subset --coco ~/datasets/coco -n 20 --out ~/vlm_pi_subset
scp -r ~/vlm_pi_subset <user>@<pi>:~/
scp ~/.models/Qwen3.5-4B-Q4_K_M.gguf ~/.models/mmproj-Qwen3.5-4B-f16.gguf <user>@<pi>:~/.models/
```

Nur Bilder mit mindestens einem Möbel oder Raum-Anker (Sofa, Bett, Tisch, Toilette, Kühlschrank …).

## 2. llama-server und Modelle auf dem Pi (einmalig)

Macht seit 13.11.2026 `utilities/setup_venvs.sh` (V2.0): llama.cpp ohne BLAS nach
`~/llama.cpp/build-noblas`, Stand a691b23 wie bei den Messungen vom 08.11.2026, dazu
`Qwen3.5-4B-Q4_K_M.gguf` und `mmproj-Qwen3.5-4B-Q8_0.gguf` nach `~/.models`.

```
bash ~/projects/slarc/utilities/setup_venvs.sh                 # fehlt etwas, wird es nachgeholt
bash ~/projects/slarc/utilities/setup_venvs.sh --update-llama  # neu bauen
bash ~/projects/slarc/utilities/setup_venvs.sh --llama-ref <commit|tag>   # anderer Stand
```

Den Server für den Betrieb startet `utilities/llm_server.sh` (Alias `llm-server`) mit den festen
Optionen aus `Brain_Konzept.md`, Abschnitt 17. Die übrigen Modellvarianten für `run_pi_matrix.sh`
(F16-mmproj, Q4_0, 2B, Qwen3-4B) lädt das Setup nicht; die bei Bedarf von Hand nach `~/.models`.

Gemessen 08.11.2026: OpenBLAS bringt nichts (gleiche Zeiten). Hintergrund: llama.cpp nutzt BLAS nur
für große Matrix-Batches (Prompt, Bild-Encoder), für Q4-Gewichte meist die eigenen ARM-Kernel.

Pillow für `bench_pi.py` installiert das Setup im venv `ai`.

## 3. Messen (Pi)

Perzeption und Motion vorher beenden (Messbedingung wie im Denk-Zustand). Terminal 1:

```
~/llama.cpp/build-noblas/bin/llama-server -m ~/.models/Qwen3.5-4B-Q4_K_M.gguf \
    --mmproj ~/.models/mmproj-Qwen3.5-4B-Q8_0.gguf -t 4 -c 4096 -np 1 --cache-ram 0 --port 8080
```

`-np 1`: nur ein Platz, damit der Speicher reicht und der Cache realistisch ist.
`--cache-ram 0`: Neuere llama-server legen zusätzlich einen Prompt-Cache im RAM an, Standard 8192 MiB.
Auf dem Pi (8 GB) lief damit am 08.11.2026 der Swap voll (2 GB), und neue Bilder zeigten nur
4 Prompt-Tokens (vermutlich falsch wiederverwendete Zustände). Der Slot-Cache (`--cache-prompt`) bleibt aktiv.
Terminal 2, im Repo-Klon auf dem Pi, venv `ai` aktiv:

```
source ~/projects/slarc/venvs/ai/bin/activate
cd ~/projects/SLARC/src_dev/ai
python -m brain.vision.bench_pi --images ~/vlm_pi_subset/val2017 -n 10 --sizes 320,448,640
```

Alle Konfigurationen in einem Rutsch (startet und beendet den Server selbst, prüft, dass er ohne BLAS
gebaut ist, überspringt fehlende Modelle, schreibt am Ende `pi_matrix_<Uhrzeit>.md`):

```
bash ~/projects/SLARC/src_dev/ai/brain/vision/run_pi_matrix.sh
N=3 SIZES=320,448 COOL=60 ONLY=q35-2b bash …/run_pi_matrix.sh     # Optionen über Umgebungsvariablen
```

Ohne `ONLY`/`ALL` laufen nur `slots-1` und `slots-4`: Qwen3.5-4B Q4_K_M + Q8-mmproj, Text-Aufgaben mit den
echten Grammatiken, einmal mit einem Slot und einmal mit einem Slot je Aufgabe (`-np 4 -c 12288`, wie
`ServerBrain(n_slots=4)` in `brain/llm.py`). „nach Wechsel“ zeigt dann, ob der Cache den Aufgabenwechsel
übersteht, „frei MB“ den Speicherpreis. Mit `ALL=1` zusätzlich die Läufe vom 08.11.:
Läufe: Qwen3.5-4B Q4_K_M mit mmproj F16 und Q8_0, Qwen3.5-4B Q4_0 mit Q8_0, Qwen3.5-2B mit F16 und Q8_0,
Qwen3-4B nur Text. Die Genauigkeit bei kleiner Bildkante misst man schneller auf dem PC:
`compare_vlm … --max-side 320`.

Einzeln, Vergleich mit dem bisherigen Qwen3-4B (nur Text): Server mit
`-m ~/.models/Qwen3-4B-Instruct-2507-Q4_K_M.gguf` ohne `--mmproj` starten, dann
`python -m brain.vision.bench_pi --text-only`.

Optional Genauigkeit auf denselben Bildern (dauert auf dem Pi entsprechend):

```
python -m brain.vision.compare_vlm --server 4B=http://127.0.0.1:8080 \
    --coco-ann ~/vlm_pi_subset/annotations/instances_subset.json \
    --coco-img ~/vlm_pi_subset/val2017 -n 20 --describe 5
```

Der Bericht landet in `brain/ergebnisse/<Datum>/pi_bench_<Uhrzeit>.md`.

## Wie die Zahlen lesen

- **ja/nein (Dose)**: die kürzeste sinnvolle Bildfrage. Das ist die Zeit einer seltenen Rückfrage im Denk-Zustand.
- **Liste (40 Klassen)**: längere Antwort; zeigt, wie stark die Erzeugung zählt.
- **Bild+Frage Tokens**: wächst mit der Bildgröße. Ist die Prompt-Geschwindigkeit der Engpass, ist eine kleinere Bildkante der Hebel.
- **Brain-Aufgaben „nach Wechsel“ / „wiederholt“**: zeigt, was der Cache spart, und wie lang eine Denkpause ohne Bild ist.
- **Temperatur und Drosselung**: Steigt die Temperatur über ~80 °C oder meldet `get_throttled` etwas anderes als `0x0`, sind die Zahlen ohne Kühlung nicht dauerhaft erreichbar.

## Was ist das? (Ausschnitt eines unbekannten Objekts)

Die Detektion meldet „unbekannt“ mit Box; `identify.py` schneidet die Box mit 25 % Rand quadratisch aus
und fragt das VLM. Test auf dem PC (Server wie oben, mit Q8-mmproj):

```
python -m brain.vision.crops_vlm --server 4B=http://127.0.0.1:8081 \
    --coco-ann ~/datasets/coco/annotations/instances_val2017.json --coco-img ~/datasets/coco/val2017 \
    -k 5 --sides 160,224,320 --modes liste,frei --known
```

Ergebnis 08.11.2026 22:13 (`vision_ausschnitt_2213.md`): Liste 0,80–0,83 Treffer bei Unbekannten,
frei 0,63–0,67; „sicher“ wertlos (98–100 % ja). Häufigster Fehler: das VLM nennt, was ebenfalls im
Ausschnitt ist (Esstisch → Pizza). Deshalb roter Rahmen (`--marks nein,ja`) und kürzere Liste
(`--vocabs voll,haushalt`), realistischer mit `--min-px 64`:

```
python -m brain.vision.crops_vlm --server 4B=http://127.0.0.1:8081 \
    --coco-ann ~/datasets/coco/annotations/instances_val2017.json --coco-img ~/datasets/coco/val2017 \
    -k 5 --min-px 64 --sides 224 --modes liste --vocabs voll,haushalt --marks nein,ja --known
```

Lesart: „Treffer Haushalt“ ist die Kennzahl für SLARC (Gabel, Schere, Obst …, ohne Tiere und Fahrzeuge).
„Treffer wenn sicher“ deutlich über „wenn unsicher“ heißt: „sicher“ taugt als Filter für Antworten ohne
Vorbehalt. „Prompt-Tokens“ zeigt, was der Ausschnitt gegenüber einem Vollbild spart.

