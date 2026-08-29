"""Typed configuration, assembled once at the process boundary.

Import ``settings`` and pass it down. No other module should read the
environment; doing so is a CI failure.

    from tsys.config import settings
    client = BrokerClient(settings.broker)
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import BaseModel, ConfigDict

from .analyst import AnalystSettings
from .base import REPO_ROOT, BaseSettingsBlock, Mode
from .broker import BrokerSettings
from .risk import LOT_SIZES, RiskSettings
from .tradingview import TradingViewSettings


class Settings(BaseModel):
    model_config = ConfigDict(frozen=True)

    base: BaseSettingsBlock
    analyst: AnalystSettings
    broker: BrokerSettings
    tradingview: TradingViewSettings
    risk: RiskSettings

    def assert_startup_safe(self) -> None:
        """Fail loudly at boot rather than surprising anyone mid-session."""
        if self.risk.mode is Mode.LIVE and not self.risk.live_confirmed:
            raise RuntimeError(
                "TSYS_MODE=live requires TSYS_LIVE_CONFIRMED=true as a separate, "
                "deliberate opt-in. Refusing to start."
            )
        if self.risk.is_live and not self.broker.configured:
            raise RuntimeError("Live mode requires OPENALGO_API_KEY. Refusing to start.")
        if self.risk.min_risk_rupees > self.risk.max_risk_rupees:
            raise RuntimeError("min risk exceeds max risk; check TSYS_*_RISK_PCT.")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Build once per process. Cached, so config is read exactly once."""
    return Settings(
        base=BaseSettingsBlock(),
        analyst=AnalystSettings(),
        broker=BrokerSettings(),
        tradingview=TradingViewSettings(),
        risk=RiskSettings(),
    )


settings = get_settings()

__all__ = [
    "LOT_SIZES",
    "REPO_ROOT",
    "AnalystSettings",
    "BaseSettingsBlock",
    "BrokerSettings",
    "Mode",
    "RiskSettings",
    "Settings",
    "TradingViewSettings",
    "get_settings",
    "settings",
]
