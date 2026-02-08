#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pi 500+ internal keyboard + mouse -> USB HID gadget bridge
- Reads evdev events from keyboard and mouse devices
- Translates to USB HID reports
- Writes to /dev/hidg0 (keyboard) and /dev/hidg1 (mouse)
- Dynamically handles mouse attach/detach
- Calls setup-hid-gadget.sh at startup
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import errno
import threading
import subprocess
from pathlib import Path
from typing import Dict, Optional, Set

from evdev import InputDevice, ecodes, list_devices


# ============================================================================
# USB HID Keyboard
# ============================================================================

# Modifier mapping: Linux KEY_* -> HID modifier bit
MODIFIER_KEYS: Dict[int, int] = {
    ecodes.KEY_LEFTCTRL: 0x01,
    ecodes.KEY_LEFTSHIFT: 0x02,
    ecodes.KEY_LEFTALT: 0x04,
    ecodes.KEY_LEFTMETA: 0x08,
    ecodes.KEY_RIGHTCTRL: 0x10,
    ecodes.KEY_RIGHTSHIFT: 0x20,
    ecodes.KEY_RIGHTALT: 0x40,
    ecodes.KEY_RIGHTMETA: 0x80,
}

# Linux KEY_* -> USB HID Usage ID mapping
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

    # Punctuation / symbols
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
    ecodes.KEY_SYSRQ: 0x46,
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
    ecodes.KEY_COMPOSE: 0x65,
    ecodes.KEY_MENU: 0x65,

    # JIS-specific / IME keys
    ecodes.KEY_HENKAN: 0x8A,
    ecodes.KEY_MUHENKAN: 0x8B,
    ecodes.KEY_KATAKANAHIRAGANA: 0x88,
    ecodes.KEY_YEN: 0x89,
    ecodes.KEY_RO: 0x87,
    ecodes.KEY_ZENKAKUHANKAKU: 0x94,
}

# Mouse button mapping: Linux BTN_* -> HID button bit
BUTTON_MAP = {
    ecodes.BTN_LEFT: 0x01,
    ecodes.BTN_RIGHT: 0x02,
    ecodes.BTN_MIDDLE: 0x04,
}


# ============================================================================
# Utilities
# ============================================================================

def log(msg: str) -> None:
    """Log message to stderr."""
    print(f"[*] {msg}", file=sys.stderr)


def open_hidg(path: str) -> int:
    """Open HID gadget device for writing."""
    fd = os.open(path, os.O_WRONLY)
    return fd


def write_report(fd: int, report: bytes) -> None:
    """Write HID report, handling EAGAIN and EPIPE when endpoint not ready."""
    max_retries = 100  # Maximum 10 seconds total
    retry_count = 0

    while True:
        try:
            os.write(fd, report)
            return
        except BlockingIOError as e:
            if e.errno != errno.EAGAIN:
                raise
            time.sleep(0.01)
        except BrokenPipeError as e:
            # EPIPE/ENOTCONN: USB gadget endpoint not yet established
            if e.errno not in (errno.EPIPE, errno.ENOTCONN):
                raise
            retry_count += 1
            if retry_count >= max_retries:
                log(f"ERROR: Failed to write HID report after {max_retries} retries")
                raise
            time.sleep(0.1)


def build_keyboard_report(mod_mask: int, pressed_usages: Set[int]) -> bytes:
    """Build 8-byte USB HID keyboard report."""
    keys = sorted(pressed_usages)[:6]
    while len(keys) < 6:
        keys.append(0)
    return bytes([mod_mask & 0xFF, 0x00] + keys)


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


def pick_keyboard_device() -> InputDevice:
    """Auto-detect keyboard device."""
    devs = [InputDevice(p) for p in list_devices()]
    keyboards = []
    for d in devs:
        caps = d.capabilities().get(ecodes.EV_KEY, [])
        if ecodes.KEY_A in caps and ecodes.KEY_ENTER in caps and ecodes.KEY_SPACE in caps:
            keyboards.append(d)

    if not keyboards:
        raise RuntimeError("No keyboard-like evdev device found.")

    keyboards.sort(key=lambda d: (("keyboard" not in (d.name or "").lower()), d.path))
    return keyboards[0]


def pick_mouse_device() -> Optional[InputDevice]:
    """Auto-detect mouse device. Returns None if no mouse found."""
    devs = [InputDevice(p) for p in list_devices()]
    mice = []

    for d in devs:
        caps = d.capabilities()
        rel_caps = caps.get(ecodes.EV_REL, [])
        key_caps = caps.get(ecodes.EV_KEY, [])

        has_rel_xy = ecodes.REL_X in rel_caps and ecodes.REL_Y in rel_caps
        has_buttons = any(btn in key_caps for btn in [ecodes.BTN_LEFT, ecodes.BTN_RIGHT, ecodes.BTN_MOUSE])

        if has_rel_xy and has_buttons:
            mice.append(d)

    if not mice:
        return None

    mice.sort(key=lambda d: ("mouse" not in (d.name or "").lower(), d.path))
    return mice[0]


def setup_hid_gadget(script_dir: Path) -> bool:
    """Call setup-hid-gadget.sh to configure USB gadget."""
    script_path = script_dir / "setup-hid-gadget.sh"
    if not script_path.exists():
        log(f"ERROR: setup-hid-gadget.sh not found at {script_path}")
        return False

    try:
        log("Setting up USB HID gadget...")
        result = subprocess.run(
            [str(script_path)],
            check=True,
            capture_output=True,
            text=True
        )
        log("USB HID gadget configured successfully")
        if result.stdout:
            print(result.stdout, file=sys.stderr, end='')
        return True
    except subprocess.CalledProcessError as e:
        log(f"ERROR: Failed to setup USB HID gadget: {e}")
        if e.stderr:
            print(e.stderr, file=sys.stderr, end='')
        return False


# ============================================================================
# Keyboard Bridge
# ============================================================================

def run_keyboard_bridge(args, hidfd: int) -> None:
    """Run keyboard bridge in main thread."""
    dev = InputDevice(args.event) if args.event else pick_keyboard_device()
    log(f"Using keyboard device: {dev.path} ({dev.name})")

    if args.grab:
        dev.grab()
        log("Grabbed keyboard device exclusively")

    pressed_keys: Set[int] = set()
    pressed_usages: Set[int] = set()
    mod_mask = 0

    # Send initial "all released"
    write_report(hidfd, build_keyboard_report(0, set()))

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

            if is_repeat:
                continue

            # Modifiers
            if e.code in MODIFIER_KEYS:
                bit = MODIFIER_KEYS[e.code]
                if is_down:
                    mod_mask |= bit
                elif is_up:
                    mod_mask &= (~bit & 0xFF)
                write_report(hidfd, build_keyboard_report(mod_mask, pressed_usages))
                continue

            # Regular keys
            hid_usage = KEY_TO_HID.get(e.code)
            if hid_usage is None:
                if args.show:
                    print(f"[!] Unmapped key: {key_event}", file=sys.stderr)
                continue

            if is_down:
                pressed_keys.add(e.code)
                pressed_usages.add(hid_usage)
            elif is_up:
                pressed_keys.discard(e.code)
                pressed_usages.discard(hid_usage)

            write_report(hidfd, build_keyboard_report(mod_mask, pressed_usages))

    except KeyboardInterrupt:
        pass
    finally:
        try:
            write_report(hidfd, build_keyboard_report(0, set()))
        except Exception:
            pass
        try:
            if args.grab:
                dev.ungrab()
        except Exception:
            pass


# ============================================================================
# Mouse Bridge (with dynamic attach/detach)
# ============================================================================

class MouseBridge:
    """Mouse bridge that handles dynamic attach/detach."""

    def __init__(self, args, hidfd: int):
        self.args = args
        self.hidfd = hidfd
        self.running = True
        self.current_device: Optional[InputDevice] = None

    def stop(self):
        """Stop the mouse bridge."""
        self.running = False

    def run(self):
        """Run mouse bridge with dynamic device detection."""
        log("Mouse bridge started (dynamic mode)")

        while self.running:
            # Try to find mouse device
            try:
                mouse_dev = pick_mouse_device()
            except Exception as e:
                log(f"Error detecting mouse: {e}")
                mouse_dev = None

            if mouse_dev is None:
                if self.current_device is not None:
                    log("Mouse device removed")
                    self.current_device = None
                # Wait before retrying
                time.sleep(1.0)
                continue

            # New mouse device found
            if self.current_device is None or self.current_device.path != mouse_dev.path:
                log(f"Mouse device detected: {mouse_dev.path} ({mouse_dev.name})")
                self.current_device = mouse_dev

                if self.args.grab:
                    try:
                        mouse_dev.grab()
                        log("Grabbed mouse device exclusively")
                    except Exception as e:
                        log(f"Failed to grab mouse: {e}")

            # Process mouse events
            try:
                self._process_mouse_events(mouse_dev)
            except OSError as e:
                # Device disappeared
                log(f"Mouse device error: {e}")
                if self.current_device:
                    try:
                        if self.args.grab:
                            self.current_device.ungrab()
                    except Exception:
                        pass
                    self.current_device = None
                time.sleep(0.5)
            except Exception as e:
                log(f"Unexpected mouse error: {e}")
                time.sleep(0.5)

        # Cleanup on exit
        if self.current_device:
            try:
                write_report(self.hidfd, build_mouse_report(0, 0, 0, 0))
            except Exception:
                pass
            try:
                if self.args.grab:
                    self.current_device.ungrab()
            except Exception:
                pass

    def _process_mouse_events(self, dev: InputDevice):
        """Process events from mouse device."""
        buttons = 0
        prev_buttons = 0
        dx_accum = 0
        dy_accum = 0
        wheel_accum = 0

        # Send initial state
        write_report(self.hidfd, build_mouse_report(0, 0, 0, 0))

        for e in dev.read_loop():
            if not self.running:
                break

            if e.type == ecodes.EV_REL:
                if e.code == ecodes.REL_X:
                    dx_accum += e.value
                elif e.code == ecodes.REL_Y:
                    dy_accum += e.value
                elif e.code == ecodes.REL_WHEEL:
                    wheel_accum += e.value

                if self.args.show:
                    rel_name = ecodes.REL.get(e.code, f"REL_{e.code}")
                    print(f"EV_REL {rel_name} value={e.value}", file=sys.stderr)

            elif e.type == ecodes.EV_KEY:
                if e.code in BUTTON_MAP:
                    bit = BUTTON_MAP[e.code]
                    if e.value == 1:
                        buttons |= bit
                    elif e.value == 0:
                        buttons &= ~bit

                    if self.args.show:
                        btn_name = ecodes.BTN.get(e.code, f"BTN_{e.code}")
                        print(f"EV_KEY {btn_name} value={e.value}", file=sys.stderr)

            elif e.type == ecodes.EV_SYN and e.code == ecodes.SYN_REPORT:
                if dx_accum != 0 or dy_accum != 0 or wheel_accum != 0 or buttons != prev_buttons:
                    write_report(self.hidfd, build_mouse_report(buttons, dx_accum, dy_accum, wheel_accum))
                    if self.args.show:
                        print(f"MOUSE: buttons={buttons:02x} dx={dx_accum} dy={dy_accum} wheel={wheel_accum}", file=sys.stderr)

                    dx_accum = 0
                    dy_accum = 0
                    wheel_accum = 0
                    prev_buttons = buttons


# ============================================================================
# Main
# ============================================================================

def main() -> int:
    ap = argparse.ArgumentParser(description="Pi 500+ HID bridge (keyboard + mouse)")
    ap.add_argument("--event", help="keyboard evdev path (auto if omitted)")
    ap.add_argument("--hidg-keyboard", default="/dev/hidg0", help="HID gadget for keyboard (default: /dev/hidg0)")
    ap.add_argument("--hidg-mouse", default="/dev/hidg1", help="HID gadget for mouse (default: /dev/hidg1)")
    ap.add_argument("--grab", action="store_true", help="exclusive grab input devices")
    ap.add_argument("--show", action="store_true", help="print events for debugging")
    ap.add_argument("--no-setup", action="store_true", help="skip calling setup-hid-gadget.sh")
    args = ap.parse_args()

    # Get script directory
    script_dir = Path(__file__).parent.resolve()

    # Setup HID gadget first (unless --no-setup)
    if not args.no_setup:
        if not setup_hid_gadget(script_dir):
            log("ERROR: Failed to setup HID gadget")
            return 1

    # Open HID devices
    try:
        keyboard_fd = open_hidg(args.hidg_keyboard)
        log(f"Opened keyboard HID: {args.hidg_keyboard}")
    except Exception as e:
        log(f"ERROR: Failed to open {args.hidg_keyboard}: {e}")
        return 1

    try:
        mouse_fd = open_hidg(args.hidg_mouse)
        log(f"Opened mouse HID: {args.hidg_mouse}")
    except Exception as e:
        log(f"ERROR: Failed to open {args.hidg_mouse}: {e}")
        os.close(keyboard_fd)
        return 1

    # Start mouse bridge in separate thread
    mouse_bridge = MouseBridge(args, mouse_fd)
    mouse_thread = threading.Thread(target=mouse_bridge.run, daemon=True)
    mouse_thread.start()

    # Run keyboard bridge in main thread
    try:
        run_keyboard_bridge(args, keyboard_fd)
    except KeyboardInterrupt:
        log("Shutting down...")
    finally:
        # Stop mouse bridge
        mouse_bridge.stop()
        mouse_thread.join(timeout=2.0)

        # Close HID devices
        try:
            os.close(keyboard_fd)
        except Exception:
            pass
        try:
            os.close(mouse_fd)
        except Exception:
            pass

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
