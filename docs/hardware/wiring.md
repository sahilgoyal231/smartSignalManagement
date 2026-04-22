# Smart Signal Hardware: Wiring & BOM

This document describes the physical setup for the two primary hardware components of the Smart Signal System.

## 1. Vehicle Sender Unit (VSU)
The VSU is installed in emergency vehicles (ambulances, fire engines). It continuously broadcasts the vehicle's location and priority via LoRa.

### Bill of Materials (BOM)
- **Raspberry Pi Zero 2 W** (Compute)
- **NEO-6M GPS Module** (Location)
- **SX1278 LoRa Module (433MHz)** (Communication)
- **12V to 5V Step-Down Converter** (Power from vehicle battery)

### Pin/Wiring Diagram
| RPi Zero 2W Pin | Component | Connection |
|---|---|---|
| Pin 2 (5V) | GPS Module | VCC |
| Pin 6 (GND) | GPS Module | GND |
| Pin 8 (TxD) | GPS Module | RxD |
| Pin 10 (RxD) | GPS Module | TxD |
| Pin 1 (3.3V) | LoRa Module | VCC |
| Pin 9 (GND) | LoRa Module | GND |
| Pin 19 (MOSI) | LoRa Module | MOSI |
| Pin 21 (MISO) | LoRa Module | MISO |
| Pin 23 (SCLK) | LoRa Module | SCK |
| Pin 24 (CE0) | LoRa Module | NSS |

---

## 2. Intersection Edge Node
The Edge Node is installed at traffic light controller cabinets. It listens for VSU beacons, runs local YOLO/Audio inference, and commands the lights.

### Bill of Materials (BOM)
- **Raspberry Pi 4 Model B (4GB or 8GB)** (Compute / ML Inference)
- **Google Coral Edge TPU (USB)** (ML Hardware Acceleration)
- **SX1278 LoRa Module (433MHz)** (Receiver)
- **USB Microphone Array** (Acoustic Siren Detection)
- **USB Web Camera (1080p)** (Visual Ambulance Detection)
- **RS-485 USB Adapter** (Interface to Traffic Controller)

### Pin/Wiring Diagram
The LoRa module uses the same SPI wiring as the VSU above. The camera, mic, and Coral TPU all connect via the RPi 4's USB 3.0 ports for maximum bandwidth. The RS-485 adapter connects to a USB 2.0 port.

1. **LoRa Module:** Connect to SPI0 pins.
2. **Coral TPU:** Connect to USB 3.0 (Blue).
3. **Webcam:** Connect to USB 3.0 (Blue).
4. **Microphone:** Connect to USB 2.0.
5. **RS-485 Adapter:** Connect to USB 2.0 (wires to Traffic Cabinet serial port).
