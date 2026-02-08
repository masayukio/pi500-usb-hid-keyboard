#!/bin/sh
set -eu

GADGET=pi500hid
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

# Check if UDC is available (OTG mode ready)
UDC="$(ls /sys/class/udc 2>/dev/null | head -n1 || true)"
if [ -z "$UDC" ]; then
  log "No UDC found - OTG mode not available, exiting gracefully"
  exit 0
fi

# ---- check if already configured -----------------------------

if [ -d "$G" ]; then
  # Check if gadget is already bound to UDC
  CURRENT_UDC="$(cat "$G/UDC" 2>/dev/null || true)"
  if [ -n "$CURRENT_UDC" ]; then
    log "Gadget $GADGET already configured and bound to $CURRENT_UDC"
    exit 0
  fi

  # Gadget exists but not bound - need to clean up
  log "Existing gadget found but not bound, cleaning up..."

  # Remove function links
  if [ -d "$G/configs" ]; then
    find "$G/configs" -maxdepth 2 -type l -exec rm -f {} \; || true
  fi

  # Remove configs
  if [ -d "$G/configs/c.1/strings" ]; then
    rmdir "$G/configs/c.1/strings/0x409" 2>/dev/null || true
    rmdir "$G/configs/c.1/strings" 2>/dev/null || true
  fi
  rmdir "$G/configs/c.1" 2>/dev/null || true
  rmdir "$G/configs" 2>/dev/null || true

  # Remove functions
  rmdir "$G/functions/hid.usb0" 2>/dev/null || true
  rmdir "$G/functions/hid.usb1" 2>/dev/null || true
  rmdir "$G/functions" 2>/dev/null || true

  # Remove strings
  rmdir "$G/strings/0x409" 2>/dev/null || true
  rmdir "$G/strings" 2>/dev/null || true

  # Finally remove gadget dir
  rmdir "$G" 2>/dev/null || true
fi

# ---- create gadget -------------------------------------------

log "Creating gadget $GADGET"
mkdir -p "$G"
cd "$G"

# Device IDs
echo 0x1d6b > idVendor      # Linux Foundation
echo 0x0104 > idProduct     # Multifunction HID gadget
echo 0x0100 > bcdDevice
echo 0x0200 > bcdUSB

# Strings
mkdir -p strings/0x409
echo "pi500hid001"              > strings/0x409/serialnumber
echo "Raspberry Pi"             > strings/0x409/manufacturer
echo "Pi 500+ USB Keyboard+Mouse" > strings/0x409/product

# Configuration
mkdir -p configs/c.1/strings/0x409
echo "HID Keyboard+Mouse" > configs/c.1/strings/0x409/configuration
echo 250                  > configs/c.1/MaxPower

# ---- HID Keyboard function -----------------------------------

log "Creating HID keyboard function"
mkdir -p functions/hid.usb0

echo 1 > functions/hid.usb0/protocol   # Keyboard
echo 1 > functions/hid.usb0/subclass   # Boot keyboard
echo 8 > functions/hid.usb0/report_length

SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
cat "$SCRIPT_DIR/hid-keyboard.bin" > functions/hid.usb0/report_desc

# Link keyboard function
ln -s functions/hid.usb0 configs/c.1/

# ---- HID Mouse function --------------------------------------

log "Creating HID mouse function"
mkdir -p functions/hid.usb1

echo 2 > functions/hid.usb1/protocol   # Mouse
echo 1 > functions/hid.usb1/subclass   # Boot mouse
echo 4 > functions/hid.usb1/report_length

cat "$SCRIPT_DIR/hid-mouse.bin" > functions/hid.usb1/report_desc

# Link mouse function
ln -s functions/hid.usb1 configs/c.1/

# ---- bind UDC ------------------------------------------------

log "Binding to UDC: $UDC"
echo "$UDC" > UDC

log "Gadget $GADGET is ready."

