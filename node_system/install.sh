#!/bin/bash
# Cavidy Node Installation Script
# Run this on each Raspberry Pi node

set -e

echo "🚀 Installing Cavidy Node System..."

# Update system
echo "📦 Updating system packages..."
sudo apt update && sudo apt upgrade -y

# Install system dependencies
echo "🔧 Installing system dependencies..."
sudo apt install -y \
    python3-pip \
    python3-venv \
    bluetooth \
    bluez \
    libbluetooth-dev \
    v4l-utils \
    wireless-tools \
    wpasupplicant \
    gstreamer1.0-tools \
    gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad \
    gstreamer1.0-plugins-ugly \
    gstreamer1.0-libav \
    libgstreamer1.0-dev \
    libgstreamer-plugins-base1.0-dev

# Install Python dependencies
echo "🐍 Installing Python dependencies..."
# Try system packages first
sudo apt install -y python3-websockets python3-psutil python3-bluetooth python3-full

# Install remaining packages with system override
pip3 install --break-system-packages pybluez asyncio-mqtt ujson || echo "Some packages may need manual installation"

# Set up permissions
echo "🔐 Setting up permissions..."
sudo usermod -a -G video $USER
sudo usermod -a -G bluetooth $USER

# Enable Bluetooth service
echo "📻 Enabling Bluetooth service..."
sudo systemctl enable bluetooth
sudo systemctl start bluetooth

# Make scripts executable
echo "⚡ Making scripts executable..."
chmod +x node.py
chmod +x install.sh

# Create systemd service (optional)
echo "🔄 Creating systemd service..."
cat > cavidy-node.service << EOF
[Unit]
Description=Cavidy Node Service
After=network.target bluetooth.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$(pwd)
ExecStart=/usr/bin/python3 $(pwd)/node.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

echo "📋 To install as a system service, run:"
echo "  sudo cp cavidy-node.service /etc/systemd/system/"
echo "  sudo systemctl enable cavidy-node"
echo "  sudo systemctl start cavidy-node"

echo ""
echo "✅ Cavidy Node installation complete!"
echo ""
echo "🎯 Usage:"
echo "  Test hardware detection: python3 hardware_detection.py"
echo "  Test WiFi management: python3 wifi_manager.py"
echo "  Run node: python3 node.py [hub_ip]"
echo ""
echo "📝 Note: Reboot recommended to ensure all permissions take effect"