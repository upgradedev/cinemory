"""What one reel actually burned.

The owner needs to be able to say, after a demo, exactly what it consumed.
Before this, the only answer was "read the logs", and even then the numbers had
to be reconstructed by eye.

Everything here is MEASURED at the moment it happens, and nothing here is
invented. In particular there is no money in this module. Reliable per-call
pricing for the generation models is not available to us, and a made-up euro
figure would be worse than an honest call count: it would look authoritative
and be wrong. What is reported is units burned:

* provider calls per run, broken down by model
* wall clock per call, and for the run as a whole
* bytes sent to the provider and bytes received back, per call
* objects written to storage, and the bytes in them

The last one is not vanity. Backblaze B2's Class B transaction allowance is a
real ceiling and a real run reached 75% of it in a day, so "objects written per
reel" is the number that predicts when that happens again.

Where this lives, and why not in the sealed manifest
----------------------------------------------------
The manifest already seals the per-step facts this is built from: provider,
model, ``started_at``, ``finished_at`` and the output asset's ``size_bytes``,
for every generative step. Those are provenance, they are hashed, and they do
not move.

This rollup is observability: it is derived from those same sealed records plus
counters the pipeline keeps while it runs. It rides on the run's RESULT, which
means it is stored with the job status (``jobs/<id>/status.json``) and comes
straight back from ``GET /reels/jobs/{job_id}`` for any run, at any time after
the fact. Keeping it out of the hashed manifest is deliberate: accounting is
not a claim about what was generated, and adding mutable bookkeeping to a
sealed artifact would change the manifest hash of every reel ever made for a
reason that has nothing to do with provenance.
"""
from __future__ import annotations

from dataclasses import dataclass, field


def _ms(seconds: float) -> int:
    """Whole milliseconds, never negative (a clock that steps backwards mid-run
    must not produce a negative duration in a report)."""
    return max(0, round(seconds * 1000))


@dataclass
class CallUsage:
    """One generation call to the media provider."""

    provider: str
    model: str
    modality: str
    started_at: str
    finished_at: str
    duration_ms: int
    #: Bytes handed to the provider (the source photos for this call).
    input_bytes: int
    #: Bytes the provider handed back (the generated clip).
    output_bytes: int
    #: How many times this call had to be asked before it answered. 1 is the
    #: normal case; more means the provider rate-limited us and the backoff
    #: worked. Worth reporting: it is the difference between "the provider is
    #: fine" and "we are at its limit and only just getting away with it".
    attempts: int = 1

    def to_dict(self) -> dict:
        return {
            "provider": self.provider,
            "model": self.model,
            "modality": self.modality,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_ms": self.duration_ms,
            "input_bytes": self.input_bytes,
            "output_bytes": self.output_bytes,
            "attempts": self.attempts,
        }


@dataclass
class RunUsage:
    """Everything one reel burned, accumulated while it was being made."""

    reel_name: str
    started_at: str = ""
    finished_at: str = ""
    duration_ms: int = 0
    calls: list[CallUsage] = field(default_factory=list)
    #: Objects written to storage during this run: every input photo, every
    #: generated clip, the reel, the manifest and the provenance-embedded reel.
    objects_written: int = 0
    #: Total bytes in those objects.
    bytes_written: int = 0
    #: Whether the per-photo generation calls actually overlapped. Recorded
    #: because it is the difference between a reel that fits the waiting window
    #: and one that cannot, and because a report of "5 photos in 6 minutes" is
    #: only interpretable next to it.
    max_concurrency: int = 1

    def record_call(self, call: CallUsage) -> None:
        self.calls.append(call)

    def record_object(self, size_bytes: int) -> None:
        self.objects_written += 1
        self.bytes_written += size_bytes

    def finish(self, *, started_at: str, finished_at: str, elapsed_seconds: float) -> None:
        self.started_at = started_at
        self.finished_at = finished_at
        self.duration_ms = _ms(elapsed_seconds)

    # ── derived ──────────────────────────────────────────────────────────────
    @property
    def calls_by_model(self) -> dict[str, int]:
        """How many calls each model took. The breakdown the owner asked for,
        and the one that maps to a provider's own per-model billing if a
        verifiable price ever exists."""
        counts: dict[str, int] = {}
        for call in self.calls:
            counts[call.model] = counts.get(call.model, 0) + 1
        return counts

    @property
    def provider_seconds(self) -> float:
        """Total time spent INSIDE provider calls, summed across calls.

        Deliberately reported alongside ``duration_ms`` rather than instead of
        it: when calls run concurrently these two diverge, and the gap is
        exactly the saving. Summed provider time is also the honest measure of
        what was consumed, since a provider charges for work done, not for how
        long we chose to wait.
        """
        return sum(c.duration_ms for c in self.calls) / 1000

    def to_dict(self) -> dict:
        return {
            "reel_name": self.reel_name,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_ms": self.duration_ms,
            "provider_calls": len(self.calls),
            "provider_calls_by_model": self.calls_by_model,
            "provider_seconds": round(self.provider_seconds, 3),
            "max_concurrency": self.max_concurrency,
            "input_bytes_to_provider": sum(c.input_bytes for c in self.calls),
            "output_bytes_from_provider": sum(c.output_bytes for c in self.calls),
            "objects_written": self.objects_written,
            "bytes_written": self.bytes_written,
            "calls": [c.to_dict() for c in self.calls],
        }

    def summary_line(self) -> str:
        """One greppable line for the operator log, alongside the readable
        per-job object above."""
        models = ", ".join(f"{m}x{n}" for m, n in sorted(self.calls_by_model.items()))
        return (
            f"reel={self.reel_name} calls={len(self.calls)} [{models}] "
            f"wall={self.duration_ms}ms provider={self.provider_seconds:.1f}s "
            f"concurrency={self.max_concurrency} objects={self.objects_written} "
            f"bytes_written={self.bytes_written}"
        )
