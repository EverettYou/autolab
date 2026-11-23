from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "seed_local.py"
SPEC = importlib.util.spec_from_file_location("seed_local", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class SeedLocalTests(unittest.TestCase):
    def test_creates_state_and_merges_legacy_threads(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            auto = root / ".auto-research"
            auto.mkdir(parents=True)
            (auto / "threads.json").write_text(
                json.dumps({"threads": [{"id": "thread-001"}]}), encoding="utf-8"
            )
            site = root / "dashboard" / "frontend"
            site.mkdir(parents=True)
            (site / "site.defaults.json").write_text('{"search": {"api_key": ""}}\n', encoding="utf-8")

            MODULE.seed_local_files(root)
            state = json.loads((auto / "state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["schema"], MODULE.SCHEMA)
            self.assertEqual(state["threads"][0]["id"], "thread-001")
            self.assertEqual((site / "site.json").read_text(encoding="utf-8"), '{"search": {"api_key": ""}}\n')

            # Does not overwrite existing state
            (auto / "state.json").write_text('{"schema": "x", "threads": [], "mine": true}\n', encoding="utf-8")
            (site / "site.json").write_text('{"search": {"api_key": "sk-local"}}\n', encoding="utf-8")
            MODULE.seed_local_files(root)
            self.assertIn("mine", (auto / "state.json").read_text(encoding="utf-8"))
            self.assertIn("sk-local", (site / "site.json").read_text(encoding="utf-8"))

    def test_adds_threads_key_to_existing_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            auto = root / ".auto-research"
            auto.mkdir(parents=True)
            (auto / "state.json").write_text(
                json.dumps({"schema": "auto-research-1", "tasks": []}), encoding="utf-8"
            )
            MODULE.seed_local_files(root)
            state = json.loads((auto / "state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["threads"], [])
