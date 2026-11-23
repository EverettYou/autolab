---
name: research-workflow
description: Structured empirical research inside a lab - pre-experiment gate, parametric sweep design, measurement with early stops, rapid interpretation, minimal ablation, and a verdict. Gate the experiment before running and measure to answer the question, not to gather data.
usage: Use when a human request, a Thread, or a task asks a closed question that needs several configurations compared under one protocol. Not for one-off validation runs or pure package work (`promote-to-lib`).
---

# Research workflow

Run inside a lab created by `create-lab`. The lab's `PLAN.md` and `REPORT.md` are the durable
record; this skill is how you fill them.

## Gate before you measure

State the question closed: not "explore the space" but a falsifiable claim with named axes and a
stop rule (for example "does claim C survive size L=… with the same controls and metric M?").

1. Search the wiki, notes, and prior labs for existing numbers on the same setting:

   ```bash
   .venv/bin/python skills/wiki-query/scripts/query_wiki.py "<topic keywords>"
   ```

2. Lock the setting: every field that moves the number (model / protocol family, parameters,
   boundary or data conditions, system sizes, solver or estimator knobs, metric, seeds).
3. Write the success criterion and the stop rule into `PLAN.md` before the first sweep.
4. Budget compute. Prefer paired comparisons that change one axis at a time. Do not kill or pause
   unrelated running research jobs. See `wiki/system/spending-compute.md` when present.

## Sweep, interpret, ablate, verdict

1. Sweep only the axes named in the plan. Log every configuration field that moves the number.
2. Interpret after each arm: update `REPORT.md` with tables, uncertainty, caveats, and what
   changed. Keep incompatible conventions in separate records.
3. Ablate the smallest set that could falsify the claim (alternate seed, tighter tolerance,
   neighboring cut, control protocol).
4. Verdict: accept, reject, or inconclusive with the evidence cited. Hand off to `wiki-ingest`
   when the lab completes, and refresh `notes/` only when a manuscript claim should move.

## Checklist

- [ ] question is closed and falsifiable
- [ ] setting fields that move the number are locked before measurement
- [ ] compared arms share the same protocol definition
- [ ] size / seed / tolerance controls are explicit
- [ ] every claim in `REPORT.md` points at a result artifact
- [ ] open scientific decisions go through `research-threads`, not silent priority changes
