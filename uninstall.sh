#!/bin/bash
set -euo pipefail

# Pi500 USB HID Keyboard - Uninstallation Script
# This script removes the Pi500+ HID keyboard installation

# Default installation directory
INSTALL_DIR="${INSTALL_DIR:-/opt/pi500-hid-keyboard}"
SYSTEMD_SERVICE_NAME="pi500-hid-keyboard.service"
GADGET_NAME="pi500kbd"
GADGET_DIR="/sys/kernel/config/usb_gadget/$GADGET_NAME"

# Color output helpers
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $*"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $*"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $*" >&2
}

# Check if running as root
if [ "$(id -u)" != "0" ]; then
    log_error "This script must be run as root (use sudo)"
    exit 1
fi

log_info "Uninstalling Pi500 HID Keyboard..."

# Stop and disable systemd service
if systemctl is-active --quiet "$SYSTEMD_SERVICE_NAME" 2>/dev/null; then
    log_info "Stopping service: $SYSTEMD_SERVICE_NAME"
    systemctl stop "$SYSTEMD_SERVICE_NAME"
fi

if systemctl is-enabled --quiet "$SYSTEMD_SERVICE_NAME" 2>/dev/null; then
    log_info "Disabling service: $SYSTEMD_SERVICE_NAME"
    systemctl disable "$SYSTEMD_SERVICE_NAME"
fi

# Remove systemd service file
SERVICE_FILE="/etc/systemd/system/$SYSTEMD_SERVICE_NAME"
if [ -f "$SERVICE_FILE" ]; then
    log_info "Removing service file: $SERVICE_FILE"
    rm -f "$SERVICE_FILE"
    systemctl daemon-reload
fi

# Remove USB HID gadget
if [ -d "$GADGET_DIR" ]; then
    log_info "Removing USB HID gadget: $GADGET_NAME"

    # Unbind UDC
    if [ -f "$GADGET_DIR/UDC" ]; then
        echo "" > "$GADGET_DIR/UDC" 2>/dev/null || true
    fi

    # Remove function links
    if [ -d "$GADGET_DIR/configs" ]; then
        find "$GADGET_DIR/configs" -type l -maxdepth 2 -exec rm -f {} \; 2>/dev/null || true
    fi

    # Remove functions
    rm -rf "$GADGET_DIR/functions" 2>/dev/null || true

    # Remove configs
    rm -rf "$GADGET_DIR/configs" 2>/dev/null || true

    # Remove strings
    rm -rf "$GADGET_DIR/strings" 2>/dev/null || true

    # Remove gadget directory
    rmdir "$GADGET_DIR" 2>/dev/null || log_warn "Could not remove gadget directory (may still be in use)"
fi

# Remove installed files
if [ -d "$INSTALL_DIR" ]; then
    log_info "Removing installation directory: $INSTALL_DIR"
    rm -rf "$INSTALL_DIR"
else
    log_warn "Installation directory not found: $INSTALL_DIR"
fi

log_info ""
log_info "Uninstallation complete!"
log_info ""
log_info "The following have been removed:"
log_info "  - systemd service: $SYSTEMD_SERVICE_NAME"
log_info "  - USB HID gadget: $GADGET_NAME"
log_info "  - Installation directory: $INSTALL_DIR"
log_info ""
log_info "A reboot is recommended to fully clean up USB gadget configuration."
log_info ""
log_warn "To reboot now, run: sudo reboot"
