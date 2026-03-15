#!/bin/bash
# =============================================================================
# rpi_config_backup.sh
# Sichert alle relevanten Raspberry Pi Konfigurationsdateien
# (config.txt, cmdline.txt, udev, modprobe, raspi-config-Werte, ...)
# Verwendung: sudo bash rpi_config_backup.sh [ZIELVERZEICHNIS]
# =============================================================================

set -euo pipefail

# --- Farben ---
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'

info()    { echo -e "${CYAN}[INFO]${NC}  $*"; }
ok()      { echo -e "${GREEN}[ OK ]${NC}  $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERR ]${NC}  $*"; }

# --- Root-Check ---
if [[ $EUID -ne 0 ]]; then
    error "Bitte als root ausführen: sudo bash $0"
    exit 1
fi

# --- Zielverzeichnis ---
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BASE_DIR="${1:-/home/${SUDO_USER:-pi}/rpi_backups}"
BACKUP_DIR="${BASE_DIR}/backup_${TIMESTAMP}"

mkdir -p "$BACKUP_DIR"
info "Backup-Verzeichnis: $BACKUP_DIR"

# =============================================================================
# Hilfsfunktion: Datei sichern (mit Pfadstruktur)
# =============================================================================
backup_file() {
    local src="$1"
    local label="${2:-$1}"
    if [[ -f "$src" ]]; then
        local dest="${BACKUP_DIR}${src}"
        mkdir -p "$(dirname "$dest")"
        cp -a "$src" "$dest"
        ok "$label"
    else
        warn "Nicht gefunden: $label"
    fi
}

backup_dir() {
    local src="$1"
    local label="${2:-$1}"
    if [[ -d "$src" ]]; then
        local dest="${BACKUP_DIR}${src}"
        mkdir -p "$(dirname "$dest")"
        cp -a "$src" "$dest"
        ok "$label (Verzeichnis)"
    else
        warn "Nicht gefunden: $label"
    fi
}

# =============================================================================
# 1. Boot-Konfiguration
# =============================================================================
echo ""
info "=== Boot-Konfiguration ==="

# Bookworm+ nutzt /boot/firmware/, ältere /boot/
if [[ -f /boot/firmware/config.txt ]]; then
    BOOT_DIR="/boot/firmware"
else
    BOOT_DIR="/boot"
    warn "Kein /boot/firmware gefunden – verwende /boot (älteres Layout)"
fi

backup_file "${BOOT_DIR}/config.txt"       "config.txt (PCIe, PWM, Overlays, ...)"
backup_file "${BOOT_DIR}/cmdline.txt"      "cmdline.txt (Kernel-Parameter)"
backup_file "${BOOT_DIR}/usercfg.txt"      "usercfg.txt (User-Overrides)"
backup_file "${BOOT_DIR}/syscfg.txt"       "syscfg.txt (System-Overrides)"

# =============================================================================
# 2. System-Konfiguration
# =============================================================================
echo ""
info "=== System-Konfiguration ==="

backup_file "/etc/rc.local"                "rc.local (Startup-Skripte)"
backup_file "/etc/modules"                 "modules (Autoload-Kernel-Module)"
backup_file "/etc/hostname"                "hostname"
backup_file "/etc/hosts"                   "hosts"
backup_file "/etc/fstab"                   "fstab (Mount-Punkte)"
backup_file "/etc/dhcpcd.conf"             "dhcpcd.conf (Netzwerk)"
backup_file "/etc/wpa_supplicant/wpa_supplicant.conf" "wpa_supplicant.conf (WLAN)"

backup_dir  "/etc/modprobe.d"              "modprobe.d (Kernel-Modul-Optionen)"
backup_dir  "/etc/udev/rules.d"            "udev/rules.d (Device-Regeln)"
backup_dir  "/etc/systemd/system"          "systemd/system (Eigene Services)"

# =============================================================================
# 3. raspi-config relevante Werte auslesen
# =============================================================================
echo ""
info "=== raspi-config Werte ==="

RASPI_DUMP="${BACKUP_DIR}/raspi-config-dump.txt"
{
    echo "# raspi-config Konfigurationsdump"
    echo "# Erstellt am: $(date)"
    echo "# Hostname: $(hostname)"
    echo "# Kernel:   $(uname -r)"
    echo ""

    # config.txt vollständig ausgeben (als Referenz, ohne Kommentare)
    echo "### Aktive Zeilen aus ${BOOT_DIR}/config.txt (ohne Kommentare) ###"
    grep -v '^\s*#' "${BOOT_DIR}/config.txt" | grep -v '^\s*$' || true
    echo ""

    # Spezifische Settings prüfen
    echo "### Gezielte Einstellungen ###"

    # PCIe
    if grep -q "pciex1_gen" "${BOOT_DIR}/config.txt" 2>/dev/null; then
        echo "PCIe-Speed:    $(grep 'pciex1_gen' "${BOOT_DIR}/config.txt")"
    else
        echo "PCIe-Speed:    (nicht gesetzt – Standard Gen2)"
    fi

    # PWM
    if grep -q "pwm" "${BOOT_DIR}/config.txt" 2>/dev/null; then
        echo "PWM-Overlays:"
        grep -i "pwm" "${BOOT_DIR}/config.txt"
    else
        echo "PWM-Overlays:  (keine gefunden)"
    fi

    # I2C / SPI / Serial / Camera / GPU
    for param in i2c_arm spi serial_console camera_auto_detect gpu_mem dtoverlay dtparam; do
        hits=$(grep -i "^${param}" "${BOOT_DIR}/config.txt" 2>/dev/null || true)
        if [[ -n "$hits" ]]; then
            echo "${param}: $hits"
        fi
    done

    echo ""
    echo "### raspi-config nonint get-Werte ###"
    if command -v raspi-config &>/dev/null; then
        for setting in \
            "do_hostname" \
            "get_boot_cli" \
            "get_autologin" \
            "get_ssh" \
            "get_vnc" \
            "get_spi" \
            "get_i2c" \
            "get_serial" \
            "get_serial_hw" \
            "get_camera" \
            "get_onewire" \
            "get_rgpio" \
            "get_pi_type"
        do
            val=$(raspi-config nonint "${setting}" 2>/dev/null || echo "(nicht unterstützt)")
            echo "  ${setting}: ${val}"
        done
    else
        warn "raspi-config nicht gefunden"
    fi

} > "$RASPI_DUMP"
ok "raspi-config-dump.txt"

# =============================================================================
# 4. Hailo-spezifische Infos (falls vorhanden)
# =============================================================================
echo ""
info "=== Hailo-spezifische Konfiguration ==="

HAILO_DUMP="${BACKUP_DIR}/hailo-info.txt"
{
    echo "# Hailo-Konfigurationsdump"
    echo "# Erstellt am: $(date)"
    echo ""

    if command -v hailortcli &>/dev/null; then
        echo "### hailortcli fw-control identify ###"
        hailortcli fw-control identify 2>&1 || echo "(Fehler – Hailo nicht verbunden?)"
    else
        echo "hailortcli nicht gefunden (Hailo evtl. nicht installiert)"
    fi

    echo ""
    echo "### Hailo PCIe-Gerät (lspci) ###"
    lspci 2>/dev/null | grep -i hailo || echo "(kein Hailo PCIe-Gerät gefunden)"

    echo ""
    echo "### Hailo-Kernel-Module ###"
    lsmod 2>/dev/null | grep -i hailo || echo "(kein Hailo-Modul geladen)"

    echo ""
    echo "### /etc/hailo* ###"
    ls -la /etc/hailo* 2>/dev/null || echo "(keine Hailo-Configs in /etc)"

} > "$HAILO_DUMP"
ok "hailo-info.txt"

# =============================================================================
# 5. System-Info als Referenz
# =============================================================================
echo ""
info "=== System-Info ==="

SYSINFO="${BACKUP_DIR}/system-info.txt"
{
    echo "# System-Info-Dump"
    echo "# Erstellt am: $(date)"
    echo ""
    echo "Hostname:     $(hostname)"
    echo "Kernel:       $(uname -r)"
    echo "OS:           $(cat /etc/os-release | grep PRETTY_NAME | cut -d= -f2 | tr -d '\"')"
    echo "Architektur:  $(uname -m)"
    echo ""
    echo "### vcgencmd-Werte ###"
    if command -v vcgencmd &>/dev/null; then
        vcgencmd get_config int 2>/dev/null || true
        vcgencmd version 2>/dev/null || true
    else
        echo "(vcgencmd nicht verfügbar)"
    fi
    echo ""
    echo "### Installierte Hailo-Pakete ###"
    dpkg -l | grep -i hailo 2>/dev/null || echo "(keine Hailo-Pakete installiert)"
    echo ""
    echo "### Kernel-Module (geladen) ###"
    lsmod
} > "$SYSINFO"
ok "system-info.txt"

# =============================================================================
# 6. Archiv erstellen
# =============================================================================
echo ""
info "=== Archiv erstellen ==="

ARCHIVE="${BASE_DIR}/rpi_backup_${TIMESTAMP}.tar.gz"
tar -czf "$ARCHIVE" -C "$BASE_DIR" "backup_${TIMESTAMP}"
ok "Archiv: $ARCHIVE"

# Optional: Backup-Verzeichnis nach Archivierung entfernen
# rm -rf "$BACKUP_DIR"

# =============================================================================
# Zusammenfassung
# =============================================================================
echo ""
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  Backup abgeschlossen!${NC}"
echo -e "${GREEN}============================================${NC}"
echo -e "  Verzeichnis : ${CYAN}${BACKUP_DIR}${NC}"
echo -e "  Archiv      : ${CYAN}${ARCHIVE}${NC}"
echo -e "  Größe       : $(du -sh "$ARCHIVE" | cut -f1)"
echo ""
info "Inhalt des Backups:"
find "$BACKUP_DIR" -type f | sed "s|${BACKUP_DIR}||" | sort
echo ""
