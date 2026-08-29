"""TradingView data-source settings.

The Python side never speaks CDP directly: it shells out to the Node `tv` CLI
that packages/tradingview-mcp already exposes as a bin, and parses JSON.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field

from .base import REPO_ROOT, _Base


class TradingViewSettings(_Base):
    cli_path: Path = Field(
        default=REPO_ROOT / "packages" / "tradingview-mcp" / "src" / "cli" / "index.js",
        alias="TV_CLI_PATH",
    )
    node_binary: str = Field(default="node", alias="TV_NODE_BINARY")
    cdp_port: int = Field(default=9222, alias="TV_CDP_PORT")
    timeout_seconds: float = Field(default=15.0, alias="TV_TIMEOUT_SECONDS")

    max_quote_age_seconds: float = Field(default=90.0, alias="TV_MAX_QUOTE_AGE_SECONDS")
    """A quote older than this is stale; the evaluator must abstain rather than guess."""

    min_bars: int = Field(default=50, alias="TV_MIN_BARS")
    """Fewer bars than this and structure analysis is not meaningful."""
