"""
core/offline_translator.py — QuMail Offline Neural Translation Subsystem.

Provides local, private, on-device translation using quantized Meta NLLB-200
(nllb-200-distilled-600M INT8 via CTranslate2 & SentencePiece).
Includes:
- Windows hardware compatibility scanner (RAM, Disk, CPU)
- Direct HTTPS model downloader with byte-level progress and cancellation
- FLORES-200 inference engine with automatic script detection & 120s idle auto-unload
- Windows DPAPI-encrypted local translation cache & history audit manager
"""

from __future__ import annotations

import ctypes
import gc
import hashlib
import json
import logging
import os
import shutil
import sys
import threading
import time
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.config import get_user_data_dir

logger = logging.getLogger("qumail.offline_translator")

# Model artifacts hosted publicly on Hugging Face (no authentication required)
HF_BASE_URL = "https://huggingface.co/JustFrederik/nllb-200-distilled-600M-ct2-int8/resolve/main"
# Pinned SHA-256 values for Hugging Face revision
# 302d78f00e6fdb50a1064059df7c392b735e9d05.  A size check is never an
# integrity check; every artifact is verified before it becomes usable.
MODEL_FILES = [
    ("config.json", 159, "0c2f6fa2057c7264d052fb4a62ba3476eeae70487acddfa8e779a53a00cbf44c"),
    ("shared_vocabulary.txt", 2_568_098, "a132a83330f45514c2476eb81d1d69b3c41762264d16ce0a7ea982e5d6c728e5"),
    ("sentencepiece.bpe.model", 4_852_054, "14bb8dfb35c0ffdea7bc01e56cea38b9e3d5efcdcb9c251d6b40538e1aab555a"),
    ("model.bin", 622_595_991, "ed1beaf75134de7505315a5223162f56acff397eff6b50638a500d3936fe707b"),
]

# FLORES-200 Language Code Mapping for QuMail Indian languages + English
FLORES_MAP = {
    "en": "eng_Latn",
    "eng": "eng_Latn",
    "eng_Latn": "eng_Latn",
    "hi": "hin_Deva",
    "hin": "hin_Deva",
    "hin_Deva": "hin_Deva",
    "mr": "mar_Deva",
    "mar": "mar_Deva",
    "mar_Deva": "mar_Deva",
}


# ============================================================================
# Windows DPAPI Encryption for Local Translation Vault
# ============================================================================

def _ensure_dll_directories() -> None:
    """Ensure Windows finds vendored native DLLs for SentencePiece and CTranslate2."""
    if sys.platform != "win32" or not hasattr(os, "add_dll_directory"):
        return

    candidate_bases = []
    if getattr(sys, "frozen", False):
        candidate_bases.extend([
            getattr(sys, "_MEIPASS", ""),
            os.path.dirname(sys.executable),
            os.path.join(os.path.dirname(sys.executable), "_internal"),
        ])
    candidate_bases.extend([
        os.path.dirname(os.path.abspath(__file__)),
        os.path.abspath("."),
        os.path.abspath("_internal"),
    ])

    for b in candidate_bases:
        if not b or not os.path.isdir(b):
            continue
        for sub in ("", "sentencepiece.libs", "numpy.libs", "ctranslate2", "sentencepiece"):
            target = os.path.join(b, sub) if sub else b
            if os.path.isdir(target):
                try:
                    os.add_dll_directory(target)
                except Exception:
                    pass


def _dpapi_protect(data_bytes: bytes) -> bytes:
    """Encrypt byte payload with Windows DPAPI (CryptProtectData)."""
    if sys.platform != "win32":
        # Fallback for non-Windows testing environments
        import base64
        return b"DEV_B64:" + base64.b64encode(data_bytes)

    try:
        from ctypes import wintypes

        class DATA_BLOB(ctypes.Structure):
            _fields_ = [
                ("cbData", wintypes.DWORD),
                ("pbData", ctypes.POINTER(ctypes.c_char)),
            ]

        data_in = DATA_BLOB(
            len(data_bytes),
            ctypes.cast(ctypes.create_string_buffer(data_bytes), ctypes.POINTER(ctypes.c_char)),
        )
        data_out = DATA_BLOB()
        if not ctypes.windll.crypt32.CryptProtectData(
            ctypes.byref(data_in), "QuMail-TransVault", None, None, None, 0, ctypes.byref(data_out)
        ):
            raise RuntimeError("CryptProtectData failed")
        encrypted = ctypes.string_at(data_out.pbData, data_out.cbData)
        ctypes.windll.kernel32.LocalFree(data_out.pbData)
        return encrypted
    except Exception as exc:
        logger.warning("DPAPI encryption failed, using fallback: %s", exc)
        import base64
        return b"DEV_B64:" + base64.b64encode(data_bytes)


def _dpapi_unprotect(cipher_bytes: bytes) -> bytes:
    """Decrypt byte payload with Windows DPAPI (CryptUnprotectData)."""
    if cipher_bytes.startswith(b"DEV_B64:"):
        import base64
        return base64.b64decode(cipher_bytes[8:])

    if sys.platform != "win32":
        import base64
        return base64.b64decode(cipher_bytes)

    try:
        from ctypes import wintypes

        class DATA_BLOB(ctypes.Structure):
            _fields_ = [
                ("cbData", wintypes.DWORD),
                ("pbData", ctypes.POINTER(ctypes.c_char)),
            ]

        data_in = DATA_BLOB(
            len(cipher_bytes),
            ctypes.cast(ctypes.create_string_buffer(cipher_bytes), ctypes.POINTER(ctypes.c_char)),
        )
        data_out = DATA_BLOB()
        if not ctypes.windll.crypt32.CryptUnprotectData(
            ctypes.byref(data_in), None, None, None, None, 0, ctypes.byref(data_out)
        ):
            raise RuntimeError("CryptUnprotectData failed")
        decrypted = ctypes.string_at(data_out.pbData, data_out.cbData)
        ctypes.windll.kernel32.LocalFree(data_out.pbData)
        return decrypted
    except Exception as exc:
        logger.warning("DPAPI decryption failed: %s", exc)
        raise RuntimeError(f"Failed to decrypt translation vault: {exc}")


# ============================================================================
# Hardware Compatibility Scanner
# ============================================================================

def check_hardware_compatibility(data_dir: Optional[Path] = None) -> Dict[str, Any]:
    """
    Inspect host Windows system specs (RAM, Free RAM, Free Disk, CPU cores)
    and return a clear readiness verdict for running quantized NLLB-200.
    """
    total_ram_gb = 8.0
    free_ram_gb = 4.0

    if sys.platform == "win32":
        try:
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
                total_ram_gb = stat.ullTotalPhys / (1024 ** 3)
                free_ram_gb = stat.ullAvailPhys / (1024 ** 3)
        except Exception as exc:
            logger.debug("Failed reading Windows GlobalMemoryStatusEx: %s", exc)

    # Free disk on the QuMail data directory drive
    if data_dir is None:
        data_dir = get_user_data_dir()

    try:
        target_path = str(data_dir)
        free_disk_gb = shutil.disk_usage(target_path).free / (1024 ** 3)
    except Exception:
        free_disk_gb = 10.0

    cpu_cores = os.cpu_count() or 4

    # Readiness Verdict
    # Optimal: >= 8.0 GB Total RAM, >= 2.0 GB Free RAM, >= 1.5 GB Free Disk
    # Compatible: >= 6.0 GB Total RAM, >= 1.3 GB Free RAM, >= 1.0 GB Free Disk
    # Limited: below thresholds
    warning = None
    if total_ram_gb >= 7.5 and free_ram_gb >= 1.9 and free_disk_gb >= 1.5:
        verdict = "optimal"
        estimated_speed = "Fast (~1–2 sec per email)"
    elif total_ram_gb >= 5.5 and free_ram_gb >= 1.2 and free_disk_gb >= 1.0:
        verdict = "compatible"
        estimated_speed = "Moderate (~3–5 sec per email)"
    else:
        verdict = "limited"
        estimated_speed = "Slow (~5–10 sec per email)"
        reasons = []
        if total_ram_gb < 5.5:
            reasons.append(f"Only {total_ram_gb:.1f} GB Total RAM detected")
        elif free_ram_gb < 1.2:
            reasons.append(f"Only {free_ram_gb:.1f} GB Free RAM available")
        if free_disk_gb < 1.0:
            reasons.append(f"Only {free_disk_gb:.1f} GB Free Disk available")
        warning = f"{', '.join(reasons)} — running local inference may slow down your system."

    return {
        "status": "ok",
        "total_ram_gb": round(total_ram_gb, 1),
        "free_ram_gb": round(free_ram_gb, 1),
        "free_disk_gb": round(free_disk_gb, 1),
        "cpu_cores": cpu_cores,
        "verdict": verdict,
        "estimated_speed": estimated_speed,
        "warning": warning,
    }


# ============================================================================
# Offline Translator Service
# ============================================================================

class OfflineTranslatorService:
    """
    Manages model download, CTranslate2 + SentencePiece inference,
    auto-unloading after 120s of inactivity, and DPAPI-encrypted translation logs.
    """

    def __init__(self, base_data_dir: Optional[Path] = None) -> None:
        self.base_data_dir = Path(base_data_dir) if base_data_dir else get_user_data_dir()
        self.model_dir = self.base_data_dir / "translation_models" / "nllb-200-distilled-600M-int8"
        self.vault_file = self.base_data_dir / "translations_vault.bin"

        self._translator = None
        self._sp_processor = None
        self._model_lock = threading.RLock()
        self._unload_timer: Optional[threading.Timer] = None
        self._idle_timeout: float = 120.0  # seconds

        # Download tracking state
        self._download_lock = threading.Lock()
        self._download_thread: Optional[threading.Thread] = None
        self._cancel_requested: bool = False
        self._cancel_translation: bool = False
        self._download_state: Dict[str, Any] = {
            "isDownloading": False,
            "progress": 0,
            "downloadedMB": 0.0,
            "totalMB": 628.7,
            "currentFile": "",
            "error": None,
        }

    # ------------------------------------------------------------------------
    # Model Status & Download Management
    # ------------------------------------------------------------------------

    def is_model_installed(self) -> bool:
        """Fast presence check; cryptographic verification occurs before use."""
        if not self.model_dir.is_dir():
            return False

        for f, expected_size, _expected_sha256 in MODEL_FILES:
            p = self.model_dir / f
            if not p.is_file() or p.stat().st_size != expected_size:
                return False
        return True

    @staticmethod
    def _sha256_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def verify_model_integrity(self) -> tuple[bool, str]:
        """Verify every installed artifact against the pinned release digest."""
        for filename, expected_size, expected_sha256 in MODEL_FILES:
            artifact = self.model_dir / filename
            if not artifact.is_file() or artifact.stat().st_size != expected_size:
                return False, f"{filename} is missing or has an unexpected size."
            if self._sha256_file(artifact) != expected_sha256:
                return False, f"{filename} failed its SHA-256 integrity check."
        return True, "Model integrity verified."

    def get_installed_size_mb(self) -> float:
        """Return total size of the installed model directory in MB."""
        if not self.model_dir.is_dir():
            return 0.0
        total_bytes = 0
        try:
            for p in self.model_dir.iterdir():
                if p.is_file() and not p.name.endswith(".part"):
                    total_bytes += p.stat().st_size
        except Exception:
            pass
        return round(total_bytes / (1024 * 1024), 1)

    def get_status(self) -> Dict[str, Any]:
        """Return full translation status dictionary for the React UI."""
        installed = self.is_model_installed()
        with self._download_lock:
            state = dict(self._download_state)
            if installed:
                state["isDownloading"] = False
                state["progress"] = 100
                state["error"] = None
                self._download_state["isDownloading"] = False
                self._download_state["progress"] = 100

        # Fast non-blocking pointer check for RAM status
        loaded = bool(self._translator is not None and self._sp_processor is not None)

        return {
            "isInstalled": installed,
            "isDownloading": False if installed else state["isDownloading"],
            "progress": 100 if installed else state["progress"],
            "downloadedMB": state["totalMB"] if installed else state["downloadedMB"],
            "totalMB": state["totalMB"],
            "currentFile": "" if installed else state["currentFile"],
            "error": None if installed else state["error"],
            "modelSizeMB": self.get_installed_size_mb() if installed else 0.0,
            "isModelLoadedInRam": loaded,
        }

    def download_model(self) -> Dict[str, Any]:
        """Start asynchronous background model download."""
        if self.is_model_installed():
            return {"status": "already_installed"}

        with self._download_lock:
            if self._download_state["isDownloading"]:
                return {"status": "already_downloading"}
            self._cancel_requested = False
            self._download_state["isDownloading"] = True
            self._download_state["progress"] = 0
            self._download_state["downloadedMB"] = 0.0
            self._download_state["totalMB"] = 628.7
            self._download_state["currentFile"] = ""
            self._download_state["error"] = None

        self._download_thread = threading.Thread(
            target=self._run_download_worker,
            daemon=True,
            name="nllb-model-downloader",
        )
        self._download_thread.start()
        return {"status": "started"}

    def cancel_download(self) -> Dict[str, Any]:
        """Signal cancellation and clean up temporary partial files."""
        with self._download_lock:
            self._cancel_requested = True
            self._download_state["error"] = "Download cancelled by user."

        # Wait briefly for thread to terminate and clean up .part files
        self._clean_part_files()
        return {"status": "cancelled"}

    def delete_model(self) -> Dict[str, Any]:
        """Unload model from RAM and delete files from disk."""
        self.unload_model()
        try:
            if self.model_dir.is_dir():
                shutil.rmtree(self.model_dir)
            with self._download_lock:
                self._download_state["isDownloading"] = False
                self._download_state["progress"] = 0
                self._download_state["downloadedMB"] = 0.0
                self._download_state["error"] = None
            return {"status": "deleted"}
        except Exception as exc:
            logger.error("Failed to delete model directory: %s", exc)
            return {"status": "error", "error": str(exc)}

    def _clean_part_files(self) -> None:
        """Remove any leftover *.part files in model_dir."""
        try:
            if self.model_dir.is_dir():
                for p in self.model_dir.glob("*.part"):
                    try:
                        p.unlink(missing_ok=True)
                    except Exception:
                        pass
        except Exception:
            pass

    def _run_download_worker(self) -> None:
        """Download artifacts sequentially via standard HTTPS streaming."""
        self.model_dir.mkdir(parents=True, exist_ok=True)
        total_expected_bytes = sum(size for _, size, _ in MODEL_FILES)
        total_downloaded_bytes = 0

        try:
            for filename, expected_size, expected_sha256 in MODEL_FILES:
                if self._cancel_requested:
                    break

                target_file = self.model_dir / filename
                part_file = self.model_dir / f"{filename}.part"

                # Never trust an earlier partial or tampered download.  A
                # correct existing file can be reused without a network call.
                if target_file.is_file() and target_file.stat().st_size == expected_size:
                    if self._sha256_file(target_file) == expected_sha256:
                        total_downloaded_bytes += expected_size
                        continue
                    target_file.unlink(missing_ok=True)

                with self._download_lock:
                    self._download_state["currentFile"] = filename

                file_url = f"{HF_BASE_URL}/{filename}"
                parsed_url = urllib.parse.urlsplit(file_url)
                if (parsed_url.scheme.lower() != "https" or not parsed_url.hostname or
                        parsed_url.username is not None or parsed_url.password is not None):
                    raise RuntimeError("Translation model download endpoint must be a direct HTTPS URL.")
                req = urllib.request.Request(
                    file_url,
                    headers={"User-Agent": "QuMail/1.0 (Windows; Post-Quantum Mail Client)"},
                )

                chunk_size = 65536  # 64 KB
                digest = hashlib.sha256()
                with urllib.request.urlopen(req, timeout=30) as response, open(part_file, "wb") as out_f:
                    while True:
                        if self._cancel_requested:
                            break
                        chunk = response.read(chunk_size)
                        if not chunk:
                            break
                        out_f.write(chunk)
                        digest.update(chunk)
                        total_downloaded_bytes += len(chunk)

                        pct = min(100, int((total_downloaded_bytes / total_expected_bytes) * 100))
                        with self._download_lock:
                            self._download_state["progress"] = pct
                            self._download_state["downloadedMB"] = round(total_downloaded_bytes / (1024 * 1024), 1)

                if self._cancel_requested:
                    self._clean_part_files()
                    break

                if not part_file.is_file() or part_file.stat().st_size != expected_size:
                    raise RuntimeError(f"Downloaded {filename} has an unexpected size.")
                if digest.hexdigest() != expected_sha256:
                    raise RuntimeError(f"Downloaded {filename} failed its SHA-256 integrity check.")

                # Atomic replace
                if part_file.is_file():
                    os.replace(part_file, target_file)

            if not self._cancel_requested:
                with self._download_lock:
                    self._download_state["isDownloading"] = False
                    self._download_state["progress"] = 100
                    self._download_state["currentFile"] = ""
                    self._download_state["error"] = None
            else:
                with self._download_lock:
                    self._download_state["isDownloading"] = False
                    self._clean_part_files()

        except Exception as exc:
            logger.error("Model download error: %s", exc)
            self._clean_part_files()
            with self._download_lock:
                self._download_state["isDownloading"] = False
                self._download_state["error"] = f"Network error during download: {exc}"

    # ------------------------------------------------------------------------
    # Neural Inference & Auto-Unload Engine
    # ------------------------------------------------------------------------

    def _ensure_model_loaded(self) -> None:
        """Load CTranslate2 Translator and SentencePiece into memory if needed."""
        with self._model_lock:
            if self._translator is not None and self._sp_processor is not None:
                return

            if not self.is_model_installed():
                raise RuntimeError("NLLB-200 INT8 model is not installed. Please download it first.")
            integrity_ok, integrity_message = self.verify_model_integrity()
            if not integrity_ok:
                raise RuntimeError(f"NLLB-200 model integrity check failed: {integrity_message} Re-download the model.")

            # Ensure Windows resolves extension dependencies in frozen PyInstaller or dev environments
            _ensure_dll_directories()

            import ctranslate2
            import sentencepiece

            sp_path = str(self.model_dir / "sentencepiece.bpe.model")
            self._sp_processor = sentencepiece.SentencePieceProcessor(model_file=sp_path)
            self._translator = ctranslate2.Translator(
                str(self.model_dir),
                device="cpu",
                compute_type="int8",
                intra_threads=min(4, os.cpu_count() or 2),
            )
            logger.info("Loaded NLLB-200 INT8 model into RAM")

    def _reset_unload_timer(self) -> None:
        """Reset the 120-second inactivity timer to auto-unload model."""
        with self._model_lock:
            if self._unload_timer:
                self._unload_timer.cancel()
            self._unload_timer = threading.Timer(self._idle_timeout, self.unload_model)
            self._unload_timer.daemon = True
            self._unload_timer.start()

    def unload_model(self) -> Dict[str, Any]:
        """Unload model from RAM and reclaim memory."""
        was_loaded = False
        with self._model_lock:
            if self._unload_timer:
                self._unload_timer.cancel()
                self._unload_timer = None
            if self._translator is not None or self._sp_processor is not None:
                was_loaded = True
                logger.info("Unloading NLLB-200 model from RAM")
                self._translator = None
                self._sp_processor = None
                gc.collect()
        return {"status": "ok", "wasLoaded": was_loaded, "isModelLoadedInRam": False}

    def cancel_translation(self) -> Dict[str, Any]:
        """Signal ongoing translation to abort immediately."""
        self._cancel_translation = True
        return {"status": "cancelled"}

    @staticmethod
    def detect_script(text: str, target_lang: str) -> str:
        """
        Auto-detect source script:
        If Devanagari characters dominate, source is Hindi or Marathi.
        Otherwise default to English (eng_Latn).
        """
        devanagari_count = sum(1 for c in text if "\u0900" <= c <= "\u097F")
        is_devanagari = devanagari_count >= max(3, int(len(text) * 0.15))

        if is_devanagari:
            # If target is Hindi, assume Marathi source; if Marathi, assume Hindi
            if target_lang in ("hi", "hin_Deva"):
                return "mar_Deva"
            if target_lang in ("mr", "mar_Deva"):
                return "hin_Deva"
            return "hin_Deva"
        return "eng_Latn"

    def translate_text(self, text: str, target_lang: str) -> Dict[str, Any]:
        """
        Translate plain text into target language using quantized NLLB-200.
        Returns dict with status, translatedText, sourceLang, targetLang.
        """
        if not text or not text.strip():
            return {
                "status": "ok",
                "translatedText": text,
                "sourceLang": "eng_Latn",
                "targetLang": target_lang,
            }

        tgt_code = FLORES_MAP.get(target_lang.lower(), "hin_Deva")
        src_code = self.detect_script(text, tgt_code)

        if src_code == tgt_code:
            return {
                "status": "ok",
                "translatedText": text,
                "sourceLang": src_code,
                "targetLang": tgt_code,
            }

        self._cancel_translation = False
        self._ensure_model_loaded()
        self._reset_unload_timer()

        # Split by newline paragraphs to maintain email formatting
        paragraphs = text.split("\n")
        translated_paras = []

        with self._model_lock:
            sp = self._sp_processor
            translator = self._translator

        if sp is None or translator is None:
            return {
                "status": "error",
                "error": "Translation model could not be loaded into memory",
                "translatedText": "",
                "sourceLang": src_code,
                "targetLang": tgt_code,
            }

        for para in paragraphs:
            if self._cancel_translation:
                logger.info("Translation cancelled by user in mid-progress.")
                return {
                    "status": "cancelled",
                    "error": "Translation cancelled by user",
                    "translatedText": "",
                    "sourceLang": src_code,
                    "targetLang": tgt_code,
                }

            trimmed = para.strip()
            if not trimmed:
                translated_paras.append("")
                continue

            # SentencePiece tokenization with source language token and EOS
            tokens = [src_code] + sp.encode(trimmed, out_type=str) + ["</s>"]
            results = translator.translate_batch(
                [tokens],
                target_prefix=[[tgt_code]],
                beam_size=2,
                max_decoding_length=512,
            )

            out_tokens = results[0].hypotheses[0]
            # Strip leading target language code if outputted
            if out_tokens and out_tokens[0] == tgt_code:
                out_tokens = out_tokens[1:]

            decoded = sp.decode(out_tokens)
            translated_paras.append(decoded)

        result_text = "\n".join(translated_paras)
        return {
            "status": "ok",
            "translatedText": result_text,
            "sourceLang": src_code,
            "targetLang": tgt_code,
        }

    # ------------------------------------------------------------------------
    # DPAPI-Encrypted Translation Vault & Audit Logs
    # ------------------------------------------------------------------------

    def _load_vault(self) -> Dict[str, Any]:
        """Read and decrypt the translation vault from disk."""
        if not self.vault_file.is_file():
            return {"entries": []}
        try:
            encrypted_data = self.vault_file.read_bytes()
            decrypted_data = _dpapi_unprotect(encrypted_data)
            return json.loads(decrypted_data.decode("utf-8"))
        except Exception as exc:
            logger.warning("Error reading translation vault: %s", exc)
            return {"entries": []}

    def _save_vault(self, data: Dict[str, Any]) -> None:
        """Encrypt and atomically write translation vault to disk."""
        raw_bytes = json.dumps(data, ensure_ascii=False).encode("utf-8")
        encrypted_bytes = _dpapi_protect(raw_bytes)

        temp_file = self.vault_file.with_suffix(".tmp")
        temp_file.write_bytes(encrypted_bytes)
        os.replace(temp_file, self.vault_file)

    def get_cached_translation(self, message_id: str, target_lang: str) -> Optional[Dict[str, Any]]:
        """Retrieve previously cached translation for this email and language."""
        vault = self._load_vault()
        tgt_code = FLORES_MAP.get(target_lang.lower(), target_lang)
        for entry in vault.get("entries", []):
            if entry.get("messageId") == message_id and entry.get("targetLang") == tgt_code:
                return entry
        return None

    def save_translation_log(
        self,
        message_id: str,
        subject: str,
        original_text: str,
        translated_text: str,
        source_lang: str,
        target_lang: str,
        translated_subject: str = "",
    ) -> None:
        """Store translation in DPAPI-encrypted vault."""
        vault = self._load_vault()
        entries = vault.get("entries", [])
        tgt_code = FLORES_MAP.get(target_lang.lower(), target_lang)

        # Update existing entry or append new one
        now_iso = datetime.now(timezone.utc).isoformat()
        updated = False
        for e in entries:
            if e.get("messageId") == message_id and e.get("targetLang") == tgt_code:
                e["translatedText"] = translated_text
                e["originalText"] = original_text
                e["subject"] = subject
                e["translatedSubject"] = translated_subject
                e["timestamp"] = now_iso
                updated = True
                break

        if not updated:
            entries.append({
                "messageId": message_id,
                "subject": subject or "(No Subject)",
                "translatedSubject": translated_subject,
                "originalText": original_text,
                "translatedText": translated_text,
                "sourceLang": source_lang,
                "targetLang": tgt_code,
                "timestamp": now_iso,
            })

        vault["entries"] = entries
        self._save_vault(vault)

    def get_translation_logs(self) -> List[Dict[str, Any]]:
        """Return audit list of translated emails (without full body to conserve memory)."""
        vault = self._load_vault()
        logs = []
        for e in vault.get("entries", []):
            logs.append({
                "messageId": e.get("messageId", ""),
                "subject": e.get("subject", "(No Subject)"),
                "targetLang": e.get("targetLang", ""),
                "sourceLang": e.get("sourceLang", ""),
                "timestamp": e.get("timestamp", ""),
                "charCount": len(e.get("translatedText", "")),
            })
        # Sort newest first
        logs.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return logs

    def delete_translation_log(self, message_id: str = "") -> Dict[str, Any]:
        """Delete translation for a specific message, or purge all if message_id is empty."""
        vault = self._load_vault()
        entries = vault.get("entries", [])

        if not message_id:
            # Purge all
            vault["entries"] = []
            self._save_vault(vault)
            return {"status": "ok", "deleted": "all", "remaining": 0}

        # Filter out message_id
        initial_len = len(entries)
        entries = [e for e in entries if e.get("messageId") != message_id]
        vault["entries"] = entries
        self._save_vault(vault)
        return {"status": "ok", "deleted": initial_len - len(entries), "remaining": len(entries)}

