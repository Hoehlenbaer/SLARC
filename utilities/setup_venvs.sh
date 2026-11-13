#!/bin/bash

# =============================================================================
# setup_venvs.sh
# Version 2.0 (13.11.2026)
# Richtet alle virtuellen Environments für das SLARC-Projekt ein, installiert den
# Hailo-Stack (hailo-all), baut llama-server für das High-Level-Brain und lädt die Modelle.
#
# V2.0: - Läuft immer als normaler User. Mit sudo gestartet, startet es sich selbst als
#         SUDO_USER neu; sudo nur noch für apt/Hailo. Vorher gehörten venvs, Modelle und
#         ~/llama-cpp-python root. Solche Ordner werden einmalig zurückgegeben (chown).
#       - Neu: llama.cpp/llama-server ohne BLAS nach ~/llama.cpp/build-noblas, Stand wie bei
#         der Pi-Messung 08.11.2026 (a691b23). Brain_Konzept.md, Abschnitt 17.
#       - Modelle: Qwen3.5-4B Q4_K_M + mmproj Q8_0 (Brain). Qwen3-4B (alte Prototypen)
#         nur mit --legacy-llm. Download über .part-Datei mit Mindestgröße; ein Fehler
#         hinterlässt keine leere Datei mehr, die beim nächsten Lauf als vorhanden gilt.
#       - llama-cpp-python (alte Prototypen, LlamaBrain) nur noch bauen, wenn es fehlt oder
#         --update-llama gesetzt ist; ohne BLAS (gemessen: kein Gewinn).
#       - venv ai: pillow, pytest dazu (Brain-Tests, Bildfragen); ollama entfällt (überholt).
#       - Alias llm-server startet den Brain-Server (utilities/llm_server.sh).
#
# Verwendung:
#   bash setup_venvs.sh [Optionen]        (sudo wird intern nur für apt/Hailo angefragt)
#   Optionen:
#     --update-llama     llama-server und llama-cpp-python neu bauen
#     --llama-ref REF    llama.cpp-Stand für llama-server (Commit, Tag, Branch; Standard: gemessener Stand)
#     --legacy-llm       zusätzlich Qwen3-4B-Instruct-2507 laden (exploration_manager, LlamaBrain)
#     --no-models        keine Modelle laden
#     -h, --help         Hilfe
# =============================================================================

# -----------------------------------------------------------------------------
# Als normaler User laufen
# -----------------------------------------------------------------------------
if [ "$(id -u)" -eq 0 ]; then
    if [ -n "${SUDO_USER:-}" ] && [ "$SUDO_USER" != "root" ]; then
        echo "↪ Mit sudo gestartet – starte neu als '$SUDO_USER' (sudo nur für apt/Hailo)."
        exec sudo -u "$SUDO_USER" -H bash "$(readlink -f "$0")" "$@"
    fi
    echo "⚠️ Bitte als normaler User starten: bash setup_venvs.sh"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"

# -----------------------------------------------------------------------------
# Optionen
# -----------------------------------------------------------------------------
# llama.cpp-Stand der Pi-Messung vom 08.11.2026 (Brain_Konzept.md, Abschnitt 17)
LLAMA_CPP_REF="a691b2345844ce1b430201fc5fd404ce062e05f2"
UPDATE_LLAMA=0
LEGACY_LLM=0
NO_MODELS=0

while [ $# -gt 0 ]; do
    case "$1" in
        --update-llama) UPDATE_LLAMA=1 ;;
        --llama-ref)    shift; LLAMA_CPP_REF="${1:?--llama-ref braucht einen Wert}"; UPDATE_LLAMA=1 ;;
        --legacy-llm)   LEGACY_LLM=1 ;;
        --no-models)    NO_MODELS=1 ;;
        -h|--help)      sed -n '/^# Verwendung:/,/^# ====/{/^# ====/d;s/^# \{0,1\}//;p}' "$0"; exit 0 ;;
        *) echo "⚠️ Unbekannte Option: $1 (siehe --help)"; exit 1 ;;
    esac
    shift
done

ACTUAL_USER="$USER"
USER_HOME="$HOME"

echo "👤 Running setup for user: $ACTUAL_USER (home: $USER_HOME)"

# Base directory for venvs
VENV_DIR="$USER_HOME/projects/slarc/venvs"

# Festes Verzeichnis für das llama-cpp-python Repository
LLAMA_REPO_DIR="$USER_HOME/llama-cpp-python"

# llama.cpp für llama-server (Brain); Pfad wie in run_pi_matrix.sh
LLAMA_CPP_DIR="$USER_HOME/llama.cpp"
LLAMA_SERVER_BIN="$LLAMA_CPP_DIR/build-noblas/bin/llama-server"

MODELS_DIR="$USER_HOME/.models"

# Create base directory
mkdir -p "$VENV_DIR"

# =============================================================================
# Venv-Hilfsfunktionen
# =============================================================================

create_venv() {
    local name=$1
    local path="$VENV_DIR/$name"
    local site_packages=$2

    if [ -d "$path" ]; then
        echo "✅ Venv '$name' already exists. Skipping creation."
    else
        echo "🆕 Creating venv '$name'..."
        if [ "$site_packages" = true ]; then
            python3 -m venv "$path" --system-site-packages
        else
            python3 -m venv "$path"
        fi
    fi
}

install_packages() {
    local name=$1
    shift
    local path="$VENV_DIR/$name"
    if [ -d "$path" ]; then
        echo "   -> Installing standard packages for '$name'..."
        source "$path/bin/activate"
        pip install --disable-pip-version-check "$@"
        deactivate
    else
        echo "⚠️ Venv '$name' not found. Skipping package installation."
    fi
}

# =============================================================================
# [V2.0] Besitz zurückgeben: frühere Läufe mit sudo legten diese Ordner als root an
# =============================================================================

fix_ownership() {
    local d
    for d in "$VENV_DIR" "$LLAMA_REPO_DIR" "$LLAMA_CPP_DIR" "$MODELS_DIR"; do
        [ -e "$d" ] || continue
        if [ -n "$(find "$d" ! -user "$ACTUAL_USER" -print -quit 2>/dev/null)" ]; then
            echo "🔧 $d gehört (teilweise) nicht $ACTUAL_USER – sudo chown -R ..."
            sudo chown -R "$ACTUAL_USER:$(id -gn)" "$d" \
                && echo "✅ $d gehört jetzt $ACTUAL_USER." \
                || echo "⚠️ chown fehlgeschlagen – pip/git in $d können scheitern."
        fi
    done
}

# =============================================================================
# System-Abhängigkeiten (apt)
# =============================================================================

install_system_deps() {
    echo ""
    echo "📦 Checking system dependencies..."

    local pkgs=()

    # Für venv-Erstellung
    dpkg -s python3-venv    &>/dev/null || pkgs+=(python3-venv)
    dpkg -s python3-pip     &>/dev/null || pkgs+=(python3-pip)

    # Für llama.cpp / llama-cpp-python Build und Downloads
    dpkg -s git             &>/dev/null || pkgs+=(git)
    dpkg -s build-essential &>/dev/null || pkgs+=(build-essential)
    dpkg -s cmake           &>/dev/null || pkgs+=(cmake)
    dpkg -s ninja-build     &>/dev/null || pkgs+=(ninja-build)
    dpkg -s libssl-dev      &>/dev/null || pkgs+=(libssl-dev)   # [V2.0] llama.cpp: HTTPS (-hf)
    dpkg -s wget            &>/dev/null || pkgs+=(wget)
    # [V2.0] libopenblas-dev entfällt: llama.cpp wird ohne BLAS gebaut (Messung 08.11.2026)

    # Für Hailo DKMS-Kernel-Modul – muss VOR hailo-all installiert sein!
    dpkg -s dkms            &>/dev/null || pkgs+=(dkms)

    if [ ${#pkgs[@]} -eq 0 ]; then
        echo "✅ All system dependencies already installed."
    else
        echo "🆕 Installing missing system packages: ${pkgs[*]}"
        sudo apt update -qq
        if sudo apt install -y "${pkgs[@]}"; then
            echo "✅ System dependencies installed."
        else
            echo "⚠️ apt install fehlgeschlagen – Setup wird trotzdem fortgesetzt."
        fi
    fi
}

# =============================================================================
# Hailo-Installation
# =============================================================================

install_hailo() {
    echo ""
    echo "🤖 Checking Hailo installation..."

    # Prüfen ob hailo-all bereits installiert ist
    if dpkg -s hailo-all &>/dev/null 2>&1; then
        echo "✅ hailo-all already installed. Skipping apt step."
    else
        echo "🆕 Installing Hailo stack (hailo-all)..."
        sudo apt update
        if sudo apt install -y hailo-all; then
            echo "✅ hailo-all installed successfully."
        else
            echo "⚠️ hailo-all installation failed."
            echo "   - Raspberry Pi OS Trixie (64-bit) wird vorausgesetzt"
            echo "   - Hailo APT-Quelle fehlt (ggf. erst: sudo apt update)"
            echo "   Setup wird trotzdem fortgesetzt."
            return 1
        fi
    fi

    # DKMS-Modul für den AKTUELL LAUFENDEN Kernel prüfen und ggf. bauen.
    # Wichtig: nach einem Kernel-Update ist das Modul für den neuen Kernel
    # noch nicht gebaut – daher immer gegen $(uname -r) prüfen, nicht nur
    # ob irgendein Build existiert.
    CURRENT_KERNEL="$(uname -r)"
    HAILO_VER=$(ls /usr/src/ 2>/dev/null | grep hailo_pci | sed 's/hailo_pci-//' | tail -1)

    echo "   -> Checking Hailo DKMS kernel module for kernel ${CURRENT_KERNEL}..."

    if dkms status 2>/dev/null | grep -q "hailo_pci.*${CURRENT_KERNEL}.*installed"; then
        echo "✅ hailo_pci DKMS module already built for current kernel."
    else
        echo "🆕 Building hailo_pci DKMS module for kernel ${CURRENT_KERNEL}..."

        # Reinstall triggert den DKMS-Build falls dkms jetzt vorhanden ist
        sudo apt install --reinstall -y hailort-pcie-driver 2>/dev/null || \
        sudo apt install --reinstall -y hailo-dkms 2>/dev/null || true

        # Falls Reinstall den Build nicht triggert: manuell anstoßen
        if [ -n "$HAILO_VER" ]; then
            sudo dkms build   "hailo_pci/${HAILO_VER}" -k "${CURRENT_KERNEL}" 2>/dev/null || true
            sudo dkms install "hailo_pci/${HAILO_VER}" -k "${CURRENT_KERNEL}" 2>/dev/null || true
        fi

        if dkms status 2>/dev/null | grep -q "hailo_pci.*${CURRENT_KERNEL}.*installed"; then
            echo "✅ hailo_pci DKMS module built successfully for ${CURRENT_KERNEL}."
        else
            echo "⚠️ DKMS build failed – bitte manuell prüfen: dkms status"
        fi
    fi

    # Post-Upgrade Hook: DKMS automatisch nach Kernel-Update rebuilden.
    # Verhindert dass nach 'apt upgrade' der Hailo-Treiber ohne Aktion fehlt.
    HOOK_PATH="/etc/kernel/postinst.d/dkms-hailo"
    if [ ! -f "$HOOK_PATH" ]; then
        echo "   -> Installing DKMS post-upgrade hook..."
        sudo tee "$HOOK_PATH" > /dev/null << 'HOOKEOF'
#!/bin/bash
# Auto-rebuild Hailo DKMS module after kernel update
KERNEL_VERSION="$1"
echo "[hailo] Rebuilding hailo_pci DKMS module for kernel ${KERNEL_VERSION}..."
dkms autoinstall -k "${KERNEL_VERSION}"
HOOKEOF
        sudo chmod +x "$HOOK_PATH"
        echo "✅ DKMS post-upgrade hook installed at ${HOOK_PATH}."
    else
        echo "✅ DKMS post-upgrade hook already installed."
    fi

    # Autoload beim Boot sicherstellen
    if [ ! -f /etc/modules-load.d/hailo.conf ]; then
        echo "   -> Configuring hailo_pci for autoload on boot..."
        echo "hailo_pci" | sudo tee /etc/modules-load.d/hailo.conf > /dev/null
        echo "✅ hailo_pci autoload configured."
    else
        echo "✅ hailo_pci autoload already configured."
    fi

    # Modul laden (für diese Session, ohne Reboot)
    if ! lsmod | grep -q hailo_pci; then
        sudo modprobe hailo_pci 2>/dev/null && echo "✅ hailo_pci module loaded." \
            || echo "⚠️ modprobe hailo_pci failed – Reboot erforderlich."
    else
        echo "✅ hailo_pci module already loaded."
    fi

    # Verbindung zum Hailo-Chip prüfen
    echo "   -> Verifying Hailo device..."
    if command -v hailortcli &>/dev/null; then
        if hailortcli fw-control identify 2>/dev/null; then
            echo "✅ Hailo device detected and responding."
        else
            echo "⚠️ hailortcli identify failed."
            echo "   - Ist das Hailo-Board verbunden und PCIe aktiv?"
            echo "   - Ein Reboot kann helfen: sudo reboot"
            echo "   - Nach Reboot prüfen: hailortcli fw-control identify"
        fi
    else
        echo "⚠️ hailortcli nicht gefunden – Reboot möglicherweise erforderlich."
    fi
}

# =============================================================================
# llama-cpp-python (Custom Build) – für die alten Prototypen und LlamaBrain
# =============================================================================

install_llama_cpp_custom() {
    local venv_name="ai"
    local path="$VENV_DIR/$venv_name"

    if [ ! -d "$path" ]; then
        echo "⚠️ Venv '$venv_name' not found. Skipping custom llama-cpp-python build."
        return 1
    fi

    # [V2.0] Nur bauen, wenn es fehlt oder ausdrücklich gewünscht (Build dauert lange)
    if [ "$UPDATE_LLAMA" != 1 ] && "$path/bin/python" -c "import llama_cpp" &>/dev/null; then
        echo "✅ llama-cpp-python already installed in '$venv_name' ($("$path/bin/python" -c 'import llama_cpp; print(llama_cpp.__version__)' 2>/dev/null)). Skipping build (--update-llama erzwingt)."
        return 0
    fi

    echo "⚙️ Starting custom build and installation of llama-cpp-python for '$venv_name'..."

    # 1. Activate the target venv
    source "$path/bin/activate"

    # 2. Pre-install dependencies for the build system
    echo "   -> Installing build dependencies (scikit-build-core, cmake, ninja)..."
    pip install --disable-pip-version-check "scikit-build-core[pyproject]" cmake ninja

    # 3. Repo klonen oder aktualisieren
    if [ -d "$LLAMA_REPO_DIR" ]; then
        echo "   -> Found existing local repository at $LLAMA_REPO_DIR. Cleaning and updating..."
        cd "$LLAMA_REPO_DIR" || { deactivate; return 1; }
        git fetch origin
        git reset --hard origin/main
        git submodule update --init --recursive
    else
        echo "   -> Cloning repository to $LLAMA_REPO_DIR ..."
        git clone --recursive https://github.com/abetlen/llama-cpp-python.git "$LLAMA_REPO_DIR"
        cd "$LLAMA_REPO_DIR" || { deactivate; return 1; }
    fi

    # 4. Alte Build-Artefakte entfernen
    echo "   -> Cleaning cached build files..."
    rm -rf _skbuild dist build

    # 5. Bestehende Installation im venv entfernen
    echo "   -> Removing any previous llama-cpp-python installation from venv..."
    pip uninstall -y llama-cpp-python

    # 6. Build und Installation
    # [V2.0] ohne BLAS: llama.cpp rechnet Q4-Gewichte mit eigenen ARM-Kerneln, BLAS brachte
    #        am 08.11.2026 keinen Unterschied (Brain_Konzept.md, Abschnitt 17)
    echo "   -> Building and installing (CPU, without BLAS)..."
    CMAKE_ARGS="-DGGML_BLAS=OFF" pip install . --no-cache-dir --verbose

    # 7. Explizit zurück – kein relatives cd ..
    cd "$VENV_DIR" || true
    deactivate

    echo "✅ Custom llama-cpp-python build complete for '$venv_name'."
}

# =============================================================================
# [V2.0] llama-server (llama.cpp) für das High-Level-Brain
# =============================================================================

install_llama_server() {
    echo ""
    echo "🧠 Checking llama-server (Brain)..."

    if [ -x "$LLAMA_SERVER_BIN" ] && [ "$UPDATE_LLAMA" != 1 ]; then
        echo "✅ llama-server already built: $LLAMA_SERVER_BIN"
        echo "   $("$LLAMA_SERVER_BIN" --version 2>&1 | grep -m1 -i version)"
        echo "   (--update-llama baut neu, --llama-ref REF wählt einen anderen Stand)"
        return 0
    fi

    echo "🆕 Building llama-server from llama.cpp @ ${LLAMA_CPP_REF} (CPU, ohne BLAS, ~10–30 min)..."

    if [ ! -d "$LLAMA_CPP_DIR/.git" ]; then
        if [ -e "$LLAMA_CPP_DIR" ] && [ -n "$(ls -A "$LLAMA_CPP_DIR" 2>/dev/null)" ]; then
            echo "⚠️ $LLAMA_CPP_DIR existiert, ist aber kein git-Repo – bitte prüfen. Übersprungen."
            return 1
        fi
        git init -q "$LLAMA_CPP_DIR"
        git -C "$LLAMA_CPP_DIR" remote add origin https://github.com/ggml-org/llama.cpp.git
    fi

    # Nur den gewünschten Stand holen (flach), dann darauf wechseln
    if ! git -C "$LLAMA_CPP_DIR" fetch --depth 1 origin "$LLAMA_CPP_REF"; then
        echo "⚠️ git fetch von ${LLAMA_CPP_REF} fehlgeschlagen. Übersprungen."
        return 1
    fi
    git -C "$LLAMA_CPP_DIR" checkout -q --detach FETCH_HEAD
    echo "   -> llama.cpp $(git -C "$LLAMA_CPP_DIR" rev-parse --short HEAD)"

    # Wie am 08.11.2026 gemessen: Release, ohne BLAS
    if cmake -S "$LLAMA_CPP_DIR" -B "$LLAMA_CPP_DIR/build-noblas" \
             -DCMAKE_BUILD_TYPE=Release -DGGML_BLAS=OFF \
       && cmake --build "$LLAMA_CPP_DIR/build-noblas" -j4 --target llama-server; then
        echo "✅ llama-server built: $LLAMA_SERVER_BIN"
        "$LLAMA_SERVER_BIN" --version 2>&1 | grep -m1 -i version
    else
        echo "⚠️ llama-server Build fehlgeschlagen – Log oben prüfen."
        return 1
    fi
}

# =============================================================================
# [V2.0] Modelle herunterladen
# =============================================================================

# download_model <Dateiname> <Mindestgröße MB> <URL> [weitere URLs als Ersatz]
# Lädt nach <Datei>.part (fortsetzbar), prüft die Größe und benennt erst dann um.
download_model() {
    local file=$1 min_mb=$2
    shift 2
    local target="$MODELS_DIR/$file"
    local part="$target.part"

    if [ -f "$target" ]; then
        local mb=$(( $(stat -c %s "$target") / 1024 / 1024 ))
        if [ "$mb" -ge "$min_mb" ]; then
            echo "✅ ${file} already exists (${mb} MB). Skipping download."
            return 0
        fi
        echo "⚠️ ${file} ist nur ${mb} MB groß (erwartet ≥ ${min_mb} MB) – lade neu."
        mv -f "$target" "$part"
    fi

    local url
    for url in "$@"; do
        echo "🆕 Downloading ${file}"
        echo "   Source: ${url}"
        echo "   (Download kann mit Ctrl+C unterbrochen und später fortgesetzt werden)"
        if command -v wget &>/dev/null; then
            wget -c --show-progress -q -O "$part" "$url"
        else
            curl -fL -C - --progress-bar -o "$part" "$url"
        fi
        if [ $? -eq 0 ] && [ -f "$part" ] && \
           [ $(( $(stat -c %s "$part") / 1024 / 1024 )) -ge "$min_mb" ]; then
            mv -f "$part" "$target"
            echo "✅ ${file} heruntergeladen ($(du -sh "$target" | cut -f1)), Quelle: ${url}"
            return 0
        fi
        echo "⚠️ Download von dieser Quelle fehlgeschlagen."
        # Fehlerseite (z. B. 404) nicht als Anfang eines Modells weiterverwenden
        [ -f "$part" ] && [ $(( $(stat -c %s "$part") / 1024 / 1024 )) -lt 1 ] && rm -f "$part"
    done

    echo "⚠️ ${file} konnte nicht geladen werden. Bitte manuell nach ${MODELS_DIR}/ kopieren."
    return 1
}

download_models() {
    echo ""
    echo "🧠 Checking AI models in ${MODELS_DIR}..."
    mkdir -p "$MODELS_DIR"

    local hf="https://huggingface.co"

    # Brain-LLM (Brain_Konzept.md, Abschnitt 17): Qwen3.5-4B Q4_K_M + Bild-Encoder mmproj Q8_0.
    # Die Dateinamen sind die, die brain/vision/run_pi_matrix.sh und llm_server.sh erwarten.
    # Quellen in Reihenfolge; die zweite nur als Ersatz, falls die erste fehlt.
    download_model "Qwen3.5-4B-Q4_K_M.gguf" 2000 \
        "$hf/ggml-org/Qwen3.5-4B-GGUF/resolve/main/Qwen3.5-4B-Q4_K_M.gguf" \
        "$hf/unsloth/Qwen3.5-4B-GGUF/resolve/main/Qwen3.5-4B-Q4_K_M.gguf"
    download_model "mmproj-Qwen3.5-4B-Q8_0.gguf" 250 \
        "$hf/ggml-org/Qwen3.5-4B-GGUF/resolve/main/mmproj-Qwen3.5-4B-Q8_0.gguf" \
        "$hf/prithivMLmods/Qwen3.5-4B-f32-GGUF/resolve/main/Qwen3.5-4B.mmproj-q8_0.gguf"

    # Alte Prototypen (exploration_manager_V4, mission_replanner_V1) und LlamaBrain
    if [ "$LEGACY_LLM" = 1 ]; then
        download_model "Qwen3-4B-Instruct-2507-Q4_K_M.gguf" 2000 \
            "$hf/unsloth/Qwen3-4B-Instruct-2507-GGUF/resolve/main/Qwen3-4B-Instruct-2507-Q4_K_M.gguf"
    else
        echo "ℹ️  Qwen3-4B-Instruct-2507 (alte Prototypen) nur mit --legacy-llm."
    fi
}

# =============================================================================
# 0. Besitz prüfen (braucht ggf. sudo, daher vorne)
# =============================================================================

fix_ownership

# =============================================================================
# 1. System-Pakete – zuerst, alles andere hängt davon ab
# =============================================================================

install_system_deps

# =============================================================================
# 2. Hailo – braucht ggf. Reboot, daher vor den venvs
# =============================================================================

install_hailo

# =============================================================================
# 3. Venvs anlegen
# =============================================================================

echo ""
echo "🔧 Checking and creating virtual environments..."

create_venv "slarc_base" false
create_venv "vision"        true
create_venv "ai"            true   # Hosts the custom llama-cpp-python build
create_venv "sensors"       false
create_venv "motion_control" false
create_venv "slam"          false

# =============================================================================
# 4. Pakete installieren
# =============================================================================

echo ""
echo "📦 Installing standard packages..."

install_packages "slarc_base" posix_ipc
install_packages "vision" opencv-python --no-deps pyzmq moderngl glcontext posix_ipc

# Custom Build zuerst, dann restliche ai-Pakete
install_llama_cpp_custom
# [V2.0] pillow (Bildfragen, bench_pi), pytest (brain/tests); ollama entfällt (überholt)
install_packages "ai" opencv-python onnxruntime posix_ipc numpy tabulate py_trees matplotlib torchvision pillow pytest

install_packages "sensors" smbus2 numpy==1.24 matplotlib icm20948 scipy==1.11.4 posix_ipc
install_packages "motion_control" RPi.GPIO posix_ipc matplotlib scipy
install_packages "slam" opencv-python matplotlib numpy==1.24 posix_ipc

# =============================================================================
# 5. llama-server für das Brain
# =============================================================================

install_llama_server

# =============================================================================
# 6. Shell-Aliases für venv-Shortcuts
# =============================================================================

install_bashrc_aliases() {
    local bashrc="${USER_HOME}/.bashrc"
    local marker="# SLARC venv shortcuts"

    # Idempotent: nur einfügen wenn der Marker noch nicht vorhanden ist
    if grep -q "$marker" "$bashrc" 2>/dev/null; then
        echo "✅ SLARC venv aliases already in ${bashrc}."
    else
        echo ""
        echo "🔧 Adding SLARC venv shortcuts to ${bashrc}..."
        cat >> "$bashrc" << EOF

${marker}
alias venv-ai='source ${VENV_DIR}/ai/bin/activate'
alias venv-vision='source ${VENV_DIR}/vision/bin/activate'
alias venv-sensors='source ${VENV_DIR}/sensors/bin/activate'
alias venv-motion='source ${VENV_DIR}/motion_control/bin/activate'
alias venv-slam='source ${VENV_DIR}/slam/bin/activate'
alias venv-base='source ${VENV_DIR}/slarc_base/bin/activate'
alias venv-off='deactivate'
EOF
        echo "✅ Aliases added. Active after next login or: source ~/.bashrc"
    fi

    # [V2.0] eigener Marker, damit bestehende Installationen den Alias nachträglich bekommen
    local marker_llm="# SLARC llm-server shortcut"
    if grep -q "$marker_llm" "$bashrc" 2>/dev/null; then
        echo "✅ llm-server alias already in ${bashrc}."
    else
        cat >> "$bashrc" << EOF

${marker_llm}
alias llm-server='bash ${SCRIPT_DIR}/llm_server.sh'
EOF
        echo "✅ Alias llm-server added (startet den Brain-Server, siehe utilities/llm_server.sh)."
    fi
}

install_bashrc_aliases

# =============================================================================
# 7. Modelle herunterladen
# =============================================================================

if [ "$NO_MODELS" = 1 ]; then
    echo ""
    echo "ℹ️  --no-models: Modell-Downloads übersprungen."
else
    download_models
fi

# =============================================================================
# Fertig
# =============================================================================

echo ""
echo "🎉 All venvs checked, created if needed, and configured successfully."
echo ""
echo "ℹ️  Hinweise:"
echo "   - Falls Hailo neu installiert wurde: sudo reboot"
echo "   - Hailo-Verify nach Reboot: hailortcli fw-control identify"
echo "   - Brain-Server starten:      llm-server   (bzw. bash ${SCRIPT_DIR}/llm_server.sh)"
echo "   - llama-server:             $LLAMA_SERVER_BIN"
echo "   - llama-cpp-python Repo:    $LLAMA_REPO_DIR"
echo "   - Modelle:                  $MODELS_DIR"
echo "   - venvs:                    $VENV_DIR"
