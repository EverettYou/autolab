# Module review checklist

Build-from-paper stage REVIEW: the gate for one module. Apply it from a second agent session
when possible; when the author applies it, reread the files from disk instead of relying on what
the code was meant to do.

Inputs: the module's code and tests, `REPRODUCTION-NOTES.md`, and its interface in
`IMPLEMENTATION-PLAN.md`.

Procedure:

1. Build a spec alignment table against `REPRODUCTION-NOTES.md`.
2. Flag audit: any magic number without a section citation or an `[UNSPECIFIED]`,
   `[ASSUMPTION]`, or `[FROM_OFFICIAL_CODE]` tag fails the review.
3. Run the module test from the attempt workspace: `python -m pytest tests/test_<module-id>.py -q`.
4. Check that tests assert real behavior, not only that code runs.

Write `reviews/<module-id>.md`:

```markdown
# Module review: <module-id> (<reference id> / <attempt>)

Verdict: PASS | FAIL

## Spec alignment
| Requirement | Status | Notes |

## Citation and flag audit
| Location | Issue |

## Test results

## Required fixes (if FAIL)
1. ...
```

Rules:

- FAIL on a spec mismatch, a missing flag, or a failing test.
- At most two retries per module; a third failure on the same gap is a dead end.
- Do not run the full pipeline smoke; SELF-TEST does that after assembly.
