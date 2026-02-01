# pi500-usb-hid-keyboard

Turn your **Raspberry Pi 500+** into a **USB HID keyboard**.

Type on the Pi500+, and keystrokes appear on a connected host
(Windows or Linux) via USB-C OTG.

---

## ✨ Features

- Raspberry Pi 500+ acts as a **standard USB keyboard**
- Linux USB HID gadget (configfs)
- systemd-based auto startup
- Physical key mapping (works with both JIS and US keyboard layouts)
- No custom drivers required on host OS

---

## 🧩 Requirements

- Raspberry Pi 500+
- Raspberry Pi OS (Trixie)
- USB-C cable (data-capable)
- Root access (sudo)

⚠️ This project relies on USB gadget mode supported on Pi500+.

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
sudo reboot
```

1. Connect Pi500+ USB-C port to the host PC
2. Start typing on Pi500+
3. The host detects it as a USB keyboard

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

### Testing Status

- ✅ JIS layout: Fully tested on real hardware
- ⚠️ US layout: Implementation complete but not validated on hardware yet

Feedback and pull requests are welcome!

---

## 📜 License

MIT License
