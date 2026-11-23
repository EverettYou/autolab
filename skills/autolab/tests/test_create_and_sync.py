"""Tests for create_project.py and sync_apply.py (AutoLab template only).

Run: .venv/bin/python -m pytest skills/autolab/tests -q
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
TEMPLATE = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(SCRIPTS))

_create_spec = importlib.util.spec_from_file_location("create_project", SCRIPTS / "create_project.py")
assert _create_spec and _create_spec.loader
CREATE = importlib.util.module_from_spec(_create_spec)
_create_spec.loader.exec_module(CREATE)

_sync_spec = importlib.util.spec_from_file_location("sync_apply", SCRIPTS / "sync_apply.py")
assert _sync_spec and _sync_spec.loader
SYNC = importlib.util.module_from_spec(_sync_spec)
_sync_spec.loader.exec_module(SYNC)


class CreateProjectTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dest = Path(self._tmp.name) / "new-lab"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_create_strips_template_skill_and_installs_consumer_workflow(self) -> None:
        code = CREATE.main(["--name", "Review Lab", "--dest", str(self.dest)])
        self.assertEqual(code, 0)
        self.assertFalse((self.dest / "skills" / "autolab").exists())
        self.assertFalse((self.dest / ".github" / "workflows" / "release-tag.yml").exists())
        wf = self.dest / ".github" / "workflows" / "lab-os-sync.yml"
        self.assertTrue(wf.is_file())
        text = wf.read_text(encoding="utf-8")
        self.assertIn("repository: EverettYou/autolab", text)
        self.assertNotIn("vars.LAB_OS_REPO", text)

    def test_create_clears_science_floors_and_writes_empty_loop_seed(self) -> None:
        code = CREATE.main(["--name", "Review Lab", "--dest", str(self.dest)])
        self.assertEqual(code, 0)
        refs = json.loads((self.dest / "references" / "references.json").read_text(encoding="utf-8"))
        labs = json.loads((self.dest / "labs" / "labs.json").read_text(encoding="utf-8"))
        self.assertEqual(refs.get("references"), [])
        self.assertEqual(labs.get("labs"), [])
        dated = [p for p in (self.dest / "labs").iterdir() if p.is_dir() and p.name.startswith("20")]
        self.assertEqual(dated, [])
        state = json.loads((self.dest / ".auto-research" / "state.json").read_text(encoding="utf-8"))
        self.assertIsNone(state.get("active_deliverable"))
        self.assertEqual(state.get("tasks"), [])
        self.assertEqual(state.get("status"), "paused")
        self.assertEqual(state.get("updated"), "1970-01-01T00:00:00Z")
        cfg = (self.dest / "config.yml").read_text(encoding="utf-8")
        self.assertIn("name: review-lab", cfg)
        self.assertIn('title: "Review Lab"', cfg)


class SyncApplyTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.consumer = self.root / "consumer"
        self.consumer.mkdir()
        # Minimal consumer tree so sync has somewhere to land.
        (self.consumer / "skills").mkdir()
        (self.consumer / "config.yml").write_text('os_version: "0.0.0"\nname: consumer\n', encoding="utf-8")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_refuses_template_dest(self) -> None:
        with self.assertRaises(SystemExit) as ctx:
            SYNC.main(["--from", str(TEMPLATE), "--to", str(TEMPLATE), "--dry-run"])
        self.assertIn("skills/autolab", str(ctx.exception))

    def test_bootstrap_writes_empty_seed_not_live_template_state(self) -> None:
        # Build a tiny fake template whose .auto-research/state.json is deliberately live.
        fake = self.root / "fake-template"
        auto = fake / ".auto-research"
        (auto / "tasks").mkdir(parents=True)
        (auto / "threads").mkdir(parents=True)
        (auto / "README.md").write_text("# auto\n", encoding="utf-8")
        (auto / "tasks" / "README.md").write_text("# tasks\n", encoding="utf-8")
        (auto / "threads" / "README.md").write_text("# threads\n", encoding="utf-8")
        (auto / "state.json").write_text(
            json.dumps(
                {
                    "schema": "auto-research-1",
                    "status": "running",
                    "updated": "2026-11-23T00:00:00Z",
                    "active_deliverable": {"lab": "2026-01-01-leak"},
                    "tasks": [{"id": "should-not-copy"}],
                    "threads": [],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        # Minimal sync trees so apply does not require a full AutoLab checkout.
        for rel in ("skills", "dashboard", "wiki/system", "labs/_tools"):
            (fake / rel).mkdir(parents=True, exist_ok=True)
        (fake / "run.sh").write_text("#!/bin/sh\n", encoding="utf-8")
        for name in ("labs", "references", "notes", "lib", "wiki"):
            (fake / name).mkdir(exist_ok=True)
            (fake / name / "README.md").write_text("#\n", encoding="utf-8")

        code = SYNC.main(["--from", str(fake), "--to", str(self.consumer)])
        self.assertEqual(code, 0)
        state = json.loads((self.consumer / ".auto-research" / "state.json").read_text(encoding="utf-8"))
        self.assertIsNone(state.get("active_deliverable"))
        self.assertEqual(state.get("tasks"), [])
        self.assertEqual(state.get("updated"), "1970-01-01T00:00:00Z")
        self.assertEqual(state, json.loads(SYNC.EMPTY_AUTO_RESEARCH_STATE))

    def test_bootstrap_is_once_only(self) -> None:
        SYNC.main(["--from", str(TEMPLATE), "--to", str(self.consumer)])
        marker = self.consumer / ".auto-research" / "state.json"
        marker.write_text('{"schema":"auto-research-1","status":"running","tasks":["keep"]}\n', encoding="utf-8")
        SYNC.main(["--from", str(TEMPLATE), "--to", str(self.consumer)])
        kept = json.loads(marker.read_text(encoding="utf-8"))
        self.assertEqual(kept.get("status"), "running")
        self.assertEqual(kept.get("tasks"), ["keep"])

    def test_strips_autolab_skill_if_present_on_consumer(self) -> None:
        stray = self.consumer / "skills" / "autolab"
        stray.mkdir(parents=True)
        (stray / "SKILL.md").write_text("x\n", encoding="utf-8")
        # Dest with skills/autolab is refused before apply — use a dest that looks like a
        # consumer after create (no autolab), then inject stray mid-flight via apply().
        changes = SYNC.apply(TEMPLATE, self.consumer, dry_run=False)
        self.assertTrue(any("remove skills/autolab" in c for c in changes))
        self.assertFalse(stray.exists())


class SharedSeedTests(unittest.TestCase):
    def test_create_and_sync_seeds_match(self) -> None:
        self.assertEqual(CREATE.EMPTY_AUTO_RESEARCH_STATE, SYNC.EMPTY_AUTO_RESEARCH_STATE)


if __name__ == "__main__":
    unittest.main()
