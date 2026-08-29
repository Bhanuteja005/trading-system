"""Process-wide settings shared by every package.

This module and its siblings are the ONLY place in the repository allowed to
read ``os.environ``. Everything else receives a typed settings object. CI
enforces this (see scripts/check_env_boundary.py).
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[4]


class Mode(StrEnum):
    """How far an order is allowed to travel."""

    DRY_RUN = "dry_run"
    """Evaluate and log. Never contacts the broker. The default."""

    PAPER = "paper"
    """Route to the paper-trading dashboard. No real money."""

    LIVE = "live"
    """Real orders against the real broker. Requires explicit opt-in."""


class _Base(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )


class BaseSettingsBlock(_Base):
    env: str = Field(default="development", alias="TSYS_ENV")
    log_level: str = Field(default="INFO", alias="TSYS_LOG_LEVEL")
    timezone: str = Field(default="Asia/Kolkata", alias="TSYS_TIMEZONE")
    data_dir: Path = Field(default=REPO_ROOT / "data", alias="TSYS_DATA_DIR")

    @property
    def repo_root(self) -> Path:
        return REPO_ROOT
