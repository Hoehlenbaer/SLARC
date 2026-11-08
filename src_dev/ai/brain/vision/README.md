# Vision-Sprachmodell (VLM) testen

Stand 08.11.2026. Hintergrund: `Documentation/Brain_Konzept.md`, Abschnitt 13, Punkt 11.

| Skript | Wo | Zweck |
|---|---|---|
| `compare_vlm.py` | PC oder Pi | Genauigkeit: welche der 40 Klassen sind im Bild (COCO als Wahrheit), Beschreibungen, Fragen an eigene Fotos; mehrere Modelle nebeneinander |
| `export_subset.py` | PC | kleine Auswahl echter Innenraumbilder + Mini-Annotation zum Kopieren auf den Pi |
| `bench_pi.py` | Pi | Geschwindigkeit: Bildfragen bei mehreren Bildgrößen und die Brain-Aufgaben ohne Bild |

## 1. Bilder für den Pi (PC, WSL)

```
cd ~/SLARC/src_dev/ai
python -m brain.vision.export_subset --coco ~/datasets/coco -n 20 --out ~/vlm_pi_subset
scp -r ~/vlm_pi_subset <user>@<pi>:~/
scp ~/.models/Qwen3.5-4B-Q4_K_M.gguf ~/.models/mmproj-Qwen3.5-4B-f16.gguf <user>@<pi>:~/.models/
```

Nur Bilder mit mindestens einem Möbel oder Raum-Anker (Sofa, Bett, Tisch, Toilette, Kühlschrank …).

## 2. llama-server auf dem Pi bauen (einmalig)

Auf dem Pi gibt es schon llama.cpp: `utilities/setup_venvs.sh` baut llama-cpp-python mit
OpenBLAS (`-DGGML_BLAS=ON -DGGML_BLAS_VENDOR=OpenBLAS`) ins venv `ai`, die Quellen liegen in
`~/llama-cpp-python/vendor/llama.cpp`, `libopenblas-dev` ist installiert. Daraus fehlt nur
das Programm `llama-server`, das `bench_pi.py` und `compare_vlm.py` ansprechen.

Erst prüfen, ob der Stand neu genug für Qwen3.5 ist (Modell seit März 2026):

```
cd ~/llama-cpp-python/vendor/llama.cpp
git log -1 --format='%cd %h'
```

Ist das Datum nach März 2026, mit denselben Einstellungen wie das venv bauen (~20 min):

```
cmake -B build-server -DCMAKE_BUILD_TYPE=Release -DGGML_BLAS=ON -DGGML_BLAS_VENDOR=OpenBLAS
cmake --build build-server -j4 --target llama-server
```

Ist es älter, ein frisches llama.cpp daneben holen und dort bauen
(`git clone --depth 1 https://github.com/ggml-org/llama.cpp ~/llama.cpp`, dann dieselben zwei Befehle).
Das venv `ai` bleibt unberührt.

Ob OpenBLAS auf dem Pi hilft, ist offen: llama.cpp nutzt BLAS nur für große Matrix-Batches
(Prompt, Bild-Encoder), für Q4-Gewichte meist die eigenen ARM-Kernel. Zum Vergleich ein
zweiter Bau ohne BLAS (`cmake -B build-noblas -DCMAKE_BUILD_TYPE=Release`, sonst gleich).

Pillow für `bench_pi.py` ist im venv `ai` über torchvision bzw. die System-Pakete schon da.

## 3. Messen (Pi)

Perzeption und Motion vorher beenden (Messbedingung wie im Denk-Zustand). Terminal 1:

```
~/llama-cpp-python/vendor/llama.cpp/build-server/bin/llama-server -m ~/.models/Qwen3.5-4B-Q4_K_M.gguf \
    --mmproj ~/.models/mmproj-Qwen3.5-4B-f16.gguf -t 4 -c 4096 -np 1 --port 8080
```

`-np 1`: nur ein Platz, damit der Speicher reicht und der Cache realistisch ist.
Terminal 2, im Repo-Klon auf dem Pi, venv `ai` aktiv:

```
source ~/projects/slarc/venvs/ai/bin/activate
cd <repo>/src_dev/ai
python -m brain.vision.bench_pi --images ~/vlm_pi_subset/val2017 -n 10 --sizes 320,448,640
```

Vergleich mit dem bisherigen Qwen3-4B (nur Text): Server mit
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
