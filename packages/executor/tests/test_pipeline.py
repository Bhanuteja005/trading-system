"""End-to-end: index name in, journal entry out. No network anywhere."""

import json
from datetime import datetime

from pydantic import SecretStr
from tsys.broker import BrokerClient, IdempotencyLedger
from tsys.config import (
    BaseSettingsBlock,
    BrokerSettings,
    Mode,
    RiskSettings,
    Settings,
    TradingViewSettings,
)
from tsys.core import IST
from tsys.executor.pipeline import Pipeline
from tsys.executor.risk import PortfolioState
from tsys.journal import Journal

OPEN = datetime(2026, 8, 28, 10, 30, tzinfo=IST)


class FakeMarket:
    def __init__(self, snapshot=None, error=None):
        self.snapshot_obj, self.error = snapshot, error

    def snapshot(self, index, *, timeframe="5", bars=200):
        if self.error:
            raise self.error
        return self.snapshot_obj


class FakeSession:
    def __init__(self):
        self.calls = []

    def post(self, url, json=None, timeout=None):
        self.calls.append((url, json))

        class R:
            status_code = 200
            text = ""

            def json(self_inner):
                return {"status": "success", "orderid": "ORD-1"}

        return R()


def build(tmp_path, snapshot, *, mode=Mode.PAPER, error=None, session=None):
    settings = Settings(
        base=BaseSettingsBlock(TSYS_DATA_DIR=tmp_path),
        broker=BrokerSettings(OPENALGO_API_KEY=SecretStr("k")),
        tradingview=TradingViewSettings(TV_MIN_BARS=50),
        risk=RiskSettings(TSYS_MODE=mode, TSYS_KILL_FILE=tmp_path / "KILL"),
    )
    broker = BrokerClient(
        settings.broker, mode=mode, kill_switch=settings.risk.kill_switch_file,
        ledger=IdempotencyLedger(tmp_path / "ledger.json"),
        session=session or FakeSession(),
    )
    return Pipeline(
        settings=settings, market=FakeMarket(snapshot, error), broker=broker,
        journal=Journal(tmp_path / "journal"),
    ), settings


def test_uptrend_places_an_order(tmp_path, uptrend):
    session = FakeSession()
    pipe, _ = build(tmp_path, uptrend, session=session)
    res = pipe.run_once("NIFTY", state=PortfolioState(), now=OPEN)
    assert res.placed and res.order.broker_order_id == "ORD-1"
    assert len(session.calls) == 1


def test_dry_run_decides_but_sends_nothing(tmp_path, uptrend):
    session = FakeSession()
    pipe, _ = build(tmp_path, uptrend, mode=Mode.DRY_RUN, session=session)
    res = pipe.run_once("NIFTY", state=PortfolioState(), now=OPEN)
    assert res.placed and res.order.broker_order_id.startswith("DRYRUN-")
    assert session.calls == [], "dry run must not reach the broker"


def test_chop_produces_no_order_but_is_still_journalled(tmp_path, chop):
    pipe, _ = build(tmp_path, chop)
    res = pipe.run_once("NIFTY", state=PortfolioState(), now=OPEN)
    assert not res.placed and res.decision.abstain_reason is not None
    lines = list((tmp_path / "journal").glob("*.jsonl"))
    assert lines and lines[0].read_text().strip()


def test_kill_switch_stops_the_order(tmp_path, uptrend):
    (tmp_path / "KILL").write_text("halt")
    pipe, _ = build(tmp_path, uptrend)
    res = pipe.run_once("NIFTY", state=PortfolioState(), now=OPEN)
    assert not res.placed and "kill switch" in res.rejected_by


def test_data_failure_ends_the_cycle_without_guessing(tmp_path):
    from tsys.core import DataUnavailable

    pipe, _ = build(tmp_path, None, error=DataUnavailable("CDP down"))
    res = pipe.run_once("NIFTY", state=PortfolioState(), now=OPEN)
    assert res.decision is None and res.order is None and "CDP down" in res.error


def test_journal_entry_can_reconstruct_the_order(tmp_path, uptrend):
    pipe, _ = build(tmp_path, uptrend)
    pipe.run_once("NIFTY", state=PortfolioState(), now=OPEN)
    record = json.loads(next((tmp_path / "journal").glob("*.jsonl")).read_text().strip())

    assert record["index"] == "NIFTY"
    assert record["decision"]["action"] == "ENTER"
    assert record["order"]["broker_order_id"] == "ORD-1"
    # the inputs that produced it are stored alongside the verdict
    assert record["input"]["bar_count"] == len(uptrend.bars)
    assert record["input"]["quote"]["last"]
    assert record["decision"]["levels"]["stop_loss"]
    assert record["mode"] == "paper"


def test_repeat_cycle_does_not_double_fill(tmp_path, uptrend):
    """Same snapshot, same session: the second cycle must dedupe."""
    session = FakeSession()
    pipe, _ = build(tmp_path, uptrend, session=session)
    first = pipe.run_once("NIFTY", state=PortfolioState(), now=OPEN)
    second = pipe.run_once("NIFTY", state=PortfolioState(), now=OPEN)
    assert first.placed
    assert second.order.deduplicated
    assert len(session.calls) == 1, "only one order may reach the broker"


def test_unknown_index_is_rejected(tmp_path, uptrend):
    pipe, _ = build(tmp_path, uptrend)
    res = pipe.run_once("DOGECOIN", state=PortfolioState(), now=OPEN)
    assert res.rejected_by and "unknown index" in res.rejected_by
