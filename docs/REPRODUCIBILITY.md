# Reproducibility contract

ASAL-M separates scientific reproducibility from release-artifact byte
reproducibility. The distinction is deliberate.

## Scientific computation

Simulation, validation, candidate selection, and final-audit decisions are
computed at full floating-point precision. ASAL-M does not round values before
scoring, applying thresholds, selecting candidates, or issuing certification
decisions.

The package supports Python 3.10 and newer with the dependency ranges declared
in `pyproject.toml`. Within that range, fixed seeds and protocols are expected
to preserve the documented decisions and results. A material metric, status,
candidate, seed, or schema difference is a reproducibility failure.

## Public JSON serialization

Different NumPy and interpreter builds can produce insignificant
floating-point differences at the last binary digits. ASAL-M normalizes only
the checked-in public JSON representation:

- finite real values are serialized to 12 decimal places;
- integers, strings, booleans, lists, and mappings retain their meaning;
- negative zero is normalized to `0.0`;
- NaN and infinity are rejected;
- keys are sorted;
- text is UTF-8 with LF line endings and one final newline.

This policy lives in `asal_m/evidence.py`. A change smaller than half of one
unit at the twelfth decimal place may therefore serialize to the same public
value. The benchmark's calculations and decisions still use the original
full-precision values.

## Public image rendering

The certification graphic does not search the operating system for fonts.
It uses the repository's exact DejaVu Sans 2.37 regular and bold files:

```text
examples/certification_benchmark/fonts/DejaVuSans.ttf
examples/certification_benchmark/fonts/DejaVuSans-Bold.ttf
```

The renderer verifies both font SHA-256 digests before use and fails if an
asset is missing or changed. The font license is shipped beside the files and
attributed in `NOTICE`.

Pillow produces the RGB pixels. ASAL-M then writes those pixels through a small
deterministic PNG encoder with filter-zero scanlines, fixed chunk order,
`Z_HUFFMAN_ONLY` compression, and no timestamp or host metadata. Avoiding
implementation-dependent LZ match selection keeps the PNG identical between
the zlib and zlib-ng runtimes in the release matrix while retaining a
standards-compliant PNG.

## Certified release environment

For exact byte reproduction of the v0.1.2 public evidence, install the pinned
direct dependencies:

```sh
python -m pip install -c requirements-repro.txt -e .
```

Then run:

```sh
python examples/certification_benchmark/regenerate.py
python examples/public_demo/regenerate.py
python tools/verify_public_evidence.py
python -O tools/verify_public_evidence.py
```

`requirements-repro.txt` selects compatible NumPy versions for each supported
Python line and pins Pillow and PyYAML. The release gate reproduces all four
artifacts on Windows and Ubuntu using Python 3.10, 3.12, and 3.14.

The expected SHA-256 digests are:

| Artifact | SHA-256 |
|---|---|
| `examples/certification_benchmark/benchmark.json` | `c9f4c6a19e254140ffd7ec3edc8cc93a351b03ecbf801d6b59aaecd56a126e26` |
| `examples/certification_benchmark/certification-comparison.png` | `d9ace3de92e11a5381dbb06aae489048f525f67445c1ac80052b0affe1490434` |
| `examples/public_demo/benchmark.json` | `02fc23842d28cf28875f0fcde93fd447e7b1afe4a3cd2abcb4ceddd2dc6cd53c` |
| `examples/public_demo/mutation_cells_seed42.gif` | `439588b196430cf2b8622def124010fbdb2449efa840db0bb61d97a2fd876e3b` |

The verifier checks canonical JSON, semantic invariants, image dimensions and
frame count, font digests, and all four artifact digests. Its checks use
explicit exceptions rather than Python `assert`, so optimization cannot
disable them.

## Boundary

The exact-byte guarantee applies to the documented v0.1.2 release constraints
and CI matrix. Arbitrary future dependency releases, Python implementations,
CPU architectures, or locally modified rendering assets are outside that
contract until tested.

Outside the certified matrix, the fixed protocol should still reproduce the
same candidates, decisions, and material metrics. Treat any difference as
evidence to investigate; do not silently overwrite the checked-in release
artifacts.
