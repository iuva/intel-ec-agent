#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import winreg
import socket
from dataclasses import dataclass

from ..config import get_config
from ..logger import get_logger
from ..core.global_cache import cache, set_agent_status, get_agent_status_by_key, set_init_config, get_init_config
from .constants import LOCAL_INFO_CACHE_KEY, HARDWARE_INFO_TASK_ID, HARDWARE_INFO_CYCLE_TASK_ID
from .ek import EK
from .dmr import DMR
from ..utils.version_utils import get_app_version, is_newer_version, extract_version
from local_agent.utils.http_client import http_get, http_client, http_post
from ..utils.environment import Environment
from ..core.auth import update_token

# Delay import to avoid loop dependency
# from local_agent.utils.whl_updater import update_from_whl_sync
from ..utils.message_tool import show_message_box
from ..utils.python_utils import PythonUtils  # Import PythonUtils class
from ..utils.timer_utils import set_timeout, clear_timeout, set_interval
from .vnc import VNC
from .app_update import report_version
from .tray_api import get_username


@dataclass
class LocalHostInfo:
    """Local host info data class"""
    mg_id: str
    username: str
    host_ip: str

    def to_dict(self):
        """Convert object to dictionary for JSON serialization"""
        return {
            "mg_id": self.mg_id,
            "username": self.username,
            "host_ip": self.host_ip
        }


# ── [BUG-N04 fix] Retry-cap constants for DMR probe in get_hardware_info() ──
# Tests may patch these to speed up simulated retry scenarios.
DMR_MAX_RETRIES = 3
DMR_RETRY_SLEEP_SEC = 5

# ── [BUG-N16 fix] Wait-for-idle retry: restore legacy "pending" behavior ──
# When the scheduled timer fires but the host is busy (TC executing, adhoc
# access, or EC login active), reschedule the cycle after this many seconds
# and re-check. The polling is bounded by `scheduler.is_in_scan_window()` so a
# permanently-busy host doesn't spin forever — when the window closes we
# defer to the next scheduled window. Tests may patch this to speed up
# simulated retry scenarios.
HOST_BUSY_RETRY_DELAY_SEC = 30


class HostInit:
    """Host initialization class"""
    def __init__(self):
        self.config = get_config()
        self.logger = get_logger(__name__)
        self.logger.info("Host initialization starting")

        # TryStart VNC Service
        vnc_res = VNC.start_vncserver()
        while vnc_res.state != 0:
            show_message_box(
                msg=f"VNC service start failed: {vnc_res.err_msg}",
                title="Initialization failed",
                confirm_text="Retry"
            )
            vnc_res = VNC.start_vncserver()


        # python Initialize
        PythonUtils.get_python_check()

        # Wait for message API service to be healthy (HTTP 200 response)
        import time
        import requests

        is_simulator = os.environ.get("IS_XCOPILOT_SIMULATOR", "").lower() == "true"

        if is_simulator:
            self.logger.info("[SIM] IS_XCOPILOT_SIMULATOR=true — skipping Message API health wait")
        else:
            message_api_url = self.config.get('message_api_url') + "/health"

            while True:
                try:
                    response = requests.get(message_api_url, timeout=5)
                    if response.status_code == 200:
                        self.logger.info("Message API service is healthy, continuing...")
                        break
                    else:
                        self.logger.warning(f"Message API service returned status {response.status_code}, waiting...")
                except Exception as e:
                    self.logger.warning(f"Message API service not available: {e}, waiting...")

                # Wait 30 seconds before next check
                time.sleep(30)

        # Get host info and encapsulate into object
        # Unified username identification mechanism to avoid conflicts caused by inconsistent usernames in service mode
        username = get_username()

        local_info = LocalHostInfo(
            mg_id=self.get_machine_guid(),
            username=username,
            host_ip=self.get_ip_address()
        )

        # Store host info in cache
        cache.set(LOCAL_INFO_CACHE_KEY, local_info)

        # Update token every 23.8 hours
        update_token()
        interval = 23.8 * 60 * 60
        set_interval(interval, update_token, interval)

        # Recover orphan adhoc sessions from prior crash
        from ..core.adhoc_session import recover_orphan_session
        recover_orphan_session()

        # Recover orphan EC login sessions from prior crash
        self._recover_orphan_ec_login()

        self.init_config()

        # Version verification, only check when running as exe
        # if not Environment.is_development():
        self.check_versions()

        # Timed get hardware info (skip in simulator mode)
        if is_simulator:
            self.logger.info("[SIM] Skipping ConfigSchema scan, starting WebSocket directly")
            from ..utils.websocket_sync_utils import start_websocket_sync
            start_websocket_sync(True)
        else:
            self.timing_hardware_info(start=True)


        # res = http_post(url="/host/agent/hardware/report", data = {'name': 'dmr_config_schema', 'type': '0', 'dmr_config': {'revision': '0.1.1', 'mainboard': {'plt_meta_data': {'platform': 'OKS_DMR', 'label_plt_cfg': None}, 'board': {'board_meta_data': {'board_name': 'JohnsonCity1SPCRP', 'uxi_topology': '1S', 'host_name': None, 'host_ip': None}, 'baseboard': [], 'lsio': {'usb_disc_installed': False, 'network_installed': False, 'nvme_installed': False, 'keyboard_installed': False, 'mouse_installed': False}, 'peripheral': {'itp_installed': False, 'usb_dbc_installed': False, 'controlbox_installed': False, 'flash_programmer_installed': False, 'display_installed': False, 'jumpers': []}}, 'misc': {'installed_os': [], 'bmc_version': None, 'bmc_ip': None, 'cpld_version': None}}, 'hsio': [{'hsio': {'hsio_meta_data': {'cxl_por': 'unknown', 'cxl_installed_num': 0, 'cxl_installed_tpye': None, 'cxl_mixed_device_type': False, 'cxl_switch': 'unknown', 'didvid_list': []}, 'slot': []}}], 'memory': [{'memory': {'memory_meta_data': {'dimm_type': 'RDIMM', 'platform_type': 'GNRSP', 'memory_por_id': {'value': 'Unknown Config'}, 'total_memory_size': {'value': 0}, 'mixed_dimm': {'is_mixed': True, 'common_info': '', 'special_info': ''}}, 'channel': []}}], 'security': {'security': {'Tpm': [], 'CoinBattery': []}}, 'soc': [{'soc': {'meta_data': {'soc_name': {'value': None}, 'soc_id': None, 'cpu_id': None, 'chop_type': 'UCC', 'stepping': None, 'qdf': None}, 'soc_feature': {'sgx': None, 'mktme': False, 'tdx': False, 'vab': False, 'cpu_attestation': False, 'mini_dpe': False, 'sstpp': False, 'ras_level': None, 'memory_channel': None, 'ddr5_freq': None, 'mrdimm_freq': None}, 'comp_die': [], 'io_die': []}}]}})

        # from ..utils.websocket_sync_utils import start_websocket_sync
        # start_websocket_sync(True)

    def init_config(self):
        """
        Initialize configuration
        """
        init_res = http_get(url="/host/agent/init")
        init_data = init_res.get('data', {})
        init_code = init_data.get('code', 0)

        config_data = {}
        if str(init_code) == '200':
            conf_data = init_data.get('data', {})
            configs = conf_data.get('configs', [])
            for config in configs:
                key = config.get('conf_key', '')
                config_data[key] = config

        self.logger.info(f"Initialize config: {config_data}")

        # Cache initialize config
        set_init_config(config_data)

    def _recover_orphan_ec_login(self):
        """Write orphan_end to activity log if a prior EC login session was interrupted."""
        from ..core.persistent_storage import get_persistent_data, delete_persistent_data
        session_ctx = get_persistent_data("ec_login_session", "ec_login")
        if not session_ctx:
            return
        self.logger.warning(
            f"Orphan EC login session detected on startup: "
            f"tc_id={session_ctx.get('tc_id', '?')}, user={session_ctx.get('user_name', '?')}"
        )
        try:
            from activity_monitor.logger import ActivityLogger
            from ..utils.path_utils import PathUtils
            root = PathUtils.get_root_path()
            al = ActivityLogger(log_dir=root / "logs")
            al.log_orphan_end(session_context=session_ctx, previous_state="ec_login_active")
            al.close()
        except Exception as e:
            self.logger.debug(f"Could not write EC login orphan end to activity log: {e}")
        delete_persistent_data("ec_login_session", "ec_login")


    def _run_hardware_scan(self):
        """
        Thin wrapper around get_hardware_info() so tests can patch scan-only
        behaviour without affecting IFWI / scheduling code. Owns the retry-cap
        + WS/sut recovery contract.
        """
        return self.get_hardware_info()

    def _is_host_busy(self) -> bool:
        """[BUG-N16] Return True when host is in-use — TC executing (`test`),
        EC login session active or adhoc access active (`use`).

        Used by `_do_scan_cycle` to defer IFWI flash + HW scan while the
        host is being used interactively, restoring the pre-Q1 "poll for
        idle" behavior. This is a snapshot check; caller reschedules via
        `_schedule_next_scan_fallback` to poll again later.
        """
        return bool(
            get_agent_status_by_key('test') or get_agent_status_by_key('use')
        )

    def get_hardware_info(self):
        """
        Get hardware information, if no hardware information is received within 15 minutes, automatically call again
        """
        self.logger.info("Obtained hardware info")

        # Skip scan if TC executing or adhoc_access in use
        if not get_agent_status_by_key('test') and not get_agent_status_by_key('use'):
            if not DMR.is_running():
                # [BUG-N01 fix] Only mutate state when we are actually going to
                # scan. If DMR is already running (another cycle in progress),
                # keep sut/WS untouched — the running scan owns the state.
                from ..utils.websocket_sync_utils import stop_websocket_sync
                stop_websocket_sync()
                set_agent_status(sut=True)

                import time
                DMR.kill_dmr()
                time.sleep(10)

                # [BUG-N04 fix] Cap retries to avoid infinite spin in headless
                # service mode where show_message_box returns immediately.
                # After N attempts, bail out cleanly so the next scheduled
                # cycle can retry the next day. sut flag reset + WS restarted
                # so state machine is not stuck.
                max_retries = getattr(self, "_DMR_MAX_RETRIES", DMR_MAX_RETRIES)
                retry_sleep = getattr(self, "_DMR_RETRY_SLEEP", DMR_RETRY_SLEEP_SEC)
                attempt = 0
                dmr_ok = False
                while attempt < max_retries:
                    if DMR.get_hardware_info():
                        dmr_ok = True
                        break
                    attempt += 1
                    self.logger.warning(
                        f"DMR.get_hardware_info() failed (attempt {attempt}/{max_retries})"
                    )
                    if attempt >= max_retries:
                        break
                    show_message_box(
                        msg=f"The dmr config program was not found. Please install it manually and try again",
                        title="Initialization failed",
                        confirm_text="Retry"
                    )
                    time.sleep(retry_sleep)

                if not dmr_ok:
                    self.logger.error(
                        f"DMR unreachable after {max_retries} attempts; "
                        f"skipping this scan cycle"
                    )
                    # Reset sut flag so state machine is not stuck
                    try:
                        set_agent_status(sut=False)
                    except Exception:
                        pass
                    # Restart WS so backend can still communicate with Agent
                    try:
                        from ..utils.websocket_sync_utils import start_websocket_sync
                        start_websocket_sync(True)
                    except Exception as e:
                        self.logger.warning(f"Failed to restart WS after DMR exhaustion: {e}")
                    return

                self.logger.info("Obtained hardware info - call completed")

        # [Q1 fix + BUG-N16 restore] Legacy 30 s self-reschedule USED to live
        # here (at the bottom of get_hardware_info, re-firing itself every 30 s
        # whenever `test` / `use` was set). The Q1 refactor moved the busy
        # defer to `_do_scan_cycle` (see BUG-N16 block there) where it is
        # driven by `_schedule_next_scan_fallback`, which cancels the
        # previous timer before setting the new one. That single-owner design
        # avoids the "duplicate 30 s timer racing with the fixed-window
        # timer" bug the raw legacy code had.


    def timing_hardware_info(self, start=False):
        """
        Timed hardware information retrieval.

        New (feature/local-5am-ifwi-dutycycle):
          - Reads scan window + IFWI settings from local config.ini
          - On window trigger (start=False): optionally flash IFWI before scan
          - Schedules next run at random moment inside next PRC 05:00-07:00 window
          - Falls back to backend-driven relative cycle if scheduler init fails
          - Outer safety net: any uncaught exception in the scan body triggers
            a 1-hour retry so the Agent never permanently loses its schedule.

        See docs/features/q1_fixed_scan_ifwi/spec.md §3.1
        """
        try:
            self._do_scan_cycle(start=start)
        except Exception as e:
            # [Outer fallback] Any uncaught error in the scan body → retry in 1h.
            # This is the last line of defence: without it a transient
            # ConnectionError from the backend during init_config would kill
            # the whole schedule and the host would silently stop scanning.
            self.logger.error(f"Scan cycle failed: {e} — retrying in 1 hour")
            try:
                self._schedule_next_scan_fallback(3600)
            except Exception as fallback_err:
                # If even the fallback scheduler is broken, we have nothing
                # left. Log CRITICAL so operators can escalate.
                self.logger.critical(
                    f"Fallback schedule also failed: {fallback_err}. "
                    f"Agent scan pipeline halted until process restart."
                )

    def _schedule_next_scan_fallback(self, delay):
        """Schedule the next timing_hardware_info run in `delay` seconds.

        - Cancels any previous cycle timer stored in cache to prevent
          overlapping schedules ("timer rotation").
        - Persists the new task_id in the cache under HARDWARE_INFO_CYCLE_TASK_ID.

        Used by BOTH the happy path (from _do_scan_cycle) and the 1h outer
        fallback (from timing_hardware_info) so there is one canonical
        rescheduler.
        """
        old_task_id = cache.get(HARDWARE_INFO_CYCLE_TASK_ID)
        if old_task_id:
            # Deliberately NOT caught: if clear_timeout is broken the timer
            # system is corrupt and the outer catch-all must escalate to
            # CRITICAL rather than silently leak timers.
            clear_timeout(old_task_id)
        task_id = set_timeout(delay, self.timing_hardware_info)
        cache.set(HARDWARE_INFO_CYCLE_TASK_ID, task_id)
        return task_id

    def _do_scan_cycle(self, start=False):
        """Internal: single scan-cycle body extracted from timing_hardware_info.

        Kept as a separate method so the outer fallback wrapper can catch
        anything raised here without duplicating the recovery path.
        """
        # Check version when not starting
        if not start:
            self.check_versions()

        # ── Load local scan/IFWI config from config.ini ──
        # If the config layer is broken (permission / disk / parser), let the
        # exception propagate to the outer 1h fallback rather than silently
        # scanning with defaults for potentially days on end.
        from .scan_config import load_scan_config
        scan_cfg = load_scan_config()

        # ── Build scheduler up-front to decide IFWI-flash gating ──
        # Scheduler is used for two things:
        #   (a) is_in_scan_window() → decides whether startup should skip IFWI
        #   (b) seconds_until_next_scan() → schedules the next cycle (called
        #       at the end of this method)
        # Wrapped in try/except so a broken window config doesn't cascade —
        # scan MUST still run in that case (test contract:
        # test_scheduler_exception_after_scan_triggers_fallback).
        from .scan_scheduler import ScanScheduler
        scan_section = scan_cfg.get("scan", {}) or {}
        scheduler = None
        should_flash_ifwi = True  # fail-safe default
        try:
            scheduler = ScanScheduler(
                window_start=scan_section.get("window_start", "05:00"),
                window_end=scan_section.get("window_end", "07:00"),
                tz_name=scan_section.get("timezone", "UTC+8"),
                interval_days=scan_section.get("interval_days", 1),
            )
            # On service boot (start=True), if we're currently OUTSIDE the scan
            # window, skip the (destructive) IFWI flash but still run the HW
            # scan so the host reports itself online with fresh hardware info.
            # Subsequent cycles (start=False) always flash because they're
            # triggered by the scheduler at a time inside the window.
            if start and not scheduler.is_in_scan_window():
                should_flash_ifwi = False
                self.logger.info(
                    f"Startup outside scan window "
                    f"[{scan_section.get('window_start', '05:00')}-"
                    f"{scan_section.get('window_end', '07:00')} PRC]; "
                    f"skipping IFWI flash (HW scan will still run so host "
                    f"comes online)"
                )
        except Exception as e:
            # Scheduler init failed. Be conservative: don't flash IFWI
            # (destructive), but let scan run. Re-raise happens at the end
            # of this method when we retry seconds_until_next_scan().
            should_flash_ifwi = False
            self.logger.warning(
                f"Scheduler init failed ({e}); skipping IFWI flash, "
                f"scan will still run, next-schedule will be recomputed at end"
            )

        # ── [BUG-N16 fix] Host-busy defer: wait for idle before scan ──
        # Legacy pre-Q1 behavior: if the timer fired while a TC / adhoc / EC-
        # login session was active, the cycle skipped and re-scheduled itself
        # in 30 s, polling until the host became idle. The Q1 fixed-window
        # rewrite accidentally removed this while spec.md §4 still documents
        # `Guard check (test/use=true) → Retry in 30s | No (existing)`.
        # This block restores the intended behavior:
        #
        #   start=False + busy + in-window  → retry in HOST_BUSY_RETRY_DELAY_SEC
        #   start=False + busy + out-window → defer to next scheduled window
        #   start=True  + busy              → skip IFWI (destructive; don't
        #                                     disrupt user), fall through to
        #                                     scan block (its own busy guard
        #                                     will short-circuit safely)
        #
        # No race with the fixed-window timer: `_schedule_next_scan_fallback`
        # cancels the previous timer before setting the new one.
        if self._is_host_busy():
            if start:
                should_flash_ifwi = False
                self.logger.info(
                    "Startup while host busy (test/use active); "
                    "skipping IFWI flash to avoid disrupting user session"
                )
            else:
                retry_delay = getattr(
                    self, "_HOST_BUSY_RETRY_DELAY", HOST_BUSY_RETRY_DELAY_SEC
                )
                if scheduler is not None and scheduler.is_in_scan_window():
                    self.logger.info(
                        f"Host busy (TC / adhoc / EC-login active) and inside "
                        f"scan window; retrying in {retry_delay}s to wait "
                        f"for idle"
                    )
                    self._schedule_next_scan_fallback(retry_delay)
                    return
                # Window closed OR scheduler unavailable → defer to next
                # scheduled window (or 1 h outer fallback if scheduler dead).
                if scheduler is not None:
                    delay = scheduler.seconds_until_next_scan()
                    self.logger.info(
                        f"Host busy and scan window closed; deferring to "
                        f"next window (in {delay/3600:.1f}h)"
                    )
                else:
                    delay = 3600
                    self.logger.warning(
                        f"Host busy and scheduler unavailable; retrying in "
                        f"{delay/3600:.1f}h (outer fallback)"
                    )
                self._schedule_next_scan_fallback(delay)
                return

        # ── IFWI flash (before HW scan) ──
        # Core principle: IFWI failure never blocks HW scan.
        # Note: run_if_enabled() is a no-op when config says disabled, so it's
        # safe to call unconditionally.
        #
        # DMR-overlap guard: if a previous cycle's DMR scan is still running
        # (BMC hung, slow probe, etc.), skip IFWI this round. Rationale:
        # flashing BIOS while DMR is reading Redfish/BMC = race condition
        # that can corrupt the scan result or the flash itself. HW scan has
        # its own DMR.is_running() guard downstream; this one adds symmetry.
        # Deferred flash retries next window; no schedule loss.
        if should_flash_ifwi:
            if DMR.is_running():
                self.logger.info(
                    "IFWI: skipping \u2014 previous DMR scan still running; "
                    "will retry next scan window"
                )
            else:
                try:
                    from .ifwi_manager import IFWIManager
                    mgr = IFWIManager(scan_cfg.get("ifwi", {}))
                    result = mgr.run_if_enabled()
                    # result==None       -> disabled, nothing to log
                    # result.skipped     -> logged by IFWIManager already (info-level)
                    # result.success     -> logged by IFWIManager already
                    # attempted+failed   -> surface a warning here
                    if result and not result.skipped and not result.success:
                        # Test contract: log via .error (not .warning) so that operators
                        # get paged on non-transient flash failures. See spec §3.3.
                        self.logger.error(
                            f"IFWI flash failed: {result.error} \u2014 continuing with scan"
                        )
                except Exception as e:
                    self.logger.error(
                        f"IFWI flash error: {e} \u2014 continuing with scan"
                    )

        # Get hardware info (via extracted method so tests can patch scan alone)
        self._run_hardware_scan()

        self.init_config()

        # ── Schedule next scan at absolute time within PRC window ──
        # Any exception here propagates to the outer 1h fallback wrapper in
        # timing_hardware_info, which is the single canonical recovery path.
        if scheduler is None:
            # Retry construction so the same error surfaces to outer fallback.
            scheduler = ScanScheduler(
                window_start=scan_section.get("window_start", "05:00"),
                window_end=scan_section.get("window_end", "07:00"),
                tz_name=scan_section.get("timezone", "UTC+8"),
                interval_days=scan_section.get("interval_days", 1),
            )
        # [BUG-N17] Post-scan reschedule MUST skip the current window.
        # Without `skip_current_window=True` the stateless random draw would
        # frequently roll another minute later in the same window (~66%
        # chance at 05:40 for 05:00-07:00), producing 2+ scans/day
        # (observed on SHFIVDMR15 on 2026-09-04: scans at 05:40 AND 06:12).
        # Design intent per spec.md §1 and ADR 001 is "once per day".
        delay = scheduler.seconds_until_next_scan(skip_current_window=True)
        self.logger.info(
            f"Next hardware scan in {delay/3600:.2f}h (fixed PRC window)"
        )

        # Canonical rescheduler: rotates timer + persists id.
        self._schedule_next_scan_fallback(delay)

    def get_version_info(self):

        while True:
            try:
                res = http_get(url="/host/agent/ota/latest")

                res_data = res.get('data', {})
                code = res_data.get('code', 0)

                self.logger.info(f"Version info obtained result: {res_data}")
                if code != 200:

                    result = show_message_box(
                        msg=f"Failed to retrieve the latest available version from the server!",
                        title="Network anomaly",
                        confirm_text="Retry"
                    )

                    self.logger.info("User chose to retry, re-obtaining version info")
                    continue
                else:
                    arr = res_data.get('data')

                    return {item['conf_name']: item for item in arr}

            except Exception as e:
                self.logger.error(f"Obtained version info exception: {e}")
                result = show_message_box(
                    msg=f"Failed to retrieve the latest available version from the server!",
                    title="Network anomaly",
                    confirm_text="Retry"
                )

                self.logger.info("User chose to retry, re-obtaining version info")
                continue

    def check_versions(self):
        """
        Check ek and kw versions
        """
        # Get current software version
        current_version = get_app_version(False)

        self.logger.info(f"Current software version: {current_version}")

        # Get latest version info from service
        versionInfo = self.get_version_info()

        self.logger.info(f"Latest version info: {versionInfo}")

        # Check if current software version is the latest
        agentVersion = versionInfo.get('agent')

        # Check if agent version is not None
        if agentVersion and agentVersion.get('conf_ver'):

            # Check if there are update failure records within 10 minutes to prevent infinite loop
            import time
            from local_agent.core.persistent_storage import get_persistent_data, set_persistent_data

            # Get last update failure time
            last_update_failure_time = get_persistent_data('last_update_failure_time', 'update_status', 0)

            if last_update_failure_time > 0:
                self.logger.info(f"Last update failure time: {time.ctime(last_update_failure_time)}")
                report_version('agent', agentVersion.get('conf_ver'), 3)

            # Calculate time difference (seconds)
            current_time = time.time()
            time_diff = current_time - last_update_failure_time

            # If there are update failure records within 10 minutes, do not proceed with update
            if last_update_failure_time == 0 or time_diff > 600:
                # Version comparison
                agent_new_ver = agentVersion.get('conf_ver')
                agent_is_new = is_newer_version(agent_new_ver, current_version)

                if agent_is_new:
                    self.logger.info('Agent needs update')
                    report_version('agent', agent_new_ver, 1)

                    try:
                        # Execute update operation asynchronously

                        from local_agent.auto_update.auto_updater import AutoUpdater
                        updater = AutoUpdater()
                        # Execute update operation asynchronously
                        result = updater.perform_update_sync(
                            expected_md5=agentVersion.get('conf_md5'),
                            download_url=agentVersion.get('conf_url')
                        )

                        # If the program reaches here, it means the update script didn't kill the current process, update operation failed
                        if not result.get('success', False):
                            # Persist update failure result
                            error_message = result.get('error', 'Unknown error')
                            self.logger.error(f"Update failed: {error_message}")

                            # Store update failure time
                            set_persistent_data('last_update_failure_time', current_time, 'update_status')
                            set_persistent_data('last_update_error', error_message, 'update_status')
                            self.logger.info(f"Recorded update failure time: {current_time}")
                            report_version('agent', agent_new_ver, 3)

                    except Exception as e:
                        self.logger.error(f"Update operation exception: {e}")
                        current_time = time.time()
                        set_persistent_data('last_update_failure_time', current_time, 'update_status')
                        set_persistent_data('last_update_error', str(e), 'update_status')
                        self.logger.info(f"Recorded update exception time: {current_time}")
                        report_version('agent', agent_new_ver, 3)
                else:
                    report_version('agent', current_version, 2)

        # Check if EK needs update
        ekVersion = versionInfo.get('ek')
        EK.env_check()
        if ekVersion:
            ek_new_version = ekVersion.get('conf_ver')
            ek_is_new = is_newer_version(ek_new_version, EK.version())
            if ek_is_new:
                self.logger.info('Execution Kit needs update')
                report_version('ek', ek_new_version, 1)
                res, msg = EK.update(ekVersion.get('conf_url', None))

                if not res:
                    v = extract_version(EK.version())
                    if v is None:
                        while not res:
                            show_message_box(
                                msg=f"EK installation failed: {msg}",
                                title="Initialization failed",
                                confirm_text="Retry"
                            )
                            versionInfo = self.get_version_info()
                            ekVersion = versionInfo.get('ek')
                            res, msg = EK.update(ekVersion.get('conf_url', None))

                # Check if update succeeded by comparing versions again
                res = is_newer_version(ek_new_version, EK.version())

                if res:
                    report_version('ek', ek_new_version, 3)
                else:
                    report_version('ek', ek_new_version, 2)

        else:
            self.logger.warning('Unable to obtain Execution Kit version info')

        # Check if DMR needs update
        dmrVersion = versionInfo.get('dmr_config')
        if dmrVersion:
            dmr_new_version = dmrVersion.get('conf_ver')
            dmr_is_new = is_newer_version(dmr_new_version, DMR.version())
            if dmr_is_new:
                self.logger.info('dmr_config needs update')
                report_version('dmr_config', dmr_new_version, 1)

                res, msg = DMR.update(dmrVersion.get('conf_url', None))

                if not res:
                    v = extract_version(DMR.version())
                    if v is None:
                        while not res:
                            show_message_box(
                                msg=f"DMR installation failed: {msg}",
                                title="Initialization failed",
                                confirm_text="Retry"
                            )
                            versionInfo = self.get_version_info()
                            dmrVersion = versionInfo.get('dmr_config')
                            res, msg = DMR.update(dmrVersion.get('conf_url', None))


                # Check if update succeeded by comparing versions again
                res = is_newer_version(dmr_new_version, DMR.version())

                if res:
                    report_version('dmr_config', dmr_new_version, 3)
                else:
                    report_version('dmr_config', dmr_new_version, 2)
        else:
            self.logger.warning('Unable to obtain dmr_config version info')


    """
    Get host environment - Windows compatible version
    """
    def get_ip_address(self):
        """Get local IPv4 address. Raises RuntimeError if detection fails."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(('8.8.8.8', 80))
            ip_address = s.getsockname()[0]
            s.close()
            if ip_address == '127.0.0.1' or ip_address.startswith('169.254.'):
                raise RuntimeError(f"Detected invalid IP: {ip_address} (no network)")
            return ip_address
        except Exception as e:
            self.logger.error(f"IP address detection failed: {e}")
            raise RuntimeError(f"Cannot determine host IP address: {e}")




    def get_machine_guid(self):
        """
        Get MachineGuid from Windows system.
        """
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                    "SOFTWARE\\Microsoft\\Cryptography",
                                    0, winreg.KEY_READ)
            try:
                value, regtype = winreg.QueryValueEx(key, "MachineGuid")
                return value
            finally:
                winreg.CloseKey(key)

        except FileNotFoundError:
            self.logger.error("MachineGuid not found in registry.")
            return None
        except PermissionError:
            self.logger.error("Permission denied accessing registry. Try running as administrator.")
            return "N/A (Error reading file)" # To match previous output
        except Exception as e:
            self.logger.error(f"An error occurred: {e}")
            return None


