# Ambiguity audit checklist

Build-from-paper stage AUDIT. Assume nothing; verify everything. BUILD is blocked until
`REPRODUCTION-NOTES.md` exists and every row is classified.

Inputs: `PAPER-SPEC.md`, `CONTRIBUTION.md`, `paper.md`, `paper_struct/`, `official_code.json`
if present, [ambiguity-checklist.md](ambiguity-checklist.md), [guardrails.md](guardrails.md),
and the template `templates/REPRODUCTION-NOTES.md`.

Procedure:

1. Copy the template into the attempt workspace as `REPRODUCTION-NOTES.md`.
2. Walk every row of the EM ambiguity checklist. Search methods, experiments, appendix, captions,
   and footnotes.
3. Classify each item `SPECIFIED`, `PARTIALLY_SPECIFIED`, or `UNSPECIFIED`.
   - `SPECIFIED`: exact quote and section.
   - `PARTIALLY_SPECIFIED`: the quote and what is ambiguous.
   - `UNSPECIFIED`: the default chosen and the alternatives (never "standard choice").
4. Where verified author code resolves an item, tag it `[FROM_OFFICIAL_CODE]` with file:line.
5. Record contradictions: figure against text, equation against prose, paper against code.
6. Fill Expected results with one row per `gate-state.yaml` claim id, including the full regime
   (data regime, feature map, regularization, qubit budget, shots/samples) and the table or figure it comes from.

Rules:

- Complete the audit before any code generation.
- Regime tags must be explicit enough for the reproduction review to check later.
- Do not execute code during the audit.
