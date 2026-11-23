#!/usr/bin/env python3
"""Format lint for ``.auto-research/`` (state, tasks, threads).

Contract: ``.auto-research/README.md``. Run from the repository root:

    .venv/bin/python skills/auto-research/scripts/auto_research_lint.py [--json]

Exit codes: 0 pass, 1 format problems (fix and fix), 2 usage error.

Every finding names a path and a concrete reason (missing key, wrong enum, bad id, orphan
file, …) so an agent can repair without guessing. Writers already refuse invalid updates;
this lint catches drift from hand edits, partial migrations, or bugs.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parents[3]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def collect(root: Path) -> list[str]:
    """Return every format problem under ``.auto-research/`` (empty = ok)."""
    root = root.resolve()
    scripts = Path(__file__).resolve().parent
    consult = scripts.parents[1] / "thread-interaction" / "scripts" / "thread_interaction.py"
    loop = _load("auto_research_loop_state", scripts / "loop_state.py")
    threads_mod = _load("thread_interaction_mod", consult)

    findings: list[str] = []
    auto = root / ".auto-research"
    state_rel = ".auto-research/state.json"
    state_path = auto / "state.json"

    if not auto.is_dir():
        return [".auto-research/: directory missing — run skills/auto-research/scripts/seed_local.py"]
    if not state_path.is_file():
        return [f"{state_rel}: missing — run skills/auto-research/scripts/seed_local.py"]

    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        return [f"{state_rel}: not valid JSON ({error})"]
    except OSError as error:
        return [f"{state_rel}: cannot read ({error})"]

    if not isinstance(data, dict):
        return [f"{state_rel}: must be a JSON object"]

    if "pending_human_thread_id" in data:
        findings.append(
            f"{state_rel}: unexpected key 'pending_human_thread_id' "
            "(removed; awaiting researcher is derived from open Threads — see README)"
        )
    if "thread_ids" in data:
        findings.append(
            f"{state_rel}: unexpected key 'thread_ids' "
            "(use ordered state.threads meta objects; seed_local.py migrates this)"
        )

    internal, external = loop.check(root, data)
    for msg in internal + external:
        findings.append(f"{state_rel}: {msg}")

    tasks_dir = auto / "tasks"
    if tasks_dir.is_dir():
        known_tasks = {
            item["id"]
            for item in (data.get("tasks") or [])
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        }
        for orphan in sorted(
            p for p in tasks_dir.glob("*.md")
            if p.stem not in known_tasks and p.name != "README.md"
        ):
            if not any(orphan.name in f for f in findings):
                findings.append(
                    f".auto-research/tasks/{orphan.name}: orphan body — "
                    "delete the file or add a matching entry to state.tasks"
                )

    metas = data.get("threads") if isinstance(data.get("threads"), list) else []
    for meta in metas:
        if not isinstance(meta, dict) or not isinstance(meta.get("id"), str):
            continue
        tid = meta["id"]
        rel = f".auto-research/threads/{tid}.json"
        path = root / rel
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            findings.append(f"{rel}: not valid JSON ({error})")
            continue
        except OSError as error:
            findings.append(f"{rel}: cannot read ({error})")
            continue
        if isinstance(payload, dict) and set(payload) != {"messages"}:
            findings.append(
                f"{rel}: must contain only key 'messages' "
                f"(unexpected {sorted(set(payload) - {'messages'})}; "
                "Thread meta belongs in state.threads)"
            )
        messages = payload.get("messages") if isinstance(payload, dict) else payload
        for msg in threads_mod.validate_messages(
            messages, where=tid,
            created=meta.get("created"), updated=meta.get("updated"), status=meta.get("status"),
        ):
            findings.append(f"{rel}: {msg}")

    threads_dir = auto / "threads"
    if threads_dir.is_dir():
        known = {
            meta["id"] for meta in metas
            if isinstance(meta, dict) and isinstance(meta.get("id"), str)
        }
        for orphan in sorted(p for p in threads_dir.glob("thread-*.json") if p.stem not in known):
            if not any(orphan.name in f for f in findings):
                findings.append(
                    f".auto-research/threads/{orphan.name}: orphan file — "
                    "delete it or add matching meta to state.threads"
                )

    ordered: list[str] = []
    seen: set[str] = set()
    for item in findings:
        if item not in seen:
            seen.add(item)
            ordered.append(item)
    return ordered


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Lint .auto-research/ against .auto-research/README.md (state, tasks, threads).")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--json", action="store_true", help="print findings as a JSON list")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    try:
        findings = collect(root)
    except Exception as error:  # noqa: BLE001
        print(f"auto_research_lint: {error}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps({"ok": not findings, "findings": findings}, indent=2, ensure_ascii=False))
    elif not findings:
        print("auto_research_lint: ok")
    else:
        print(f"auto_research_lint: {len(findings)} problem(s)", file=sys.stderr)
        for item in findings:
            print(f"error: {item}", file=sys.stderr)
        print(
            "Fix via loop_state.py / thread_interaction.py (do not hand-edit), "
            "then re-run this lint. Format contract: .auto-research/README.md",
            file=sys.stderr,
        )
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
