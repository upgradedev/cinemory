# Sample data — SYNTHETIC ONLY

This project **never** ships real personal photos or memories.

All demo inputs are generated programmatically at runtime by
[`src/cinemory/synthetic.py`](../src/cinemory/synthetic.py) (Pillow gradients +
shapes, deterministic per seed). There are no real images checked into this
repository, and the `.gitignore` blocks common photo formats and a `private/`
directory as a safety net.

To materialise a set of synthetic demo photos on disk:

```bash
python scripts/generate_demo.py --out sample-data/generated --count 6
```

The output directory (`sample-data/generated/`) is git-ignored.
