#!/usr/bin/env python3
"""
Hardware detection utilities for Cavidy nodes.
Detects HDMI capture devices and output capabilities.
"""

import os
import glob
import subprocess
import json
import logging
from pathlib import Path
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)

def get_video_devices() -> List[str]:
    """Get all available video devices."""
    return sorted(glob.glob('/dev/video*'))

def is_capture_device(device_path: str) -> bool:
    """Check if a video device is a real HDMI capture device (not Pi built-in)."""
    try:
        # Get device driver information first
        result = subprocess.run([
            'v4l2-ctl', '--device', device_path, '--info'
        ], capture_output=True, text=True, timeout=5)

        if result.returncode != 0:
            return False

        device_info = result.stdout.lower()

        # Exclude Pi built-in devices that aren't real capture devices
        pi_builtin_drivers = [
            'pispbe',           # Pi ISP backend
            'rpi-hevc-dec',     # Pi hardware decoder
            'rpi-h264-dec',     # Pi hardware decoder
            'rpi-hevc-enc',     # Pi hardware encoder
            'rpi-h264-enc',     # Pi hardware encoder
            'bcm2835-codec',    # Pi codec
            'bcm2835-isp'       # Pi ISP
        ]

        # Check if this is a Pi built-in device - EXCLUDE these
        for builtin in pi_builtin_drivers:
            if builtin in device_info:
                logger.debug(f"Excluding Pi built-in device: {device_path} ({builtin})")
                return False

        # Look for USB Video Class devices (most HDMI capture cards)
        if 'uvcvideo' in device_info:
            logger.info(f"Found USB capture device: {device_path}")
            return True

        # Check for other external capture device indicators
        external_indicators = [
            'usb',
            'hdmi',
            'capture card',
            'video capture',
            'elgato',
            'avermedia',
            'blackmagic'
        ]

        for indicator in external_indicators:
            if indicator in device_info:
                logger.info(f"Found external capture device: {device_path} ({indicator})")
                return True

        # If none of the above, it's likely not a real capture device
        logger.debug(f"Not a real capture device: {device_path}")
        return False

    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        logger.warning(f"Could not check device {device_path}: {e}")
        return False

def get_device_info(device_path: str) -> Dict:
    """Get detailed information about a video device."""
    info = {
        'path': device_path,
        'name': f'video{device_path.split("video")[-1]}',
        'is_capture': False,
        'formats': [],
        'resolutions': []
    }

    try:
        # Get device name and capabilities
        result = subprocess.run([
            'v4l2-ctl', '--device', device_path, '--info'
        ], capture_output=True, text=True, timeout=5)

        if result.returncode == 0:
            lines = result.stdout.split('\n')
            for line in lines:
                if 'Card type' in line:
                    info['card_type'] = line.split(':')[1].strip()
                elif 'Driver name' in line:
                    info['driver'] = line.split(':')[1].strip()

        # Check if it's a real capture device
        info['is_capture'] = is_capture_device(device_path)

        # Get supported formats
        if info['is_capture']:
            fmt_result = subprocess.run([
                'v4l2-ctl', '--device', device_path, '--list-formats-ext'
            ], capture_output=True, text=True, timeout=5)

            if fmt_result.returncode == 0:
                info['formats'] = parse_v4l2_formats(fmt_result.stdout)

    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        logger.warning(f"Could not get info for {device_path}: {e}")

    return info

def parse_v4l2_formats(output: str) -> List[Dict]:
    """Parse v4l2-ctl format output."""
    formats = []
    current_format = None

    for line in output.split('\n'):
        line = line.strip()
        if 'Pixel Format:' in line:
            if current_format:
                formats.append(current_format)
            current_format = {
                'pixel_format': line.split(':')[1].strip(),
                'resolutions': []
            }
        elif 'Size:' in line and current_format:
            size_info = line.split(':')[1].strip()
            current_format['resolutions'].append(size_info)

    if current_format:
        formats.append(current_format)

    return formats

def check_hdmi_output() -> Dict:
    """Check for HDMI output capabilities."""
    hdmi_info = {
        'available': True,  # Pi always has HDMI output capability
        'displays': [],
        'active_display': None
    }

    try:
        # Check for active displays using xrandr (if available)
        result = subprocess.run(['xrandr'], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            hdmi_info['displays'] = parse_xrandr_output(result.stdout)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    # Fallback: Pi always has framebuffer even without monitor connected
    if not hdmi_info['displays']:
        fb_devices = glob.glob('/dev/fb*')
        if fb_devices:
            hdmi_info['displays'] = [{'name': 'framebuffer', 'connected': False}]
        else:
            # Even without framebuffer detected, Pi has HDMI output capability
            hdmi_info['displays'] = [{'name': 'hdmi', 'connected': False}]

    logger.info(f"HDMI output capability: {hdmi_info['available']}")
    return hdmi_info

def parse_xrandr_output(output: str) -> List[Dict]:
    """Parse xrandr output to find connected displays."""
    displays = []

    for line in output.split('\n'):
        if ' connected' in line:
            parts = line.split()
            display_name = parts[0]
            is_primary = 'primary' in line

            displays.append({
                'name': display_name,
                'connected': True,
                'primary': is_primary
            })

    return displays

def detect_hardware_capabilities() -> Dict:
    """Main function to detect all hardware capabilities."""
    logger.info("Detecting hardware capabilities...")

    capabilities = {
        'can_transmit': False,
        'can_receive': False,
        'capture_devices': [],
        'output_info': {},
        'role_suggestion': 'IDLE'
    }

    # Detect video capture devices
    video_devices = get_video_devices()
    logger.info(f"Found {len(video_devices)} video devices")

    for device in video_devices:
        device_info = get_device_info(device)
        if device_info['is_capture']:
            capabilities['capture_devices'].append(device_info)
            capabilities['can_transmit'] = True
            logger.info(f"Found capture device: {device}")

    # Detect HDMI output
    capabilities['output_info'] = check_hdmi_output()
    capabilities['can_receive'] = capabilities['output_info']['available']

    # Suggest role based on capabilities
    if capabilities['can_transmit'] and capabilities['can_receive']:
        capabilities['role_suggestion'] = 'TX_RX'
    elif capabilities['can_transmit']:
        capabilities['role_suggestion'] = 'TX'
    elif capabilities['can_receive']:
        capabilities['role_suggestion'] = 'RX'
    else:
        capabilities['role_suggestion'] = 'IDLE'

    logger.info(f"Hardware detection complete. Role suggestion: {capabilities['role_suggestion']}")
    return capabilities

def get_preferred_capture_device() -> str:
    """Get the best capture device for transmission."""
    capabilities = detect_hardware_capabilities()

    if not capabilities['capture_devices']:
        return None

    # Prefer USB Video Class devices (common for HDMI capture cards)
    for device in capabilities['capture_devices']:
        if 'uvcvideo' in device.get('driver', '').lower():
            return device['path']

    # Fallback to first available real capture device
    return capabilities['capture_devices'][0]['path']

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    caps = detect_hardware_capabilities()
    print(json.dumps(caps, indent=2))