"""
IFWI Flash Orchestrator — subprocess isolation.

Detects DUT topology from:
  1. Agent in-memory DMR cache (get_dmr_info, from previous scan cycle)
  2. Local sut_data.json file (fallback, survives Agent restart)

Delegates topology → image mapping to ``flash_tool.bios_flasher.
resolve_image_for_topology`` (loaded dynamically from the flash_tool
directory declared in ``config.ini[ifwi].flash_cli``), then requests
Process A (Session 1, via message_api's ``/ifwi/flash``) to invoke
flash_tool/flash_cli.py (deployed separately by ops as a sibling of
the agent, at ``<agent_dir>/flash_tool/``). The actual subprocess must
run in Session 1 because this manager runs inside Process B (the
Session 0 system service), and the flash programmer device is not
visible to a Session 0 process — running flash_cli.py directly here
reliably fails with "No device is connected!" during the scheduled
scan window. ``run_flash_cli()`` (the function that owns the
subprocess + JSON-line parsing) is called by message_api.py from
Process A; it lives in this module purely so both processes share one
implementation.
"""

import json
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import requests

from ..config import get_config
from ..logger import get_logger
from ..utils.python_utils import PythonUtils

logger = get_logger(__name__)

# Process A's message_api base URL (same channel already used by DMR.get_hardware_info()/kill_dmr()).
api_host = get_config().get('message_api_url')


# ── flash_tool.bios_flasher.resolve_image_for_topology loader ─────────
# Cached on first successful load. Key is the resolved flash_tool
# directory (parent of flash_cli.py). We deliberately do NOT hard-import
# bios_flasher at module load because:
#   1. flash_tool is deployed by ops as a sibling of local_agent.exe;
#      its location is only known at runtime via config.ini.
#   2. Unit tests for IFWIManager should not require flash_tool to be
#      importable — mocking the config's `flash_cli` path is enough.
_RESOLVER_CACHE: dict = {}


def _load_flash_tool_resolver(flash_cli_path: str):
    """Return ``bios_flasher.resolve_image_for_topology`` or ``None``.

    Dynamically imports ``bios_flasher`` from the directory containing
    ``flash_cli.py`` (from config.ini's ``ifwi.flash_cli``). Cached per
    directory so we don't re-inject sys.path or re-import on every scan
    cycle. Any failure (missing path, ImportError, older bios_flasher
    without the function) returns ``None`` so the caller can log/skip
    safely — the agent MUST NOT crash because ops haven't deployed a
    recent-enough flash_tool.
    """
    if not flash_cli_path:
        return None
    flash_tool_dir = str(Path(flash_cli_path).resolve().parent)
    if flash_tool_dir in _RESOLVER_CACHE:
        return _RESOLVER_CACHE[flash_tool_dir]

    if not Path(flash_tool_dir).is_dir():
        logger.debug(f"flash_tool dir does not exist: {flash_tool_dir}")
        _RESOLVER_CACHE[flash_tool_dir] = None
        return None

    if flash_tool_dir not in sys.path:
        sys.path.insert(0, flash_tool_dir)

    try:
        import bios_flasher  # type: ignore[import-not-found]
        resolver = getattr(bios_flasher, "resolve_image_for_topology", None)
    except ImportError as e:
        logger.debug(f"Cannot import bios_flasher from {flash_tool_dir}: {e}")
        resolver = None

    _RESOLVER_CACHE[flash_tool_dir] = resolver
    return resolver


@dataclass
class IFWIFlashResult:
    """Agent-side result parsed from flash_cli.py JSON output."""
    success: bool = False
    duration_sec: float = 0.0
    error: str = ""
    skipped: bool = False
    skip_reason: str = ""
    programmer_type: str = ""
    stages: list = field(default_factory=list)


def run_flash_cli(flash_cli: str, image_path: str, timeout_sec: int = 1800) -> IFWIFlashResult:
    """Invoke flash_cli.py as subprocess, parse JSON-line progress.

    MUST be called from Process A (Session 1) — the flash programmer device
    is not visible to a Session 0 service process. message_api.py's
    ``/ifwi/flash`` endpoint calls this directly; it lives here (rather than
    in message_api.py) so IFWIManager.flash()'s HTTP client and Process A's
    endpoint share one implementation.

    Reads stdout line by line:
    - Progress lines: {"stage": "...", "message": "..."}  -> logged
    - Final line:     {"final": true, "success": ..., ...} -> parsed into result

    Returns:
        IFWIFlashResult with success/error/duration info.
    """
    # Use the same Python as the Agent
    python_exe = PythonUtils.get_python_executable() or sys.executable

    cmd = [
        str(python_exe), str(flash_cli),
        "--bios-file", str(image_path),
        "--timeout", str(timeout_sec),
    ]
    logger.info(f"IFWI flash subprocess: {' '.join(cmd)}")

    result = IFWIFlashResult()

    # [BUG-N10 fix] Cap stages list to avoid unbounded memory growth
    # when a malicious/malformed flash_cli emits thousands of progress lines.
    _MAX_STAGES = 100

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,  # line-buffered
        )

        # [BUG-N05 fix] Drain stderr concurrently in a daemon thread so
        # child cannot block on a full stderr pipe (>64 KB on Windows).
        stderr_chunks: list = []
        def _drain_stderr():
            try:
                if proc.stderr is None:
                    return
                for chunk in iter(lambda: proc.stderr.read(4096), ""):
                    if not chunk:
                        break
                    stderr_chunks.append(chunk)
            except Exception:
                pass
        stderr_thread = threading.Thread(target=_drain_stderr, daemon=True)
        stderr_thread.start()

        # Watchdog timer — kills process if stdout blocks forever (C3 fix)
        def _safe_kill():
            try:
                proc.kill()
            except OSError:
                pass

        kill_timer = threading.Timer(timeout_sec, _safe_kill)
        kill_timer.start()

        try:
            # Read progress lines from stdout
            for line in proc.stdout:
                line = line.strip()
                if not line:
                    continue

                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    logger.debug(f"IFWI non-JSON output: {line}")
                    continue

                if data.get("final"):
                    # Final result line
                    result.success = data.get("success", False)
                    result.duration_sec = data.get("duration_seconds", 0.0)
                    result.error = data.get("error", "") or ""
                    result.programmer_type = data.get("programmer_type", "")
                else:
                    # Progress line
                    stage = data.get("stage", "?")
                    message = data.get("message", "")
                    if len(result.stages) < _MAX_STAGES:
                        result.stages.append(stage)
                    elif len(result.stages) == _MAX_STAGES:
                        result.stages.append("...")  # sentinel: truncated
                    logger.info(f"IFWI [{stage}] {message}")

            # Wait for process to finish
            proc.wait(timeout=60)
        finally:
            kill_timer.cancel()
            # Ensure stderr drain thread finishes
            stderr_thread.join(timeout=5)

        # Assemble stderr for logging / error diagnostics
        stderr_output = "".join(stderr_chunks)
        if stderr_output and not result.success:
            result.error = result.error or stderr_output.strip()[-2048:]

        # If no final line was parsed, use exit code
        if not result.error and proc.returncode != 0:
            result.error = f"flash_cli.py exited with code {proc.returncode}"
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()  # prevent zombie (W5 fix)
        result.error = f"flash_cli.py timed out after {timeout_sec}s"
        logger.error(result.error)
    except FileNotFoundError:
        result.error = f"Python executable not found: {python_exe}"
        result.skipped = True
        result.skip_reason = result.error
        logger.error(result.error)
    except Exception as e:
        result.error = f"Unexpected error running flash_cli.py: {e}"
        logger.error(result.error)

    return result


class IFWIManager:
    """Orchestrate IFWI image flashing before ConfigSchema scan.

    Requests Process A (Session 1) to run flash_tool/flash_cli.py via
    message_api's ``/ifwi/flash`` endpoint, since the flash programmer
    device is not visible to this (Process B, Session 0) process.
    """

    def __init__(self, ifwi_config: dict):
        """
        Args:
            ifwi_config: dict from load_scan_config()["ifwi"]
        """
        self._config = ifwi_config

    def detect_topology(self) -> Optional[str]:
        """Detect DUT topology from cached DMR info or local sut_data.json.

        Priority:
            1. In-memory cache (get_dmr_info) — from previous scan cycle
            2. Local sut_data.json file — survives Agent restart

        JSON path: mainboard.board.board_meta_data.uxi_topology

        Returns:
            "1S" | "2S" | "4S" | None (if no prior scan data)
        """
        # ── Try 1: in-memory cache from previous scan cycle ──
        topo = self._topology_from_cache()
        if topo:
            return topo

        # ── Try 2: local sut_data.json (persists across restarts) ──
        topo = self._topology_from_file()
        if topo:
            return topo

        logger.info("No topology data available (first boot?)")
        return None

    @staticmethod
    def _extract_topology(data: dict) -> Optional[str]:
        """Extract uxi_topology from DMR config dict."""
        return (
            data.get("mainboard", {})
            .get("board", {})
            .get("board_meta_data", {})
            .get("uxi_topology")
        )

    def _topology_from_cache(self) -> Optional[str]:
        """Try to get topology from Agent's in-memory DMR cache."""
        from .global_cache import get_dmr_info

        dmr_info = get_dmr_info()
        if not dmr_info:
            logger.debug("DMR cache is empty")
            return None

        dmr_config = dmr_info.get("dmr_config", {})
        if not dmr_config:
            logger.debug("DMR cache has no dmr_config")
            return None

        try:
            topo = self._extract_topology(dmr_config)
        except (TypeError, AttributeError):
            logger.debug("Malformed structure in DMR cache")
            return None

        if topo:
            topo_str = str(topo).strip()
            if not topo_str:
                logger.debug("uxi_topology is blank in DMR cache")
                return None
            logger.info(f"Detected topology from DMR cache: {topo_str}")
            return topo_str

        logger.debug("uxi_topology not found in DMR cache")
        return None

    def _topology_from_file(self) -> Optional[str]:
        """Try to read topology from local sut_data.json."""
        sut_path = Path(self._config.get("sut_data_path", ""))
        if not sut_path.exists():
            logger.debug(f"sut_data.json not found at {sut_path}")
            return None

        try:
            with open(sut_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            topo = self._extract_topology(data)
            if topo:
                topo_str = str(topo).strip()
                if not topo_str:
                    logger.warning("uxi_topology field is blank in sut_data.json")
                    return None
                logger.info(f"Detected topology from sut_data.json: {topo_str}")
                return topo_str

            logger.warning("uxi_topology field missing in sut_data.json")
            return None
        except (json.JSONDecodeError, KeyError, TypeError, AttributeError,
                UnicodeDecodeError, OSError) as e:
            # [BUG-N11 fix] Add UnicodeDecodeError (binary/corrupt sut_data.json)
            # and OSError (permission / IO error) so a corrupt file does not
            # abort the whole scan cycle.
            logger.error(f"Failed to parse sut_data.json: {type(e).__name__}: {e}")
            return None

    def select_image(self, topology: str) -> Optional[Path]:
        """Resolve full image path via ``flash_tool.bios_flasher``.

        Delegates to ``bios_flasher.resolve_image_for_topology`` — the
        flash-tool side owns the authoritative topology→image mapping so
        ops can update it in ``deploy_config.json`` without rebuilding
        the agent. Agent only supplies the image_map / images_dir it
        read from ``config.ini``.

        Compound topologies (``"2S2L"``, ``"4S6L"``, ``"1S1C"``) are
        reduced to their 1S/2S/4S socket-count prefix inside the
        resolver.

        Returns None when the resolver cannot find a matching image
        (unknown prefix, missing map key, or file not on disk).
        """
        image_map = self._config.get("image_map", {})
        images_dir = self._config.get("images_dir", "")
        resolver = _load_flash_tool_resolver(self._config.get("flash_cli", ""))
        if resolver is None:
            logger.warning(
                "flash_tool.bios_flasher unavailable; cannot resolve IFWI image "
                f"for topology '{topology}'"
            )
            return None

        full_path = resolver(topology, image_map, images_dir)
        if full_path is None:
            logger.warning(
                f"No IFWI image resolved for topology '{topology}' "
                f"(image_map={list(image_map.keys())}, images_dir={images_dir})"
            )
            return None

        logger.info(f"Selected IFWI image: {full_path} (topology={topology})")
        return full_path

    def flash(self, image_path: Path) -> IFWIFlashResult:
        """Request Process A (Session 1) to flash ``image_path`` via message_api.

        This manager runs inside Process B (Session 0 service). The flash
        programmer device is only visible to the interactive user session,
        so the actual subprocess must run in Process A — this method just
        posts the request over the same HTTP channel already used by
        DMR.get_hardware_info()/kill_dmr() and converts the JSON response
        back into an IFWIFlashResult.

        Returns:
            IFWIFlashResult with success/error/duration info.
        """
        flash_cli = self._config.get("flash_cli", "")
        timeout_sec = int(self._config.get("timeout_sec", 1800))

        if not Path(flash_cli).exists():
            return IFWIFlashResult(
                skipped=True,
                skip_reason=f"flash_cli.py not found: {flash_cli}",
            )

        try:
            response = requests.post(
                f"{api_host}/ifwi/flash",
                json={
                    "flash_cli": str(flash_cli),
                    "image_path": str(image_path),
                    "timeout_sec": timeout_sec,
                },
                # Must exceed Process A's own worst-case bound (its
                # asyncio.wait_for cap is timeout_sec + 90) so we never give
                # up here before A has a chance to return its own timeout result.
                timeout=timeout_sec + 120,
            )
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.JSONDecodeError as e:
            # Must be caught before the broader RequestException below —
            # requests.exceptions.JSONDecodeError subclasses RequestException,
            # so a broad except there would mislabel this as "unreachable".
            logger.error(f"IFWI flash response from Process A was not valid JSON: {e}")
            return IFWIFlashResult(
                error=f"invalid response from Process A: {e}",
                skipped=True,
                skip_reason="invalid_response",
            )
        except requests.exceptions.RequestException as e:
            logger.error(f"IFWI flash request to Process A failed: {e}")
            return IFWIFlashResult(
                error=f"message_api unreachable: {e}",
                skipped=True,
                skip_reason="message_api_unreachable",
            )

        return IFWIFlashResult(
            success=data.get("success", False),
            duration_sec=data.get("duration_sec", 0.0),
            error=data.get("error", "") or "",
            skipped=data.get("skipped", False),
            skip_reason=data.get("skip_reason", ""),
            programmer_type=data.get("programmer_type", ""),
            stages=data.get("stages", []) or [],
        )

    def run_if_enabled(self) -> Optional[IFWIFlashResult]:
        """Top-level entry. Returns None if disabled.

        Pipeline:
            1. enabled=false -> return None
            2. detect_topology() -> None -> skip (first boot)
            3. select_image(topology) -> None -> skip (no image)
            4. flash(image_path) -> return result
            5. Log outcome
        """
        if not self._config.get("enabled", False):
            logger.debug("IFWI flashing is disabled in config.ini")
            return None

        # Step 2: detect topology
        topology = self.detect_topology()
        if topology is None:
            logger.info("IFWI: skipping — no prior sut_data.json (first boot)")
            return IFWIFlashResult(skipped=True, skip_reason="no_topology")

        # Step 3: select image
        image_path = self.select_image(topology)
        if image_path is None:
            logger.info(f"IFWI: skipping — no image for topology '{topology}'")
            return IFWIFlashResult(skipped=True, skip_reason=f"no_image_{topology}")

        # Step 4: flash
        logger.info(f"IFWI: starting flash — {image_path} (topology={topology})")
        result = self.flash(image_path)

        # Step 5: log outcome
        if result.success:
            logger.info(
                f"IFWI flash succeeded — {result.programmer_type}, "
                f"{result.duration_sec:.1f}s"
            )
        elif result.skipped:
            logger.info(f"IFWI flash skipped — {result.skip_reason}")
        else:
            logger.error(f"IFWI flash failed — {result.error}")

        return result
