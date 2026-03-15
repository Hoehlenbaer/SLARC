#!/bin/bash
# =============================================================================
# rpi_config_restore.sh
# Spielt ein Bookworm-Backup auf Raspberry Pi OS Trixie zurück.
# WICHTIG: Nicht blind alles überschreiben – dieses Script ist selektiv
# und validiert vor dem Schreiben.
#
# Verwendung: sudo bash rpi_config_restore.sh <backup_YYYYMMDD_HHMMSS.tar.gz>
#         oder sudo bash rpi_config_restore.sh <backup_YYYYMMDD_HHMMSS/>
# =============================================================================

set -euo pipefail

# --- Farben ---
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BLUE='\033[0;34m'; NC='\033[0m'

info()    { echo -e "${CYAN}[INFO]${NC}  $*"; }
ok()      { echo -e "${GREEN}[ OK ]${NC}  $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERR ]${NC}  $*"; }
section() { echo -e "\n${BLUE}=== $* ===${NC}"; }
ask()     { echo -e "${YELLOW}[?]${NC}    $*"; }

# =============================================================================
# Hilfsfunktionen
# =============================================================================

# Sicherheitskopie einer Datei anlegen bevor sie überschrieben wird
safe_backup() {
    local file="$1"
    if [[ -f "$file" ]]; then
        cp -a "$file" "${file}.pre-restore.bak"
    fi
}

# Datei aus Backup zurückspielen (mit Pre-Backup und optionalem Diff)
restore_file() {
    local src="$1"       # Pfad im entpackten Backup (absolut)
    local dest="$2"      # Zieldpfad auf dem System
    local label="${3:-$dest}"
    local mode="${4:-644}"

    if [[ ! -f "$src" ]]; then
        warn "Im Backup nicht vorhanden: $label"
        return 0
    fi

    # Diff anzeigen wenn Zieldatei existiert
    if [[ -f "$dest" ]]; then
        if diff -q "$src" "$dest" &>/dev/null; then
            ok "$label (identisch, kein Schreibvorgang)"
            return 0
        fi
        if [[ "$SHOW_DIFF" == "1" ]]; then
            echo -e "${YELLOW}--- Diff für $label ---${NC}"
            diff --color=always "$dest" "$src" || true
            echo ""
        fi
        safe_backup "$dest"
    fi

    mkdir -p "$(dirname "$dest")"
    cp -a "$src" "$dest"
    chmod "$mode" "$dest"
    ok "$label"
}

# Verzeichnis aus Backup zurückspielen
restore_dir() {
    local src="$1"
    local dest="$2"
    local label="${3:-$dest}"

    if [[ ! -d "$src" ]]; then
        warn "Im Backup nicht vorhanden: $label"
        return 0
    fi

    # Einzelne Dateien im Verzeichnis sichern
    if [[ -d "$dest" ]]; then
        find "$dest" -maxdepth 1 -type f | while read -r f; do
            safe_backup "$f"
        done
    fi

    mkdir -p "$dest"
    cp -a "$src"/. "$dest/"
    ok "$label"
}

# Einzelne Einträge selektiv in config.txt mergen
merge_config_entry() {
    local key="$1"
    local value="$2"
    local target="$3"

    if grep -qE "^\s*${key}=${value}" "$target" 2>/dev/null; then
        ok "  config.txt: ${key}=${value} (bereits gesetzt)"
    elif grep -qE "^\s*${key}=" "$target" 2>/dev/null; then
        warn "  config.txt: ${key} hat anderen Wert – manuell prüfen!"
        echo "  Backup:  ${key}=${value}"
        echo "  Aktuell: $(grep -E "^\s*${key}=" "$target")"
    else
        echo "${key}=${value}" >> "$target"
        ok "  config.txt: ${key}=${value} hinzugefügt"
    fi
}

# =============================================================================
# Argumente & Vorbedingungen
# =============================================================================

if [[ $EUID -ne 0 ]]; then
    error "Bitte als root ausführen: sudo bash $0 <backup>"
    exit 1
fi

if [[ $# -lt 1 ]]; then
    error "Kein Backup angegeben."
    echo "Verwendung: sudo bash $0 <backup.tar.gz | backup-verzeichnis/>"
    exit 1
fi

INPUT="$1"
TMPDIR_CREATED=0

# Archiv entpacken falls nötig
if [[ -f "$INPUT" && "$INPUT" == *.tar.gz ]]; then
    WORK_DIR=$(mktemp -d /tmp/rpi_restore_XXXXXX)
    TMPDIR_CREATED=1
    info "Entpacke Archiv nach $WORK_DIR ..."
    tar -xzf "$INPUT" -C "$WORK_DIR"
    # Das Backup liegt in einem Unterordner backup_TIMESTAMP/
    BACKUP_DIR=$(find "$WORK_DIR" -maxdepth 1 -mindepth 1 -type d | head -n1)
elif [[ -d "$INPUT" ]]; then
    BACKUP_DIR="${INPUT%/}"
else
    error "Backup nicht gefunden oder ungültiges Format: $INPUT"
    exit 1
fi

info "Backup-Quelle: $BACKUP_DIR"

# Boot-Dir ermitteln (Trixie: /boot/firmware)
if [[ -d /boot/firmware ]]; then
    BOOT_DIR="/boot/firmware"
else
    BOOT_DIR="/boot"
    warn "Kein /boot/firmware gefunden – verwende /boot"
fi

BACKUP_BOOT="${BACKUP_DIR}${BOOT_DIR}"

# =============================================================================
# Interaktiver Modus
# =============================================================================

echo ""
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  RPi Config Restore – Bookworm → Trixie${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""
warn "Dieses Script spielt selektiv Konfiguration zurück."
warn "Systemdateien werden VOR dem Überschreiben als *.pre-restore.bak gesichert."
echo ""

# Diff-Anzeige?
ask "Diffs vor dem Überschreiben anzeigen? [j/N]"
read -r SHOW_DIFF_INPUT
SHOW_DIFF=$([[ "$SHOW_DIFF_INPUT" =~ ^[jJyY]$ ]] && echo "1" || echo "0")

# =============================================================================
# 1. config.txt – SELEKTIV (nicht blind überschreiben!)
# =============================================================================
section "Boot-Konfiguration (config.txt) – selektiver Merge"

TARGET_CONFIG="${BOOT_DIR}/config.txt"
SRC_CONFIG="${BACKUP_BOOT}/config.txt"

if [[ ! -f "$SRC_CONFIG" ]]; then
    warn "config.txt im Backup nicht gefunden – überspringe"
else
    info "Lese Backup-config.txt und merge relevante Einträge..."
    safe_backup "$TARGET_CONFIG"

    # PCIe Gen3
    if grep -qE "pciex1_gen\s*=\s*3" "$SRC_CONFIG" 2>/dev/null; then
        merge_config_entry "dtparam=pciex1_gen" "3" "$TARGET_CONFIG"
        # Alternativschreibweise
        grep -qE "pciex1_gen=3" "$SRC_CONFIG" && \
            merge_config_entry "pciex1_gen" "3" "$TARGET_CONFIG" 2>/dev/null || true
    fi

    # Alle dtoverlay-Einträge (PWM, UART, SPI, I2C, etc.)
    while IFS= read -r line; do
        line_clean=$(echo "$line" | sed 's/\s*#.*//' | xargs)
        [[ -z "$line_clean" ]] && continue
        if ! grep -qF "$line_clean" "$TARGET_CONFIG" 2>/dev/null; then
            echo "$line_clean" >> "$TARGET_CONFIG"
            ok "  config.txt: '$line_clean' hinzugefügt"
        else
            ok "  config.txt: '$line_clean' (bereits vorhanden)"
        fi
    done < <(grep -E "^\s*(dtoverlay|dtparam|gpu_mem|arm_freq|over_voltage|enable_uart)" \
                 "$SRC_CONFIG" 2>/dev/null | grep -v '^\s*#' || true)

    # gpu_mem, enable_uart, arm_boost einzeln
    for key in gpu_mem enable_uart arm_boost; do
        val=$(grep -E "^\s*${key}=" "$SRC_CONFIG" 2>/dev/null | tail -1 | cut -d= -f2 | xargs || true)
        [[ -n "$val" ]] && merge_config_entry "$key" "$val" "$TARGET_CONFIG"
    done

    echo ""
    info "Finaler Zustand der config.txt (aktive Zeilen):"
    grep -v '^\s*#' "$TARGET_CONFIG" | grep -v '^\s*$' | sed 's/^/    /'
fi

# cmdline.txt – NUR als Referenz, nie blind überschreiben
section "cmdline.txt (nur Diff, kein Auto-Restore)"

SRC_CMDLINE="${BACKUP_BOOT}/cmdline.txt"
TARGET_CMDLINE="${BOOT_DIR}/cmdline.txt"

if [[ -f "$SRC_CMDLINE" ]]; then
    if diff -q "$SRC_CMDLINE" "$TARGET_CMDLINE" &>/dev/null; then
        ok "cmdline.txt identisch – kein Handlungsbedarf"
    else
        warn "cmdline.txt weicht ab. Bitte manuell prüfen!"
        echo -e "${YELLOW}--- Backup ---${NC}"
        cat "$SRC_CMDLINE"
        echo -e "${YELLOW}--- Aktuell ---${NC}"
        cat "$TARGET_CMDLINE"
        echo ""
        ask "cmdline.txt trotzdem überschreiben? [j/N]"
        read -r OVERWRITE_CMDLINE
        if [[ "$OVERWRITE_CMDLINE" =~ ^[jJyY]$ ]]; then
            restore_file "$SRC_CMDLINE" "$TARGET_CMDLINE" "cmdline.txt"
        else
            info "cmdline.txt übersprungen – bitte manuell anpassen"
        fi
    fi
fi

# =============================================================================
# 2. System-Konfiguration
# =============================================================================
section "System-Konfiguration"

restore_file "${BACKUP_DIR}/etc/rc.local"   "/etc/rc.local"   "rc.local"   "755"
restore_file "${BACKUP_DIR}/etc/modules"    "/etc/modules"    "modules (Autoload-Kernel-Module)"
restore_file "${BACKUP_DIR}/etc/fstab"      "/etc/fstab"      "fstab"

# Netzwerk – nur wenn explizit gewünscht (MAC-Adressen etc. können abweichen)
echo ""
ask "Netzwerk-Config zurückspielen (dhcpcd.conf, wpa_supplicant)? [j/N]"
read -r RESTORE_NET
if [[ "$RESTORE_NET" =~ ^[jJyY]$ ]]; then
    restore_file "${BACKUP_DIR}/etc/dhcpcd.conf" "/etc/dhcpcd.conf" "dhcpcd.conf"
    restore_file "${BACKUP_DIR}/etc/wpa_supplicant/wpa_supplicant.conf" \
                 "/etc/wpa_supplicant/wpa_supplicant.conf" "wpa_supplicant.conf" "600"
else
    info "Netzwerk-Config übersprungen"
fi

# Hostname
SRC_HOSTNAME="${BACKUP_DIR}/etc/hostname"
if [[ -f "$SRC_HOSTNAME" ]]; then
    OLD_HOST=$(cat "$SRC_HOSTNAME" | xargs)
    CUR_HOST=$(hostname)
    if [[ "$OLD_HOST" != "$CUR_HOST" ]]; then
        ask "Hostname von '$CUR_HOST' auf '$OLD_HOST' ändern? [j/N]"
        read -r RESTORE_HOST
        if [[ "$RESTORE_HOST" =~ ^[jJyY]$ ]]; then
            restore_file "$SRC_HOSTNAME" "/etc/hostname" "hostname"
            sed -i "s/$CUR_HOST/$OLD_HOST/g" /etc/hosts
            ok "Hostname und /etc/hosts aktualisiert"
        fi
    else
        ok "Hostname identisch: $CUR_HOST"
    fi
fi

# =============================================================================
# 3. Kernel-Module & udev
# =============================================================================
section "Kernel-Module & udev-Regeln"

restore_dir "${BACKUP_DIR}/etc/modprobe.d"   "/etc/modprobe.d"   "modprobe.d"
restore_dir "${BACKUP_DIR}/etc/udev/rules.d" "/etc/udev/rules.d" "udev/rules.d"

# =============================================================================
# 4. Systemd-Units
# =============================================================================
section "Systemd-Units"

SRC_SYSTEMD="${BACKUP_DIR}/etc/systemd/system"
if [[ -d "$SRC_SYSTEMD" ]]; then
    UNITS=$(find "$SRC_SYSTEMD" -maxdepth 1 -name "*.service" -o -name "*.timer" \
            -o -name "*.socket" 2>/dev/null | sort)
    if [[ -z "$UNITS" ]]; then
        info "Keine eigenen systemd-Units im Backup"
    else
        echo ""
        info "Folgende Units wurden im Backup gefunden:"
        echo "$UNITS" | sed 's/.*\//    /'
        ask "Systemd-Units zurückspielen? [j/N]"
        read -r RESTORE_UNITS
        if [[ "$RESTORE_UNITS" =~ ^[jJyY]$ ]]; then
            restore_dir "$SRC_SYSTEMD" "/etc/systemd/system" "systemd/system"
            systemctl daemon-reload
            ok "systemctl daemon-reload ausgeführt"

            ask "Sollen die Units auch aktiviert (enable) werden? [j/N]"
            read -r ENABLE_UNITS
            if [[ "$ENABLE_UNITS" =~ ^[jJyY]$ ]]; then
                echo "$UNITS" | xargs -I{} basename {} | while read -r unit; do
                    systemctl enable "$unit" 2>/dev/null && ok "  enabled: $unit" \
                        || warn "  enable fehlgeschlagen: $unit"
                done
            fi
        fi
    fi
else
    info "Keine systemd-Units im Backup"
fi

# =============================================================================
# 5. Hailo-spezifische Konfiguration
# =============================================================================
section "Hailo-Konfiguration"

# hailo in /etc
if ls "${BACKUP_DIR}/etc/hailo"* &>/dev/null 2>&1; then
    for f in "${BACKUP_DIR}/etc/hailo"*; do
        dest="/etc/$(basename "$f")"
        restore_file "$f" "$dest" "Hailo-Config: $(basename "$f")"
    done
else
    info "Keine Hailo-Configs in /etc im Backup gefunden"
fi

# Prüfe ob Hailo-Pakete installiert sind
info "Installierte Hailo-Pakete (aktuell):"
dpkg -l | grep -i hailo | awk '{print "  " $2 "\t" $3}' || echo "  (keine)"

# Aus Backup-Info empfohlene Versionen anzeigen
HAILO_INFO="${BACKUP_DIR}/hailo-info.txt"
if [[ -f "$HAILO_INFO" ]]; then
    info "Hailo-Pakete aus Backup (Bookworm):"
    grep -A5 "Installierte Hailo-Pakete" "$HAILO_INFO" 2>/dev/null | sed 's/^/  /' || true
fi

# =============================================================================
# 6. PCIe Gen3 über raspi-config setzen (falls noch nicht in config.txt)
# =============================================================================
section "PCIe Gen3 prüfen"

if grep -qE "pciex1_gen=3|dtparam=pciex1_gen=3" "${BOOT_DIR}/config.txt" 2>/dev/null; then
    ok "PCIe Gen3 ist in config.txt gesetzt"
else
    warn "PCIe Gen3 ist NICHT gesetzt"
    ask "PCIe Gen3 über raspi-config aktivieren? [j/N]"
    read -r SET_PCIE
    if [[ "$SET_PCIE" =~ ^[jJyY]$ ]]; then
        if command -v raspi-config &>/dev/null; then
            raspi-config nonint do_pcie_speed 1
            ok "PCIe Gen3 aktiviert"
        else
            warn "raspi-config nicht gefunden – manuell setzen:"
            echo "  echo 'dtparam=pciex1_gen=3' | sudo tee -a ${BOOT_DIR}/config.txt"
        fi
    fi
fi

# =============================================================================
# 7. Udev neu laden
# =============================================================================
section "Udev & Module neu laden"

udevadm control --reload-rules 2>/dev/null && ok "udev-Regeln neu geladen" || warn "udev reload fehlgeschlagen"
depmod -a 2>/dev/null && ok "depmod -a ausgeführt" || warn "depmod fehlgeschlagen"

# =============================================================================
# Aufräumen
# =============================================================================

if [[ "$TMPDIR_CREATED" == "1" ]]; then
    rm -rf "$WORK_DIR"
fi

# =============================================================================
# Zusammenfassung & Reboot-Hinweis
# =============================================================================

echo ""
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  Restore abgeschlossen!${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""
info "Erstelle Sicherungskopien wurden als *.pre-restore.bak abgelegt."
info "Bitte folgende Punkte manuell prüfen:"
echo ""
echo "  1. ${BOOT_DIR}/config.txt auf korrekte Overlays prüfen"
echo "  2. ${BOOT_DIR}/cmdline.txt vergleichen (falls nicht restored)"
echo "  3. Hailo-Pakete auf Trixie installieren:"
echo "     sudo apt install hailo-all"
echo "  4. Nach dem Reboot: hailortcli fw-control identify"
echo ""
ask "Jetzt neustarten? [j/N]"
read -r DO_REBOOT
if [[ "$DO_REBOOT" =~ ^[jJyY]$ ]]; then
    info "Starte neu..."
    sleep 2
    reboot
else
    warn "Bitte manuell neu starten: sudo reboot"
fi
