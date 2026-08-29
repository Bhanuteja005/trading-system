from decimal import Decimal as D

import pytest
from tsys.domain import Abstain, Action, Decision, Levels, Side


def test_reward_risk_long():
    assert Levels(D("100"), D("90"), D("130")).reward_risk(Side.LONG) == D("3")


def test_reward_risk_short():
    assert Levels(D("100"), D("110"), D("80")).reward_risk(Side.SHORT) == D("2")


def test_stop_on_wrong_side_is_rejected():
    with pytest.raises(ValueError, match="wrong side"):
        Levels(D("100"), D("110"), D("130")).risk_per_unit(Side.LONG)


def test_target_on_wrong_side_is_rejected():
    with pytest.raises(ValueError, match="wrong side"):
        Levels(D("100"), D("110"), D("130")).reward_per_unit(Side.SHORT)


def test_enter_requires_side_and_levels():
    with pytest.raises(ValueError, match="ENTER requires"):
        Decision(action=Action.ENTER, index="NIFTY", confidence=D("0.9"))


def test_no_trade_requires_a_reason():
    with pytest.raises(ValueError, match="requires an abstain_reason"):
        Decision(action=Action.NO_TRADE, index="NIFTY", confidence=D("0.1"))


def test_no_trade_is_not_actionable():
    d = Decision(
        action=Action.NO_TRADE, index="NIFTY", confidence=D("0.1"),
        abstain_reason=Abstain.LOW_CONFIDENCE,
    )
    assert not d.is_actionable
