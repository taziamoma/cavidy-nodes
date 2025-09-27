#!/usr/bin/env python3
"""
Bluetooth WiFi provisioning for Cavidy nodes.
Allows nodes to receive WiFi credentials via Bluetooth when not connected.
"""

import json
import asyncio
import logging
import time
from typing import Dict, Optional
import bluetooth
import threading
from wifi_manager import WiFiManager

logger = logging.getLogger(__name__)

class BluetoothProvisioning:
    def __init__(self, device_name: str = "Cavidy-Node"):
        self.device_name = device_name
        self.wifi_manager = WiFiManager()
        self.server_socket = None
        self.is_running = False
        self.provisioning_complete = False

    def start_provisioning(self) -> bool:
        """Start Bluetooth provisioning service."""
        if self.wifi_manager.is_connected():
            logger.info("Already connected to WiFi, skipping provisioning")
            return True

        logger.info("Starting Bluetooth WiFi provisioning...")

        try:
            # Make device discoverable
            self._make_discoverable()

            # Start Bluetooth server
            self.is_running = True
            self._start_bluetooth_server()

            return self.provisioning_complete

        except Exception as e:
            logger.error(f"Bluetooth provisioning failed: {e}")
            return False

    def _make_discoverable(self):
        """Make the Bluetooth device discoverable."""
        try:
            # Enable Bluetooth and make discoverable
            import subprocess
            subprocess.run(['sudo', 'hciconfig', 'hci0', 'up'], check=True)
            subprocess.run(['sudo', 'hciconfig', 'hci0', 'discoverable'], check=True)

            # Set device name
            subprocess.run([
                'sudo', 'bluetoothctl', 'system-alias', self.device_name
            ], check=True)

            logger.info(f"Bluetooth device '{self.device_name}' is now discoverable")

        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to make device discoverable: {e}")
            raise

    def _start_bluetooth_server(self):
        """Start Bluetooth RFCOMM server to receive WiFi credentials."""
        try:
            # Create server socket
            self.server_socket = bluetooth.BluetoothSocket(bluetooth.RFCOMM)
            self.server_socket.bind(("", bluetooth.PORT_ANY))
            self.server_socket.listen(1)

            port = self.server_socket.getsockname()[1]
            logger.info(f"Bluetooth server listening on RFCOMM channel {port}")

            # Advertise service
            bluetooth.advertise_service(
                self.server_socket,
                "Cavidy WiFi Provisioning",
                service_id="00000000-0000-0000-0000-000000000001",
                service_classes=[bluetooth.SERIAL_PORT_CLASS],
                profiles=[bluetooth.SERIAL_PORT_PROFILE]
            )

            # Accept connections
            timeout_counter = 0
            max_timeout = 300  # 5 minutes

            while self.is_running and timeout_counter < max_timeout:
                try:
                    # Set socket timeout for non-blocking operation
                    self.server_socket.settimeout(1)
                    client_socket, client_info = self.server_socket.accept()

                    logger.info(f"Bluetooth client connected: {client_info}")

                    # Handle the client connection
                    if self._handle_client(client_socket):
                        self.provisioning_complete = True
                        break

                    client_socket.close()

                except bluetooth.BluetoothError:
                    timeout_counter += 1
                    continue
                except Exception as e:
                    logger.error(f"Error accepting connection: {e}")
                    break

            if timeout_counter >= max_timeout:
                logger.warning("Bluetooth provisioning timed out")

        except Exception as e:
            logger.error(f"Bluetooth server error: {e}")

        finally:
            self._cleanup()

    def _handle_client(self, client_socket) -> bool:
        """Handle WiFi credential exchange with connected client."""
        try:
            # Send status message
            status_msg = {
                "type": "status",
                "device_name": self.device_name,
                "message": "Ready for WiFi credentials"
            }
            client_socket.send(json.dumps(status_msg).encode('utf-8'))

            # Receive WiFi credentials
            data = client_socket.recv(1024).decode('utf-8')
            credentials = json.loads(data)

            logger.info(f"Received WiFi credentials for SSID: {credentials.get('ssid')}")

            if self._validate_credentials(credentials):
                # Attempt to connect to WiFi
                success = self.wifi_manager.connect_to_network(
                    credentials['ssid'],
                    credentials.get('password')
                )

                response = {
                    "type": "response",
                    "success": success,
                    "message": "Connected to WiFi" if success else "Failed to connect"
                }

                client_socket.send(json.dumps(response).encode('utf-8'))
                return success

            else:
                error_response = {
                    "type": "error",
                    "message": "Invalid credentials format"
                }
                client_socket.send(json.dumps(error_response).encode('utf-8'))
                return False

        except Exception as e:
            logger.error(f"Error handling client: {e}")
            return False

    def _validate_credentials(self, credentials: Dict) -> bool:
        """Validate received WiFi credentials."""
        required_fields = ['ssid']
        return all(field in credentials for field in required_fields)

    def _cleanup(self):
        """Clean up Bluetooth resources."""
        self.is_running = False
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass

        # Stop advertising
        try:
            bluetooth.stop_advertising()
        except:
            pass

        logger.info("Bluetooth provisioning service stopped")

    def stop(self):
        """Stop the provisioning service."""
        self.is_running = False


class BluetoothProvisioningClient:
    """Client side for sending WiFi credentials to nodes."""

    def __init__(self):
        self.discovered_devices = []

    def scan_for_nodes(self, scan_time: int = 10) -> List[Dict]:
        """Scan for discoverable Cavidy nodes."""
        logger.info(f"Scanning for Bluetooth devices for {scan_time} seconds...")

        try:
            nearby_devices = bluetooth.discover_devices(
                duration=scan_time,
                lookup_names=True
            )

            cavidy_nodes = []
            for addr, name in nearby_devices:
                if "cavidy" in name.lower():
                    cavidy_nodes.append({
                        'address': addr,
                        'name': name
                    })
                    logger.info(f"Found Cavidy node: {name} ({addr})")

            return cavidy_nodes

        except Exception as e:
            logger.error(f"Bluetooth scan failed: {e}")
            return []

    def provision_node(self, node_address: str, ssid: str, password: str = None) -> bool:
        """Send WiFi credentials to a specific node."""
        logger.info(f"Provisioning node {node_address} with SSID: {ssid}")

        try:
            # Connect to node
            socket = bluetooth.BluetoothSocket(bluetooth.RFCOMM)
            socket.connect((node_address, 1))  # RFCOMM channel 1

            # Receive status message
            status_data = socket.recv(1024).decode('utf-8')
            status = json.loads(status_data)
            logger.info(f"Node status: {status.get('message')}")

            # Send WiFi credentials
            credentials = {
                'ssid': ssid,
                'password': password
            }
            socket.send(json.dumps(credentials).encode('utf-8'))

            # Receive response
            response_data = socket.recv(1024).decode('utf-8')
            response = json.loads(response_data)

            success = response.get('success', False)
            message = response.get('message', 'Unknown response')

            logger.info(f"Provisioning result: {message}")
            socket.close()

            return success

        except Exception as e:
            logger.error(f"Failed to provision node: {e}")
            return False


async def wait_for_wifi_or_provision(device_name: str = None, timeout: int = 60) -> bool:
    """
    Main function: Wait for WiFi connection or start Bluetooth provisioning.
    Returns True if WiFi is available, False otherwise.
    """
    wifi_manager = WiFiManager()

    # Quick check if already connected
    if wifi_manager.is_connected():
        logger.info("Already connected to WiFi")
        return True

    # Wait a bit for automatic connection
    logger.info("Waiting for WiFi connection...")
    for i in range(10):  # Wait up to 10 seconds
        if wifi_manager.is_connected():
            logger.info("WiFi connection established")
            return True
        await asyncio.sleep(1)

    # Start Bluetooth provisioning
    logger.info("No WiFi connection, starting Bluetooth provisioning")
    if device_name is None:
        import socket
        device_name = f"Cavidy-{socket.gethostname()}"

    provisioning = BluetoothProvisioning(device_name)

    # Run provisioning in separate thread
    def run_provisioning():
        return provisioning.start_provisioning()

    # Create thread for blocking Bluetooth operations
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future = executor.submit(run_provisioning)

        # Wait for either completion or timeout
        try:
            result = await asyncio.wait_for(
                asyncio.wrap_future(future),
                timeout=timeout
            )
            return result
        except asyncio.TimeoutError:
            logger.warning("Bluetooth provisioning timed out")
            provisioning.stop()
            return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Test provisioning
    async def test():
        result = await wait_for_wifi_or_provision("Test-Node", timeout=30)
        print(f"Provisioning result: {result}")

    asyncio.run(test())