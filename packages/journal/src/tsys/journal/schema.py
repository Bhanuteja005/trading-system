"""The record written for every decision, whether or not it became an order.

The input snapshot is stored alongside the verdict, so any order can be
reconstructed and re-evaluated after the fact.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from tsys.domain import Decision, MarketSnapshot, OrderResult

SCHEMA_VERSION = 1


def _plain(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if hasattr(value, "value"):  # StrEnum
        return value.value
    return value


@dataclass(frozen=True, slots=True)
class JournalEntry:
    cycle_id: str
    index: str
    mode: str
    decision: Decision
    snapshot: MarketSnapshot
    order: OrderResult | None = None
    rejected_by: str | None = None
    at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_record(self, *, include_bars: int = 30) -> dict[str, Any]:
        """A JSON-safe record. Bars are truncated to the most recent N: enough
        to re-derive the decision, small enough to keep the log readable."""
        snap = self.snapshot
        return _plain(
            {
                "v": SCHEMA_VERSION,
                "at": self.at,
                "cycle_id": self.cycle_id,
                "index": self.index,
                "mode": self.mode,
                "decision": asdict(self.decision),
                "input": {
                    "timeframe": snap.timeframe,
                    "captured_at": snap.captured_at,
                    "source": snap.source,
                    "age_seconds": round(snap.age_seconds(self.at), 3),
                    "quote": asdict(snap.quote),
                    "bar_count": len(snap.bars),
                    "bars": [asdict(b) for b in snap.bars[-include_bars:]],
                },
                "order": asdict(self.order) if self.order else None,
                "rejected_by": self.rejected_by,
            }
        )
