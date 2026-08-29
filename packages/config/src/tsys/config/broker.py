"""OpenAlgo broker connection settings."""

from __future__ import annotations

from pydantic import Field, SecretStr

from .base import _Base


class BrokerSettings(_Base):
    url: str = Field(default="http://127.0.0.1:5000", alias="OPENALGO_URL")
    api_key: SecretStr = Field(default=SecretStr(""), alias="OPENALGO_API_KEY")
    strategy_tag: str = Field(default="ClaudeTrader", alias="OPENALGO_STRATEGY")
    timeout_seconds: float = Field(default=8.0, alias="OPENALGO_TIMEOUT_SECONDS")
    max_retries: int = Field(default=3, alias="OPENALGO_MAX_RETRIES")

    @property
    def configured(self) -> bool:
        return bool(self.api_key.get_secret_value())
