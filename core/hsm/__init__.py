"""
core/hsm — Hardware Security Module, Physical TRNG & ETSI GS QKD 014 Integration.
"""

from .entropy_pool import EntropyPool, HealthReport, NISTHealthMonitor
from .etsi_qkd import ETSI014Client, ETSI014LocalSimulator, KMEStatus, QKDKeyContainer
from .detector import SerialPortInfo, SerialTRNGReader, list_com_ports
from .manager import HSMManager, HSMStatusSnapshot, HSMMode

__all__ = [
    "EntropyPool",
    "HealthReport",
    "NISTHealthMonitor",
    "ETSI014Client",
    "ETSI014LocalSimulator",
    "KMEStatus",
    "QKDKeyContainer",
    "SerialPortInfo",
    "SerialTRNGReader",
    "list_com_ports",
    "HSMManager",
    "HSMStatusSnapshot",
    "HSMMode",
]
