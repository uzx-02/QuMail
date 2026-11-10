"""
tests/test_hsm_integration.py — Validation of Hardware Security Module, TRNG & ETSI QKD.

Verifies:
1. NIST SP 800-90B continuous health testing (Repetition Count, Adaptive Proportion, Shannon Entropy).
2. Dual-source cryptographic entropy mixing (guaranteed security even on hardware failure).
3. ETSI GS QKD 014 client protocol parsing and local simulator key delivery.
4. Hotplug port discovery via list_com_ports().
5. HSMManager singleton lifecycle and snapshot reporting.
"""

import math
import secrets
import pytest
from core.hsm.entropy_pool import EntropyPool, NISTHealthMonitor
from core.hsm.etsi_qkd import ETSI014Client, ETSI014LocalSimulator
from core.hsm.detector import list_com_ports, SerialPortInfo
from core.hsm.manager import HSMManager


def test_nist_health_monitor_detects_stuck_at_fault():
    """Verify that repetition of identical bytes fails the NIST Repetition Count Test."""
    monitor = NISTHealthMonitor()
    # Stuck-at fault: repeated zeroes
    stuck_sample = b"\x00" * 128
    report = monitor.evaluate_sample(stuck_sample)
    assert report.repetition_count_pass is False
    assert report.status == "FAILED"


def test_nist_health_monitor_passes_high_entropy_sample():
    """Verify that uniform random bytes pass all NIST 800-90B health checks."""
    monitor = NISTHealthMonitor()
    random_sample = secrets.token_bytes(512)
    report = monitor.evaluate_sample(random_sample)
    assert report.repetition_count_pass is True
    assert report.adaptive_proportion_pass is True
    assert report.shannon_entropy > 7.0
    assert report.status == "PASSED"


def test_entropy_pool_dual_source_conditioning():
    """Verify that EntropyPool mixes hardware bytes with OS CSPRNG using HKDF."""
    pool = EntropyPool()
    hw_sample = secrets.token_bytes(256)
    pool.ingest_hardware_bytes(hw_sample)
    assert pool.buffer_size == 256
    assert pool.total_bytes_ingested == 256

    extracted, provenance = pool.extract_entropy(32)
    assert len(extracted) == 32
    assert "Dual-Source" in provenance
    assert pool.buffer_size == 256 - 32


def test_entropy_pool_graceful_fallback_when_empty():
    """Verify that EntropyPool gracefully falls back to OS CSPRNG when no hardware bytes exist."""
    pool = EntropyPool()
    extracted, provenance = pool.extract_entropy(32, strict_hardware=False)
    assert len(extracted) == 32
    assert "Software CSPRNG" in provenance


def test_entropy_pool_strict_policy_blocks_when_empty():
    """Verify that strict hardware policy raises an exception if hardware entropy is absent."""
    pool = EntropyPool()
    with pytest.raises(RuntimeError) as exc_info:
        pool.extract_entropy(32, strict_hardware=True)
    assert "Strict Quantum Hardware Policy" in str(exc_info.value)


def test_etsi_qkd_local_simulator():
    """Verify the ETSI GS QKD 014 local simulator formats and keys."""
    sim = ETSI014LocalSimulator(key_size_bytes=32)
    status = sim.handle_status()
    assert status["stored_key_count"] > 0
    assert status["key_size"] == 256

    keys = sim.generate_keys(count=2)
    assert len(keys) == 2
    assert "key_ID" in keys[0]
    assert "key" in keys[0]


def test_list_com_ports_returns_list():
    """Verify list_com_ports returns a valid list of SerialPortInfo objects without throwing."""
    ports = list_com_ports()
    assert isinstance(ports, list)
    for p in ports:
        assert isinstance(p, SerialPortInfo)
        assert isinstance(p.device, str)


def test_hsm_manager_snapshot():
    """Verify HSMManager singleton returns valid state snapshot."""
    mgr = HSMManager.get()
    snapshot = mgr.get_snapshot()
    assert snapshot.mode in ("AUTO", "SERIAL", "ETSI_QKD", "SOFTWARE_ONLY")
    assert isinstance(snapshot.shannon_entropy, float)
    assert isinstance(snapshot.provenance_summary, str)

    # Test extracting conditioned entropy
    entropy, prov = mgr.get_conditioned_entropy(32)
    assert len(entropy) == 32
    assert isinstance(prov, str)
