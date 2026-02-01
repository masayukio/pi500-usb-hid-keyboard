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

echo 1 > functions/hid.usb0/protocol      # keyboard
echo 0 > functions/hid.usb0/subclass      # BIOS不要
echo 8 > functions/hid.usb0/report_length

# Correct, Windows-safe HID report descriptor (Boot keyboard compatible)
cat > functions/hid.usb0/report_desc << 'EOF'
\x05\x01\x09\x06\xa1\x01\x05\x07\x19\xe0\x29\xe7\x15\x00\x25\x01\x75\x01\x95\x08\x81\x02\
\x95\x01\x75\x08\x81\x03\x95\x05\x75\x01\x05\x08\x19\x01\x29\x05\x91\x02\
\x95\x01\x75\x03\x91\x03\x95\x06\x75\x08\x15\x00\x25\x65\x05\x07\x19\x00\x29\x65\x81\x00\xc0
EOF

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

