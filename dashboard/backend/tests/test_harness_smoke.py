"""Smoke tests for the lab harness wiring (empty template defaults)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


class HarnessSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        sys.path.insert(0, str(ROOT))
        os.chdir(ROOT)

    def test_notes_empty_when_feature_off(self) -> None:
        from dashboard.backend.notes import projects
        # Template ships notes/README only; no manuscript projects required.
        self.assertIsInstance(projects(), list)

    def test_auto_research_state_shape(self) -> None:
        state = json.loads((ROOT / ".auto-research" / "state.json").read_text(encoding="utf-8"))
        self.assertEqual(state.get("schema"), "auto-research-1")
        self.assertIn(state.get("status"), {"running", "paused", "idle"})
        self.assertIsInstance(state.get("tasks"), list)
        self.assertIsInstance(state.get("threads"), list)

    def test_discussion_validates(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(ROOT / "skills/research-threads/scripts/research_threads.py"), "validate"],
            cwd=ROOT, capture_output=True, text=True, check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_search_returns_semantic_flags(self) -> None:
        from dashboard.backend.app import App
        from dashboard.backend import search
        payload = search.search(App(), "wiki schema", limit=5)
        self.assertIn("groups", payload)
        self.assertIn("semantic_enabled", payload)
        self.assertIn("pending", payload)

    def test_apidocs_unavailable_without_package(self) -> None:
        from dashboard.backend.app import App
        app = App()
        tree = app.apidocs.tree(False, app.root)
        self.assertEqual(tree["package"], "(none)")
        self.assertFalse(tree.get("available"))
        self.assertIn("no package", (tree.get("error") or "").lower())

    def test_fs_health_passes(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(ROOT / "skills/auto-research/scripts/fs_health_lint.py")],
            cwd=ROOT, capture_output=True, text=True, check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)


if __name__ == "__main__":
    unittest.main()
