"""Turn the CLI's JSON into domain types.

Pure functions: given bytes, produce a MarketSnapshot or raise. No subprocess,
no clock beyond the timestamp handed in, so every branch is testable against a
recorded fixture.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from tsys.core import DataUnavailable
from tsys.domain import Bar, MarketSnapshot, Quote


def _dec(value: Any, field: str) -> Decimal:
    if value is None:
        raise DataUnavailable(f"missing field {field!r}")
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError) as e:
        raise DataUnavailable(f"unparseable {field}={value!r}") from e


def _opt(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError):
        return None


def _ts(value: Any) -> datetime:
    """Bar timestamps arrive as unix seconds or ms."""
    if isinstance(value, (int, float)):
        seconds = value / 1000 if value > 10_000_000_000 else value
        return datetime.fromtimestamp(seconds, UTC)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as e:
            raise DataUnavailable(f"unparseable bar timestamp {value!r}") from e
    raise DataUnavailable(f"unparseable bar timestamp {value!r}")


def unwrap(raw: str | bytes) -> dict[str, Any]:
    """The CLI wraps payloads in {ok, data} or {error}. Unwrap or raise."""
    try:
        doc = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as e:
        snippet = (raw or b"")[:160]
        raise DataUnavailable(f"CLI returned non-JSON: {snippet!r}") from e
    if isinstance(doc, dict):
        if doc.get("error"):
            raise DataUnavailable(f"CLI error: {doc['error']}")
        if doc.get("ok") is False:
            raise DataUnavailable(f"CLI reported failure: {doc}")
        inner = doc.get("data")
        if isinstance(inner, (dict, list)):
            return {"data": inner} if isinstance(inner, list) else inner
    return doc if isinstance(doc, dict) else {"data": doc}


def parse_quote(raw: str | bytes, *, symbol: str, now: datetime | None = None) -> Quote:
    d = unwrap(raw)
    last = d.get("last") or d.get("ltp") or d.get("price") or d.get("last_price")
    return Quote(
        symbol=d.get("symbol") or symbol,
        last=_dec(last, "last"),
        ts=now or datetime.now(UTC),
        bid=_opt(d.get("bid")),
        ask=_opt(d.get("ask")),
    )


def parse_bars(raw: str | bytes) -> tuple[Bar, ...]:
    d = unwrap(raw)
    # Explicit None checks: an empty list is falsy, and "empty" is a different
    # failure from "absent" — the caller needs to tell them apart.
    rows = next(
        (d[k] for k in ("bars", "data", "ohlcv") if d.get(k) is not None),
        None,
    )
    if rows is None or not isinstance(rows, list):
        raise DataUnavailable("no bar array in CLI response")
    out: list[Bar] = []
    for r in rows:
        if isinstance(r, dict):
            out.append(
                Bar(
                    ts=_ts(r.get("time") or r.get("ts") or r.get("timestamp")),
                    open=_dec(r.get("open"), "open"),
                    high=_dec(r.get("high"), "high"),
                    low=_dec(r.get("low"), "low"),
                    close=_dec(r.get("close"), "close"),
                    volume=_opt(r.get("volume")) or Decimal(0),
                )
            )
        elif isinstance(r, (list, tuple)) and len(r) >= 5:
            out.append(
                Bar(
                    ts=_ts(r[0]), open=_dec(r[1], "open"), high=_dec(r[2], "high"),
                    low=_dec(r[3], "low"), close=_dec(r[4], "close"),
                    volume=_opt(r[5] if len(r) > 5 else None) or Decimal(0),
                )
            )
    if not out:
        raise DataUnavailable("bar array was empty")
    return tuple(sorted(out, key=lambda b: b.ts))


def build_snapshot(
    *, index: str, timeframe: str, quote_raw: str | bytes, bars_raw: str | bytes,
    captured_at: datetime | None = None,
) -> MarketSnapshot:
    captured = captured_at or datetime.now(UTC)
    return MarketSnapshot(
        index=index,
        timeframe=timeframe,
        quote=parse_quote(quote_raw, symbol=index, now=captured),
        bars=parse_bars(bars_raw),
        captured_at=captured,
    )
