"""WiFi hotspot management via NetworkManager/nmcli."""

from __future__ import annotations

import logging
import re
import subprocess

logger = logging.getLogger(__name__)


class HotspotManager:
    def __init__(self, ssid: str, band: str = "5GHz", password: str | None = None) -> None:
        self.ssid = ssid
        self.band = band
        self.password = password
        self.connection_name = ssid

    def is_available(self) -> bool:
        try:
            result = subprocess.run(
                ["nmcli", "--version"],
                capture_output=True,
                check=True,
                text=True,
            )
        except (FileNotFoundError, subprocess.CalledProcessError):
            return False
        return result.returncode == 0

    def start(self) -> bool:
        command = [
            "nmcli",
            "device",
            "wifi",
            "hotspot",
            "con-name",
            self.connection_name,
            "ssid",
            self.ssid,
            "band",
            "a" if "5" in self.band else "bg",
        ]
        if self.password:
            command.extend(["password", self.password])
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                check=False,
                text=True,
            )
        except FileNotFoundError:
            logger.warning("Cannot start hotspot: nmcli is not available.")
            return False

        if result.returncode == 0:
            logger.info("Started hotspot %s", self.ssid)
            return True
        logger.warning("Hotspot start failed: %s", (result.stderr or result.stdout).strip())
        return False

    def stop(self) -> bool:
        try:
            result = subprocess.run(
                ["nmcli", "connection", "down", self.connection_name],
                capture_output=True,
                check=False,
                text=True,
            )
        except FileNotFoundError:
            logger.warning("Cannot stop hotspot: nmcli is not available.")
            return False

        if result.returncode == 0:
            logger.info("Stopped hotspot %s", self.ssid)
            return True
        logger.warning("Hotspot stop failed: %s", (result.stderr or result.stdout).strip())
        return False

    def get_ip(self) -> str | None:
        try:
            result = subprocess.run(
                ["nmcli", "-t", "-f", "IP4.ADDRESS", "connection", "show", self.connection_name],
                capture_output=True,
                check=False,
                text=True,
            )
        except FileNotFoundError:
            return None
        if result.returncode != 0:
            return None
        match = re.search(r"(\d+\.\d+\.\d+\.\d+)", result.stdout)
        return match.group(1) if match else None

    def status(self) -> dict[str, object]:
        available = self.is_available()
        ip_address = self.get_ip() if available else None
        return {
            "available": available,
            "ssid": self.ssid,
            "band": self.band,
            "connection_name": self.connection_name,
            "ip_address": ip_address,
            "manual_instructions": None if available else self.get_manual_instructions(),
        }

    def get_manual_instructions(self) -> str:
        security_hint = (
            "Set a WPA3/WPA2 passphrase before sharing the network."
            if not self.password
            else "Use the same passphrase when you create the hotspot manually."
        )
        return (
            "NetworkManager (nmcli) is not available.\n"
            "To create a WiFi hotspot manually:\n"
            f"  1. Create a hotspot with SSID: {self.ssid}\n"
            f"  2. Preferred band: {self.band}\n"
            f"  3. {security_hint}\n"
            "  4. Note the IP address assigned to your WiFi interface\n"
            '  5. Run: osk start "Operation Name"'
        )
