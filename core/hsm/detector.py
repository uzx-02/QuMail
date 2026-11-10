"""
core/hsm/detector.py — USB Serial COM Port Discovery & Hardware TRNG Hotplug Detection.

Discovers physical hardware devices (ESP32, Arduino, microcontroller noise generators)
across Windows COM ports without mandatory external dependencies.
Uses Windows Registry (HARDWARE\\DEVICEMAP\\SERIALCOMM) as the primary discovery
mechanism, with optional pyserial acceleration if present.
"""

from __future__ import annotations

import logging
import os
import sys
import time
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("qumail.hsm.detector")


@dataclass
class SerialPortInfo:
    device: str          # e.g., 'COM3'
    description: str     # e.g., 'USB Serial Port (COM3)'
    hw_id: str           # e.g., 'USB\\VID_10C4&PID_EA60'


def list_com_ports() -> list[SerialPortInfo]:
    """Discover available serial COM ports on the local system."""
    ports: list[SerialPortInfo] = []

    # Method 1: Try pyserial if installed
    try:
        import serial.tools.list_ports
        for p in serial.tools.list_ports.comports():
            ports.append(SerialPortInfo(
                device=p.device,
                description=p.description or p.device,
                hw_id=p.hwid or "",
            ))
        if ports:
            return ports
    except Exception:
        pass

    # Method 2: Windows Registry query (100% native, zero dependencies)
    if sys.platform == "win32":
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"HARDWARE\DEVICEMAP\SERIALCOMM",
                0,
                winreg.KEY_READ,
            )
            count = winreg.QueryInfoKey(key)[1]
            for i in range(count):
                name, port, _ = winreg.EnumValue(key, i)
                ports.append(SerialPortInfo(
                    device=str(port),
                    description=f"Serial Device ({port}) [{name}]",
                    hw_id=name,
                ))
            winreg.CloseKey(key)
        except Exception:
            pass

    return ports


class SerialTRNGReader:
    """Non-blocking reader sampling physical entropy bytes from a serial COM port."""

    def __init__(self, port: str, baud_rate: int = 115200, timeout: float = 0.5) -> None:
        self.port = port
        self.baud_rate = baud_rate
        self.timeout = timeout
        self._handle: Any = None
        self._connected = False

    def connect(self) -> bool:
        """Attempt to open connection to the serial port."""
        try:
            import serial
            self._handle = serial.Serial(
                port=self.port,
                baudrate=self.baud_rate,
                timeout=self.timeout,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
            )
            self._connected = True
            logger.info(f"Connected to TRNG hardware on {self.port} at {self.baud_rate} baud.")
            return True
        except ImportError:
            # Fallback to direct Windows device path open if possible
            if sys.platform == "win32":
                try:
                    dev_path = f"\\\\.\\{self.port}"
                    self._handle = open(dev_path, "rb", buffering=0)
                    self._connected = True
                    return True
                except Exception as exc:
                    logger.debug(f"Direct device open failed for {self.port}: {exc}")
            return False
        except Exception as exc:
            logger.debug(f"Failed to connect to {self.port}: {exc}")
            self._connected = False
            return False

    def read_entropy(self, max_bytes: int = 256) -> bytes:
        """Read available raw entropy bytes from the hardware device."""
        if not self._connected or not self._handle:
            return b""
        try:
            if hasattr(self._handle, "in_waiting"):
                available = self._handle.in_waiting
                if available > 0:
                    return self._handle.read(min(available, max_bytes))
                return b""
            if hasattr(self._handle, "read"):
                # Direct device read
                return self._handle.read(max_bytes)
        except Exception as exc:
            logger.warning(f"Error reading from {self.port}: {exc}")
            self.disconnect()
        return b""

    def disconnect(self) -> None:
        if self._handle:
            try:
                self._handle.close()
            except Exception:
                pass
            self._handle = None
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected
