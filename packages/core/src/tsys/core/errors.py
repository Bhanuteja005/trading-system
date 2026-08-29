"""Exception hierarchy. Callers distinguish 'try again' from 'stop'."""

from __future__ import annotations


class TsysError(Exception):
    """Base for every error this system raises deliberately."""


class ConfigError(TsysError):
    """Configuration is missing or incoherent. Never retryable."""


class DataUnavailable(TsysError):
    """Upstream data could not be fetched. Retryable."""


class StaleData(TsysError):
    """Data arrived but is too old to act on. Not retryable this cycle."""


class BrokerError(TsysError):
    """The broker rejected or failed a request."""

    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


class RiskRejection(TsysError):
    """A risk limit refused the trade. Never retried — the answer is no."""


class KillSwitchEngaged(TsysError):
    """The kill switch is on. Every order path must refuse."""
