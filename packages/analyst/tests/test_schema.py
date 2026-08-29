"""The mandate is enforced here, not trusted to the model."""

from decimal import Decimal as D

import pytest
from tsys.analyst import AnalystRejected, validate
from tsys.domain import Side

LAST = D("24800")
BASE = dict(
    decision="LONG", stop_loss=24700, target=25000, lots=4, confidence=72,
    reward_risk=2.0, technical_reasons="BOS above 24780", macro_reasons="Dovish Fed",
)
ARGS = dict(last_price=LAST, min_reward_ratio=D("2.0"), min_lots=1, max_lots=12,
            model="claude-opus-5")


def test_valid_call_is_accepted():
    call = validate(BASE, **ARGS)
    assert call.side is Side.LONG and call.lots == 4
    assert call.confidence == D("0.72")
    assert call.levels.entry == LAST


def test_reward_risk_is_recomputed_not_trusted():
    """Entry 24800, stop 24700, target 25000: risk 100, reward 200, so RR is 2.
    The model claims 99. Ours wins."""
    call = validate({**BASE, "reward_risk": 99}, **ARGS)
    assert call.reward_risk == D(2)


def test_reward_risk_below_the_floor_is_rejected():
    with pytest.raises(AnalystRejected, match="below the"):
        validate({**BASE, "target": 24850}, **ARGS)  # 50 reward vs 100 risk


def test_stop_on_the_wrong_side_is_rejected():
    with pytest.raises(AnalystRejected, match="wrong side"):
        validate({**BASE, "stop_loss": 24900}, **ARGS)


def test_short_with_inverted_levels_is_rejected():
    with pytest.raises(AnalystRejected, match="wrong side"):
        validate({**BASE, "decision": "SHORT"}, **ARGS)


def test_valid_short_is_accepted():
    call = validate({**BASE, "decision": "SHORT", "stop_loss": 24900, "target": 24600}, **ARGS)
    assert call.side is Side.SHORT and call.reward_risk == D(2)


def test_lots_outside_the_range_are_rejected():
    with pytest.raises(AnalystRejected, match="outside the permitted"):
        validate({**BASE, "lots": 40}, **ARGS)


def test_wait_is_not_an_available_answer():
    with pytest.raises(AnalystRejected, match="LONG or SHORT"):
        validate({**BASE, "decision": "WAIT"}, **ARGS)


def test_negative_levels_are_rejected():
    with pytest.raises(AnalystRejected, match="positive"):
        validate({**BASE, "stop_loss": -5}, **ARGS)


def test_render_reproduces_the_mandated_format():
    out = validate(BASE, **ARGS).render()
    assert out.startswith("TRADE DECISION: LONG")
    for field in ("STOP LOSS:", "TARGET:", "LOTS:", "CONFIDENCE:", "REWARD:RISK:"):
        assert field in out
