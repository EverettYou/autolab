from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "ensure_topics.py"
SPEC = importlib.util.spec_from_file_location("ensure_topics", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

TAXONOMY = """# comment stays
scope: project
page_types:
  system: {folder: system}
topics:
  - Research Pipeline
  - Lab Practice
statuses:
  - active
"""


class EnsureTopicsTests(unittest.TestCase):
    def test_appends_new_topics_and_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "taxonomy.yml"
            path.write_text(TAXONOMY, encoding="utf-8")
            added = MODULE.ensure_topics(path, ["Imaging", "Research Pipeline"], dry_run=False)
            self.assertEqual(added, ["Imaging"])
            text = path.read_text(encoding="utf-8")
            self.assertIn("# comment stays", text)
            self.assertIn("  - Imaging\n", text)
            self.assertEqual(text.count("Imaging"), 1)
            again = MODULE.ensure_topics(path, ["Imaging"], dry_run=False)
            self.assertEqual(again, [])

    def test_dry_run_does_not_write(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "taxonomy.yml"
            path.write_text(TAXONOMY, encoding="utf-8")
            added = MODULE.ensure_topics(path, ["Calibration"], dry_run=True)
            self.assertEqual(added, ["Calibration"])
            self.assertNotIn("Calibration", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
