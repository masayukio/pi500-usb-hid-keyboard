# pi500-usb-hid-keyboard

```text
+--------------------+             +-------------------+
| Windows / Linux PC | -- USB-C -- | Raspberry Pi 500+ |
+--------------------+             +-------------------+
```

Turn your **Raspberry Pi 500+** into a **USB HID keyboard and mouse**.

Type on the Pi500+ built-in keyboard and use a USB mouse, and all input appears
on a connected host (Windows or Linux) via USB-C OTG.

---

## ✨ Features

- Raspberry Pi 500+ acts as a **standard USB keyboard and mouse**
- Bridges built-in keyboard and external USB mouse to USB HID gadgets
- **Multiple keyboard layouts supported**: US and JIS (Japanese)
- Dynamic mouse attach/detach support
- Linux USB HID gadget (configfs)
- systemd-based auto startup (USB gadget automatically configured at boot)
- No custom drivers required on host OS

---

## 🧩 Requirements

- Raspberry Pi 500+
- Raspberry Pi OS (Trixie)
- USB-C cable (data-capable? I'm using USB4 cable)
- Root access (sudo)

⚠️ This project relies on USB gadget mode supported on Pi 500+. A low-voltage warning may be displayed.

### 🔌 USB OTG Setup (Required)

This project requires USB OTG peripheral mode on Raspberry Pi 500+.

#### Enable OTG Peripheral Mode

Edit /boot/firmware/config.txt:

```shell
sudo nano /boot/firmware/config.txt
```

Add the following lines:

```text
[all]
dtoverlay=dwc2,dr_mode=peripheral
```

Then reboot:

```shell
sudo reboot
```

This forces the SoC USB controller into peripheral (device) mode.

---

## 🚀 Quick Start

```bash
git clone https://github.com/masayukio/pi500-usb-hid-keyboard.git
cd pi500-usb-hid-keyboard
sudo ./install.sh
```

During installation, you'll be prompted to select your keyboard layout:
- **1) US** (default) - Standard US keyboard layout
- **2) JIS** - Japanese keyboard layout (106/109 key)

After installation:
1. Connect Pi500+ USB-C port to the host PC
2. Start typing on Pi500+ built-in keyboard
3. Optionally connect a USB mouse to the Pi500+
4. The host detects them as a USB keyboard and mouse

**Note:** The service starts automatically after installation. After reboot, the USB gadget is automatically reconfigured at boot time. Mouse can be attached or detached at any time.

---

## 🗑 Uninstall

```bash
sudo ./uninstall.sh
sudo reboot
```

Removes:
- systemd service
- USB HID gadget
- Installed files

Reboot is recommended after uninstall.

---

## ⚙️ Configuration

### Keyboard Layout

The keyboard layout is stored in `/opt/pi500-hid-keyboard/keyboard-layout.conf`. To change the layout after installation:

1. Edit the configuration file:
   ```bash
   sudo nano /opt/pi500-hid-keyboard/keyboard-layout.conf
   ```

2. Change `KEYBOARD_LAYOUT=us` to `KEYBOARD_LAYOUT=jis` (or vice versa)

3. Restart the service:
   ```bash
   sudo systemctl restart pi500-hid-keyboard.service
   ```

### Testing Status

- ✅ **JIS layout**: Fully tested on real hardware
- ⚠️ **US layout**: Implementation complete but not validated on hardware yet

Feedback and pull requests are welcome!

---

## 📜 License

MIT License
