"""A durable record of which client_order_ids already reached the broker.

Placement is retried on timeout, and a timeout is exactly the case where we do
not know whether the order landed. The ledger is written *before* the request
goes out, so a crash mid-flight still leaves evidence that the id was used.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class IdempotencyLedger:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, dict[str, Any]] = self._load()

    def _load(self) -> dict[str, dict[str, Any]]:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def _flush(self) -> None:
        # Atomic replace: a crash mid-write must not truncate the ledger.
        fd, tmp = tempfile.mkstemp(dir=str(self.path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(self._cache, fh, indent=2, default=str)
            os.replace(tmp, self.path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    def seen(self, client_order_id: str) -> bool:
        return client_order_id in self._cache

    def get(self, client_order_id: str) -> dict[str, Any] | None:
        return self._cache.get(client_order_id)

    def reserve(self, client_order_id: str, payload: dict[str, Any]) -> None:
        """Claim the id before the request is sent."""
        self._cache[client_order_id] = {
            "state": "in_flight",
            "reserved_at": datetime.now(UTC).isoformat(),
            "request": payload,
        }
        self._flush()

    def complete(self, client_order_id: str, broker_order_id: str | None, ok: bool) -> None:
        entry = self._cache.setdefault(client_order_id, {})
        entry.update(
            state="placed" if ok else "failed",
            broker_order_id=broker_order_id,
            completed_at=datetime.now(UTC).isoformat(),
        )
        self._flush()

    def release(self, client_order_id: str) -> None:
        """Drop a reservation that provably never reached the broker."""
        if self._cache.pop(client_order_id, None) is not None:
            self._flush()
