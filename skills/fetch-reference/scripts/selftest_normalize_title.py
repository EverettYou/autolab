#!/usr/bin/env python3
"""Self-test for `normalize_title`: the ligature fold and its accent regression guard.

Run: `python3 skills/fetch-reference/scripts/selftest_normalize_title.py` (standard library only).
Exits non-zero on any mismatch, so it is usable as a pre-commit check.

`normalize_title` is the single choke point for matching arXiv metadata titles (plain ASCII)
against typeset PDF text, and it has two failure modes that pull in opposite directions. Too
little normalisation and LaTeX ligatures never match; too much (bare NFKD) and accented letters
get split by the punctuation filter. A change that fixes one silently breaks the other.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from arxiv_fetch import normalize_title  # noqa: E402

CASES = [
    # ligatures must expand ...
    ("Eﬃcient Post-Selection", "efficient post selection"),  # ffi U+FB03 (the measured failure)
    ("ﬁdelity", "fidelity"),  # fi  U+FB01
    ("ﬂux qubits", "flux qubits"),  # fl  U+FB02
    # ... and accented letters must not be split into fragments (the bare-NFKD regression)
    ("Schrödinger", "schrodinger"),
    ("naïve Bayes", "naive bayes"),
    ("René Descartes", "rene descartes"),
    # unchanged behaviour on plain input
    ("Fault-Tolerant Quantum Computing", "fault tolerant quantum computing"),
    ("Quantum Oracle Sketching, revisited", "quantum oracle sketching revisited"),
]


def main() -> int:
    fails = 0
    for raw, expected in CASES:
        got = normalize_title(raw)
        ok = got == expected
        if not ok:
            fails += 1
        print(f"  {'ok  ' if ok else 'FAIL'}  {raw!r} -> {got!r}" + ("" if ok else f"  (expected {expected!r})"))
    # the property that matters: a ligature title must match its ASCII metadata form
    lig = normalize_title("Eﬃcient Post-Selection in Quantum Error Correction")
    asc = normalize_title("Efficient Post-Selection in Quantum Error Correction")
    if lig != asc:
        print(f"  FAIL  ligature and ASCII forms disagree: {lig!r} != {asc!r}")
        fails += 1
    else:
        print("  ok    ligature form == ASCII form (the property the title gate depends on)")
    print(f"\nselftest_normalize_title: {len(CASES) + 1 - fails} passed, {fails} failed")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
