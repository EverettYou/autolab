# Reconstructing a missing PLAN.md or REPORT.md

Every lab has a `PLAN.md` and a `REPORT.md` ([report-contract.md](report-contract.md)). Labs from
before that rule often have neither, or keep them under other names. This is how to supply them
after the fact without inventing history. Never do it in a lab whose runs are still going.

## 1. Promote before writing

A document already in the lab that was written before the runs and states the plan (a `plan.md`,
`design.md`, `proposal.md`, a design note under `notes/`) becomes `PLAN.md` as it is. A document
that already reports the lab's results under another name becomes `REPORT.md` as it is.

```
python3 skills/organize-lab/scripts/lab_layout.py move <lab-id> <path> PLAN.md
python3 skills/organize-lab/scripts/lab_layout.py move <lab-id> <path> PLAN.md --apply
```

The first command previews; the second renames the file and rewrites every link to it. Do not
edit the promoted text: it is the record of what was planned. A document counts as written before
running when its first commit predates the first results and logs
(`git log --diff-filter=A --format='%h %ad' -- <path>`) or when it says so itself.

Only write a new document when nothing can be promoted.

## 2. Gather sources, in this order

1. **The lab itself.** `lab.json` (`title`, `summary`, `current_focus`, `next_action`), `notes/`,
   entry-point docstrings and argument defaults in `scripts/`, `configs/`, `results/`, the first
   and    last lines of `logs/`, and the lab's git history. Labs lived under `lab/` before commit
   `b8ea89e1`, so ask for both paths (with `ID` set to the lab id):
   `git log --stat --format='%h %ad %s' -- labs/$ID lab/$ID`. Read a file that no longer exists
   with `git show <commit>:lab/$ID/<file>`. Early commit messages and first versions of files
   usually show the plan.
2. **The wiki.** `rg -l <lab-id> wiki/records wiki/models wiki/algorithms`, then the rest of `wiki/`. Records
   often hold the design and the conclusion.
3. **Open work and decisions.** `.auto-research/tasks/*.md` and `.auto-research/state.json`
   (threads whose `related_labs` or messages name the lab).
4. **Fallback: the predecessor repository.** `qecbench-dev/notes/design/`, when it is checked out
   next to this repository. Read it; never modify it.

## 3. Cite

- Material in this repository's working tree: summarize it in your own words and link it with a
  relative link. Do not copy it.
- Material outside the repository, or only in git history: it cannot be linked. Copy the relevant
  part verbatim into a new note in the lab's `notes/` (lowercase kebab-case name) under this
  header, then summarize and link that note:

  ```
  # <title of the source>

  > Transcribed verbatim on <YYYY-MM-DD> from `<repository>/<path>` at <commit or "working tree">.
  > Only this header was added.
  ```

  Keep the copy exact, old paths included. `lab_layout.py` never rewrites or link-checks a note
  with this header, just as it leaves results and logs alone.
- Never cite what you did not open.

## 4. Write

- Directly under the title, a provenance note. For a plan:
  `> Reconstructed on <YYYY-MM-DD> from <linked sources>. Written after the lab ran: it records the plan as those sources show it, not a registration.`
  For a report:
  `> Reconstructed on <YYYY-MM-DD> from <linked sources>. No experiment was rerun.`
- Headings: `PLAN.md` uses the `create-lab` template (Question, Motivation, Prior anchors,
  Hypotheses and alternatives, Setting, Design, Success criterion, Stop rules, Completion,
  Amendments). `REPORT.md` uses the six sections of the contract.
- Where the sources are silent, write "Not recorded at the time." Do not supply hypotheses,
  predictions, success criteria, or stop rules that nobody wrote down. A criterion read off the
  result is not a criterion.
- Amendments in a reconstructed plan are changes that a dated source records (a commit, a thread
  message, a record), each with its date and link. Without one, write "None recorded at the time."
- Numbers only as a source states them, each linked to it (a `results/` file, a registry entry, a
  wiki record). No recomputation and no rounding changes.
- Setting: the exact command when a launcher, log, or docstring shows it
  (`.venv/bin/python labs/<id>/scripts/<entry>.py ...`); otherwise name the entry point and write
  that the command was not recorded at the time.
- Verdict: the conclusion the sources state, at their strength. Where they state none, say so and
  call the result inconclusive.
- Keep it short. A reconstructed document is an index to the evidence, not a new analysis.
- Change nothing else: not `lab.json`, not an existing report's text, not other labs.

## 5. Check

```
python3 skills/organize-lab/scripts/lab_report_lint.py <lab-id>
python3 skills/organize-lab/scripts/lab_layout.py check <lab-id> --links
```

Links in a reconstructed document must resolve. A promoted or legacy document keeps its own
headings, so the lint's heading errors for it are expected; broken links are not.
