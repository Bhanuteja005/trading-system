"""Bounded retry with exponential backoff.

Only errors that declare themselves retryable are retried. Order placement is
safe to retry because the client_order_id makes it idempotent.
"""

from __future__ import annotations

import time
from collections.abc import Callable

from .errors import BrokerError, DataUnavailable

RETRYABLE = (DataUnavailable, TimeoutError, ConnectionError)


def with_retry[T](
    fn: Callable[[], T],
    *,
    attempts: int = 3,
    base_delay: float = 0.5,
    max_delay: float = 4.0,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    last: Exception | None = None
    for i in range(attempts):
        try:
            return fn()
        except BrokerError as e:
            if not e.retryable:
                raise
            last = e
        except RETRYABLE as e:
            last = e
        if i < attempts - 1:
            sleep(min(base_delay * (2**i), max_delay))
    assert last is not None
    raise last
