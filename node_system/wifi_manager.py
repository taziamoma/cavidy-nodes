#!/usr/bin/env python3
"""
WiFi management utilities for Cavidy nodes.
Handles WiFi connection, configuration, and network status.
"""

import os
import subprocess
import json
import time
import logging
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

class WiFiManager:
    def __init__(self):
        self.wpa_supplicant_conf = "/etc/wpa_supplicant/wpa_supplicant.conf"
        self.interface = self.get_wifi_interface()

    def get_wifi_interface(self) -> Optional[str]:
        """Get the primary WiFi interface name."""
        try:
            result = subprocess.run(['iwconfig'], capture_output=True, text=True)
            for line in result.stdout.split('\n'):
                if 'IEEE 802.11' in line:
                    interface = line.split()[0]
                    return interface

            # Fallback: look for wlan interfaces
            result = subprocess.run(['ip', 'link', 'show'], capture_output=True, text=True)
            for line in result.stdout.split('\n'):
                if 'wlan' in line and 'state' in line:
                    interface = line.split(':')[1].strip().split('@')[0]
                    return interface

            return 'wlan0'  # Default fallback
        except Exception as e:
            logger.error(f"Could not detect WiFi interface: {e}")
            return 'wlan0'

    def is_connected(self) -> bool:
        """Check if WiFi is currently connected."""
        try:
            result = subprocess.run([
                'iwgetid', self.interface, '--raw'
            ], capture_output=True, text=True)

            # If iwgetid returns a non-empty SSID, we're connected
            return bool(result.stdout.strip())
        except Exception:
            # Fallback: check if we have an IP address
            try:
                result = subprocess.run([
                    'ip', 'addr', 'show', self.interface
                ], capture_output=True, text=True)
                return 'inet ' in result.stdout
            except Exception:
                return False

    def get_current_ssid(self) -> Optional[str]:
        """Get the SSID of the currently connected network."""
        try:
            result = subprocess.run([
                'iwgetid', self.interface, '--raw'
            ], capture_output=True, text=True)
            ssid = result.stdout.strip()
            return ssid if ssid else None
        except Exception as e:
            logger.error(f"Could not get current SSID: {e}")
            return None

    def get_signal_strength(self) -> Optional[int]:
        """Get current WiFi signal strength."""
        try:
            result = subprocess.run([
                'iwconfig', self.interface
            ], capture_output=True, text=True)

            for line in result.stdout.split('\n'):
                if 'Signal level' in line:
                    # Extract signal level (e.g., "Signal level=-45 dBm")
                    parts = line.split('Signal level=')[1].split()[0]
                    return int(parts.replace('dBm', ''))
            return None
        except Exception as e:
            logger.error(f"Could not get signal strength: {e}")
            return None

    def scan_networks(self) -> List[Dict]:
        """Scan for available WiFi networks."""
        networks = []
        try:
            # Trigger a scan
            subprocess.run(['iwlist', self.interface, 'scan'],
                         capture_output=True, timeout=10)

            # Get scan results
            result = subprocess.run([
                'iwlist', self.interface, 'scan'
            ], capture_output=True, text=True, timeout=10)

            if result.returncode == 0:
                networks = self._parse_iwlist_output(result.stdout)

        except Exception as e:
            logger.error(f"WiFi scan failed: {e}")

        return networks

    def _parse_iwlist_output(self, output: str) -> List[Dict]:
        """Parse iwlist scan output."""
        networks = []
        current_network = {}

        for line in output.split('\n'):
            line = line.strip()

            if 'Cell' in line and 'Address:' in line:
                if current_network:
                    networks.append(current_network)
                current_network = {
                    'bssid': line.split('Address: ')[1],
                    'ssid': '',
                    'quality': 0,
                    'signal_level': 0,
                    'encryption': 'Open'
                }
            elif 'ESSID:' in line and current_network:
                ssid = line.split('ESSID:')[1].strip('"')
                current_network['ssid'] = ssid
            elif 'Quality=' in line and current_network:
                quality_part = line.split('Quality=')[1].split()[0]
                if '/' in quality_part:
                    num, den = quality_part.split('/')
                    current_network['quality'] = int(num) / int(den) * 100
            elif 'Signal level=' in line and current_network:
                signal = line.split('Signal level=')[1].split()[0]
                current_network['signal_level'] = int(signal.replace('dBm', ''))
            elif 'Encryption key:' in line and current_network:
                if 'off' in line:
                    current_network['encryption'] = 'Open'
                else:
                    current_network['encryption'] = 'WPA/WPA2'

        if current_network:
            networks.append(current_network)

        return networks

    def connect_to_network(self, ssid: str, password: str = None) -> bool:
        """Connect to a WiFi network."""
        logger.info(f"Attempting to connect to {ssid}")

        try:
            # Create network configuration
            network_config = self._create_network_config(ssid, password)

            # Add to wpa_supplicant configuration
            if self._add_network_to_config(network_config):
                # Reconfigure wpa_supplicant
                if self._reconfigure_wpa_supplicant():
                    # Wait for connection
                    return self._wait_for_connection(timeout=30)

        except Exception as e:
            logger.error(f"Failed to connect to {ssid}: {e}")

        return False

    def _create_network_config(self, ssid: str, password: str = None) -> str:
        """Create wpa_supplicant network configuration."""
        if password:
            return f'''
network={{
    ssid="{ssid}"
    psk="{password}"
    key_mgmt=WPA-PSK
}}'''
        else:
            return f'''
network={{
    ssid="{ssid}"
    key_mgmt=NONE
}}'''

    def _add_network_to_config(self, network_config: str) -> bool:
        """Add network configuration to wpa_supplicant.conf."""
        try:
            # Read existing configuration
            existing_config = ""
            if os.path.exists(self.wpa_supplicant_conf):
                with open(self.wpa_supplicant_conf, 'r') as f:
                    existing_config = f.read()

            # Remove existing network with same SSID (if any)
            lines = existing_config.split('\n')
            filtered_lines = []
            skip_network = False

            for line in lines:
                if line.strip().startswith('network={'):
                    skip_network = True
                elif line.strip() == '}' and skip_network:
                    skip_network = False
                    continue

                if not skip_network:
                    filtered_lines.append(line)

            # Add new network configuration
            new_config = '\n'.join(filtered_lines) + network_config + '\n'

            # Write back to file
            with open(self.wpa_supplicant_conf, 'w') as f:
                f.write(new_config)

            return True

        except Exception as e:
            logger.error(f"Failed to update wpa_supplicant config: {e}")
            return False

    def _reconfigure_wpa_supplicant(self) -> bool:
        """Reconfigure wpa_supplicant to use new settings."""
        try:
            # Kill existing wpa_supplicant
            subprocess.run(['sudo', 'killall', 'wpa_supplicant'],
                         capture_output=True)
            time.sleep(1)

            # Start new wpa_supplicant
            subprocess.run([
                'sudo', 'wpa_supplicant', '-B', '-i', self.interface,
                '-c', self.wpa_supplicant_conf
            ], capture_output=True)

            # Start DHCP client
            subprocess.run([
                'sudo', 'dhclient', self.interface
            ], capture_output=True)

            return True

        except Exception as e:
            logger.error(f"Failed to reconfigure wpa_supplicant: {e}")
            return False

    def _wait_for_connection(self, timeout: int = 30) -> bool:
        """Wait for WiFi connection to be established."""
        start_time = time.time()

        while time.time() - start_time < timeout:
            if self.is_connected():
                logger.info("WiFi connection established")
                return True
            time.sleep(1)

        logger.error("WiFi connection timeout")
        return False

    def disconnect(self) -> bool:
        """Disconnect from current WiFi network."""
        try:
            subprocess.run(['sudo', 'killall', 'wpa_supplicant'],
                         capture_output=True)
            subprocess.run(['sudo', 'ip', 'link', 'set', self.interface, 'down'],
                         capture_output=True)
            subprocess.run(['sudo', 'ip', 'link', 'set', self.interface, 'up'],
                         capture_output=True)
            return True
        except Exception as e:
            logger.error(f"Failed to disconnect: {e}")
            return False

    def get_status(self) -> Dict:
        """Get comprehensive WiFi status."""
        return {
            'interface': self.interface,
            'connected': self.is_connected(),
            'ssid': self.get_current_ssid(),
            'signal_strength': self.get_signal_strength(),
            'available_networks': len(self.scan_networks())
        }

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    wifi = WiFiManager()
    status = wifi.get_status()
    print(json.dumps(status, indent=2))