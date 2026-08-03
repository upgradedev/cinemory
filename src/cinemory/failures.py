"""Classifying a live-provider failure into one coarse, visitor-safe category.

Two callers, one vocabulary:

* ``cinemory.api`` puts the category in the response (``degrade_kind``) so the
  UI can say WHY a reel fell back to the built-in generator, in plain language,
  without any of the upstream detail reaching a browser.
* ``cinemory.pipeline`` asks whether a failure is worth retrying: a rate limit
  is the provider saying "not right now", which backs off and succeeds, while
  a rejected request or an exhausted balance will fail identically however many
  times it is asked.

The category is the ONLY thing about a failure that ever crosses the wire.
Everything the exception actually said, which can embed upstream URLs, request
identifiers, account details, or a raw provider response body, stays in the
process log where an operator can find it and a browser cannot.

This is a heuristic over the exception's class name and text, and is meant to
be one: the wording a remote generation backend uses is not ours to control,
and no amount of exception-type matching would survive it changing. Getting a
category wrong costs one slightly-too-general sentence on screen, or one
retry that was never going to help; the operator's log line carries the real
thing either way.
"""
from __future__ import annotations

#: Ordered: the FIRST match wins, so the most specific and most actionable
#: causes are listed first.
PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    # Billing. Listed first because it is the one an operator can FIX, and the
    # one that made this classification necessary: a "(402): Insufficient
    # credits" that reached a visitor as "taking longer than expected".
    ("credit", ("402", "insufficient credit", "insufficient balance", "insufficient funds",
                "out of credit", "payment required", "quota", "billing")),
    ("busy", ("429", "rate limit", "ratelimit", "too many requests", "overloaded",
              "at capacity")),
    ("timeout", ("timeout", "timedout", "timed out", "deadline exceeded", "504", "408")),
    ("unavailable", ("500", "502", "503", "connectionerror", "connection refused",
                     "connection reset", "unreachable", "temporarily unavailable",
                     "name resolution", "dns")),
    ("refused", ("401", "403", "400", "422", "unauthorized", "unauthorised", "forbidden",
                 "invalid request", "bad request")),
)

#: Every category this module can return.
KINDS = tuple(kind for kind, _ in PATTERNS) + ("unknown",)


def classify(exc: BaseException) -> str:
    """The category of ``exc``, or ``"unknown"`` when nothing matches.

    ``"unknown"`` is not an error state: the UI renders it as the honest
    general sentence rather than a blank, so an unclassified failure is still
    a complete explanation of what the visitor is looking at.
    """
    haystack = f"{type(exc).__name__} {exc}".lower()
    for kind, needles in PATTERNS:
        if any(needle in haystack for needle in needles):
            return kind
    return "unknown"


def is_retryable(exc: BaseException) -> bool:
    """Whether asking again, after a wait, could plausibly succeed.

    Only ``"busy"``. A rate limit is the provider saying "not right now", and
    that is the one failure a backoff actually answers. Deliberately NOT
    ``timeout`` or ``unavailable``: a generation call that already ran for
    minutes before timing out would, on retry, spend those minutes again
    inside a fixed waiting window that a visitor is watching, and this
    pipeline already has an honest fallback for a failure it cannot fix. And
    emphatically not ``credit`` or ``refused``, which will fail identically
    however many times they are asked, only slower and, for credit, only after
    burning more of the thing that ran out.
    """
    return classify(exc) == "busy"
