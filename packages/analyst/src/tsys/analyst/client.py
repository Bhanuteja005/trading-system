"""Ask Claude for the call.

Opus 5 with adaptive thinking and web search: the brief demands current macro
and geopolitical context, which cannot come from model memory.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import anthropic
from tsys.config import AnalystSettings
from tsys.core import BrokerError, DataUnavailable, get_logger, log_event
from tsys.domain import MarketSnapshot

from .prompt import SYSTEM, BriefSpec, render_user_message
from .schema import RESPONSE_SCHEMA, AnalystCall, AnalystRejected, validate

log = get_logger(__name__)


class Analyst:
    def __init__(self, settings: AnalystSettings, *, client: Any = None) -> None:
        self._s = settings
        if client is not None:
            self._client = client
        else:
            if not settings.configured:
                raise DataUnavailable(
                    "ANTHROPIC_API_KEY is not set; the analyst cannot run. "
                    "Add it to .env, or use the deterministic evaluator instead."
                )
            self._client = anthropic.Anthropic(api_key=settings.api_key.get_secret_value())

    def _tools(self) -> list[dict[str, Any]]:
        if not self._s.web_search:
            return []
        return [
            {
                "type": "web_search_20260209",
                "name": "web_search",
                "max_uses": self._s.max_web_searches,
            }
        ]

    def call(self, snapshot: MarketSnapshot, spec: BriefSpec) -> AnalystCall:
        """One brief, one call. Raises AnalystRejected if the mandate is broken."""
        user_message = render_user_message(snapshot, spec)

        kwargs: dict[str, Any] = {
            "model": self._s.model,
            "max_tokens": self._s.max_tokens,
            "system": SYSTEM,
            "thinking": {"type": "adaptive"},
            "output_config": {
                "effort": self._s.effort,
                "format": {
                    "type": "json_schema",
                    "schema": RESPONSE_SCHEMA,
                },
            },
            "messages": [{"role": "user", "content": user_message}],
        }
        tools = self._tools()
        if tools:
            kwargs["tools"] = tools

        try:
            # Streaming: the brief is long, effort is high, and max_tokens is
            # large enough that a non-streaming call risks an HTTP timeout.
            with self._client.messages.stream(**kwargs) as stream:
                response = stream.get_final_message()
        except anthropic.APIStatusError as e:
            retryable = e.status_code >= 500 or e.status_code == 429
            raise BrokerError(f"analyst API error {e.status_code}", retryable=retryable) from e
        except anthropic.APIConnectionError as e:
            raise DataUnavailable(f"analyst unreachable: {e}") from e

        if response.stop_reason == "refusal":
            detail = getattr(response, "stop_details", None)
            raise AnalystRejected(
                f"model declined to answer ({getattr(detail, 'category', 'unknown')})"
            )

        text = "".join(b.text for b in response.content if b.type == "text")
        if not text.strip():
            raise AnalystRejected("analyst returned no text content")
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as e:
            raise AnalystRejected(f"analyst response was not valid JSON: {text[:200]}") from e

        call = validate(
            payload,
            last_price=snapshot.quote.last,
            min_reward_ratio=spec.min_reward_ratio,
            min_lots=spec.min_lots,
            max_lots=spec.max_lots,
            model=self._s.model,
        )
        log_event(
            log, logging.INFO, "analyst.call",
            index=snapshot.index, side=call.side.value, lots=call.lots,
            confidence=str(call.confidence), reward_risk=str(call.reward_risk),
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )
        return call
