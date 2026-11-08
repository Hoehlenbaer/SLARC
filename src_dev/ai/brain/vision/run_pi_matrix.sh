#!/usr/bin/env bash
# brain/vision/run_pi_matrix.sh
# Version 0.5 (08.11.2026) – Alle Pi-Messungen nacheinander gegen einen llama-server ohne BLAS.
# V0.5: Läufe mem-… (Speicher unter 4 GB): kleinerer Kontext, KV-Cache q8_0, kleinere Puffer.
#       Ohne ONLY/ALL laufen jetzt die mem-Läufe.
# V0.4: -np/-c nur einmal an den Server (doppelt gab eine DEPRECATED-Warnung).
# V0.3: Zusatzspalten für Server- und bench-Optionen; Läufe „slots-…“ vergleichen einen Slot
#       mit einem Slot je Aufgabe (-np 4). Standard ohne ONLY: nur die slots-Läufe, ALL=1 für alle.
# V0.2: BLAS-Prüfung schlug wegen des Ordnernamens build-noblas fälschlich an.
#
# Startet für jede Konfiguration selbst einen llama-server, wartet auf /health, lässt
# bench_pi laufen, beendet den Server, lässt den Pi kurz abkühlen. Am Ende eine Übersicht
# (brain/ergebnisse/<Datum>/pi_matrix_<Uhrzeit>.md). Fehlende Modelldateien werden übersprungen.
#
# Aufruf auf dem Pi (Perzeption und Motion vorher beenden):
#   bash ~/projects/SLARC/src_dev/ai/brain/vision/run_pi_matrix.sh
# Anpassbar über Umgebungsvariablen, z. B.:
#   N=3 SIZES=320,448 COOL=60 IMAGES=~/vlm_pi_subset/val2017 bash run_pi_matrix.sh
#   ONLY=q35-2b bash run_pi_matrix.sh          # nur Läufe, deren Label so beginnt
#   ALL=1 bash run_pi_matrix.sh                # alle Läufe (ohne ONLY/ALL: nur mem-…)
# Dauer grob 10–15 min je Konfiguration mit Bild (4B), weniger fürs 2B und Text allein.

set -u

M=${MODELS:-$HOME/.models}
BIN=${SERVER_BIN:-$HOME/llama.cpp/build-noblas/bin/llama-server}
IMAGES=${IMAGES:-$HOME/vlm_pi_subset/val2017}
N=${N:-3}
SIZES=${SIZES:-320,448}
COOL=${COOL:-60}
PORT=${PORT:-8080}
ONLY=${ONLY:-}
[ -z "$ONLY" ] && [ -z "${ALL:-}" ] && ONLY=mem
Q40=${Q40:-$(ls "$M"/Qwen3.5-4B-Q4_0*.gguf 2>/dev/null | head -1)}

Q4KM=$M/Qwen3.5-4B-Q4_K_M.gguf
Q8MM=$M/mmproj-Qwen3.5-4B-Q8_0.gguf
# Label | Modell | mmproj (leer = nur Text) | zusätzliche Server-Optionen | zusätzliche bench_pi-Optionen
CONFIGS=(
  "slots-1|$Q4KM|$Q8MM||--text-only"
  "slots-4|$Q4KM|$Q8MM|-np 4 -c 12288|--text-only --slots 4"
  "mem-1-c12k|$Q4KM|$Q8MM|-np 4 -c 12288|--text-only --slots 4"
  "mem-2-c8k|$Q4KM|$Q8MM|-np 4 -c 8192|--text-only --slots 4"
  "mem-3-c8k-kvq8|$Q4KM|$Q8MM|-np 4 -c 8192 -fa on -ctk q8_0 -ctv q8_0|--text-only --slots 4"
  "mem-4-c8k-kvq8-ub256|$Q4KM|$Q8MM|-np 4 -c 8192 -fa on -ctk q8_0 -ctv q8_0 -ub 256|--text-only --slots 4"
  "mem-5-ohne-mmproj|$Q4KM||-np 4 -c 8192 -fa on -ctk q8_0 -ctv q8_0 -ub 256|--text-only --slots 4"
  "q35-4b-q4km-f16|$M/Qwen3.5-4B-Q4_K_M.gguf|$M/mmproj-Qwen3.5-4B-f16.gguf"
  "q35-4b-q4km-q8|$M/Qwen3.5-4B-Q4_K_M.gguf|$M/mmproj-Qwen3.5-4B-Q8_0.gguf"
  "q35-4b-q40-q8|${Q40:-$M/Qwen3.5-4B-Q4_0.gguf}|$M/mmproj-Qwen3.5-4B-Q8_0.gguf"
  "q35-2b-q4km-f16|$M/Qwen3.5-2B-Q4_K_M.gguf|$M/mmproj-Qwen3.5-2B-f16.gguf"
  "q35-2b-q4km-q8|$M/Qwen3.5-2B-Q4_K_M.gguf|$M/mmproj-Qwen3.5-2B-Q8_0.gguf"
  "q3-4b-text|$M/Qwen3-4B-Instruct-2507-Q4_K_M.gguf|"
)

AI_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)    # src_dev/ai
cd "$AI_DIR" || exit 1

# Python: aktives venv, sonst venv ai (alte und neue Schreibweise), sonst System
if [ -n "${VIRTUAL_ENV:-}" ]; then PY=python
elif [ -x "$HOME/projects/slarc/venvs/ai/bin/python" ]; then PY=$HOME/projects/slarc/venvs/ai/bin/python
elif [ -x "$HOME/projects/SLARC/venvs/ai/bin/python" ]; then PY=$HOME/projects/SLARC/venvs/ai/bin/python
else PY=python3; fi
"$PY" -c "import PIL" 2>/dev/null || { echo "Pillow fehlt für $PY"; exit 1; }

# Läuft der Server wirklich ohne BLAS?
[ -x "$BIN" ] || { echo "llama-server nicht gefunden: $BIN"; exit 1; }
# [V0.2] nur Bibliotheksnamen prüfen, nicht den Pfad (der heißt selbst "build-noblas")
BLAS=$( { ldd "$BIN" 2>/dev/null | awk '{print $1}'; ls "$(dirname "$BIN")" 2>/dev/null; } \
        | grep -iE '^lib(ggml-blas|openblas|blas|cblas|blis|mkl)' )
if [ -n "$BLAS" ] && [ -z "${ALLOW_BLAS:-}" ]; then
  echo "Achtung, $BIN hängt an BLAS:"; echo "$BLAS"; echo "Abbruch (ALLOW_BLAS=1 erzwingt)."; exit 1
fi
echo "Server: $BIN ($( [ -n "$BLAS" ] && echo "mit BLAS" || echo "ohne BLAS"))"
echo "Python: $PY, Bilder: $IMAGES, n=$N, Größen $SIZES"

if curl -s -o /dev/null "http://127.0.0.1:$PORT/health"; then
  echo "Auf Port $PORT läuft schon ein Server. Bitte erst beenden."; exit 1
fi

LOGDIR=$AI_DIR/brain/ergebnisse/$(date +%F)
mkdir -p "$LOGDIR"
START=$(date +%s)
JSONS=()
SRV=""
trap '[ -n "$SRV" ] && kill "$SRV" 2>/dev/null; exit 130' INT TERM

for c in "${CONFIGS[@]}"; do
  IFS='|' read -r LABEL MODEL MMPROJ SXTRA BXTRA <<< "$c"
  [ -n "$ONLY" ] && [[ "$LABEL" != "$ONLY"* ]] && continue
  MISSING=""
  [ -f "$MODEL" ] || MISSING="$MODEL"
  [ -n "$MMPROJ" ] && [ ! -f "$MMPROJ" ] && MISSING="$MISSING $MMPROJ"
  if [ -n "$MISSING" ]; then echo; echo "== $LABEL: übersprungen, fehlt:$MISSING"; continue; fi
  echo; echo "== $LABEL: $(basename "$MODEL") ${MMPROJ:+ + $(basename "$MMPROJ")}  ($(date +%H:%M))"
  echo "   Swap belegt: $(free -m | awk '/Swap/ {print $3}') MB"

  ARGS=(-m "$MODEL" -t 4 --cache-ram 0 --port "$PORT")
  [[ " ${SXTRA:-} " == *" -np "* ]] || ARGS+=(-np 1)
  [[ " ${SXTRA:-} " == *" -c "* ]] || ARGS+=(-c 4096)
  [ -n "$MMPROJ" ] && ARGS+=(--mmproj "$MMPROJ")
  # shellcheck disable=SC2206
  [ -n "${SXTRA:-}" ] && ARGS+=($SXTRA)
  "$BIN" "${ARGS[@]}" > "$LOGDIR/server_$LABEL.log" 2>&1 &
  SRV=$!

  ok=""
  for _ in $(seq 1 180); do
    curl -sf -o /dev/null "http://127.0.0.1:$PORT/health" && { ok=1; break; }
    kill -0 "$SRV" 2>/dev/null || break
    sleep 1
  done
  if [ -z "$ok" ]; then
    echo "   Server startet nicht, siehe $LOGDIR/server_$LABEL.log"; kill "$SRV" 2>/dev/null; wait "$SRV" 2>/dev/null; SRV=""; continue
  fi

  MARK=$(mktemp); sleep 1
  B=(--url "http://127.0.0.1:$PORT" --label "$LABEL")
  [ -n "$MMPROJ" ] && B+=(--mmproj "$(basename "$MMPROJ")")
  if [ -n "$MMPROJ" ] && [[ "${BXTRA:-}" != *--text-only* ]]; then
    B+=(--images "$IMAGES" -n "$N" --sizes "$SIZES")
  elif [[ "${BXTRA:-}" != *--text-only* ]]; then
    B+=(--text-only)
  fi
  # shellcheck disable=SC2206
  [ -n "${BXTRA:-}" ] && B+=($BXTRA)
  "$PY" -m brain.vision.bench_pi "${B[@]}"
  NEW=$(find "$LOGDIR" -name "pi_bench_${LABEL}_*.json" -newer "$MARK" 2>/dev/null | sort | tail -1); rm -f "$MARK"
  [ -n "$NEW" ] && JSONS+=("$NEW")

  kill "$SRV" 2>/dev/null; wait "$SRV" 2>/dev/null; SRV=""
  echo "   Abkühlen $COOL s ..."; sleep "$COOL"
done

echo
if [ ${#JSONS[@]} -gt 0 ]; then
  "$PY" -m brain.vision.bench_pi --summarize "${JSONS[@]}"
else
  echo "Keine Läufe fertig."
fi
echo "Gesamtdauer: $(( ($(date +%s) - START) / 60 )) min. Server-Logs: $LOGDIR/server_*.log"
