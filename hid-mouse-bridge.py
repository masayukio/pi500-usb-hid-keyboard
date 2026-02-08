#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pi 500+ mouse -> USB HID mouse gadget bridge
- Reads evdev mouse events from /dev/input/event* (auto-detect or specified)
- Translates to USB HID mouse reports (buttons, X, Y, wheel)
- Writes 4-byte mouse reports to /dev/hidg1

Report format (4 bytes):
[0] buttons bitmask (LEFT=1, RIGHT=2, MIDDLE=4)
[1] X movement (signed -127 to 127)
[2] Y movement (signed -127 to 127)
[3] Wheel movement (signed -127 to 127)
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import errno
from typing import Set

from evdev import InputDevice, ecodes, list_devices


# Button mapping: Linux BTN_* -> HID button bit
BUTTON_MAP = {
    ecodes.BTN_LEFT: 0x01,
    ecodes.BTN_RIGHT: 0x02,
    ecodes.BTN_MIDDLE: 0x04,
}


def clamp(value: int, min_val: int = -127, max_val: int = 127) -> int:
    """Clamp value to signed byte range."""
    return max(min_val, min(max_val, value))


def signed_byte(value: int) -> int:
    """Convert signed int to unsigned byte (two's complement)."""
    if value < 0:
        return (256 + value) & 0xFF
    return value & 0xFF


def build_mouse_report(buttons: int, dx: int, dy: int, wheel: int) -> bytes:
    """Build 4-byte USB HID mouse report."""
    return bytes([
        buttons & 0xFF,
        signed_byte(clamp(dx)),
        signed_byte(clamp(dy)),
        signed_byte(clamp(wheel))
    ])


def open_hidg(path: str) -> int:
    """Open HID gadget device for writing."""
    fd = os.open(path, os.O_WRONLY)
    return fd


def write_report(fd: int, report: bytes) -> None:
    """Write HID report, handling EAGAIN when endpoint not ready."""
    while True:
        try:
            os.write(fd, report)
            return
        except BlockingIOError as e:
            if e.errno != errno.EAGAIN:
                raise
            time.sleep(0.01)


def pick_mouse_device() -> InputDevice:
    """Auto-detect mouse device from available input devices."""
    devs = [InputDevice(p) for p in list_devices()]
    mice = []

    for d in devs:
        caps = d.capabilities()
        # Mouse heuristic: has REL events (X, Y) and button events
        rel_caps = caps.get(ecodes.EV_REL, [])
        key_caps = caps.get(ecodes.EV_KEY, [])

        has_rel_xy = ecodes.REL_X in rel_caps and ecodes.REL_Y in rel_caps
        has_buttons = any(btn in key_caps for btn in [ecodes.BTN_LEFT, ecodes.BTN_RIGHT, ecodes.BTN_MOUSE])

        if has_rel_xy and has_buttons:
            mice.append(d)

    if not mice:
        raise RuntimeError("No mouse-like evdev device found.")

    # Prefer devices with 'mouse' in name
    mice.sort(key=lambda d: ("mouse" not in (d.name or "").lower(), d.path))
    return mice[0]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--event", help="evdev path, e.g. /dev/input/event9 (auto if omitted)")
    ap.add_argument("--hidg", default="/dev/hidg1", help="HID gadget node (default: /dev/hidg1)")
    ap.add_argument("--grab", action="store_true", help="exclusive grab input device")
    ap.add_argument("--show", action="store_true", help="print mouse events for debugging")
    args = ap.parse_args()

    dev = InputDevice(args.event) if args.event else pick_mouse_device()
    print(f"[+] Using input device: {dev.path} ({dev.name})", file=sys.stderr)

    if args.grab:
        dev.grab()
        print("[+] Grabbed input device exclusively", file=sys.stderr)

    hidfd = open_hidg(args.hidg)
    print(f"[+] Writing HID reports to: {args.hidg}", file=sys.stderr)

    buttons = 0
    prev_buttons = 0
    dx_accum = 0
    dy_accum = 0
    wheel_accum = 0

    # Send initial "no movement, no buttons"
    write_report(hidfd, build_mouse_report(0, 0, 0, 0))

    try:
        for e in dev.read_loop():
            if e.type == ecodes.EV_REL:
                if e.code == ecodes.REL_X:
                    dx_accum += e.value
                elif e.code == ecodes.REL_Y:
                    dy_accum += e.value
                elif e.code == ecodes.REL_WHEEL:
                    wheel_accum += e.value
                elif e.code == ecodes.REL_HWHEEL:
                    # Horizontal wheel - optional, could map differently
                    pass

                if args.show:
                    rel_name = ecodes.REL.get(e.code, f"REL_{e.code}")
                    print(f"EV_REL {rel_name} value={e.value}", file=sys.stderr)

            elif e.type == ecodes.EV_KEY:
                if e.code in BUTTON_MAP:
                    bit = BUTTON_MAP[e.code]
                    if e.value == 1:  # Press
                        buttons |= bit
                    elif e.value == 0:  # Release
                        buttons &= ~bit

                    if args.show:
                        btn_name = ecodes.BTN.get(e.code, f"BTN_{e.code}")
                        print(f"EV_KEY {btn_name} value={e.value}", file=sys.stderr)

            elif e.type == ecodes.EV_SYN and e.code == ecodes.SYN_REPORT:
                # Send report if movement occurred or button state changed
                if dx_accum != 0 or dy_accum != 0 or wheel_accum != 0 or buttons != prev_buttons:
                    write_report(hidfd, build_mouse_report(buttons, dx_accum, dy_accum, wheel_accum))
                    if args.show:
                        print(f"REPORT: buttons={buttons:02x} dx={dx_accum} dy={dy_accum} wheel={wheel_accum}", file=sys.stderr)

                    # Reset accumulators and update previous button state
                    dx_accum = 0
                    dy_accum = 0
                    wheel_accum = 0
                    prev_buttons = buttons

    except KeyboardInterrupt:
        pass
    finally:
        # Release all on exit
        try:
            write_report(hidfd, build_mouse_report(0, 0, 0, 0))
        except Exception:
            pass
        try:
            os.close(hidfd)
        except Exception:
            pass
        try:
            if args.grab:
                dev.ungrab()
        except Exception:
            pass

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
