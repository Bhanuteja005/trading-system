"""The only code in the system that talks to OpenAlgo.

Three gates sit in front of every write, in order, and none can be bypassed by
calling a different method: the kill switch, the mode gate, then the ledger.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import requests

from tsys.config import BrokerSettings, Mode
from tsys.core import (
    BrokerError,
    DataUnavailable,
    KillSwitchEngaged,
    client_order_id as make_id,
    get_logger,
    log_event,
    with_retry,
)
from tsys.domain import OrderRequest, OrderResult, Quote

from .idempotency import IdempotencyLedger

log = get_logger(__name__)

__all__ = ["BrokerClient", "make_id"]


class BrokerClient:
    def __init__(
        self,
        settings: BrokerSettings,
        *,
        mode: Mode,
        kill_switch: Path,
        ledger: IdempotencyLedger,
        session: requests.Session | None = None,
    ) -> None:
        self._s = settings
        self._mode = mode
        self._kill_switch = kill_switch
        self._ledger = ledger
        self._http = session or requests.Session()

    # ---- gates --------------------------------------------------------------

    def _assert_orders_allowed(self) -> None:
        if self._kill_switch.exists():
            raise KillSwitchEngaged(
                f"kill switch present at {self._kill_switch}; refusing to place orders"
            )

    @property
    def will_contact_broker(self) -> bool:
        """DRY_RUN never sends a write. This is the mode gate."""
        return self._mode in (Mode.PAPER, Mode.LIVE)

    # ---- transport ----------------------------------------------------------

    def _post(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = {"apikey": self._s.api_key.get_secret_value(), **payload}
        try:
            r = self._http.post(
                f"{self._s.url}/api/v1/{endpoint}",
                json=body,
                timeout=self._s.timeout_seconds,
            )
        except requests.Timeout as e:
            raise DataUnavailable(f"{endpoint} timed out") from e
        except requests.RequestException as e:
            raise DataUnavailable(f"{endpoint} unreachable: {e}") from e

        if r.status_code >= 500:
            raise BrokerError(f"{endpoint} HTTP {r.status_code}", retryable=True)
        if r.status_code >= 400:
            raise BrokerError(f"{endpoint} HTTP {r.status_code}: {r.text[:200]}", retryable=False)
        try:
            return r.json()
        except ValueError as e:
            raise BrokerError(f"{endpoint} returned non-JSON", retryable=False) from e

    # ---- reads --------------------------------------------------------------

    def quote(self, symbol: str, exchange: str) -> Quote:
        def _fetch() -> dict[str, Any]:
            return self._post("quotes", {"symbol": symbol, "exchange": exchange})

        data = with_retry(_fetch, attempts=self._s.max_retries)
        node = data.get("data", data)
        raw = node.get("ltp") or node.get("last_price")
        if raw is None:
            raise DataUnavailable(f"no ltp for {symbol}")
        try:
            last = Decimal(str(raw))
        except InvalidOperation as e:
            raise DataUnavailable(f"unparseable ltp {raw!r} for {symbol}") from e

        def _opt(key: str) -> Decimal | None:
            v = node.get(key)
            try:
                return Decimal(str(v)) if v is not None else None
            except InvalidOperation:
                return None

        return Quote(
            symbol=symbol, last=last, ts=datetime.now(UTC),
            bid=_opt("bid"), ask=_opt("ask"),
        )

    # ---- writes -------------------------------------------------------------

    def place_order(self, req: OrderRequest) -> OrderResult:
        """Idempotent by client_order_id. Safe to retry after a timeout."""
        self._assert_orders_allowed()

        prior = self._ledger.get(req.client_order_id)
        if prior is not None and prior.get("state") in ("placed", "in_flight"):
            log_event(
                log, logging.WARNING, "order.duplicate_suppressed",
                client_order_id=req.client_order_id, prior_state=prior.get("state"),
            )
            return OrderResult(
                ok=prior.get("state") == "placed",
                client_order_id=req.client_order_id,
                broker_order_id=prior.get("broker_order_id"),
                deduplicated=True,
                error=None if prior.get("state") == "placed" else "previous attempt in flight",
            )

        payload = {
            "strategy": self._s.strategy_tag,
            "symbol": req.symbol,
            "action": req.action.value,
            "exchange": req.exchange,
            "pricetype": req.price_type,
            "product": req.product.value,
            "quantity": str(req.quantity),
        }

        if not self.will_contact_broker:
            log_event(
                log, logging.INFO, "order.dry_run",
                client_order_id=req.client_order_id, **payload,
            )
            return OrderResult(
                ok=True, client_order_id=req.client_order_id,
                broker_order_id=f"DRYRUN-{req.client_order_id}",
                submitted_at=datetime.now(UTC),
            )

        # Claim the id before the request leaves, so a crash still records intent.
        self._ledger.reserve(req.client_order_id, payload)
        try:
            resp = self._post("placeorder", payload)
        except DataUnavailable:
            # Unknown outcome: keep the reservation so a retry cannot double-fill.
            log_event(
                log, logging.ERROR, "order.unknown_outcome",
                client_order_id=req.client_order_id,
            )
            raise
        except BrokerError as e:
            if not e.retryable:
                # Definitively rejected: the id was never consumed, so free it.
                self._ledger.release(req.client_order_id)
            raise

        ok = resp.get("status") == "success"
        broker_id = resp.get("orderid")
        self._ledger.complete(req.client_order_id, broker_id, ok)
        log_event(
            log, logging.INFO if ok else logging.ERROR,
            "order.placed" if ok else "order.rejected",
            client_order_id=req.client_order_id, broker_order_id=broker_id,
            symbol=req.symbol, quantity=req.quantity, action=req.action.value,
        )
        return OrderResult(
            ok=ok, client_order_id=req.client_order_id, broker_order_id=broker_id,
            error=None if ok else str(resp)[:300], submitted_at=datetime.now(UTC),
        )
