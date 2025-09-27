#!/usr/bin/env python3
"""
Enhanced Cavidy Node with dynamic role detection and Bluetooth WiFi provisioning.
Replaces separate tx.py and rx.py with a unified, hardware-aware node.
"""

import asyncio
import websockets
import json
import socket
import logging
import sys
import os
import signal
import time
from typing import Dict, Optional

# Import our custom modules
from hardware_detection import detect_hardware_capabilities, get_preferred_capture_device
from wifi_manager import WiFiManager
from bluetooth_provisioning import wait_for_wifi_or_provision

# Configuration
DEFAULT_HUB_HOST = "192.168.1.148"
DEFAULT_HUB_PORT = 8000
HEARTBEAT_INTERVAL = 5
RECONNECT_DELAY = 10

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class CavidyNode:
    def __init__(self, hub_host: str = DEFAULT_HUB_HOST, hub_port: int = DEFAULT_HUB_PORT):
        self.hub_host = hub_host
        self.hub_port = hub_port
        self.hub_url = f"ws://{hub_host}:{hub_port}/ws/nodes/"

        self.name = socket.gethostname()
        self.capabilities = {}
        self.role = "UNKNOWN"
        self.is_running = False
        self.websocket = None

        # Hardware and network managers
        self.wifi_manager = WiFiManager()

        # Streaming state
        self.is_streaming = False
        self.stream_process = None

    async def initialize(self) -> bool:
        """Initialize the node with network connectivity and hardware detection."""
        logger.info(f"Initializing Cavidy Node: {self.name}")

        # Step 1: Ensure WiFi connectivity
        if not await self._ensure_wifi_connectivity():
            logger.error("Failed to establish WiFi connectivity")
            return False

        # Step 2: Detect hardware capabilities
        self._detect_hardware()

        # Step 3: Determine role based on hardware
        self._determine_role()

        logger.info(f"Node initialized successfully. Role: {self.role}")
        return True

    async def _ensure_wifi_connectivity(self) -> bool:
        """Ensure WiFi connectivity, using Bluetooth provisioning if needed."""
        if self.wifi_manager.is_connected():
            current_ssid = self.wifi_manager.get_current_ssid()
            logger.info(f"Already connected to WiFi: {current_ssid}")
            return True

        logger.info("No WiFi connection detected, attempting provisioning...")

        # Use Bluetooth provisioning to get WiFi credentials
        device_name = f"Cavidy-{self.name}"
        success = await wait_for_wifi_or_provision(device_name, timeout=300)  # 5 minutes

        if success:
            logger.info("WiFi connectivity established via Bluetooth provisioning")
            return True
        else:
            logger.error("Failed to establish WiFi connectivity")
            return False

    def _detect_hardware(self):
        """Detect available hardware capabilities."""
        logger.info("Detecting hardware capabilities...")
        self.capabilities = detect_hardware_capabilities()

        logger.info(f"Hardware detection results:")
        logger.info(f"  Can transmit: {self.capabilities['can_transmit']}")
        logger.info(f"  Can receive: {self.capabilities['can_receive']}")
        logger.info(f"  Capture devices: {len(self.capabilities['capture_devices'])}")
        logger.info(f"  Output displays: {self.capabilities['output_info']['available']}")

    def _determine_role(self):
        """Determine node role based on detected hardware."""
        suggested_role = self.capabilities.get('role_suggestion', 'IDLE')

        # Allow environment variable override for testing
        env_role = os.getenv('CAVIDY_ROLE')
        if env_role and env_role in ['TX', 'RX', 'TX_RX', 'IDLE']:
            self.role = env_role
            logger.info(f"Role overridden by environment: {self.role}")
        else:
            self.role = suggested_role
            logger.info(f"Role determined by hardware: {self.role}")

    async def start(self):
        """Start the node and maintain connection to hub."""
        self.is_running = True

        while self.is_running:
            try:
                logger.info(f"Connecting to hub at {self.hub_url}")
                async with websockets.connect(self.hub_url) as websocket:
                    self.websocket = websocket

                    # Register with hub
                    await self._register_with_hub()

                    # Start heartbeat task
                    heartbeat_task = asyncio.create_task(self._heartbeat_loop())

                    try:
                        # Listen for commands
                        await self._listen_for_commands()
                    finally:
                        heartbeat_task.cancel()

            except websockets.exceptions.ConnectionClosed:
                logger.warning("Connection to hub lost")
            except Exception as e:
                logger.error(f"Connection error: {e}")

            if self.is_running:
                logger.info(f"Reconnecting in {RECONNECT_DELAY} seconds...")
                await asyncio.sleep(RECONNECT_DELAY)

    async def _register_with_hub(self):
        """Register this node with the hub."""
        registration_msg = {
            "type": "register",
            "name": self.name,
            "role": self.role,
            "capabilities": {
                "can_transmit": self.capabilities['can_transmit'],
                "can_receive": self.capabilities['can_receive'],
                "capture_devices": len(self.capabilities['capture_devices']),
                "output_available": self.capabilities['output_info']['available']
            },
            "hardware": {
                "capture_devices": [dev['path'] for dev in self.capabilities['capture_devices']],
                "preferred_capture": get_preferred_capture_device(),
                "displays": self.capabilities['output_info'].get('displays', [])
            },
            "network": {
                "wifi_ssid": self.wifi_manager.get_current_ssid(),
                "signal_strength": self.wifi_manager.get_signal_strength()
            }
        }

        await self.websocket.send(json.dumps(registration_msg))
        logger.info(f"Registered with hub: {registration_msg}")

    async def _heartbeat_loop(self):
        """Send periodic heartbeat messages to hub."""
        while True:
            try:
                heartbeat_msg = {
                    "type": "heartbeat",
                    "name": self.name,
                    "role": self.role,
                    "status": "streaming" if self.is_streaming else "online",
                    "network": {
                        "wifi_ssid": self.wifi_manager.get_current_ssid(),
                        "signal_strength": self.wifi_manager.get_signal_strength()
                    }
                }

                await self.websocket.send(json.dumps(heartbeat_msg))
                logger.debug(f"Sent heartbeat: {heartbeat_msg}")

                await asyncio.sleep(HEARTBEAT_INTERVAL)

            except Exception as e:
                logger.error(f"Heartbeat error: {e}")
                break

    async def _listen_for_commands(self):
        """Listen for commands from the hub."""
        async for message in self.websocket:
            try:
                data = json.loads(message)
                await self._handle_command(data)
            except json.JSONDecodeError:
                logger.error(f"Invalid JSON received: {message}")
            except Exception as e:
                logger.error(f"Error handling command: {e}")

    async def _handle_command(self, command: Dict):
        """Handle incoming commands from hub."""
        command_type = command.get("type")
        logger.info(f"Received command: {command}")

        if command_type == "route":
            await self._handle_route_command(command)
        elif command_type == "start_stream":
            await self._handle_start_stream(command)
        elif command_type == "stop_stream":
            await self._handle_stop_stream(command)
        elif command_type == "get_status":
            await self._handle_status_request(command)
        else:
            logger.warning(f"Unknown command type: {command_type}")

    async def _handle_route_command(self, command: Dict):
        """Handle route command for establishing connections."""
        source = command.get("from")
        target = command.get("to")

        if self.role in ["RX", "TX_RX"] and target == self.name:
            logger.info(f"Setting up route from {source} to {self.name}")
            # TODO: Implement actual HDMI stream reception
            await self._start_receiving_stream(source)

        elif self.role in ["TX", "TX_RX"] and source == self.name:
            logger.info(f"Starting transmission from {self.name} to {target}")
            # TODO: Implement actual HDMI stream transmission
            await self._start_transmitting_stream(target)

    async def _start_receiving_stream(self, source_node: str):
        """Start receiving HDMI stream from source node."""
        logger.info(f"Starting to receive stream from {source_node}")
        # TODO: Implement GStreamer pipeline for receiving stream
        self.is_streaming = True

    async def _start_transmitting_stream(self, target_node: str):
        """Start transmitting HDMI stream to target node."""
        logger.info(f"Starting to transmit stream to {target_node}")
        # TODO: Implement GStreamer pipeline for transmitting stream
        self.is_streaming = True

    async def _handle_start_stream(self, command: Dict):
        """Handle explicit start stream command."""
        logger.info("Starting stream on demand")
        self.is_streaming = True

    async def _handle_stop_stream(self, command: Dict):
        """Handle stop stream command."""
        logger.info("Stopping stream")
        self.is_streaming = False
        if self.stream_process:
            self.stream_process.terminate()
            self.stream_process = None

    async def _handle_status_request(self, command: Dict):
        """Handle status request from hub."""
        status = {
            "type": "status_response",
            "name": self.name,
            "role": self.role,
            "capabilities": self.capabilities,
            "is_streaming": self.is_streaming,
            "wifi_status": self.wifi_manager.get_status()
        }

        await self.websocket.send(json.dumps(status))

    def stop(self):
        """Stop the node gracefully."""
        logger.info("Stopping Cavidy Node...")
        self.is_running = False
        if self.stream_process:
            self.stream_process.terminate()


def signal_handler(signum, frame):
    """Handle system signals for graceful shutdown."""
    logger.info(f"Received signal {signum}, shutting down...")
    global node
    if node:
        node.stop()
    sys.exit(0)


async def main():
    """Main entry point."""
    global node

    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Parse command line arguments
    hub_host = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_HUB_HOST

    # Create and initialize node
    node = CavidyNode(hub_host)

    if await node.initialize():
        logger.info("Starting Cavidy Node...")
        await node.start()
    else:
        logger.error("Failed to initialize node")
        sys.exit(1)


if __name__ == "__main__":
    # Global node reference for signal handler
    node = None

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Node stopped by user")
    except Exception as e:
        logger.error(f"Node crashed: {e}")
        sys.exit(1)