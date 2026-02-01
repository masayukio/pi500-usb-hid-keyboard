#!/bin/sh
# Exit 0: OTG ready
# Exit 1: not OTG

GADGET_DIR="/sys/kernel/config/usb_gadget/pi500kbd"

# UDC が存在しない
[ -d /sys/class/udc ] || exit 1

# gadget が無い
[ -d "$GADGET_DIR" ] || exit 1

# UDC が bind されていない
UDC="$(cat "$GADGET_DIR/UDC" 2>/dev/null)"
[ -n "$UDC" ] || exit 1

# hidg0 が無い
[ -e /dev/hidg0 ] || exit 1

exit 0

