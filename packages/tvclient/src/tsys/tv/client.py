"""Run the Node CLI and hand back typed data.

The Python side never speaks CDP. It shells out to the same `tv` CLI a human
would use, which keeps one implementation of the TradingView protocol.
"""

from __future__ import annotations

import logging
import subprocess
from datetime import UTC, datetime

from tsys.config import TradingViewSettings
from tsys.core import DataUnavailable, StaleData, get_logger, log_event, with_retry
from tsys.domain import MarketSnapshot

from .parse import build_snapshot

log = get_logger(__name__)


class TradingViewClient:
    def __init__(self, settings: TradingViewSettings, *, runner=None) -> None:
        self._s = settings
        self._run = runner or self._subprocess_run

    def _subprocess_run(self, args: list[str]) -> bytes:
        cmd = [self._s.node_binary, str(self._s.cli_path), *args]
        try:
            proc = subprocess.run(
                cmd, capture_output=True, timeout=self._s.timeout_seconds, check=False
            )
        except FileNotFoundError as e:
            raise DataUnavailable(f"node or CLI not found: {cmd[0]} {cmd[1]}") from e
        except subprocess.TimeoutExpired as e:
            raise DataUnavailable(f"tv {' '.join(args)} timed out") from e
        if proc.returncode != 0:
            err = (proc.stderr or b"")[:300].decode("utf-8", "replace")
            raise DataUnavailable(f"tv {' '.join(args)} exited {proc.returncode}: {err}")
        return proc.stdout

    def health(self) -> bool:
        """Is TradingView reachable over CDP right now?"""
        try:
            self._run(["status"])
            return True
        except DataUnavailable:
            return False

    def snapshot(self, index: str, *, timeframe: str = "5", bars: int = 200) -> MarketSnapshot:
        """Fetch one index. Raises rather than returning partial or stale data."""
        self._run(["symbol", index])
        self._run(["timeframe", timeframe])

        quote_raw = with_retry(lambda: self._run(["quote", index]), attempts=2)
        bars_raw = with_retry(lambda: self._run(["ohlcv", "-n", str(bars)]), attempts=2)

        snap = build_snapshot(
            index=index, timeframe=timeframe,
            quote_raw=quote_raw, bars_raw=bars_raw,
            captured_at=datetime.now(UTC),
        )

        if snap.is_stale(self._s.max_quote_age_seconds):
            raise StaleData(
                f"{index} snapshot is {snap.age_seconds():.0f}s old, "
                f"limit {self._s.max_quote_age_seconds:.0f}s"
            )
        if not snap.has_enough_history(self._s.min_bars):
            raise DataUnavailable(
                f"{index} returned {len(snap.bars)} bars, need {self._s.min_bars}"
            )

        log_event(
            log, logging.INFO, "tv.snapshot",
            index=index, timeframe=timeframe, bars=len(snap.bars), last=str(snap.quote.last),
        )
        return snap
