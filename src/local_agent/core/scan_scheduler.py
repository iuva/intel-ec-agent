"""
Fixed-time scan window scheduler.

Calculates delay (in seconds) until a random moment within
the configured PRC scan window [window_start, window_end).

500+ agents each pick a random offset per cycle, naturally
staggering across the 2-hour window.

No external dependencies — stdlib only.
"""

import random
from datetime import datetime, timedelta, timezone

from ..logger import get_logger

logger = get_logger(__name__)

# PRC = UTC+8 (fixed offset, avoids zoneinfo/pytz dependency on Python 3.8)
_PRC = timezone(timedelta(hours=8))


class ScanScheduler:
    """Calculate delay to next scan window."""

    def __init__(self, window_start: str = "05:00", window_end: str = "07:00",
                 tz_name: str = "UTC+8", interval_days: int = 1):
        """
        Args:
            window_start:  "HH:MM" start of daily scan window (inclusive).
            window_end:    "HH:MM" end of daily scan window (exclusive).
            tz_name:       Timezone label used for logging only. Scheduler is
                           hardcoded to UTC+8; supplying any other value emits
                           a warning at construction time.
            interval_days: Number of days between successive scans. 1 = daily
                           (default), 2 = every other day, etc. Clamped to
                           [1, 30]; values outside that range (including 0,
                           negatives, or absurdly large numbers) fall back to 1
                           with a warning. Zero is explicitly rejected because
                           it would produce a zero-second reschedule delay,
                           causing a tight-loop scan storm.
        """
        try:
            sh, sm = (int(x) for x in window_start.split(":"))
            eh, em = (int(x) for x in window_end.split(":"))
            if not (0 <= sh <= 23 and 0 <= sm <= 59 and 0 <= eh <= 23 and 0 <= em <= 59):
                raise ValueError("out of range")
        except (ValueError, AttributeError):
            logger.warning(
                f"Invalid window format '{window_start}'-'{window_end}', "
                f"falling back to 05:00-07:00"
            )
            sh, sm, eh, em = 5, 0, 7, 0

        # Clamp interval_days to [1, 30]. See docstring for rationale.
        try:
            interval_days = int(interval_days)
        except (TypeError, ValueError):
            logger.warning(
                f"interval_days={interval_days!r} is not an integer, using 1"
            )
            interval_days = 1
        if not (1 <= interval_days <= 30):
            logger.warning(
                f"interval_days={interval_days} out of [1,30], using 1"
            )
            interval_days = 1
        self._interval_days = interval_days

        self._start_minutes = sh * 60 + sm
        self._end_minutes = eh * 60 + em
        self._tz_name = tz_name

        # Guard: this scheduler hardcodes UTC+8 (see _PRC). If operator
        # configures a non-PRC timezone in config.ini, warn loudly so the
        # divergence between config and behavior is not silent.
        if tz_name and tz_name.strip().lower() not in ("asia/shanghai", "prc", "utc+8", "utc+08:00"):
            logger.warning(
                f"scan.timezone='{tz_name}' is not honored — scheduler always "
                f"uses PRC (UTC+8). Set scan.timezone=Asia/Shanghai to silence "
                f"this warning."
            )

        if self._end_minutes <= self._start_minutes:
            logger.warning(
                f"window_end ({window_end}) <= window_start ({window_start}), "
                f"falling back to 05:00-07:00"
            )
            self._start_minutes = 5 * 60
            self._end_minutes = 7 * 60

    def seconds_until_next_scan(self, skip_current_window: bool = False) -> float:
        """Return seconds until a random time within next scan window.

        Logic:
        1. Pick a random minute within [window_start, window_end).
        2. Build target datetime for today (PRC).
        3. If that time is still in the future today, use today.
        4. Otherwise, use tomorrow (advance by interval_days).
        5. Return (target - now).total_seconds().

        Args:
            skip_current_window: When True, if `now` is currently inside the
                scan window, force the next target to be at least
                `interval_days` days from today. This is the correct choice
                for the "just finished a scan cycle" call site: without it,
                the stateless random draw would frequently roll another
                minute later in the same window (~66% chance at 05:40 for a
                05:00-07:00 window), causing 2+ scans/day (BUG-N17).
                Defaults to False so busy-defer and startup paths keep their
                pre-existing behavior (roll a fresh time inside the current
                window when appropriate).

        Each call re-rolls the random offset, so 500+ agents
        naturally stagger across the window.
        """
        now = datetime.now(tz=_PRC)

        # Random minute within window
        rand_minute = random.randint(self._start_minutes, self._end_minutes - 1)
        target_hour = rand_minute // 60
        target_min = rand_minute % 60

        # Build target for today
        target = now.replace(hour=target_hour, minute=target_min, second=0, microsecond=0)

        # If already past, push to next scheduled day (respects interval_days).
        # Also push if the caller explicitly requested skipping the current
        # window (post-scan reschedule path — see BUG-N17).
        if target <= now:
            target += timedelta(days=self._interval_days)
        elif skip_current_window and self.is_in_scan_window():
            target += timedelta(days=self._interval_days)

        delay = (target - now).total_seconds()
        logger.info(
            f"Next scan scheduled at {target.strftime('%Y-%m-%d %H:%M')} {self._tz_name} "
            f"(in {delay / 3600:.1f}h, interval={self._interval_days}d)"
        )
        return delay

    def is_in_scan_window(self) -> bool:
        """True if current PRC time is within [window_start, window_end)."""
        now = datetime.now(tz=_PRC)
        now_minutes = now.hour * 60 + now.minute
        return self._start_minutes <= now_minutes < self._end_minutes
