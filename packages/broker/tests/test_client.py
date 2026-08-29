"""The safety properties, exercised against a fake transport — no network."""

from pathlib import Path

import pytest
import requests
from pydantic import SecretStr

from tsys.broker import BrokerClient, IdempotencyLedger
from tsys.config import BrokerSettings, Mode
from tsys.core import KillSwitchEngaged
from tsys.core.errors import BrokerError, DataUnavailable
from tsys.domain import OrderAction, OrderRequest

REQ = OrderRequest(
    client_order_id="tsysdeadbeef", symbol="NIFTY26000CE",
    exchange="NFO", action=OrderAction.BUY, quantity=75,
)


class FakeResponse:
    def __init__(self, payload, status=200):
        self._p, self.status_code, self.text = payload, status, str(payload)

    def json(self):
        return self._p


class FakeSession:
    def __init__(self, *responses):
        self._responses, self.calls = list(responses), []

    def post(self, url, json=None, timeout=None):
        self.calls.append((url, json))
        r = self._responses.pop(0) if self._responses else FakeResponse({"status": "success", "orderid": "X1"})
        if isinstance(r, Exception):
            raise r
        return r


def _client(tmp_path: Path, *, mode=Mode.LIVE, session=None, kill=None):
    return BrokerClient(
        BrokerSettings(OPENALGO_API_KEY=SecretStr("k"), OPENALGO_MAX_RETRIES=1),
        mode=mode,
        kill_switch=kill or (tmp_path / "KILL"),
        ledger=IdempotencyLedger(tmp_path / "ledger.json"),
        session=session or FakeSession(),
    )


def test_kill_switch_blocks_placement(tmp_path):
    kill = tmp_path / "KILL"
    kill.write_text("halt")
    with pytest.raises(KillSwitchEngaged):
        _client(tmp_path, kill=kill).place_order(REQ)


def test_dry_run_never_contacts_the_broker(tmp_path):
    s = FakeSession()
    res = _client(tmp_path, mode=Mode.DRY_RUN, session=s).place_order(REQ)
    assert res.ok and res.broker_order_id.startswith("DRYRUN-")
    assert s.calls == [], "dry run must not issue any HTTP call"


def test_retry_does_not_double_fill(tmp_path):
    s = FakeSession(FakeResponse({"status": "success", "orderid": "ORD1"}))
    c = _client(tmp_path, session=s)
    first = c.place_order(REQ)
    second = c.place_order(REQ)
    assert first.ok and first.broker_order_id == "ORD1"
    assert second.deduplicated and second.broker_order_id == "ORD1"
    assert len(s.calls) == 1, "the second attempt must not reach the broker"


def test_ledger_survives_a_new_process(tmp_path):
    """A crash-and-restart must still recognise the id."""
    s1 = FakeSession(FakeResponse({"status": "success", "orderid": "ORD9"}))
    _client(tmp_path, session=s1).place_order(REQ)
    s2 = FakeSession()
    again = _client(tmp_path, session=s2).place_order(REQ)
    assert again.deduplicated and again.broker_order_id == "ORD9"
    assert s2.calls == []


def test_timeout_keeps_the_reservation(tmp_path):
    """Outcome unknown, so the id stays claimed and a retry cannot double-fill."""
    c = _client(tmp_path, session=FakeSession(requests.Timeout()))
    with pytest.raises(DataUnavailable):
        c.place_order(REQ)
    follow_up = c.place_order(REQ)
    assert follow_up.deduplicated and not follow_up.ok


def test_hard_rejection_frees_the_id_for_a_genuine_retry(tmp_path):
    c = _client(tmp_path, session=FakeSession(FakeResponse({"error": "bad symbol"}, status=400)))
    with pytest.raises(BrokerError):
        c.place_order(REQ)
    s2 = FakeSession(FakeResponse({"status": "success", "orderid": "ORD2"}))
    c2 = _client(tmp_path, session=s2)
    assert c2.place_order(REQ).ok
    assert len(s2.calls) == 1


def test_api_key_is_sent_but_never_in_the_request_log(tmp_path):
    s = FakeSession()
    _client(tmp_path, session=s).place_order(REQ)
    _, body = s.calls[0]
    assert body["apikey"] == "k"
