#!/usr/bin/env bash
# utilities/llm_server.sh
# Version 1.0 (13.11.2026) – Startet llama-server für das High-Level-Brain.
#
# Einstellungen wie in Documentation/Brain_Konzept.md, Abschnitt 17 (fest seit 08.11.2026):
# Qwen3.5-4B Q4_K_M + mmproj Q8_0, Build ohne BLAS, 4 Slots (einer je Aufgabe, passend zu
# ServerBrain(n_slots=4) in src_dev/ai/brain/llm.py), KV-Cache q8_0, --cache-ram 0. ~4,2 GB.
#
# Aufruf (auf dem Pi, Perzeption und Motion brauchen den Rest des RAM):
#   bash llm_server.sh                 # Vordergrund, Ctrl+C beendet
#   PORT=8081 bash llm_server.sh       # anderer Port
#   NO_MMPROJ=1 bash llm_server.sh     # nur Text (~0,4 GB weniger)
#   bash llm_server.sh --verbose       # weitere Optionen gehen direkt an llama-server
# Prüfen: curl -s http://127.0.0.1:8080/health
# Umgebungsvariablen: SERVER_BIN, MODELS, MODEL, MMPROJ, PORT, HOST, THREADS, NO_MMPROJ

set -u

BIN=${SERVER_BIN:-$HOME/llama.cpp/build-noblas/bin/llama-server}
M=${MODELS:-$HOME/.models}
MODEL=${MODEL:-$M/Qwen3.5-4B-Q4_K_M.gguf}
MMPROJ=${MMPROJ:-$M/mmproj-Qwen3.5-4B-Q8_0.gguf}
PORT=${PORT:-8080}
HOST=${HOST:-127.0.0.1}
THREADS=${THREADS:-4}

[ -x "$BIN" ] || { echo "llama-server nicht gefunden: $BIN (utilities/setup_venvs.sh baut ihn)"; exit 1; }
[ -f "$MODEL" ] || { echo "Modell fehlt: $MODEL"; exit 1; }

if curl -s -o /dev/null "http://$HOST:$PORT/health"; then
    echo "Auf $HOST:$PORT läuft schon ein Server."; exit 1
fi

ARGS=(-m "$MODEL" -t "$THREADS" --host "$HOST" --port "$PORT"
      -np 4 -c 8192 -fa on -ctk q8_0 -ctv q8_0 -ub 256 --cache-ram 0)

if [ -z "${NO_MMPROJ:-}" ]; then
    [ -f "$MMPROJ" ] || { echo "mmproj fehlt: $MMPROJ (NO_MMPROJ=1 für nur Text)"; exit 1; }
    ARGS+=(--mmproj "$MMPROJ")
fi

echo "Starte $(basename "$MODEL")${NO_MMPROJ:+ (nur Text)} auf $HOST:$PORT"
exec "$BIN" "${ARGS[@]}" "$@"
