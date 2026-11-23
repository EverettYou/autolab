---
name: autolab
description: Autolab template administration — scaffold a new consumer lab from this repository, or sync OS files (skills, dashboard, …) into an existing consumer. Never present in consumer labs.
usage: Use only inside the Autolab template repo to create a consumer lab or sync OS files into one; never leave this skill in a consumer checkout.
---

# autolab (template only)

This skill is why the Autolab repository exists. It lives **only here** and is the admin surface for:

1. **Creating** a new lab project from this template (`create_project.py`)
2. **Syncing** sync-zone files into a consumer lab (`sync_apply.py`)

Consumer labs must **not** contain this skill. `create_project` strips it from the new tree; `sync_apply` never copies it and deletes it if found on the consumer.

## When to use

- You are working **in Autolab** and need a new domain lab.
- You are releasing / bumping Autolab and need to push `skills/` + `dashboard/` (and agreed OS files) into a consumer via PR.

Do **not** use this skill inside a consumer lab checkout as a resident procedure—those repos consume the OS; they do not own the template.

## Create a project

### Before creating (interview — do not invent)

Do **not** run `create_project.py` until the researcher has answered the required items
below (or already stated them clearly in this conversation). Ask in chat; do not guess a
name, path, or research direction.

| Ask? | Item | Default if they defer |
|------|------|------------------------|
| **Required** | **Project name** — display title; also becomes `config.yml` `name` (slugified) | none — stop and ask |
| **Required** | **Destination path** — where the new lab directory should live | `../<slug>` next to this Autolab checkout (confirm before using) |
| **Required** | **One-line direction** — what this lab is for (not a full thesis) | none — stop and ask |
| Optional | `git init` + initial commit | **yes** (`--git-init`) |
| Skip for now | `lib` / `--package` | **omit** — do not ask; most labs never need a package. Researcher can enable later |

Hard rules:

- Never invent `--name` or `--dest`.
- Never scaffold from a vague prompt like “make me a lab” without the three required answers.
- Do not open an `lib` / package interview unless the researcher brings it up.
- A full scientific `wiki/thesis.md` is **not** required at create time; the one-liner is enough
  to orient the new README. Leave thesis provisional unless they volunteer more.

### Scaffold

From the Autolab repo root, only after the interview:

```bash
python skills/autolab/scripts/create_project.py \
  --name my-lab \
  --dest ../mylab \
  --git-init
```

Add `--package mypkg` only when the researcher explicitly wants `features.lib` now.

What it does:

- Full-copies this template (minus template-only paths)
- Clears project-zone payloads (empty `references` / `labs` / `wiki` scaffolds)
- Writes `config.yml`, a human `README.md`, a full `AGENTS.md` (agent operating manual), and `CLAUDE.md` as `@AGENTS.md` only  <!-- rules-lint: allow -->
- **Removes `skills/autolab/`** from the new lab
- Localizes `.auto-research/` (minimum scaffold on disk; consumer `.gitignore` ignores the whole folder)

### After create

1. Fold the **one-line direction** into the new lab’s `README.md` opening (keep the Autolab layout
   help; do not replace the whole file with marketing copy).
2. If they gave only the one-liner, leave `wiki/thesis.md` as the provisional placeholder (or put
   that sentence under **Summary** and keep `status: provisional`).
3. Tell them the created path and how to `cd` + `./run.sh start`.

## Sync into a consumer

```bash
python skills/autolab/scripts/sync_apply.py \
  --from . \
  --to ../my-lab \
  --bump-pin
```

Use `--dry-run` first. Opens no PR by itself; CI workflows call the same script and open a PR.
Consumer-side example workflow: `workflows/lab-os-sync.example.yml` (copy into the consumer as `.github/workflows/lab-os-sync.yml`; set `LAB_OS_REPO`).

Sync registry is `scripts/sync_apply.py` (`SYNC_TREES` / `SYNC_FILES`):

- **Every sync:** `skills/` (except this skill), `dashboard/`, `run.sh`, `labs/_tools/`, floor READMEs (`labs/`, `references/`, `notes/`, `lib/`, `wiki/`), `wiki/taxonomy.yml`, `wiki/project/`
- **Bootstrap-once:** `.auto-research/` only if the consumer has no folder yet
- **Never sync:** project payloads (dated labs, reference bodies, domain wiki, notes manuscripts, lib code, live catalogs, consumer README/config); template-only this skill; **future Autolab-only dashboard demos**

`--bump-pin` updates the consumer `config.yml` `os_version` from this template's `config.yml` `os_version`.

## Identity

| Repo | Has `skills/autolab/`? |
|------|-------------------------|
| Autolab (template) | yes |
| Any scaffolded / synced consumer | no |
