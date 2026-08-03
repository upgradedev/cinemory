"""One vocabulary for "why did the live provider fail", two readers.

``cinemory.api`` asks for a category to show a visitor; ``cinemory.pipeline``
asks whether waiting and asking again could help. Both go through this module,
so they can never drift into disagreeing about what a failure was.
"""
from __future__ import annotations

import pytest

from cinemory import failures


@pytest.mark.parametrize(("message", "expected"), [
    ("GMICloud submit failed (402): Insufficient credits", "credit"),
    ("payment required", "credit"),
    ("monthly quota exhausted", "credit"),
    ("429 Too Many Requests", "busy"),
    ("upstream rate limit hit", "busy"),
    ("model is at capacity", "busy"),
    ("read timeout after 600s", "timeout"),
    ("context deadline exceeded", "timeout"),
    ("503 Service Unavailable", "unavailable"),
    ("connection refused", "unavailable"),
    ("401 unauthorized", "refused"),
    ("submit failed (400): invalid payload parameters", "refused"),
    ("the moon was in the wrong phase", "unknown"),
    ("", "unknown"),
])
def test_classify(message, expected):
    assert failures.classify(RuntimeError(message)) == expected


def test_classify_reads_the_exception_class_name_too():
    """Some clients raise a typed error with an empty message."""
    exc = type("ConnectionError", (Exception,), {})()
    assert failures.classify(exc) == "unavailable"


def test_every_result_is_a_declared_kind():
    for message in ("402", "429", "timeout", "503", "401", "nothing recognisable"):
        assert failures.classify(RuntimeError(message)) in failures.KINDS


def test_only_a_rate_limit_is_worth_asking_again():
    """The retry policy in one assertion.

    A rate limit is the provider saying "not right now", and waiting answers
    it. A dead balance and a rejected request will fail identically however
    many times they are asked, only slower, and for credit only after burning
    more of the thing that ran out. A timeout is excluded on purpose: a
    generation call that already ran for minutes would spend those minutes
    again inside a waiting window a visitor is watching.
    """
    assert failures.is_retryable(RuntimeError("429 rate limit")) is True
    for message in (
        "402 Insufficient credits",
        "401 unauthorized",
        "submit failed (400)",
        "read timeout",
        "503 Service Unavailable",
        "something nobody has seen before",
    ):
        assert failures.is_retryable(RuntimeError(message)) is False, message
