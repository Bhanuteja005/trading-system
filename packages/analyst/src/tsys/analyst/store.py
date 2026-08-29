"""Append-only record of analyst calls, so accuracy can be scored later.

One line per call, holding the levels, the reasoning, and the snapshot that
produced it. Scoring reads this back and walks the bars that came after.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from tsys.domain import MarketSnapshot

from .schema import AnalystCall


class CallStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, call: AnalystCall, snapshot: MarketSnapshot, *, mode: str) -> str:
        call_id = f"{snapshot.index}-{datetime.now(UTC):%Y%m%dT%H%M%S}"
        record = {
            "call_id": call_id,
            "at": datetime.now(UTC).isoformat(),
            "mode": mode,
            "index": snapshot.index,
            "timeframe": snapshot.timeframe,
            "model": call.model,
            "side": call.side.value,
            "entry": str(call.levels.entry),
            "stop_loss": str(call.levels.stop_loss),
            "target": str(call.levels.target),
            "lots": call.lots,
            "confidence": str(call.confidence),
            "reward_risk": str(call.reward_risk),
            "technical_reasons": call.technical_reasons,
            "macro_reasons": call.macro_reasons,
            "snapshot_captured_at": snapshot.captured_at.isoformat(),
            "last_price": str(snapshot.quote.last),
        }
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, separators=(",", ":")) + "\n")
            fh.flush()
        return call_id

    def read(self) -> Iterator[dict[str, Any]]:
        if not self.path.exists():
            return
        with self.path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError:
                        continue

    def unscored(self) -> list[dict[str, Any]]:
        return [r for r in self.read() if not r.get("outcome")]

    def record_outcome(self, call_id: str, outcome: str, r_multiple: Decimal) -> None:
        """Rewrite the file with the outcome attached. The file is small (one
        line per call per day), so a full rewrite is cheaper than an index."""
        rows = list(self.read())
        for r in rows:
            if r.get("call_id") == call_id:
                r["outcome"] = outcome
                r["r_multiple"] = str(r_multiple)
                r["scored_at"] = datetime.now(UTC).isoformat()
        tmp = self.path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r, separators=(",", ":")) + "\n")
        tmp.replace(self.path)
