"""Cinemory — synthetic photos -> AI-generated video reel, orchestrated with
Genblaze, stored on Backblaze B2, with verifiable SHA-256 provenance.

PII-safe by design: the reference pipeline operates on *synthetic* demo photos
generated programmatically (see ``cinemory.synthetic``). No real personal
media is ever read, generated, or committed.
"""

__version__ = "0.1.0"
