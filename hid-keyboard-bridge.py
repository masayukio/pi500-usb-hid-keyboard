#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pi 500+ internal keyboard -> USB HID keyboard gadget bridge
- Reads evdev key events from a selected /dev/input/event*
- Translates Linux KEY_* codes to USB HID usage IDs
- Writes 8-byte keyboard reports to /dev/hidg0

Notes:
- This sends "physical key" events, not characters.
- Set Windows host keyboard layout to Japanese 106/109 for correct symbols.
- Requires root (or udev perms) to read /dev/input/event* and write /dev/hidg0.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import errno
from typing import Dict, Optional, Set, Tuple

from evdev import InputDevice, ecodes, list_devices


# --- USB HID keyboard report format (8 bytes) ---
# [0] modifiers bitmask (LCTRL=1, LSHIFT=2, LALT=4, LGUI=8, RCTRL=16, RSHIFT=32, RALT=64, RGUI=128)
# [1] reserved
# [2..7] up to 6 simultaneous key usage IDs


# Modifier mapping: Linux KEY_* -> HID modifier bit
MODIFIER_KEYS: Dict[int, int] = {
    ecodes.KEY_LEFTCTRL: 0x01,
    ecodes.KEY_LEFTSHIFT: 0x02,
    ecodes.KEY_LEFTALT: 0x04,
    ecodes.KEY_LEFTMETA: 0x08,   # Windows / Command key
    ecodes.KEY_RIGHTCTRL: 0x10,
    ecodes.KEY_RIGHTSHIFT: 0x20,
    ecodes.KEY_RIGHTALT: 0x40,   # AltGr (if used)
    ecodes.KEY_RIGHTMETA: 0x80,
}

# Minimal-but-wide Linux KEY_* -> USB HID Usage ID mapping
# (This is largely layout-independent: it represents physical key positions/usages.)
KEY_TO_HID: Dict[int, int] = {
    # Letters
    ecodes.KEY_A: 0x04, ecodes.KEY_B: 0x05, ecodes.KEY_C: 0x06, ecodes.KEY_D: 0x07,
    ecodes.KEY_E: 0x08, ecodes.KEY_F: 0x09, ecodes.KEY_G: 0x0A, ecodes.KEY_H: 0x0B,
    ecodes.KEY_I: 0x0C, ecodes.KEY_J: 0x0D, ecodes.KEY_K: 0x0E, ecodes.KEY_L: 0x0F,
    ecodes.KEY_M: 0x10, ecodes.KEY_N: 0x11, ecodes.KEY_O: 0x12, ecodes.KEY_P: 0x13,
    ecodes.KEY_Q: 0x14, ecodes.KEY_R: 0x15, ecodes.KEY_S: 0x16, ecodes.KEY_T: 0x17,
    ecodes.KEY_U: 0x18, ecodes.KEY_V: 0x19, ecodes.KEY_W: 0x1A, ecodes.KEY_X: 0x1B,
    ecodes.KEY_Y: 0x1C, ecodes.KEY_Z: 0x1D,

    # Numbers row
    ecodes.KEY_1: 0x1E, ecodes.KEY_2: 0x1F, ecodes.KEY_3: 0x20, ecodes.KEY_4: 0x21,
    ecodes.KEY_5: 0x22, ecodes.KEY_6: 0x23, ecodes.KEY_7: 0x24, ecodes.KEY_8: 0x25,
    ecodes.KEY_9: 0x26, ecodes.KEY_0: 0x27,

    # Control keys
    ecodes.KEY_ENTER: 0x28,
    ecodes.KEY_ESC: 0x29,
    ecodes.KEY_BACKSPACE: 0x2A,
    ecodes.KEY_TAB: 0x2B,
    ecodes.KEY_SPACE: 0x2C,

    # Punctuation / symbols (physical keys)
    ecodes.KEY_MINUS: 0x2D,
    ecodes.KEY_EQUAL: 0x2E,
    ecodes.KEY_LEFTBRACE: 0x2F,
    ecodes.KEY_RIGHTBRACE: 0x30,
    ecodes.KEY_BACKSLASH: 0x31,
    ecodes.KEY_SEMICOLON: 0x33,
    ecodes.KEY_APOSTROPHE: 0x34,
    ecodes.KEY_GRAVE: 0x35,
    ecodes.KEY_COMMA: 0x36,
    ecodes.KEY_DOT: 0x37,
    ecodes.KEY_SLASH: 0x38,

    # Caps / function row
    ecodes.KEY_CAPSLOCK: 0x39,
    ecodes.KEY_F1: 0x3A, ecodes.KEY_F2: 0x3B, ecodes.KEY_F3: 0x3C, ecodes.KEY_F4: 0x3D,
    ecodes.KEY_F5: 0x3E, ecodes.KEY_F6: 0x3F, ecodes.KEY_F7: 0x40, ecodes.KEY_F8: 0x41,
    ecodes.KEY_F9: 0x42, ecodes.KEY_F10: 0x43, ecodes.KEY_F11: 0x44, ecodes.KEY_F12: 0x45,

    # Navigation
    ecodes.KEY_SYSRQ: 0x46,      # PrintScreen
    ecodes.KEY_SCROLLLOCK: 0x47,
    ecodes.KEY_PAUSE: 0x48,
    ecodes.KEY_INSERT: 0x49,
    ecodes.KEY_HOME: 0x4A,
    ecodes.KEY_PAGEUP: 0x4B,
    ecodes.KEY_DELETE: 0x4C,
    ecodes.KEY_END: 0x4D,
    ecodes.KEY_PAGEDOWN: 0x4E,
    ecodes.KEY_RIGHT: 0x4F,
    ecodes.KEY_LEFT: 0x50,
    ecodes.KEY_DOWN: 0x51,
    ecodes.KEY_UP: 0x52,

    # Keypad
    ecodes.KEY_NUMLOCK: 0x53,
    ecodes.KEY_KPSLASH: 0x54,
    ecodes.KEY_KPASTERISK: 0x55,
    ecodes.KEY_KPMINUS: 0x56,
    ecodes.KEY_KPPLUS: 0x57,
    ecodes.KEY_KPENTER: 0x58,
    ecodes.KEY_KP1: 0x59, ecodes.KEY_KP2: 0x5A, ecodes.KEY_KP3: 0x5B,
    ecodes.KEY_KP4: 0x5C, ecodes.KEY_KP5: 0x5D, ecodes.KEY_KP6: 0x5E,
    ecodes.KEY_KP7: 0x5F, ecodes.KEY_KP8: 0x60, ecodes.KEY_KP9: 0x61,
    ecodes.KEY_KP0: 0x62,
    ecodes.KEY_KPDOT: 0x63,

    # Menu / Application
    ecodes.KEY_COMPOSE: 0x65,    # Many keyboards map this to "Application"
    ecodes.KEY_MENU: 0x65,

    # JIS-specific / IME keys (best-effort)
    # These depend on how the kernel reports your 500+ keyboard.
    # If some don't work, run with --show and check the KEY_* names you get.
    ecodes.KEY_HENKAN: 0x8A,     # Henkan (JIS): HID 0x8A
    ecodes.KEY_MUHENKAN: 0x8B,   # Muhenkan (JIS): HID 0x8B
    ecodes.KEY_KATAKANAHIRAGANA: 0x88,  # HID 0x88 (Kana)
    ecodes.KEY_YEN: 0x89,        # HID 0x89 (International 3 / Yen)
    ecodes.KEY_RO: 0x87,         # HID 0x87 (International 1 / Ro)
}

# Some kernels use different keycodes for JIS keys; we can alias if present.
# We'll populate aliases at runtime if those ecodes exist.
JIS_ALIASES = [
    ("KEY_ZENKAKUHANKAKU", 0x35),  # often maps to grave / or a special key; adjust if needed
]


def build_report(mod_mask: int, pressed_usages: Set[int]) -> bytes:
    keys = sorted(pressed_usages)[:6]
    while len(keys) < 6:
        keys.append(0)
    return bytes([mod_mask & 0xFF, 0x00] + keys)


def open_hidg(path: str) -> int:
    fd = os.open(path, os.O_WRONLY)
    return fd


def write_report(fd: int, report: bytes) -> None:
    """
    Write HID report, waiting until the gadget endpoint is ready.
    This handles the case where /dev/hidg0 exists but the host
    has not finished HID enumeration yet.
    """
    while True:
        try:
            os.write(fd, report)
            return
        except BlockingIOError as e:
            if e.errno != errno.EAGAIN:
                raise
            # HID endpoint not ready yet – wait a bit
            time.sleep(0.01)


def pick_keyboard_device() -> InputDevice:
    devs = [InputDevice(p) for p in list_devices()]
    keyboards = []
    for d in devs:
        caps = d.capabilities().get(ecodes.EV_KEY, [])
        # Heuristic: has A, ENTER, SPACE
        if ecodes.KEY_A in caps and ecodes.KEY_ENTER in caps and ecodes.KEY_SPACE in caps:
            keyboards.append(d)

    if not keyboards:
        raise RuntimeError("No keyboard-like evdev device found.")

    # Prefer devices that contain 'keyboard' in name/phys
    keyboards.sort(key=lambda d: (("keyboard" not in (d.name or "").lower()), d.path))
    return keyboards[0]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--event", help="evdev path, e.g. /dev/input/event3 (auto if omitted)")
    ap.add_argument("--hidg", default="/dev/hidg0", help="hid gadget node (default: /dev/hidg0)")
    ap.add_argument("--grab", action="store_true", help="exclusive grab input device (prevents local handling)")
    ap.add_argument("--show", action="store_true", help="print key events for debugging")
    args = ap.parse_args()

    # Add JIS aliases if available
    for name, hid in JIS_ALIASES:
        code = getattr(ecodes, name, None)
        if isinstance(code, int) and code not in KEY_TO_HID:
            KEY_TO_HID[code] = hid

    dev = InputDevice(args.event) if args.event else pick_keyboard_device()
    print(f"[+] Using input device: {dev.path} ({dev.name})", file=sys.stderr)

    if args.grab:
        dev.grab()
        print("[+] Grabbed input device exclusively", file=sys.stderr)

    hidfd = open_hidg(args.hidg)
    print(f"[+] Writing HID reports to: {args.hidg}", file=sys.stderr)

    pressed_keys: Set[int] = set()     # linux key codes pressed (non-mod)
    pressed_usages: Set[int] = set()   # hid usage IDs pressed (non-mod)
    mod_mask = 0

    # Send initial "all released"
    write_report(hidfd, build_report(0, set()))

    try:
        for e in dev.read_loop():
            if e.type != ecodes.EV_KEY:
                continue

            key_event = ecodes.KEY.get(e.code, f"KEY_{e.code}")
            is_down = e.value == 1
            is_up = e.value == 0
            is_repeat = e.value == 2

            if args.show:
                print(f"EV_KEY {key_event} value={e.value}", file=sys.stderr)

            # Ignore repeats (Windows will handle auto-repeat from its side if needed);
            # if you want repeats, treat value==2 as down.
            if is_repeat:
                continue

            # Modifiers
            if e.code in MODIFIER_KEYS:
                bit = MODIFIER_KEYS[e.code]
                if is_down:
                    mod_mask |= bit
                elif is_up:
                    mod_mask &= (~bit & 0xFF)
                write_report(hidfd, build_report(mod_mask, pressed_usages))
                continue

            # Regular keys
            hid_usage = KEY_TO_HID.get(e.code)
            if hid_usage is None:
                # Unknown key: just ignore (or print)
                if args.show:
                    print(f"[!] Unmapped key: {key_event}", file=sys.stderr)
                continue

            if is_down:
                pressed_keys.add(e.code)
                pressed_usages.add(hid_usage)
            elif is_up:
                pressed_keys.discard(e.code)
                pressed_usages.discard(hid_usage)

            write_report(hidfd, build_report(mod_mask, pressed_usages))

    except KeyboardInterrupt:
        pass
    finally:
        # Release all keys on exit (important to avoid "stuck keys")
        try:
            write_report(hidfd, build_report(0, set()))
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

