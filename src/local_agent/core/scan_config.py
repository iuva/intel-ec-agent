"""
Local config.ini reader for scan window and IFWI settings.

Reads from config.ini (path via PathUtils.get_config_file_path()).
Creates the file with defaults if it does not exist.
"""

import configparser
import sys
from pathlib import Path
from typing import Optional

from ..logger import get_logger

logger = get_logger(__name__)

# ── Defaults ──────────────────────────────────────────────────────────


def _default_flash_cli_path() -> str:
    """Default flash_cli.py path — <agent_dir>/flash_tool/flash_cli.py.

    flash_tool/ is deployed independently by ops (or a future OTA channel)
    into a `flash_tool` subdirectory next to local_agent.exe. In dev mode,
    sys.executable is the Python interpreter, so this returns a path
    relative to that (dev typically has IFWI disabled anyway).
    """
    return str(Path(sys.executable).parent / "flash_tool" / "flash_cli.py")


_DEFAULTS = {
    "scan": {
        "window_start": "05:00",
        "window_end": "07:00",
        "timezone": "UTC+8",
        # Days between successive HW scans. 1 = daily (default), 2 = every
        # other day, etc. Range [1, 30] enforced by ScanScheduler; invalid
        # values fall back to 1. Zero/negative would cause a tight-loop
        # rescheduling storm, so they are rejected.
        "interval_days": "1",
    },
    "ifwi": {
        # [ADR 004] Default flipped to "true" so fresh installs and hosts
        # that lose their config.ini fall back to "IFWI enabled". Ops can
        # still opt out per-host by setting `enabled = false` in local
        # config.ini. Rationale: the whole q1_fixed_scan_ifwi feature
        # exists to run scheduled IFWI flashes; shipping a template that
        # disables it by default made new deployments silently no-op.
        "enabled": "true",
        "images_dir": r"C:\agent\ifwi_images",
        "timeout_sec": "1800",
        "sut_data_path": r"C:\Users\sys_realvnc\PythonSv\sut_data.json",
        "flash_cli": _default_flash_cli_path(),
        "image_1s": "dmr_1s.bin",
        "image_2s": "dmr_2s.bin",
        "image_4s": "dmr_4s.bin",
    },
}


def _get_default_config_path() -> Path:
    """Return config.ini path via PathUtils."""
    from ..utils.path_utils import PathUtils
    return PathUtils.get_config_file_path()


def _ensure_config_file(path: Path) -> None:
    """Create config.ini with defaults if missing.

    [BUG-N09 fix] Wrap mkdir/write in try/except so an unwritable path
    (nonexistent drive letter, read-only mount, permission denied) does
    not crash the whole scan cycle — caller will still get defaults.
    """
    if path.exists():
        return

    cp = configparser.RawConfigParser()  # [BUG-N13 fix] no interpolation
    for section, kvs in _DEFAULTS.items():
        cp[section] = kvs

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            cp.write(f)
        logger.info(f"Created default config.ini at {path}")
    except (OSError, PermissionError) as e:
        # Non-fatal — downstream _get() falls back to _DEFAULTS.
        logger.warning(
            f"Cannot write config.ini at {path}: {type(e).__name__}: {e}; "
            f"using in-memory defaults"
        )


def load_scan_config(config_path: Optional[Path] = None) -> dict:
    """Read config.ini and return scan + IFWI settings.

    Falls back to defaults if file/section/key is missing.
    Creates config.ini with defaults if file does not exist.

    Returns:
        {
            "scan": {
                "window_start": "05:00",
                "window_end": "07:00",
                "timezone": "Asia/Shanghai",
            },
            "ifwi": {
                "enabled": False,
                "images_dir": "C:\\agent\\ifwi_images",
                "timeout_sec": 1800,
                "sut_data_path": "C:\\Users\\sys_realvnc\\PythonSv\\sut_data.json",
                "flash_cli": "<agent_dir>\\flash_tool\\flash_cli.py",
                "image_map": {"1S": "dmr_1s.bin", "2S": "dmr_2s.bin", "4S": "dmr_4s.bin"},
            },
        }
    """
    path = config_path or _get_default_config_path()
    _ensure_config_file(path)

    # [BUG-N13 fix] RawConfigParser disables %-interpolation so INI values
    # containing '%' (e.g. 'timeout_sec=50%', comments like '# 100% margin')
    # do not crash with InterpolationSyntaxError.
    #
    # [BUG-N15 fix] Use 'utf-8-sig' (not 'utf-8') so a leading UTF-8 BOM
    # written by Windows editors (Notepad, PowerShell `Set-Content -Encoding
    # utf8` in 5.1, VSCode default-save) is stripped transparently.
    # Without this, the BOM appears before '[scan]' and configparser raises
    # MissingSectionHeaderError → entire config silently falls back to
    # defaults, which is a silent-catastrophic-failure mode (agent runs
    # with wrong window and no visible error other than one WARNING line).
    cp = configparser.RawConfigParser()
    try:
        cp.read(str(path), encoding="utf-8-sig")
    except (UnicodeDecodeError, configparser.Error, OSError) as e:
        logger.warning(
            f"Failed to parse config.ini at {path} ({type(e).__name__}: {e}), "
            f"using defaults"
        )
        cp = configparser.RawConfigParser()  # empty → all keys fall back to defaults

    def _get(section: str, key: str) -> str:
        try:
            return cp.get(section, key)
        except (configparser.NoSectionError, configparser.NoOptionError):
            return _DEFAULTS.get(section, {}).get(key, "")

    # interval_days: parse as int with safe fallback. ScanScheduler will
    # additionally clamp out-of-range values to 1 (see its __init__).
    try:
        interval_days_val = int(_get("scan", "interval_days") or "1")
    except ValueError:
        logger.warning("Invalid interval_days in config.ini, using default 1")
        interval_days_val = 1

    scan_cfg = {
        "window_start": _get("scan", "window_start"),
        "window_end": _get("scan", "window_end"),
        "timezone": _get("scan", "timezone"),
        "interval_days": interval_days_val,
    }

    try:
        timeout_val = int(_get("ifwi", "timeout_sec") or "1800")
        if timeout_val < 30:
            logger.warning(f"timeout_sec={timeout_val} too low, using default 1800")
            timeout_val = 1800
    except ValueError:
        timeout_val = 1800
        logger.warning("Invalid timeout_sec in config.ini, using default 1800")

    ifwi_cfg = {
        "enabled": _get("ifwi", "enabled").lower() in ("true", "1", "yes"),
        "images_dir": _get("ifwi", "images_dir"),
        "timeout_sec": timeout_val,
        "sut_data_path": _get("ifwi", "sut_data_path"),
        "flash_cli": _get("ifwi", "flash_cli"),
        "image_map": {
            "1S": _get("ifwi", "image_1s"),
            "2S": _get("ifwi", "image_2s"),
            "4S": _get("ifwi", "image_4s"),
        },
    }

    return {"scan": scan_cfg, "ifwi": ifwi_cfg}
