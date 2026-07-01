"""Concrete adapters for the MemoryReel ports.

Fakes (offline, no creds) — ``FakeMediaProvider``, ``FakeStorage``.
Real (require creds)      — ``GenblazeMediaProvider``, ``B2Storage``.
"""
from .fake_provider import FakeMediaProvider
from .fake_storage import FakeStorage

__all__ = ["FakeMediaProvider", "FakeStorage"]
