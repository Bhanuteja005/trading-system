"""Scoring walks forward; it never picks the flattering level."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal as D

from tsys.analyst import Outcome, score_call, summarise
from tsys.domain import Bar, Levels, Side

T0 = datetime(2026, 8, 28, 5, 0, tzinfo=UTC)
LONG = Levels(entry=D("100"), stop_loss=D("90"), target=D("120"))


def bar(i, high, low, close=None):
    return Bar(ts=T0 + timedelta(minutes=15 * i), open=D("100"), high=D(str(high)),
               low=D(str(low)), close=D(str(close if close is not None else high)))


def test_target_first_is_a_win():
    card = score_call(levels=LONG, side=Side.LONG,
                      subsequent=(bar(1, 110, 99), bar(2, 121, 105)))
    assert card.outcome is Outcome.TARGET and card.correct
    assert card.bars_to_resolve == 2 and card.r_multiple == D(2)


def test_stop_first_is_a_loss():
    card = score_call(levels=LONG, side=Side.LONG,
                      subsequent=(bar(1, 105, 89), bar(2, 130, 120)))
    assert card.outcome is Outcome.STOP and not card.correct
    assert card.r_multiple == D(-1), "a later target cannot rescue a stopped trade"


def test_a_bar_spanning_both_levels_counts_against_us():
    """Intrabar order is unknowable at this resolution; assuming the good fill
    first is how a backtest flatters itself."""
    card = score_call(levels=LONG, side=Side.LONG, subsequent=(bar(1, 125, 85),))
    assert card.outcome is Outcome.AMBIGUOUS and not card.correct
    assert card.r_multiple == D(-1)


def test_neither_level_touched_stays_open():
    card = score_call(levels=LONG, side=Side.LONG,
                      subsequent=(bar(1, 105, 95, 103),))
    assert card.outcome is Outcome.OPEN and not card.resolved


def test_no_bars_yet_is_open():
    card = score_call(levels=LONG, side=Side.LONG, subsequent=())
    assert card.outcome is Outcome.OPEN and card.bars_to_resolve == 0


def test_short_scoring_is_mirrored():
    short = Levels(entry=D("100"), stop_loss=D("110"), target=D("80"))
    card = score_call(levels=short, side=Side.SHORT, subsequent=(bar(1, 102, 79),))
    assert card.outcome is Outcome.TARGET and card.r_multiple == D(2)


def test_summary_reports_hit_rate_and_expectancy():
    cards = [
        score_call(levels=LONG, side=Side.LONG, subsequent=(bar(1, 121, 99),)),   # win
        score_call(levels=LONG, side=Side.LONG, subsequent=(bar(1, 105, 89),)),   # loss
        score_call(levels=LONG, side=Side.LONG, subsequent=(bar(1, 105, 95, 101),)),  # open
    ]
    s = summarise(cards)
    assert (s.total, s.resolved, s.wins, s.losses, s.open) == (3, 2, 1, 1, 1)
    assert s.hit_rate == D("0.500")
    # +2R and -1R over two resolved calls
    assert s.expectancy_r == D("0.500")


def test_expectancy_shows_a_low_hit_rate_can_still_win():
    """One win at 1:2 and two losses is a 33% hit rate and still profitable."""
    wide = Levels(entry=D("100"), stop_loss=D("90"), target=D("130"))
    cards = [
        score_call(levels=wide, side=Side.LONG, subsequent=(bar(1, 131, 99),)),
        score_call(levels=wide, side=Side.LONG, subsequent=(bar(1, 105, 89),)),
        score_call(levels=wide, side=Side.LONG, subsequent=(bar(1, 105, 89),)),
    ]
    s = summarise(cards)
    assert s.hit_rate == D("0.333")
    assert s.expectancy_r > 0, "1:3 winners outweigh a 33% hit rate"
