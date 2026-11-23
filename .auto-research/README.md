# Auto Research

This checkout’s loop and Threads store. This template ships the **minimum scaffold** under this
folder — all of it tracked. This README is the format contract.

| Path | Role |
| --- | --- |
| `state.json` | Empty seed + loop status, deliverable, next action, **ordered** `tasks` / `threads` meta |
| `tasks/<id>.md` | Task body (fixed sections). Order stays in `state.tasks` — created by the loop, not scaffold |
| `tasks/README.md` | Task body contract (`## Goal` / `## Work` / `## Done when`) |
| `threads/<id>.json` | **Only** `{"messages": [...]}` for that Thread. Meta stays in `state.threads` — loop-created |
| `threads/README.md` | Message object contract (`author` / `type` enums and fields) |

### Lifecycle (scaffold once, then local)

| Stage | What happens |
| --- | --- |
| **this template** | Track the minimum setup (this README, `tasks/` + `threads/` READMEs, `state.json`). If a path would need to be gitignored, it does not belong in the template. |
| **Create project / first sync** | Scaffold is **copied** into the consumer, then reset to empty `tasks/` / `threads/` + paused `state.json`. |
| **After that** | Consumer **gitignore ignores all of `.auto-research/`** (live checkout data, not a template). `sync_apply` **skips** the folder if it already exists — no later sync. |
| **Day to day** | Agents never hand-edit; use the scripts below. `seed_local` only fills a missing `state.json` (e.g. broken checkout). |

**Format lint.** Writers refuse invalid updates; for a full census (including hand-edit drift),
run:

```bash
.venv/bin/python skills/auto-research/scripts/auto_research_lint.py
```

Exit `1` means fix the listed findings (each line is `path: reason`) and re-run. Also in the
`land` / `all` guard bundles as `auto-research`.

**Cite direction.** Threads cite labs (`related_labs`). Labs do **not** cite threads in prose.
Durable outcomes belong in the lab `REPORT.md` / `results/` (and wiki when ingested), not as a
dependency on a thread id. Checkout-local state may name a thread as
`.auto-research/threads/thread-042.json` (or `thread-042` in a task `blocked_on`).

---

## `state.json`

```json
{
  "schema": "auto-research-1",
  "status": "paused",
  "updated": "2026-11-20T09:02:04Z",
  "active_deliverable": null,
  "next_action": "Run one supervisor tick after the researcher sets a deliverable.",
  "last_action": null,
  "last_supervisor_at": null,
  "idle": null,
  "tasks": [],
  "threads": []
}
```

Exact top-level keys (no extras):

| Key | Type | Meaning |
| --- | --- | --- |
| `schema` | string | Format version of this store: currently `auto-research-1` (project-agnostic schema id) |
| `status` | string | `running` \| `paused` \| `idle` |
| `updated` | string | ISO-8601 UTC, e.g. `2026-11-20T09:02:04Z` |
| `active_deliverable` | object \| null | `{lab, summary, acceptance}` or `null` |
| `next_action` | string | One concrete non-empty sentence |
| `last_action` | object \| null | `{at, summary}` or `null` |
| `last_supervisor_at` | string \| null | ISO-8601 UTC of last supervisor tick, or `null` |
| `idle` | object \| null | Idle backstop record when `status` is `idle`; otherwise `null` (see below) |
| `tasks` | array | Ordered task meta (see [Tasks](#tasks)); first = highest priority |
| `threads` | array | Ordered Thread meta (see [Threads](#threads)); **no** `messages` in these rows |

`active_deliverable` when set:

| Field | Type | Rules |
| --- | --- | --- |
| `lab` | string | Existing `labs/<lab-id>/` directory (`YYYY-MM-DD-slug`) |
| `summary` | string | Non-empty |
| `acceptance` | string[] | Non-empty list of acceptance criteria |

`last_action` when set: `at` is ISO-8601 UTC; `summary` is non-empty.

`idle` when `status` is `idle` (otherwise must be `null`):

```json
{
  "reason": "router-empty",
  "detail": "Supervisor refill and maintain side-work also found nothing runnable.",
  "lift_when": "An unblocked task appears, or thread-042 gets a researcher reply.",
  "since": "2026-11-23T12:00:00Z",
  "fingerprint": {
    "next_action": "…",
    "unblocked_task_ids": [],
    "awaiting_human": ["thread-042"]
  }
}
```

| Field | Type | Rules |
| --- | --- | --- |
| `reason` | string | `router-empty` \| `repeated-tick` \| `supervisor-refill-failed` \| `other` |
| `detail` | string | Non-empty: why idle after seeking work |
| `lift_when` | string | Non-empty, concrete condition the next `idle-check` tick can evaluate |
| `since` | string | ISO-8601 UTC when idle was entered |
| `fingerprint` | object | Cheap snapshot (`idle-check` compares against a fresh fingerprint) |

Enter idle only via `loop_state.py idle --reason … --lift-when …`. Prefer staying `running` and
finding work; idle is a backstop. See `skills/auto-research/references/idle.md`.

`schema` is the **format version** of `.auto-research/` (state + tasks + threads layout). Loaders
and the lint refuse unknown values so a newer checkout can migrate deliberately. The id is
project-agnostic (`auto-research-1`, then `auto-research-2`, …) — not branded with a lab or
template name — so every repo that uses this store shares the same version line.

`status` is a flag the loop wrote about itself. It is not evidence that ticks are firing; see
`skills/auto-research/references/starting-the-loop.md`.

Threads awaiting the researcher are **derived**: open threads whose last message is from an
agent question (`loop_state.py status` → `awaiting_human`; same rule as the dashboard badge).
There is no `pending_human_thread_id`.

Owned by `skills/auto-research/scripts/loop_state.py` (and the dashboard order API).

---

## Tasks

Each task is one object in the ordered `state.tasks` list, plus a body file
`tasks/<id>.md`. The list order **is** priority (index 0 runs first among unblocked items that
fit the GPU tier).

### Meta fields (`state.tasks[]`)

```json
{
  "id": "port-the-relay-decoder",
  "title": "Port the relay decoder",
  "for": "integrator",
  "gpu": "free",
  "time": "5min",
  "blocked_on": null,
  "related_labs": ["2026-09-25-some-lab"],
  "detail": ".auto-research/tasks/port-the-relay-decoder.md",
  "added": "2026-11-20"
}
```

Exact keys (no extras):

| Field | Type | Rules |
| --- | --- | --- |
| `id` | string | Kebab-case slug (`^[a-z0-9]+(?:-[a-z0-9]+)*$`), unique |
| `title` | string | One non-empty line |
| `for` | string | Comma-separated roles from `scout`, `reproducer`, `integrator`, `auditor`, `maintain`, `auto`, `all` |
| `gpu` | string | `free` \| `light` \| `heavy` |
| `time` | string | `0` \| `1min` \| `5min` \| `15min` \| `30min` \| `1hr` \| `2hr` \| `4hr` \| `8hr` \| `1d` \| `2d` |
| `blocked_on` | string \| null | `null`, or a reason. If it cites a thread, name it (`thread-042`). GPU/time/credits/outages go through `gpu`/`time`, never here |
| `related_labs` | string[] | Distinct existing lab ids, or `[]` |
| `detail` | string | Must be exactly `.auto-research/tasks/<id>.md` |
| `added` | string | `YYYY-MM-DD` |

### Body (`tasks/<id>.md`)

```markdown
# Port the relay decoder

## Goal
Relay decoder runs through the package API on the lab’s fixture.

## Work
Wire the driver under labs/<id>/scripts/; compare against the reference numbers in REPORT.md.

## Done when
Lab REPORT.md shows a matching figure and the package test for the port passes.
```

Fixed sections only — see **`tasks/README.md`**. Finished tasks are **deleted** (`task done`).

### Working with tasks

```bash
L=".venv/bin/python skills/auto-research/scripts/loop_state.py"
$L status
$L task list [--unblocked | --blocked] [--fits free|light|heavy] [--json]
$L task show <id>
$L task add --title "..." --for integrator --gpu free --time 5min [--lab <lab-id>] \
    [--top | --before <id> | --after <id>] (--content "..." | --content-file body.md)
$L task move <id> (--top | --bottom | --before <id> | --after <id>)
$L task set <id> [--title "..."] [--for ...] [--gpu ...] [--time ...] [--lab <lab-id>]
$L task done <id> [--summary "..."]
$L task block <id> --on "researcher decision in thread-042"
$L task unblock <id>
$L validate
```

---

## Threads

Split so `state.json` stays small: **meta in `state.threads`**, **messages in files**.

`state.threads` is ordered (`threads[0].id` must be `thread-001`, then `thread-002`, …). Every
meta row must have `.auto-research/threads/<id>.json`; every such file must have a meta row.

### Thread meta (`state.threads[]`)

```json
{
  "id": "thread-001",
  "title": "Choose the decoder family",
  "category": "decision",
  "priority": "normal",
  "status": "open",
  "related_labs": ["2026-09-25-some-lab"],
  "created": "2026-11-20T09:41:22Z",
  "updated": "2026-11-20T09:41:22Z"
}
```

Exact keys (no extras — **do not** put `messages` here):

| Field | Type | Rules |
| --- | --- | --- |
| `id` | string | `thread-NNN` (at least three digits), sequential in list order |
| `title` | string | One non-empty line, ≤ 200 characters |
| `category` | string | `direction` \| `decision` \| `scope` \| `checkpoint` |
| `priority` | string | `high` \| `normal` \| `low` |
| `status` | string | `open` \| `closed` |
| `related_labs` | string[] | Distinct lab ids (`YYYY-MM-DD-slug`), or `[]` |
| `created` | string | ISO-8601 UTC; must equal the first message’s `created` |
| `updated` | string | ISO-8601 UTC; must be ≥ last message’s `created` |

`direction` = researcher steers work; `decision` = agent needs a choice; `scope` = change the
accepted question/budget/deliverable; `checkpoint` = planned researcher review before continuing.

### Messages file (`threads/<id>.json`)

```json
{
  "messages": [
    {
      "id": "msg-001",
      "author": "agent",
      "type": "question",
      "created": "2026-11-20T09:41:22Z",
      "content": "…"
    }
  ]
}
```

Only `messages` at the top level. Full message field rules: **`threads/README.md`**. Parsers join
meta from `state.threads` with this file by id. Append only via the script.

### Awaiting / hygiene

- Latest message from the **researcher** → waiting on an agent.
- Latest message is an agent **`question`** and a task’s `blocked_on` cites the thread →
  “awaiting reply” for the researcher.
- An agent progress note does **not** belong in the Thread; put it in the lab report.
- New concern → new thread (after a decision the agent already took up). Clarifying questions
  before that acknowledgment stay on the same thread.
- Do not agent-`reply` on top of your own unanswered `question` (clears the awaiting-reply badge).

Details and when to ask: `skills/thread-interaction/SKILL.md`.

### Working with Threads

```bash
M=".venv/bin/python skills/thread-interaction/scripts/thread_interaction.py"
$M list [--status open|closed] [--json]
$M show thread-042 [--json]
$M open --title "..." [--category decision|scope|checkpoint|direction] [--priority high|normal|low] \
    [--lab <lab-id> ...] [--author agent|user] (--content "..." | --content-file brief.md)
$M reply thread-042 --author agent|user [--type reply|decision|instruction|question] [--lab <lab-id>] \
    (--content "..." | --content-file -)
$M close thread-042 [--author agent|user] (--content "..." | --content-file -)
$M reopen thread-042 --author agent|user [--type reply|decision|instruction] (--content "..." | ...)
$M validate
```

The dashboard **Threads** section reads the same files. Researcher posts from the UI are
`author=user` through this script.

---

## Scripts (owners)

| Concern | Script |
| --- | --- |
| Loop + tasks | `skills/auto-research/scripts/loop_state.py` |
| Threads | `skills/thread-interaction/scripts/thread_interaction.py` |
| Create / migrate local store | `skills/auto-research/scripts/seed_local.py` |

Procedure (when to tick, when to ask): `skills/auto-research/SKILL.md`
(detail in `skills/auto-research/references/`), `skills/thread-interaction/SKILL.md`.
