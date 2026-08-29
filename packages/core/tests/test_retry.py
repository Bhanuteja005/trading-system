import pytest

from tsys.core import DataUnavailable, with_retry
from tsys.core.errors import BrokerError


def test_returns_on_first_success():
    assert with_retry(lambda: 42, sleep=lambda _: None) == 42


def test_retries_then_succeeds():
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) < 3:
            raise DataUnavailable("not yet")
        return "ok"

    assert with_retry(flaky, sleep=lambda _: None) == "ok"
    assert len(calls) == 3


def test_non_retryable_broker_error_is_not_retried():
    calls = []

    def hard_fail():
        calls.append(1)
        raise BrokerError("rejected: insufficient margin", retryable=False)

    with pytest.raises(BrokerError):
        with_retry(hard_fail, sleep=lambda _: None)
    assert len(calls) == 1


def test_gives_up_after_attempts():
    calls = []

    def always():
        calls.append(1)
        raise DataUnavailable("down")

    with pytest.raises(DataUnavailable):
        with_retry(always, attempts=4, sleep=lambda _: None)
    assert len(calls) == 4
