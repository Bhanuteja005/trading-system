"""Deterministic identifiers, which is what makes retries safe.

A client_order_id is derived from the decision's own content. Re-submitting the
same decision yields the same id, so the broker client can recognise a duplicate;
a genuinely new decision yields a different one.
"""

from __future__ import annotations

import hashlib
from datetime import date
from decimal import Decimal


def client_order_id(
    *,
    index: str,
    side: str,
    entry: Decimal,
    stop_loss: Decimal,
    target: Decimal,
    session: date,
    sequence: int = 0,
) -> str:
    """Stable 24-char id for one intended entry.

    ``sequence`` exists for the rare deliberate re-entry on identical levels in
    the same session; leave it at 0 and identical intent collapses to one id.
    """
    payload = "|".join(
        [
            index.upper(),
            side.upper(),
            f"{entry:.4f}",
            f"{stop_loss:.4f}",
            f"{target:.4f}",
            session.isoformat(),
            str(sequence),
        ]
    )
    return "tsys" + hashlib.sha256(payload.encode()).hexdigest()[:20]
