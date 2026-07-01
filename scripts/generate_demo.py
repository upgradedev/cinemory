"""Materialise synthetic demo photos on disk (PII-safe input source).

    python scripts/generate_demo.py --out sample-data/generated --count 6

These are the ONLY sanctioned inputs for the public demo. No real personal
media is ever used.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from cinemory.synthetic import synth_photo  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=Path("sample-data/generated"))
    ap.add_argument("--count", type=int, default=6)
    args = ap.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    for i in range(args.count):
        photo = synth_photo(f"demo_{i:02d}.png", seed=i + 1)
        (args.out / photo.filename).write_bytes(photo.data)
    print(f"Wrote {args.count} synthetic photos to {args.out.resolve()}")


if __name__ == "__main__":
    main()
