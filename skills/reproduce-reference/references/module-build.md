# Module build checklist

Build-from-paper stage BUILD, one module at a time, inside the attempt workspace.

Inputs: the module id, `IMPLEMENTATION-PLAN.md`, `REPRODUCTION-NOTES.md`, the relevant parts of
`PAPER-SPEC.md` and `paper_struct/`, `configs/base.yaml`, figure renders, the scaffolds in
`templates/scaffolds/` (seed them with `scripts/copy_scaffolds.sh <id> <attempt>`), and on a
retry the module's review in `reviews/<module-id>.md`. Read [guardrails.md](guardrails.md) first.

Deliverables:

- `src/<module-id>/` with a short `README.md`;
- `tests/test_<module-id>.py`: shapes, finite values, and a tiny Stim instance where it applies;
- new config keys in `configs/base.yaml`, each with its citation.

Citation anchoring, for every non-trivial constant and choice:

```python
# §3.2, Eq. 4: softmax attention over syndrome embeddings
# [UNSPECIFIED] dropout rate not in paper; using 0.1; alternatives 0.0, 0.2
```

Rules:

- Build order inside a module: utils, core logic, public API.
- Write only this module's tree and its test.
- No silent deviation from numbers the paper states; smoke-size shrinks carry an explicit comment.
- Never import from another reference's files or from `lib/src/<package>` internals that the paper
  does not use; the attempt must run on its own.
- Finish with a summary: files written, the pytest command, open issues.
