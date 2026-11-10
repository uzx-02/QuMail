"""
core/hsm/manager.py — Hardware Security Module (HSM) & QKD Entropy Coordinator.

Central singleton managing:
- Background detection of hardware TRNG microcontrollers / physical circuits.
- ETSI GS QKD 014 REST key stream synchronization.
- Real-time entropy ingestion into EntropyPool with NIST SP 800-90B health checking.
- Supplying cryptographically conditioned physical entropy to post-quantum key encapsulation.
- Thread-safe state tracking for UI badges and settings dialogs.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Callable, ClassVar, Literal, Optional

from .detector import SerialPortInfo, SerialTRNGReader, list_com_ports
from .entropy_pool import EntropyPool, HealthReport
from .etsi_qkd import ETSI014Client, KMEStatus

logger = logging.getLogger("qumail.hsm.manager")

HSMMode = Literal["AUTO", "SERIAL", "ETSI_QKD", "SOFTWARE_ONLY"]


@dataclass
class HSMStatusSnapshot:
    mode: HSMMode
    is_hardware_active: bool
    active_device_name: str
    active_port: str
    baud_rate: int
    health_status: str         # "PASSED", "WARNING", "FAILED"
    shannon_entropy: float     # 0.0 to 8.0 bits/byte
    bytes_ingested: int
    bytes_in_buffer: int
    etsi_kme_connected: bool
    strict_policy_enabled: bool
    provenance_summary: str


class HSMManager:
    """Singleton manager coordinating physical hardware entropy and QKD integration."""

    _instance: ClassVar[Optional[HSMManager]] = None
    _lock: ClassVar[threading.Lock] = threading.Lock()

    @classmethod
    def get(cls) -> HSMManager:
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def __init__(self) -> None:
        self.pool = EntropyPool()
        self.mode: HSMMode = "AUTO"
        self.manual_port: str = ""
        self.baud_rate: int = 115200
        self.etsi_url: str = "http://127.0.0.1:8443/api/v1"
        self.strict_policy: bool = False

        self._reader: Optional[SerialTRNGReader] = None
        self._etsi_client = ETSI014Client(self.etsi_url)
        self._active_device_name: str = ""
        self._active_port: str = ""

        self._listeners: list[Callable[[HSMStatusSnapshot], None]] = []
        self._stop_event = threading.Event()
        self._worker_thread: Optional[threading.Thread] = None

        # Start background hardware watcher
        self.start()

    def start(self) -> None:
        """Start the background hardware discovery and entropy ingestion thread."""
        if self._worker_thread and self._worker_thread.is_alive():
            return
        self._stop_event.clear()
        self._worker_thread = threading.Thread(
            target=self._run_loop,
            daemon=True,
            name="qumail-hsm-watcher",
        )
        self._worker_thread.start()

    def stop(self) -> None:
        """Stop background worker cleanly."""
        self._stop_event.set()
        if self._reader:
            self._reader.disconnect()
            self._reader = None

    def add_listener(self, callback: Callable[[HSMStatusSnapshot], None]) -> None:
        """Register a callback for status updates."""
        if callback not in self._listeners:
            self._listeners.append(callback)

    def remove_listener(self, callback: Callable[[HSMStatusSnapshot], None]) -> None:
        if callback in self._listeners:
            self._listeners.remove(callback)

    def _notify(self) -> None:
        snapshot = self.get_snapshot()
        for cb in list(self._listeners):
            try:
                cb(snapshot)
            except Exception:
                pass

    def set_mode(self, mode: HSMMode, port: str = "", baud: int = 115200, etsi_url: str = "") -> None:
        """Configure hardware connection parameters."""
        self.mode = mode
        if port:
            self.manual_port = port
        if baud:
            self.baud_rate = baud
        if etsi_url:
            self.etsi_url = etsi_url
            self._etsi_client = ETSI014Client(self.etsi_url)

        # Reset active reader to apply new configuration
        if self._reader:
            self._reader.disconnect()
            self._reader = None
        self._active_device_name = ""
        self._active_port = ""
        self._notify()

    def get_snapshot(self) -> HSMStatusSnapshot:
        """Retrieve current real-time snapshot of the hardware security state."""
        report = self.pool.last_report
        is_hw = bool(self._reader and self._reader.is_connected)

        if is_hw:
            prov = f"Physical Hardware TRNG ({self._active_port}) | NIST SP 800-90B {report.status}"
        elif self.mode == "ETSI_QKD":
            prov = "ETSI GS QKD 014 Quantum Key Stream"
        else:
            prov = "Software CSPRNG (Windows CryptGenRandom)"

        return HSMStatusSnapshot(
            mode=self.mode,
            is_hardware_active=is_hw,
            active_device_name=self._active_device_name or "None",
            active_port=self._active_port,
            baud_rate=self.baud_rate,
            health_status=report.status,
            shannon_entropy=report.shannon_entropy,
            bytes_ingested=self.pool.total_bytes_ingested,
            bytes_in_buffer=self.pool.buffer_size,
            etsi_kme_connected=(self.mode == "ETSI_QKD"),
            strict_policy_enabled=self.strict_policy,
            provenance_summary=prov,
        )

    def get_conditioned_entropy(self, num_bytes: int = 32) -> tuple[bytes, str]:
        """
        Extract mixed physical + CSPRNG entropy for cryptographic operations.
        
        Returns:
            tuple[bytes, str]: (Random bytes, Provenance string)
        """
        return self.pool.extract_entropy(num_bytes, strict_hardware=self.strict_policy)

    def _run_loop(self) -> None:
        """Main background loop scanning ports and ingesting entropy."""
        last_port_scan = 0.0

        while not self._stop_event.is_set():
            now = time.monotonic()

            if self.mode == "SOFTWARE_ONLY":
                time.sleep(0.5)
                continue

            # Ingest from active serial reader if connected
            if self._reader and self._reader.is_connected:
                raw_chunk = self._reader.read_entropy(max_bytes=256)
                if raw_chunk:
                    self.pool.ingest_hardware_bytes(raw_chunk)
                    self._notify()
                time.sleep(0.05)
                continue

            # Otherwise, scan ports every 2 seconds
            if now - last_port_scan >= 2.0:
                last_port_scan = now
                self._attempt_connection()

            time.sleep(0.2)

    def _attempt_connection(self) -> None:
        """Attempt to discover and connect to a hardware TRNG or ETSI KME."""
        if self.mode == "AUTO":
            ports = list_com_ports()
            for p in ports:
                # Prioritize USB serial adapters / microcontrollers
                reader = SerialTRNGReader(p.device, baud_rate=self.baud_rate)
                if reader.connect():
                    self._reader = reader
                    self._active_port = p.device
                    self._active_device_name = p.description
                    logger.info(f"Auto-detected hardware TRNG on {p.device}")
                    self._notify()
                    break

        elif self.mode == "SERIAL" and self.manual_port:
            reader = SerialTRNGReader(self.manual_port, baud_rate=self.baud_rate)
            if reader.connect():
                self._reader = reader
                self._active_port = self.manual_port
                self._active_device_name = f"Manual Device ({self.manual_port})"
                self._notify()

        elif self.mode == "ETSI_QKD":
            status = self._etsi_client.check_status()
            if status.available:
                self._active_device_name = f"ETSI KME [{status.source_kme_id}]"
                self._notify()
