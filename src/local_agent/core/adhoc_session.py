#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Manual Session Pipeline
Handles adhoc_access exec_mode — VNC monitoring without EK launch.
Fully isolated from EC Login flow.
"""

import asyncio
import time
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Dict, Any, Optional

from ..logger import get_logger
from ..core.global_cache import cache, get_agent_status_by_key, set_agent_status
from ..core.constants import MANUAL_SESSION_CACHE_KEY
from ..core.vnc import VNC
from ..utils.http_client import http_post
from ..utils.message_tool import show_message_box_async
from ..utils.path_utils import PathUtils

try:
    from activity_monitor import ActivityMonitor
except ImportError:
    ActivityMonitor = None


logger = get_logger(__name__)


# Maximum time to wait for a single http_post call (seconds).
# Matches global http_timeout in config.py (60s).
_HTTP_TIMEOUT = 60


class AdhocSessionState(str, Enum):
    IDLE = "idle"
    INIT = "init"
    WAIT_VNC = "wait_vnc"
    ACTIVE = "active"
    ENDING = "ending"
    CLEANUP = "cleanup"


def _http_post_safe(url: str, data: dict, timeout: float = _HTTP_TIMEOUT) -> dict:
    """
    Non-blocking-safe wrapper around http_post.
    Enforces a hard timeout to prevent the infinite-retry loop in http_client
    from blocking the caller indefinitely.
    Returns the response dict, or an error dict on failure.
    """
    import concurrent.futures
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(http_post, url=url, data=data)
            return future.result(timeout=timeout)
    except concurrent.futures.TimeoutError:
        logger.error(f"http_post timed out ({timeout}s): {url}")
        return {"status_code": 408, "success": False, "data": {"error": "timeout"}}
    except Exception as e:
        logger.error(f"http_post exception: {url} -> {e}")
        return {"status_code": 500, "success": False, "data": {"error": str(e)}}


class AdhocSessionPipeline:
    """
    Pipeline for adhoc_access exec_mode.
    Stages: init -> wait_vnc -> active_monitor -> cleanup
    """

    def __init__(self):
        self._state: AdhocSessionState = AdhocSessionState.IDLE
        self._context: Dict[str, Any] = {}
        self._deadline: float = 0.0
        self._absolute_max_deadline: float = 0.0
        self._start_time: float = 0.0
        self._force_end_event: asyncio.Event = asyncio.Event()
        self._extend_event: asyncio.Event = asyncio.Event()
        self._extend_seconds: int = 0
        self._cleanup_done: bool = False
        self._activity_monitor: Optional[Any] = None
        # True once a real VNC connect has been confirmed and vnc_state=1
        # reported. Lets the ACTIVE loop know whether it still needs to keep
        # watching for a late connect (see _stage_active_monitor).
        self._vnc_confirmed: bool = False

    @property
    def state(self) -> AdhocSessionState:
        return self._state

    @property
    def is_active(self) -> bool:
        return self._state in (
            AdhocSessionState.INIT,
            AdhocSessionState.WAIT_VNC,
            AdhocSessionState.ACTIVE,
            AdhocSessionState.ENDING,
            AdhocSessionState.CLEANUP,
        )

    async def start(self, notification: Dict[str, Any]):
        """Entry point — called by message_handler router."""
        try:
            await self._stage_init(notification)
            # R1/R2 resumes (Agent process restart) intentionally bypass the
            # 60-second initial VNC handshake.  The user client is commonly
            # still asleep while the Agent restarts; treating that absence as
            # a failed connection would immediately emit session_ended and
            # defeat reconnect. A browser-initiated Reconnect click also sets
            # is_resume (to preserve remaining_seconds) but is NOT a process
            # restart — it must still run _stage_wait_vnc so vnc_state=1 gets
            # reported and host_state can flip locked -> occupied. Only the
            # internal orphan-recovery caller sets skip_vnc_wait.
            if self._context.get("is_ltr") and self._context.get("is_resume") and self._context.get("skip_vnc_wait"):
                remaining = int(self._context.get("remaining_seconds") or 0)
                if remaining <= 0:
                    self._state = AdhocSessionState.ENDING
                else:
                    await self._stage_active_monitor()
            else:
                connected = await self._stage_wait_vnc()
                if connected:
                    await self._stage_active_monitor()
            await self._stage_cleanup()
        except asyncio.CancelledError:
            logger.info("Adhoc session pipeline cancelled")
            await self._stage_cleanup()
        except Exception as e:
            logger.error(f"Adhoc session pipeline error: {e}")
            await self._stage_cleanup()

    # ------------------------------------------------------------------
    # Stage: INIT
    # ------------------------------------------------------------------
    async def _stage_init(self, notification: Dict[str, Any]):
        self._state = AdhocSessionState.INIT
        details = notification.get("details", {})

        self._context = {
            "host_id": notification.get("host_id", ""),
            "exec_log_id": details.get("exec_log_id"),
            "exec_mode": details.get("exec_mode", "adhoc_access"),
            "category": details.get("category", ""),
            "is_ltr": details.get("is_ltr", False),
            "user_name": details.get("user_name", ""),
            "tc_id": details.get("tc_id", ""),
            "cycle_name": details.get("cycle_name", ""),
            "session_timeout": details.get("session_timeout", 7200),
            "max_session_duration": details.get("max_session_duration", 14400),
            "notify_before_expire": details.get("notify_before_expire", 900),
            "poll_interval": details.get("poll_interval", 10),
            "vnc_wait_timeout": details.get("vnc_wait_timeout", 60),
            # R1 resume scaffolding — populated by recover_orphan_session().
            # Defaults preserve legacy behavior when not a resume.
            "is_resume": bool(details.get("is_resume", False)),
            "remaining_seconds": details.get("remaining_seconds"),
            # Only set internally by recover_orphan_session()'s resume path;
            # a browser Reconnect never sets this, so it still runs WAIT_VNC.
            "skip_vnc_wait": bool(details.get("skip_vnc_wait", False)),
            # Preserved wall-clock anchor for R1 recovery across restarts.
            # Keep an incoming resume anchor; fresh sessions are stamped below.
            "begin_time_utc": details.get("begin_time_utc") or datetime.now(timezone.utc).isoformat(),
        }

        now = time.monotonic()
        self._start_time = now
        # R1: on resume, honor remaining_seconds so the pipeline exits at the
        # original wall-clock deadline instead of restarting the countdown.
        if self._context.get("is_resume") and self._context.get("remaining_seconds") is not None:
            remaining = max(0, int(self._context["remaining_seconds"]))
            self._deadline = now + remaining
            self._absolute_max_deadline = now + remaining
            logger.info(
                f"Adhoc session RESUME: host={self._context['host_id']}, "
                f"remaining={remaining}s, exec_log_id={self._context.get('exec_log_id')}"
            )
        else:
            self._deadline = now + self._context["session_timeout"]
            self._absolute_max_deadline = now + self._context["max_session_duration"]

        set_agent_status(use=True)
        _save_session_state(self._context, self._state)

        logger.info(
            f"Adhoc session INIT: host={self._context['host_id']}, "
            f"timeout={self._context['session_timeout']}s, max={self._context['max_session_duration']}s"
        )

    # ------------------------------------------------------------------
    # Stage: WAIT_VNC (60s timeout for VNC connection)
    # ------------------------------------------------------------------
    async def _stage_wait_vnc(self) -> bool:
        self._state = AdhocSessionState.WAIT_VNC
        _save_session_state(self._context, self._state)

        vnc_wait_timeout = self._context.get("vnc_wait_timeout", 60)
        poll_interval = 2
        elapsed = 0
        retry_failures = 0

        logger.info(f"Waiting for VNC connection ({vnc_wait_timeout}s timeout)...")

        while elapsed < vnc_wait_timeout:
            if self._force_end_event.is_set():
                logger.info("Force end received during WAIT_VNC")
                return False

            try:
                connected = await asyncio.to_thread(VNC.is_connecting)
                if connected:
                    logger.info(f"VNC connected after {elapsed}s")
                    report_result = await asyncio.to_thread(
                        _http_post_safe, "/host/agent/vnc/report", {"vnc_state": 1}
                    )
                    # Only mark confirmed on a successful report — a
                    # transient failure here must not permanently suppress
                    # the retry, since _vnc_confirmed gates the late-connect
                    # retry path in _stage_active_monitor (LTR only). VNC is
                    # physically connected either way, so we still proceed
                    # to ACTIVE.
                    if report_result.get("success"):
                        set_agent_status(vnc=True)
                        self._vnc_confirmed = True
                    else:
                        logger.warning("vnc_state=1 report failed; will retry from ACTIVE (LTR only)")
                    return True
                retry_failures = 0
            except Exception as e:
                retry_failures += 1
                logger.warning(f"VNC check error ({retry_failures}/3): {e}")
                if retry_failures >= 3:
                    logger.error("VNC check failed 3 times, aborting")
                    return False

            # Tighter sampling for the first 10s halves the miss window for
            # very brief connections. VNC.is_connecting() shells out to
            # vncserver, so this isn't widened further to avoid piling up
            # subprocess calls.
            poll_interval = 1 if elapsed < 10 else 2
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

        logger.warning("VNC connection timeout (60s)")
        await asyncio.to_thread(
            _http_post_safe, "/host/agent/vnc/report", {"vnc_state": 2}
        )
        # An LTR has already been reserved in the backend.  A delayed first
        # VNC connection is therefore the same recoverable user-side outage
        # as a laptop sleep, not a lifecycle terminal signal.
        return bool(self._context.get("is_ltr", False))

    # ------------------------------------------------------------------
    # Stage: ACTIVE_MONITOR (poll VNC + countdown timer)
    # ------------------------------------------------------------------
    async def _stage_active_monitor(self):
        self._state = AdhocSessionState.ACTIVE
        _save_session_state(self._context, self._state)

        # Start activity monitor for duty_cycle tracking
        if ActivityMonitor is not None:
            try:
                root = PathUtils.get_root_path()
                self._activity_monitor = ActivityMonitor(
                    config_path=root / "config" / "activity_tracker.json",
                    session_context={
                        "user_name": self._context.get("user_name", ""),
                        "host_id": self._context.get("host_id", ""),
                        "exec_mode": self._context.get("exec_mode", ""),
                        "category": self._context.get("category", ""),
                        "is_ltr": self._context.get("is_ltr", False),
                        "tc_id": self._context.get("tc_id", ""),
                        "cycle_name": self._context.get("cycle_name", ""),
                    },
                )
                self._activity_monitor.start_background()
                logger.info("Activity monitor started for session")
            except Exception as e:
                logger.warning(f"Activity monitor start failed: {e}")
                self._activity_monitor = None

        poll_interval = self._context["poll_interval"]
        notify_threshold = self._context["notify_before_expire"]
        notified = False
        retry_failures = 0

        remaining = self._deadline - time.monotonic()
        logger.info(
            f"Adhoc session ACTIVE: remaining={remaining:.0f}s, "
            f"poll={poll_interval}s"
        )

        while time.monotonic() < self._deadline:
            # Check force end
            if self._force_end_event.is_set():
                logger.info("Force end received during ACTIVE")
                break

            # Check extend
            if self._extend_event.is_set():
                self._extend_event.clear()
                self._apply_extend()
                notified = False

            # LTR sessions ignore VNC disconnect — user laptop sleep/shutdown
            # is expected and dominant behavior (see plan §2.1.1 Bug B).
            # Non-LTR adhoc sessions retain the original 3-strike break so
            # short sessions clean up promptly when the user closes VNC.
            is_ltr = bool(self._context.get("is_ltr", False))
            if not is_ltr:
                # Check VNC still connected (non-blocking via thread)
                try:
                    is_connected = await asyncio.to_thread(VNC.is_connecting)
                    if not is_connected:
                        retry_failures += 1
                        if retry_failures >= 3:
                            logger.info("VNC disconnected (3 consecutive checks)")
                            break
                    else:
                        retry_failures = 0
                except Exception as e:
                    retry_failures += 1
                    logger.warning(f"VNC poll error ({retry_failures}/3): {e}")
                    if retry_failures >= 3:
                        logger.info("VNC poll failed 3 times, treating as disconnect")
                        break
            elif not self._vnc_confirmed:
                # WAIT_VNC's sampling window missed the connect (or it hadn't
                # happened yet). Keep watching so a later real connection
                # still promotes locked -> occupied instead of being lost —
                # this does NOT turn into disconnect-monitoring afterward,
                # matching the existing LTR ignore-disconnect behavior.
                try:
                    if await asyncio.to_thread(VNC.is_connecting):
                        logger.info("VNC connected late (after WAIT_VNC timeout)")
                        report_result = await asyncio.to_thread(
                            _http_post_safe, "/host/agent/vnc/report", {"vnc_state": 1}
                        )
                        # Gate on success so a transient report failure keeps
                        # _vnc_confirmed False and this branch retries on the
                        # next poll, instead of permanently giving up.
                        if report_result.get("success"):
                            set_agent_status(vnc=True)
                            self._vnc_confirmed = True
                        else:
                            logger.warning("Late vnc_state=1 report failed; will retry next poll")
                except Exception as e:
                    logger.warning(f"Late VNC confirmation check error: {e}")

            # DUT Toast notification at threshold (non-blocking to avoid websocket timeout)
            remaining = self._deadline - time.monotonic()
            if not notified and remaining <= notify_threshold and remaining > 0:
                notified = True
                mins_left = int(remaining) // 60
                await show_message_box_async(
                    msg=f"Adhoc session expires in {mins_left} min. Extend or save your work.",
                    title="xCopilot Session Warning",
                )
                logger.info(f"DUT Toast sent: {mins_left} min remaining")

            await asyncio.sleep(poll_interval)

        self._state = AdhocSessionState.ENDING

    # ------------------------------------------------------------------
    # Stage: CLEANUP
    # ------------------------------------------------------------------
    async def _stage_cleanup(self):
        if self._cleanup_done:
            return
        self._cleanup_done = True
        self._state = AdhocSessionState.CLEANUP

        # Disconnect VNC if still connected
        try:
            if get_agent_status_by_key("vnc"):
                await asyncio.to_thread(VNC.disconnect)
                logger.info("VNC disconnected in cleanup")
        except Exception as e:
            logger.warning(f"VNC disconnect error in cleanup: {e}")

        # Calculate elapsed
        elapsed_seconds = int(time.monotonic() - self._start_time) if self._start_time else 0

        # Determine end reason
        reason = "timeout"
        if self._force_end_event.is_set():
            reason = "force_end"
        elif time.monotonic() < self._deadline:
            reason = "vnc_closed"

        # Stop activity monitor and get duty_cycle
        duty_cycle = None
        if self._activity_monitor is not None:
            try:
                duty_cycle = self._activity_monitor.stop_and_get_duty_cycle()
                logger.info(f"Activity monitor stopped, duty_cycle={duty_cycle:.4f}")
            except Exception as e:
                logger.warning(f"Activity monitor stop error: {e}")
            self._activity_monitor = None

        # Report vnc disconnect to ensure host_state transitions correctly.
        # vnc/report with vnc_state=2 uses exec_log-based host lookup (works
        # regardless of whether host_id is numeric id or mg_id UUID).
        vnc_report_payload = {"vnc_state": 2}
        try:
            if get_agent_status_by_key("vnc") or reason != "force_end":
                await asyncio.to_thread(
                    _http_post_safe, "/host/agent/vnc/report", vnc_report_payload
                )
        except Exception as e:
            logger.warning(f"Failed to report vnc disconnect: {e}")

        # Report session ended to backend (sole owner of exec_log closure)
        session_ended_payload = {
            "host_id": self._context.get("host_id", ""),
            "reason": reason,
            "elapsed_seconds": elapsed_seconds,
        }
        if self._context.get("exec_log_id"):
            session_ended_payload["exec_log_id"] = self._context["exec_log_id"]
        if duty_cycle is not None:
            session_ended_payload["duty_cycle"] = round(duty_cycle, 4)
        try:
            await asyncio.to_thread(
                _http_post_safe,
                "/host/agent/adhoc/session_ended",
                session_ended_payload,
            )
        except Exception as e:
            logger.error(f"Failed to report session_ended: {e}")

        # Release agent status AFTER all HTTP reporting is done.
        # This prevents a new session from starting while cleanup is still
        # communicating with the backend.
        set_agent_status(use=False, vnc=False)

        _clear_session_state()
        self._state = AdhocSessionState.IDLE
        logger.info(f"Adhoc session CLEANUP done: reason={reason}, elapsed={elapsed_seconds}s")

    # ------------------------------------------------------------------
    # External event handlers
    # ------------------------------------------------------------------
    def handle_extend(self, extend_seconds: int = 1800):
        """Called when session_extended message received."""
        if not self.is_active:
            logger.warning("Extend received but no active adhoc session")
            return

        new_deadline = self._deadline + extend_seconds
        if new_deadline > self._absolute_max_deadline:
            logger.warning(
                f"Extend rejected: would exceed absolute max deadline"
            )
            return

        self._extend_seconds = extend_seconds
        self._extend_event.set()
        logger.info(f"Extend queued: +{extend_seconds}s")

    def handle_force_end(self, reason: str = "user_disconnect", exec_log_id: Any = None):
        """Called when session_force_end message received."""
        if not self.is_active:
            logger.warning("Force end received but no active adhoc session")
            return

        current_exec_log_id = self._context.get("exec_log_id")
        # A force_end that names a specific (older) exec_log_id but doesn't
        # match the session actually running now is stale — e.g. it was
        # queued for a reservation that has since ended and been replaced by
        # a new one on the same host. Messages without an exec_log_id (older
        # senders) are accepted unconditionally for backward compatibility.
        if (
            exec_log_id is not None
            and current_exec_log_id is not None
            and str(exec_log_id) != str(current_exec_log_id)
        ):
            logger.warning(
                f"Ignoring stale force_end for exec_log_id={exec_log_id}, "
                f"current session is exec_log_id={current_exec_log_id}"
            )
            return

        logger.info(f"Force end triggered: reason={reason}")
        self._force_end_event.set()

    def _apply_extend(self):
        self._deadline += self._extend_seconds
        remaining = self._deadline - time.monotonic()
        logger.info(
            f"Session extended: +{self._extend_seconds}s, "
            f"new remaining={remaining:.0f}s"
        )
        self._extend_seconds = 0


# ----------------------------------------------------------------------
# Module-level singleton & helpers
# ----------------------------------------------------------------------
_current_pipeline: Optional[AdhocSessionPipeline] = None
_pipeline_task: Optional[asyncio.Task] = None
_start_lock: asyncio.Lock = asyncio.Lock()


def get_current_pipeline() -> Optional[AdhocSessionPipeline]:
    return _current_pipeline


async def start_adhoc_session(notification: Dict[str, Any]) -> Optional[str]:
    """
    Public entry point — starts a new adhoc session pipeline.
    Called from message_handler exec_mode router.

    Returns:
        None on success (pipeline started or scheduled to start).
        "busy" if another pipeline is already active — caller can log/report.
    """
    global _current_pipeline, _pipeline_task

    async with _start_lock:
        if _pipeline_task and not _pipeline_task.done():
            logger.warning("Adhoc session start already scheduled; returning 'busy' marker")
            return "busy"
        if _current_pipeline and _current_pipeline.is_active:
            logger.warning(
                "Adhoc session already active; returning 'busy' marker "
                f"(current state={_current_pipeline.state.value if hasattr(_current_pipeline.state, 'value') else _current_pipeline.state})"
            )
            return "busy"

        _current_pipeline = AdhocSessionPipeline()
        _pipeline_task = asyncio.create_task(_current_pipeline.start(notification))
    return None


def handle_session_extended(message: Dict[str, Any]):
    """Handle session_extended WebSocket message."""
    extend_seconds = message.get("extend_seconds", 1800)
    if _current_pipeline:
        _current_pipeline.handle_extend(extend_seconds)
    else:
        logger.warning("session_extended received but no pipeline active")


def handle_session_force_end(message: Dict[str, Any]):
    """Handle session_force_end WebSocket message."""
    reason = message.get("reason", "user_disconnect")
    exec_log_id = message.get("exec_log_id")
    if _current_pipeline:
        _current_pipeline.handle_force_end(reason, exec_log_id)
    else:
        logger.warning("session_force_end received but no pipeline active")


def _save_session_state(context: Dict[str, Any], state: AdhocSessionState):
    ttl = context.get("max_session_duration", 14400) + 600
    # Enrich context with wall-clock deadline anchor for R1 recovery.
    # This must be a UTC ISO string so it survives Agent process restarts.
    # Stamp only once — preserve the original begin_time_utc on later saves
    # (do not reset when the pipeline moves through WAIT_VNC → ACTIVE).
    enriched = dict(context)
    if not enriched.get("begin_time_utc"):
        enriched["begin_time_utc"] = datetime.now(timezone.utc).isoformat()
    payload = {"context": enriched, "state": state.value}
    cache.set(MANUAL_SESSION_CACHE_KEY, payload, ttl=ttl)
    from ..core.persistent_storage import set_persistent_data
    set_persistent_data("adhoc_session", payload, "adhoc_session")


def _clear_session_state():
    cache.delete(MANUAL_SESSION_CACHE_KEY)
    from ..core.persistent_storage import delete_persistent_data
    delete_persistent_data("adhoc_session", "adhoc_session")


def _compute_ltr_remaining_seconds(context: Dict[str, Any]) -> int:
    """R1 helper: compute LTR remaining time from persisted begin_time_utc
    and max_session_duration. Returns 0 if inputs are missing or the deadline
    has already passed.

    Invariant (Phase 8 hotfix A-1): the returned value is always in
    ``[0, max_session_duration]`` for any input, including clock-skew cases
    where ``begin_time_utc`` is in the future (elapsed < 0) or where
    ``begin_time_utc`` was tampered to a value far in the past
    (elapsed > max_session_duration).
    """
    begin_iso = context.get("begin_time_utc")
    try:
        max_dur = int(context.get("max_session_duration", 0) or 0)
    except (TypeError, ValueError):
        max_dur = 0
    if not begin_iso or max_dur <= 0:
        return 0
    try:
        begin_dt = datetime.fromisoformat(begin_iso)
        if begin_dt.tzinfo is None:
            begin_dt = begin_dt.replace(tzinfo=timezone.utc)
        elapsed = (datetime.now(timezone.utc) - begin_dt).total_seconds()
        # A-1: clamp negative elapsed (future begin_time from clock skew or
        # tamper) to 0 so remaining cannot exceed max_dur; also clamp the
        # upper bound explicitly for defense-in-depth against future changes.
        remaining = int(max_dur - max(0.0, elapsed))
        return max(0, min(max_dur, remaining))
    except Exception as e:
        logger.warning(f"Failed to compute LTR remaining: {e}")
        return 0


def _report_orphan_ended(
    context: Dict[str, Any],
    host_id: str,
    *,
    reason: str,
    elapsed_seconds: int,
):
    """Report session end to backend for an orphan session that cannot be
    resumed. Ensures exec_log_id (§0 authoritative binding key) is included
    when present so the backend can close the correct row.
    """
    try:
        orphan_payload: Dict[str, Any] = {
            "host_id": host_id,
            "reason": reason,
            "elapsed_seconds": elapsed_seconds,
        }
        if context.get("exec_log_id"):
            orphan_payload["exec_log_id"] = context["exec_log_id"]
        result = _http_post_safe(
            "/host/agent/adhoc/session_ended",
            orphan_payload,
            timeout=10,
        )
        if result.get("success"):
            logger.info(
                f"Orphan session reported (reason={reason}, "
                f"exec_log_id={context.get('exec_log_id')})"
            )
        else:
            logger.warning(f"Orphan session report failed: {result.get('data')}")
    except Exception as e:
        logger.error(f"Failed to report orphan session: {e}")


def _schedule_ltr_resume(context: Dict[str, Any], remaining_seconds: int) -> bool:
    """R1 helper: schedule start_adhoc_session on the running asyncio loop
    to rebuild an AdhocSessionPipeline in resume mode.

    recover_orphan_session() itself is sync (called from HostInit.__init__
    which runs inside async Application.initialize()). By the time it fires
    the asyncio loop is already running (see docs/features/ltr_reconnect/
    IMPLEMENTATION_PLAN.md §9 Q1).

    Returns True if a resume task was scheduled, False otherwise. The caller
    keeps the persistent state on True (pipeline will re-save) and deletes
    it on False (falls through to legacy report path).
    """
    resume_notification = {
        "host_id": context.get("host_id", ""),
        # Pass the full persisted context back as `details` so _stage_init
        # reconstructs the same _context — including exec_log_id (§0 binding
        # key), is_ltr, user_name, exec_mode, category, tc_id, cycle_name,
        # and the newly minted is_resume/remaining_seconds fields.
        "details": {
            **context,
            "is_resume": True,
            "remaining_seconds": remaining_seconds,
            "skip_vnc_wait": True,
        },
    }
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        logger.warning(
            "R1 resume: no running asyncio loop at recover time; "
            "cannot schedule resume — falling back to legacy report path"
        )
        return False

    # Fire-and-forget. start_adhoc_session is async and holds _start_lock
    # internally; the task will begin as soon as the loop yields.
    loop.create_task(start_adhoc_session(resume_notification))
    logger.info(
        f"R1 resume scheduled: host={context.get('host_id')}, "
        f"exec_log_id={context.get('exec_log_id')}, remaining={remaining_seconds}s"
    )
    return True


def recover_orphan_session():
    """
    On Agent startup, check persistent storage for an interrupted adhoc
    session and take one of three actions:

      1. **LTR + alive** → schedule R1 resume on the running asyncio loop.
         Persistent state is preserved (pipeline will re-save on state
         change). Backend is not notified of a "restart" — the session
         continues transparently.

      2. **LTR + deadline passed** → report reason=timeout to backend and
         clear state. (Never emit "agent_restart" for LTR — the session
         did complete, it just did so while the Agent was down.)

      3. **Non-LTR orphan** → legacy behavior: write activity_log orphan
         end, report reason=agent_restart to backend, clear state.

    All backend HTTP goes through `_http_post_safe` (60s hard cap).
    exec_log_id (§0 authoritative binding key) survives via
    `adhoc_session.json` and is included in every payload.
    """
    from ..core.persistent_storage import get_persistent_data, delete_persistent_data
    session_data = get_persistent_data("adhoc_session", "adhoc_session")
    if not session_data:
        return

    context = session_data.get("context", {})
    state = session_data.get("state", "")
    if state in ("idle", "cleanup", ""):
        delete_persistent_data("adhoc_session", "adhoc_session")
        return

    host_id = context.get("host_id", "")
    is_ltr = bool(context.get("is_ltr", False))
    exec_log_id = context.get("exec_log_id")
    logger.warning(
        f"Orphan adhoc session detected on startup: "
        f"host={host_id}, state={state}, is_ltr={is_ltr}, exec_log_id={exec_log_id}"
    )

    # ─── LTR R1 branch — attempt local resume ─────────────────────────────
    if is_ltr:
        remaining = _compute_ltr_remaining_seconds(context)
        if remaining > 0:
            logger.info(
                f"LTR R1 resume: attempting to rebuild pipeline locally, "
                f"remaining={remaining}s"
            )
            if _schedule_ltr_resume(context, remaining):
                # Keep persistent state — the resumed pipeline will re-save.
                return
            # Scheduling failed (no running loop) — fall through to timeout
            # report so the row does not linger with end_time IS NULL.
            _report_orphan_ended(
                context, host_id, reason="timeout", elapsed_seconds=0
            )
            delete_persistent_data("adhoc_session", "adhoc_session")
            return
        else:
            logger.info("LTR deadline already passed; reporting timeout")
            _report_orphan_ended(
                context, host_id, reason="timeout", elapsed_seconds=0
            )
            delete_persistent_data("adhoc_session", "adhoc_session")
            return

    # ─── Legacy non-LTR path (unchanged behavior) ─────────────────────────
    try:
        from activity_monitor.logger import ActivityLogger
        root = PathUtils.get_root_path()
        log_dir = root / "logs"
        al = ActivityLogger(log_dir=log_dir)
        al.log_orphan_end(
            session_context={
                "user_name": context.get("user_name", ""),
                "exec_mode": context.get("exec_mode", ""),
            },
            previous_state=state,
        )
        al.close()
    except Exception as e:
        logger.debug(f"Could not write orphan end to activity log: {e}")

    _report_orphan_ended(
        context, host_id, reason="agent_restart", elapsed_seconds=0
    )
    delete_persistent_data("adhoc_session", "adhoc_session")
