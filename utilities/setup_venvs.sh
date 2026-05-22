#!/bin/bash

# =============================================================================
# setup_venvs.sh
# Richtet alle virtuellen Environments für das SLARC-Projekt ein.
# Installiert außerdem den Hailo-Stack (hailo-all) falls noch nicht vorhanden.
#
# Verwendung: bash setup_venvs.sh
# (sudo-Rechte werden nur für den Hailo-apt-Block benötigt und intern angefragt)
# =============================================================================

# Aktuell angemeldeten User ermitteln – funktioniert auch bei sudo-Aufruf
ACTUAL_USER="${SUDO_USER:-$USER}"
USER_HOME=$(getent passwd "$ACTUAL_USER" | cut -d: -f6)

echo "👤 Running setup for user: $ACTUAL_USER (home: $USER_HOME)"

# Base directory for venvs
VENV_DIR="$USER_HOME/projects/slarc/venvs"

# Festes Verzeichnis für das llama-cpp-python Repository
LLAMA_REPO_DIR="$USER_HOME/llama-cpp-python"

# Create base directory
mkdir -p "$VENV_DIR"

echo "🔧 Checking and creating virtual environments..."

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
# System-Abhängigkeiten (apt)
# =============================================================================

install_system_deps() {
    echo ""
    echo "📦 Checking system dependencies..."

    local pkgs=()

    # Für venv-Erstellung
    dpkg -s python3-venv    &>/dev/null || pkgs+=(python3-venv)
    dpkg -s python3-pip     &>/dev/null || pkgs+=(python3-pip)

    # Für llama-cpp-python Build
    dpkg -s git             &>/dev/null || pkgs+=(git)
    dpkg -s build-essential &>/dev/null || pkgs+=(build-essential)
    dpkg -s cmake           &>/dev/null || pkgs+=(cmake)
    dpkg -s ninja-build     &>/dev/null || pkgs+=(ninja-build)
    dpkg -s libopenblas-dev &>/dev/null || pkgs+=(libopenblas-dev)

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
# llama-cpp-python (Custom Build)
# =============================================================================

install_llama_cpp_custom() {
    local venv_name="ai"
    local path="$VENV_DIR/$venv_name"

    if [ ! -d "$path" ]; then
        echo "⚠️ Venv '$venv_name' not found. Skipping custom llama-cpp-python build."
        return 1
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
        cd "$LLAMA_REPO_DIR"
        git fetch origin
        git reset --hard origin/main
        git submodule update --init --recursive
    else
        echo "   -> Cloning repository to $LLAMA_REPO_DIR ..."
        git clone --recursive https://github.com/abetlen/llama-cpp-python.git "$LLAMA_REPO_DIR"
        cd "$LLAMA_REPO_DIR"
    fi

    # 4. Alte Build-Artefakte entfernen
    echo "   -> Cleaning cached build files..."
    rm -rf _skbuild dist build

    # 5. Bestehende Installation im venv entfernen
    echo "   -> Removing any previous llama-cpp-python installation from venv..."
    pip uninstall -y llama-cpp-python

    # 6. Build und Installation
    echo "   -> Building and installing with OpenBLAS acceleration..."
    CMAKE_ARGS="-DGGML_BLAS=ON -DGGML_BLAS_VENDOR=OpenBLAS" pip install . --no-cache-dir --verbose

    # 7. Explizit zurück – kein relatives cd ..
    cd "$VENV_DIR"
    deactivate

    echo "✅ Custom llama-cpp-python build complete for '$venv_name'."
}

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
install_packages "ai" opencv-python onnxruntime posix_ipc numpy tabulate ollama py_trees matplotlib

install_packages "sensors" smbus2 numpy==1.24 matplotlib icm20948 scipy==1.11.4 posix_ipc
install_packages "motion_control" RPi.GPIO posix_ipc matplotlib scipy
install_packages "slam" opencv-python matplotlib numpy==1.24 posix_ipc

# =============================================================================
# 5. Shell-Aliases für venv-Shortcuts
# =============================================================================

install_bashrc_aliases() {
    local bashrc="${USER_HOME}/.bashrc"
    local marker="# SLARC venv shortcuts"

    # Idempotent: nur einfügen wenn der Marker noch nicht vorhanden ist
    if grep -q "$marker" "$bashrc" 2>/dev/null; then
        echo "✅ SLARC venv aliases already in ${bashrc}."
        return 0
    fi

    echo ""
    echo "🔧 Adding SLARC venv shortcuts to ${bashrc}..."

    # Als eigentlicher User schreiben (nicht als root)
    sudo -u "$ACTUAL_USER" tee -a "$bashrc" > /dev/null << EOF

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
}

install_bashrc_aliases

# =============================================================================
# 6. Modelle herunterladen
# =============================================================================

download_models() {
    local models_dir="${USER_HOME}/.models"
    local model_file="Qwen3-4B-Instruct-2507-Q4_K_M.gguf"
    local model_path="${models_dir}/${model_file}"
    local model_url="https://huggingface.co/unsloth/Qwen3-4B-Instruct-2507-GGUF/resolve/main/${model_file}"

    echo ""
    echo "🧠 Checking AI models..."

    # Zielverzeichnis anlegen (als User, nicht root)
    sudo -u "$ACTUAL_USER" mkdir -p "$models_dir"

    if [ -f "$model_path" ]; then
        local size
        size=$(du -sh "$model_path" | cut -f1)
        echo "✅ ${model_file} already exists (${size}). Skipping download."
        return 0
    fi

    echo "🆕 Downloading ${model_file} (~2.3 GB)..."
    echo "   Source: ${model_url}"
    echo "   Target: ${model_path}"
    echo "   (Download kann mit Ctrl+C unterbrochen und später fortgesetzt werden)"

    # wget -c = Resume bei Unterbrechung
    # Als User downloaden damit die Datei nicht root gehört
    if command -v wget &>/dev/null; then
        sudo -u "$ACTUAL_USER" wget -c --show-progress \
            -O "${model_path}" \
            "${model_url}"
    elif command -v curl &>/dev/null; then
        sudo -u "$ACTUAL_USER" curl -L -C - \
            --progress-bar \
            -o "${model_path}" \
            "${model_url}"
    else
        echo "⚠️ Weder wget noch curl gefunden – manuell herunterladen:"
        echo "   wget -c -O ${model_path} ${model_url}"
        return 1
    fi

    if [ -f "$model_path" ]; then
        local size
        size=$(du -sh "$model_path" | cut -f1)
        echo "✅ ${model_file} heruntergeladen (${size})."
    else
        echo "⚠️ Download fehlgeschlagen – bitte manuell herunterladen:"
        echo "   wget -c -O ${model_path} ${model_url}"
    fi
}

download_models

# =============================================================================
# Fertig
# =============================================================================

echo ""
echo "🎉 All venvs checked, created if needed, and configured successfully."
echo ""
echo "ℹ️  Hinweise:"
echo "   - Falls Hailo neu installiert wurde: sudo reboot"
echo "   - Hailo-Verify nach Reboot: hailortcli fw-control identify"
echo "   - llama-cpp-python Repo:    $LLAMA_REPO_DIR"
echo "   - venvs:                    $VENV_DIR"
