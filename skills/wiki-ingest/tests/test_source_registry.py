from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "source_registry.py"
SPEC = importlib.util.spec_from_file_location("source_registry", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

TAXONOMY = """\
allowed_source_prefixes: []
citable_wiki_prefixes:
  - wiki/records/
  - wiki/models/
retired_path_prefixes:
  - inbox/
"""


class SourceRegistryTests(unittest.TestCase):
    def make_scope(self, root: Path) -> Path:
        (root / "wiki" / "records" / "design").mkdir(parents=True)
        (root / "wiki" / "models").mkdir()
        (root / "wiki" / "concepts").mkdir()
        (root / "wiki" / "README.md").write_text("# Wiki schema\n", encoding="utf-8")
        (root / "wiki" / "taxonomy.yml").write_text(TAXONOMY, encoding="utf-8")
        for page in ("records/design/2026-01-01-plan.md", "models/ising-boundary.md", "concepts/idea.md"):
            (root / "wiki" / page).write_text("# Page\n", encoding="utf-8")
        (root / "labs" / "2026-01-01-lab").mkdir(parents=True)
        (root / "labs" / "2026-01-01-lab" / "report.md").write_text("# Report\n", encoding="utf-8")
        (root / "inbox").mkdir()
        (root / "inbox" / "old.pdf").write_text("", encoding="utf-8")
        return root

    def register(self, root: Path, path: str, kind: str = "lab", source_id: str = "lab:x") -> dict:
        return MODULE.register_source(
            root,
            source_id=source_id,
            title="Title",
            kind=kind,
            source_path=path,
            revision="2026-01-01",
            updated_pages=["wiki/concepts/idea.md"],
        )

    def test_repo_root_is_found_from_the_script_location(self) -> None:
        root = MODULE.find_repo_root()
        self.assertTrue((root / "wiki" / "README.md").is_file())
        self.assertEqual(root / "skills" / "wiki-ingest" / "scripts" / "source_registry.py", SCRIPT)
        self.assertEqual(MODULE.scope_path(None), root)

    def test_kinds_cover_the_schema(self) -> None:
        for kind in ("paper", "repository", "dataset", "reproduction", "lab", "record", "knowledge"):
            self.assertIn(kind, MODULE.SOURCE_KINDS)

    def test_register_and_reregister_updates_one_entry(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_scope(Path(directory))
            self.register(root, "labs/2026-01-01-lab/report.md")
            self.register(root, "labs/2026-01-01-lab/report.md")
            registry = yaml.safe_load((root / "wiki" / "sources.yml").read_text(encoding="utf-8"))
            self.assertEqual(len(registry["sources"]), 1)
            self.assertEqual(registry["sources"][0]["updated_pages"], ["wiki/concepts/idea.md"])

    def test_records_and_ledger_pages_are_citable_sources(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_scope(Path(directory))
            record = self.register(root, "wiki/records/design/2026-01-01-plan.md", "record", "record:plan")
            ledger = self.register(root, "wiki/models/ising-boundary.md", "knowledge", "knowledge:ising-boundary")
            self.assertEqual(record["kind"], "record")
            self.assertEqual(ledger["path"], "wiki/models/ising-boundary.md")

    def test_compiled_pages_retired_and_missing_paths_are_refused(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.make_scope(Path(directory))
            with self.assertRaisesRegex(ValueError, "compiled pages are not evidence"):
                self.register(root, "wiki/concepts/idea.md", "knowledge", "knowledge:idea")
            with self.assertRaisesRegex(ValueError, "retired location"):
                self.register(root, "inbox/old.pdf", "paper", "paper:old")
            with self.assertRaisesRegex(ValueError, "does not exist"):
                self.register(root, "labs/2026-01-02-missing/report.md")


if __name__ == "__main__":
    unittest.main()
