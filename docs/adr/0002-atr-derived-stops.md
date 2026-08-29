# 2. Stops derive from ATR, targets from the reward:risk floor

**Status:** accepted

## Context

A stop has to come from somewhere. The obvious options are a fixed point count
(NIFTY: 30 points), a structural level (below the last swing low), or a
volatility multiple.

A fixed stop is wrong twice over: too tight in a volatile session, where it is
taken out by noise, and too loose in a quiet one, where it risks the full budget
on a move that was never going to happen. Structural stops are better but need a
swing point that exists, which is not guaranteed on any given bar.

## Decision

`stop_distance = ATR(14) × atr_stop_multiple`, default 1.5.

The target is then placed at exactly `min_reward_ratio × stop_distance` from
entry.

## Consequences

The 1:2 floor is true **by construction** rather than checked afterwards. There is
no path where the evaluator produces a trade below the floor — except tick
rounding, which can shave the ratio, and is why the code re-checks once after
rounding and abstains with `reward_risk_too_low` rather than accepting a worse
trade.

Position size follows: risk per unit is known, so lots are floored from the risk
budget. Sizing never picks a quantity first.

The multiple is a parameter, not a constant, so `test_stop_scales_with_volatility`
can assert the relationship holds rather than asserting a magic number.
