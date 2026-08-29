"""LLM analyst settings.

The analyst asks Claude for a discretionary institutional-desk call. It is a
second opinion alongside the deterministic evaluator, never a replacement for
the risk layer: whatever it returns still passes through sizing and risk checks.
"""

from __future__ import annotations

from pydantic import Field, SecretStr

from .base import _Base


class AnalystSettings(_Base):
    api_key: SecretStr = Field(default=SecretStr(""), alias="ANTHROPIC_API_KEY")
    model: str = Field(default="claude-opus-5", alias="ANALYST_MODEL")
    effort: str = Field(default="high", alias="ANALYST_EFFORT")
    max_tokens: int = Field(default=16000, alias="ANALYST_MAX_TOKENS")

    web_search: bool = Field(default=True, alias="ANALYST_WEB_SEARCH")
    """The prompt demands current macro and geopolitical context, which cannot
    come from model memory. Off only for deterministic replay tests."""

    max_web_searches: int = Field(default=6, alias="ANALYST_MAX_WEB_SEARCHES")

    @property
    def configured(self) -> bool:
        return bool(self.api_key.get_secret_value())
