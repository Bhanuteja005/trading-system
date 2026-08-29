# 3. The LLM analyst is a participant, not an authority

**Status:** accepted

## Context

The analyst asks Claude for a discretionary institutional call. The model returns
a direction, a stop, a target, a lot count, a confidence and a claimed
reward:risk. The naive integration takes those numbers and trades them.

Two things make that unsafe. Arithmetic in prose is not reliable — a model can
state "reward:risk 2.4" above levels that give 1.6. And prose parsing is brittle:
a regex over `STOP LOSS: 24,812` breaks on the thousands separator, a currency
symbol, or an added sentence.

## Decision

Structured outputs for the response shape, and re-derivation of every number in
`schema.validate` before anything is recorded:

- reward:risk is recomputed from the levels; the model's own figure is ignored
- both levels are checked against the correct side of the last price
- lots are checked against the permitted range
- a call that breaks the mandate is **rejected**, never nudged into range

`"WAIT"` is not representable in the schema.

## Consequences

The analyst can be wrong about the market — that is what accuracy scoring is for —
but it cannot be wrong about the arithmetic, and it cannot produce a trade that
breaches the mandate.

The mandated display format is rendered back from the validated object, so the
user still sees the exact format they asked for without it being the parse target.

The analyst path never constructs a `BrokerClient`. It is paper-only by
construction rather than by configuration, so no env var can make it place an
order.
