"""The evaluator is pure, so every case is a fixture and a verdict."""

from decimal import Decimal

from tsys.domain import Abstain, Action, Side

from tsys.executor.evaluate import EvalParams, evaluate

from conftest import make_snapshot

P = EvalParams()


def test_is_deterministic(uptrend):
    a, b = evaluate(uptrend, P), evaluate(uptrend, P)
    assert a == b


def test_strong_uptrend_goes_long(uptrend):
    d = evaluate(uptrend, P)
    assert d.action is Action.ENTER and d.side is Side.LONG
    assert d.confidence >= P.min_confidence


def test_chop_abstains_with_a_reason(chop):
    d = evaluate(chop, P)
    assert d.action is Action.NO_TRADE
    assert d.abstain_reason is not None
    assert d.reasons, "an abstention must say why"


def test_short_history_abstains():
    d = evaluate(make_snapshot([str(100 + i) for i in range(20)]), P)
    assert d.abstain_reason is Abstain.INSUFFICIENT_HISTORY


def test_reward_risk_floor_holds_by_construction(uptrend):
    """The RR floor is not checked after the fact; the target is placed at it."""
    d = evaluate(uptrend, P)
    assert d.levels.reward_risk(d.side) >= P.min_reward_ratio


def test_stop_is_below_entry_for_a_long(uptrend):
    d = evaluate(uptrend, P)
    assert d.levels.stop_loss < d.levels.entry < d.levels.target


def test_stop_scales_with_volatility(uptrend):
    """A wider ATR multiple must produce a wider stop — never a fixed distance."""
    tight = evaluate(uptrend, EvalParams(atr_stop_multiple=Decimal("1.0")))
    wide = evaluate(uptrend, EvalParams(atr_stop_multiple=Decimal("3.0")))
    tight_risk = tight.levels.entry - tight.levels.stop_loss
    wide_risk = wide.levels.entry - wide.levels.stop_loss
    assert wide_risk > tight_risk * Decimal("2.5")


def test_raising_the_threshold_suppresses_the_trade(uptrend):
    d = evaluate(uptrend, EvalParams(min_confidence=Decimal("0.99")))
    assert d.action is Action.NO_TRADE
    assert d.abstain_reason is Abstain.LOW_CONFIDENCE


def test_levels_are_rounded_to_the_tick(uptrend):
    d = evaluate(uptrend, P)
    for level in (d.levels.entry, d.levels.stop_loss, d.levels.target):
        assert (level / Decimal("0.05")) % 1 == 0
