#!/bin/sh
set -eu

GADGET=pi500kbd
BASE=/sys/kernel/config/usb_gadget
G=$BASE/$GADGET

# ---- helpers -------------------------------------------------

log() { echo "[*] $*"; }

# ---- preflight -----------------------------------------------

if [ "$(id -u)" != "0" ]; then
  echo "Run as root." >&2
  exit 1
fi

modprobe libcomposite

# ---- cleanup (idempotent) ------------------------------------

if [ -d "$G" ]; then
  log "Existing gadget found, cleaning up..."

  # Unbind if bound
  if [ -f "$G/UDC" ]; then
    echo "" > "$G/UDC" || true
  fi

  # Remove function links
  if [ -d "$G/configs" ]; then
    find "$G/configs" -type l -maxdepth 2 -exec rm -f {} \; || true
  fi

  # Remove functions
  rm -rf "$G/functions" || true

  # Remove configs
  rm -rf "$G/configs" || true

  # Remove strings
  rm -rf "$G/strings" || true

  # Finally remove gadget dir
  rmdir "$G" || true
fi

# ---- create gadget -------------------------------------------

log "Creating gadget $GADGET"
mkdir -p "$G"
cd "$G"

# Device IDs
echo 0x1d6b > idVendor      # Linux Foundation
echo 0x0104 > idProduct     # HID gadget
echo 0x0100 > bcdDevice
echo 0x0200 > bcdUSB

# Strings
mkdir -p strings/0x409
echo "pi500kbd001"            > strings/0x409/serialnumber
echo "Raspberry Pi"           > strings/0x409/manufacturer
echo "Pi 500+ USB Keyboard"   > strings/0x409/product

# Configuration
mkdir -p configs/c.1/strings/0x409
echo "HID Keyboard" > configs/c.1/strings/0x409/configuration
echo 250            > configs/c.1/MaxPower

# ---- HID function --------------------------------------------

log "Creating HID function"
mkdir -p functions/hid.usb0

echo 1 > functions/hid.usb0/protocol   # Keyboard
echo 1 > functions/hid.usb0/subclass   # Boot keyboard
echo 8 > functions/hid.usb0/report_length

# Windows-safe boot keyboard report descriptor
#cat << 'EOF' | xxd -r -p > functions/hid.usb0/report_desc
#05010906a101050719e029e715002501750195088102
#950175088103
#95067508150025650507190029658100c0
#EOF
SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
cat "$SCRIPT_DIR/report_desc.bin" > functions/hid.usb0/report_desc

# Link function
ln -s functions/hid.usb0 configs/c.1/

# ---- bind UDC ------------------------------------------------

UDC="$(ls /sys/class/udc | head -n 1 || true)"
if [ -z "$UDC" ]; then
  echo "No UDC found. Is OTG enabled (dwc2,dr_mode=peripheral)?" >&2
  exit 1
fi

log "Binding to UDC: $UDC"
echo "$UDC" > UDC

log "Gadget $GADGET is ready."

