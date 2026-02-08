#!/bin/sh
set -eu

GADGET=pi500hid
BASE=/sys/kernel/config/usb_gadget
G=$BASE/$GADGET

# ---- helpers -------------------------------------------------

log() { echo "[*] $*"; }

usage() {
  echo "Usage: $0 [--config <path-to-keyboard-layout.conf>]" >&2
  exit 1
}

# ---- parameter parsing ---------------------------------------

CONFIG_FILE_PARAM=""

while [ $# -gt 0 ]; do
  case "$1" in
    --config)
      if [ $# -lt 2 ]; then
        echo "ERROR: --config requires an argument" >&2
        usage
      fi
      CONFIG_FILE_PARAM="$2"
      shift 2
      ;;
    -h|--help)
      usage
      ;;
    *)
      echo "ERROR: Unknown option: $1" >&2
      usage
      ;;
  esac
done

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

# ---- Keyboard layout configuration ---------------------------

SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"

# Determine config file path: parameter > default location
if [ -n "$CONFIG_FILE_PARAM" ]; then
  CONFIG_FILE="$CONFIG_FILE_PARAM"
else
  CONFIG_FILE="$SCRIPT_DIR/keyboard-layout.conf"
fi

# Read keyboard layout from config file
KEYBOARD_LAYOUT="us"  # Default

if [ -f "$CONFIG_FILE" ]; then
  # Read from config file (format: KEYBOARD_LAYOUT=us or KEYBOARD_LAYOUT=jis)
  LAYOUT_VALUE="$(grep -E '^KEYBOARD_LAYOUT=' "$CONFIG_FILE" | cut -d= -f2 | tr -d ' ' || true)"
  if [ -n "$LAYOUT_VALUE" ]; then
    KEYBOARD_LAYOUT="$LAYOUT_VALUE"
  fi
  log "Reading keyboard layout from: $CONFIG_FILE"
else
  log "Config file not found: $CONFIG_FILE (using default: us)"
fi

# Validate keyboard layout
case "$KEYBOARD_LAYOUT" in
  us|jis)
    log "Using $KEYBOARD_LAYOUT keyboard layout"
    ;;
  *)
    log "WARNING: Unknown KEYBOARD_LAYOUT '$KEYBOARD_LAYOUT', defaulting to 'us'"
    KEYBOARD_LAYOUT="us"
    ;;
esac

# ---- HID Keyboard function -----------------------------------

log "Creating HID keyboard function"
mkdir -p functions/hid.usb0

echo 1 > functions/hid.usb0/protocol   # Keyboard
#echo 1 > functions/hid.usb0/subclass   # Boot keyboard
echo 0 > functions/hid.usb0/subclass   # Boot keyboard is BIOS 101/102, JP106/109 keyboard should be 0
echo 8 > functions/hid.usb0/report_length

# Select appropriate HID descriptor based on layout
if [ "$KEYBOARD_LAYOUT" = "jis" ]; then
  HID_DESC="$SCRIPT_DIR/hid-keyboard-jis.bin"
else
  HID_DESC="$SCRIPT_DIR/hid-keyboard-us.bin"
fi

if [ ! -f "$HID_DESC" ]; then
  log "ERROR: HID descriptor not found: $HID_DESC"
  exit 1
fi

cat "$HID_DESC" > functions/hid.usb0/report_desc
log "Using HID descriptor: $(basename "$HID_DESC")"

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

