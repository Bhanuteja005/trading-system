"""The analyst's response contract and its validation.

Structured outputs rather than prose parsing: a regex over "STOP LOSS: 24,812"
fails on a thousands separator, a stray currency symbol, or a model that adds a
sentence. The display format is rendered from the validated object instead.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from tsys.core import TsysError
from tsys.domain import Levels, Side

RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "decision", "stop_loss", "target", "lots", "confidence",
        "reward_risk", "technical_reasons", "macro_reasons",
    ],
    "properties": {
        "decision": {"type": "string", "enum": ["LONG", "SHORT"]},
        "stop_loss": {"type": "number", "description": "Absolute price level."},
        "target": {"type": "number", "description": "Absolute price level."},
        "lots": {"type": "integer", "description": "Within the stated range."},
        "confidence": {
            "type": "integer", "minimum": 0, "maximum": 100,
            "description": "Combined technical and macro confluence, as a percentage.",
        },
        "reward_risk": {"type": "number", "description": "The ratio you calculated."},
        "technical_reasons": {
            "type": "string",
            "description": "Structure, liquidity, zones and confirmations. Cite levels.",
        },
        "macro_reasons": {
            "type": "string",
            "description": "Current macro and geopolitical context, expected developments, "
                           "and how smart money is positioned.",
        },
    },
}


class AnalystRejected(TsysError):
    """The model's call broke the mandate. Never silently repaired."""


@dataclass(frozen=True, slots=True)
class AnalystCall:
    side: Side
    levels: Levels
    lots: int
    confidence: Decimal
    reward_risk: Decimal
    technical_reasons: str
    macro_reasons: str
    model: str
    raw: dict[str, Any]

    def render(self) -> str:
        """The mandated display format, rebuilt from validated fields."""
        return (
            f"TRADE DECISION: {self.side.value}\n\n"
            f"STOP LOSS: {self.levels.stop_loss}\n"
            f"TARGET: {self.levels.target}\n"
            f"LOTS: {self.lots}\n"
            f"CONFIDENCE: {int(self.confidence * 100)}%\n"
            f"REWARD:RISK: {self.reward_risk}\n\n"
            f"TECHNICAL REASONS:\n{self.technical_reasons}\n\n"
            f"MACRO / GEOPOLITICAL REASONS:\n{self.macro_reasons}"
        )


def _dec(value: Any, field: str) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError) as e:
        raise AnalystRejected(f"unparseable {field}: {value!r}") from e


def validate(
    payload: dict[str, Any],
    *,
    last_price: Decimal,
    min_reward_ratio: Decimal,
    min_lots: int,
    max_lots: int,
    model: str,
) -> AnalystCall:
    """Turn a raw response into a call, or refuse it.

    The model is a participant, not an authority: every number it returns is
    re-derived here, and a call that breaks the mandate is rejected rather than
    nudged into range.
    """
    try:
        side = Side(str(payload["decision"]).upper())
    except (KeyError, ValueError) as e:
        got = payload.get("decision")
        raise AnalystRejected(f"decision must be LONG or SHORT, got {got!r}") from e

    stop = _dec(payload.get("stop_loss"), "stop_loss")
    target = _dec(payload.get("target"), "target")
    lots = int(payload.get("lots", 0))

    if stop <= 0 or target <= 0:
        raise AnalystRejected(f"levels must be positive (stop={stop}, target={target})")
    if not (min_lots <= lots <= max_lots):
        raise AnalystRejected(f"lots {lots} outside the permitted {min_lots}-{max_lots}")

    levels = Levels(entry=last_price, stop_loss=stop, target=target)

    # Sidedness: risk_per_unit / reward_per_unit raise if either level is wrong.
    try:
        achieved = levels.reward_risk(side)
    except ValueError as e:
        raise AnalystRejected(f"levels are on the wrong side for {side.value}: {e}") from e

    if achieved < min_reward_ratio:
        raise AnalystRejected(
            f"reward:risk {achieved:.2f} below the {min_reward_ratio} minimum"
        )

    confidence = _dec(payload.get("confidence", 0), "confidence") / Decimal(100)
    if not (Decimal(0) <= confidence <= Decimal(1)):
        raise AnalystRejected(f"confidence {payload.get('confidence')!r} outside 0-100")

    return AnalystCall(
        side=side, levels=levels, lots=lots, confidence=confidence,
        reward_risk=achieved,
        technical_reasons=str(payload.get("technical_reasons", "")).strip(),
        macro_reasons=str(payload.get("macro_reasons", "")).strip(),
        model=model, raw=payload,
    )
