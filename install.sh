#!/bin/bash
set -euo pipefail

# Pi500 USB HID Keyboard - Installation Script
# This script installs the Pi500+ HID keyboard project to a configurable location

# Default installation directory
INSTALL_DIR="${INSTALL_DIR:-/opt/pi500-hid-keyboard}"
SYSTEMD_SERVICE_NAME="pi500-hid-keyboard.service"

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

# Verify we're on a compatible platform
if [ ! -d /sys/class/udc ]; then
    log_warn "USB Device Controller (UDC) not found at /sys/class/udc"
    log_warn "This might not be a Pi500+ or OTG mode is not enabled"
    read -p "Continue anyway? [y/N] " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_info "Installation cancelled"
        exit 0
    fi
fi

# Check if OTG peripheral mode is configured
CONFIG_FILE="/boot/firmware/config.txt"
if [ -f "$CONFIG_FILE" ]; then
    if ! grep -q "dtoverlay=dwc2" "$CONFIG_FILE" || ! grep -q "dr_mode=peripheral" "$CONFIG_FILE"; then
        log_error "OTG peripheral mode is not configured in $CONFIG_FILE"
        log_error "Please add the following lines to $CONFIG_FILE:"
        log_error ""
        log_error "  [all]"
        log_error "  dtoverlay=dwc2,dr_mode=peripheral"
        log_error ""
        log_error "Then reboot and run this script again."
        exit 1
    fi
else
    log_warn "Cannot verify OTG configuration: $CONFIG_FILE not found"
fi

# Check for required commands
for cmd in python3 modprobe systemctl; do
    if ! command -v "$cmd" &> /dev/null; then
        log_error "Required command '$cmd' not found"
        exit 1
    fi
done

# Check for Python evdev module
if ! python3 -c "import evdev" 2>/dev/null; then
    log_warn "Python 'evdev' module not found"
    log_info "Installing python3-evdev..."
    apt-get update -qq
    apt-get install -y python3-evdev
fi

log_info "Installing Pi500 HID Keyboard to: $INSTALL_DIR"

# Create installation directory
mkdir -p "$INSTALL_DIR"

# Get the script's directory (where the source files are)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Copy files
log_info "Copying files..."
cp -v "$SCRIPT_DIR/hid-keyboard-bridge.py" "$INSTALL_DIR/"
cp -v "$SCRIPT_DIR/check-gadget-ready.sh" "$INSTALL_DIR/"
cp -v "$SCRIPT_DIR/setup-hid-gadget.sh" "$INSTALL_DIR/"
cp -v "$SCRIPT_DIR/report_desc.bin" "$INSTALL_DIR/"

# Set executable permissions
chmod +x "$INSTALL_DIR/hid-keyboard-bridge.py"
chmod +x "$INSTALL_DIR/check-gadget-ready.sh"
chmod +x "$INSTALL_DIR/setup-hid-gadget.sh"

# Generate systemd service file from template
log_info "Generating systemd service file..."
if [ -f "$SCRIPT_DIR/pi500-hid-keyboard.service.template" ]; then
    SERVICE_FILE="/etc/systemd/system/$SYSTEMD_SERVICE_NAME"
    sed "s|{{INSTALL_DIR}}|$INSTALL_DIR|g" "$SCRIPT_DIR/pi500-hid-keyboard.service.template" > "$SERVICE_FILE"
    log_info "Created service file: $SERVICE_FILE"
else
    log_error "Service template file not found: $SCRIPT_DIR/pi500-hid-keyboard.service.template"
    exit 1
fi

# Setup USB HID gadget
log_info "Setting up USB HID gadget..."
if "$INSTALL_DIR/setup-hid-gadget.sh"; then
    log_info "USB HID gadget configured successfully"
else
    log_error "Failed to setup USB HID gadget"
    exit 1
fi

# Reload systemd daemon
log_info "Reloading systemd daemon..."
systemctl daemon-reload

# Enable and start the service
log_info "Enabling and starting $SYSTEMD_SERVICE_NAME..."
systemctl enable "$SYSTEMD_SERVICE_NAME"
systemctl start "$SYSTEMD_SERVICE_NAME"

# Check service status
if systemctl is-active --quiet "$SYSTEMD_SERVICE_NAME"; then
    log_info "Service started successfully"
else
    log_warn "Service may not have started correctly. Check status with:"
    log_warn "  sudo systemctl status $SYSTEMD_SERVICE_NAME"
fi

log_info ""
log_info "Installation complete!"
log_info ""
log_info "Files installed to: $INSTALL_DIR"
log_info "Service name: $SYSTEMD_SERVICE_NAME"
log_info ""
log_info "To check status:    sudo systemctl status $SYSTEMD_SERVICE_NAME"
log_info "To view logs:       sudo journalctl -u $SYSTEMD_SERVICE_NAME -f"
log_info "To uninstall:       sudo ./uninstall.sh"
log_info ""
log_info "Connect your Pi500+ to a host via USB-C and start typing!"
