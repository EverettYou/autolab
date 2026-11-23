# File review checklist

One lib package source file per review. Dual objective: the code mirrors the algorithm of its paper
and reproduction, and it meets production quality. Input: the audit id and one `.py` path.
Environment: the repository `.venv` with the configured lab package (when `features.lib` is on).

## Find the paper context yourself

1. `references/<id>/paper.pdf` and `provenance.json` (restore a missing PDF with
   `python3 skills/fetch-reference/scripts/fetch_reference.py refetch <id>`).
2. `references/<id>/reproduce/` and, if present locally, `references/<id>/attempts/`.
3. The web, if your tools allow it.
4. Still nothing: never invent equations. Cross-check against the reproduction and the platform,
   audit quality, and mark the file REVISE.

Record the sources used.

## Four passes, in order

1. Algorithm alignment and math: symbol mapping; 0- and 1-based indexing; signs, scaling, and
   dimensions; initialization and convergence.
2. Critical bugs and edge cases: empty, null, and infinite inputs; off-by-one; numerical stability
   (epsilon, log space); resource leaks.
3. Quality, readability, and security: structure, naming, dead code, performance.
4. Platform fidelity: against the reproduction; `wiki/models/platform-abstraction-invariants.md`;
   honesty (defaults against checkpoint behavior, regime labels).

## Output: `workspace/<basename>.md`

```markdown
# File review: <relative path> (<id>)

Verdict: PASS | REVISE | FAIL

### Paper sources
| Source | Location | Used for |

### Symbol mapping
| Paper symbol | Code variable | Location | Notes |

### Algorithm alignment discrepancies
| ID | Paper eq or section | Code location | Issue | Severity | Proposed action | Done when |

### Critical bugs and stability issues
| ID | Location | Issue | Proposed action | Done when |

### Quality and readability
| ID | Location | Issue | Proposed action | Done when |

### Suggested fix snippets

### Reproduction cross-check
| Component | Reproduction | This file | Match |

### Tests
Coverage: ...; pytest: pass | fail | skipped
```

Verdict rubric:

- FAIL: a critical algorithm mismatch, a broken platform invariant, or a dishonest claim.
- REVISE: major fixable gaps; every row has a proposed action and a "done when".
- PASS: minor or style issues only.

Rules: do not edit source files; one file per review; every gap row needs a proposed action and
a "done when" (the `auto-research` supervisor tick copies them into tasks). A short file-specific pytest run is
allowed.
