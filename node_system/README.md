# Cavidy Node System

Enhanced node system with Bluetooth WiFi provisioning and hardware auto-detection.

## Features

🔧 **Hardware Auto-Detection**
- Automatically detects HDMI capture devices (USB capture cards)
- Detects HDMI output capabilities
- Dynamic role assignment (TX/RX/TX_RX/IDLE)

📻 **Bluetooth WiFi Provisioning**
- Automatic WiFi setup via Bluetooth when no connection
- No manual WiFi configuration needed
- Seamless hub connection after provisioning

🔄 **Dynamic Roles**
- Single `node.py` replaces separate `tx.py`/`rx.py`
- Hardware-based role determination
- Interchangeable TX/RX based on connected devices

## Architecture

```
┌─────────────────┐    ┌─────────────────┐
│   Node (Pi)     │    │      Hub        │
│                 │    │                 │
│ ┌─────────────┐ │    │ ┌─────────────┐ │
│ │Hardware     │ │    │ │Dashboard    │ │
│ │Detection    │ │    │ │WebSocket    │ │
│ └─────────────┘ │    │ │Server       │ │
│ ┌─────────────┐ │◄──►│ └─────────────┘ │
│ │WiFi Manager │ │    │ ┌─────────────┐ │
│ └─────────────┘ │    │ │Bluetooth    │ │
│ ┌─────────────┐ │    │ │Provisioning │ │
│ │Bluetooth    │ │    │ │Client       │ │
│ │Provisioning │ │    │ └─────────────┘ │
│ └─────────────┘ │    └─────────────────┘
└─────────────────┘
```

## Installation

1. **Copy files to your Raspberry Pi:**
```bash
scp -r node_system/ pi@your-pi-ip:~/cavidy-node/
```

2. **Run installation script:**
```bash
cd ~/cavidy-node/
chmod +x install.sh
./install.sh
```

3. **Test hardware detection:**
```bash
python3 hardware_detection.py
```

## Usage

### Manual Start
```bash
# Start node (will auto-detect hub or use Bluetooth provisioning)
python3 node.py

# Start with specific hub IP
python3 node.py 192.168.1.100
```

### Service Installation
```bash
# Install as system service
sudo cp cavidy-node.service /etc/systemd/system/
sudo systemctl enable cavidy-node
sudo systemctl start cavidy-node

# Check status
sudo systemctl status cavidy-node
```

## Hardware Setup

### For TX (Transmitter) Nodes:
- Connect USB HDMI capture device
- Connect HDMI source (laptop, game console, etc.)

### For RX (Receiver) Nodes:
- Connect micro HDMI to HDMI cable to monitor
- Ensure display output is available

### For TX_RX (Both) Nodes:
- Connect both USB capture device AND monitor
- Node can switch roles dynamically

## Configuration

### Environment Variables
```bash
# Force specific role (overrides hardware detection)
export CAVIDY_ROLE=TX        # TX, RX, TX_RX, or IDLE

# Custom device name for Bluetooth
export CAVIDY_DEVICE_NAME="My-Custom-Node"
```

### Hub Discovery
1. **Automatic (Recommended):** Node scans for hub on local network
2. **Manual:** Specify hub IP as command line argument
3. **Bluetooth Provisioning:** Hub can provision WiFi + its own IP

## Troubleshooting

### WiFi Issues
```bash
# Check WiFi status
python3 wifi_manager.py

# Manual WiFi configuration
sudo nano /etc/wpa_supplicant/wpa_supplicant.conf
```

### Bluetooth Issues
```bash
# Check Bluetooth status
sudo systemctl status bluetooth
sudo hciconfig

# Make discoverable manually
sudo bluetoothctl
[bluetooth]# discoverable on
```

### Hardware Detection Issues
```bash
# List video devices
ls -la /dev/video*

# Check device capabilities
v4l2-ctl --list-devices
v4l2-ctl --device=/dev/video0 --info
```

### Permission Issues
```bash
# Add user to required groups
sudo usermod -a -G video,bluetooth $USER

# Reboot after group changes
sudo reboot
```

## API Reference

### Registration Message
```json
{
  "type": "register",
  "name": "raspberrypi",
  "role": "TX_RX",
  "capabilities": {
    "can_transmit": true,
    "can_receive": true,
    "capture_devices": 1,
    "output_available": true
  },
  "hardware": {
    "capture_devices": ["/dev/video0"],
    "preferred_capture": "/dev/video0",
    "displays": [{"name": "HDMI-1", "connected": true}]
  },
  "network": {
    "wifi_ssid": "MyNetwork",
    "signal_strength": -45
  }
}
```

### Heartbeat Message
```json
{
  "type": "heartbeat",
  "name": "raspberrypi",
  "role": "TX_RX",
  "status": "online",
  "network": {
    "wifi_ssid": "MyNetwork",
    "signal_strength": -45
  }
}
```

### Route Command (from Hub)
```json
{
  "type": "route",
  "from": "tx-node",
  "to": "rx-node"
}
```

## Development

### Testing Individual Components
```bash
# Test hardware detection
python3 hardware_detection.py

# Test WiFi management
python3 wifi_manager.py

# Test Bluetooth provisioning
python3 bluetooth_provisioning.py
```

### Adding Custom Hardware
Edit `hardware_detection.py` to add support for new capture devices or display outputs.

### Extending Commands
Add new command handlers in `node.py` `_handle_command()` method.

## Dependencies

- **Python 3.8+**
- **BlueZ** (Bluetooth stack)
- **v4l-utils** (Video4Linux utilities)
- **GStreamer** (Media streaming framework)
- **wpa_supplicant** (WiFi client)

See `requirements.txt` for Python packages.