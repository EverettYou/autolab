from __future__ import annotations

import importlib.util
import io
import json
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

REPO_GITIGNORE = Path(__file__).resolve().parents[3] / ".gitignore"
SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "new_lab.py"
SPEC = importlib.util.spec_from_file_location("new_lab", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class NewLabTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "labs").mkdir()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def run_cli(self, *args: str) -> int:
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            return MODULE.main(["--root", str(self.root), *args])

    def test_creates_a_valid_lab_and_catalog(self) -> None:
        code = self.run_cli("--slug", "bb144-sweep", "--title", "BB144 sweep", "--summary", "Sweeps p.", "--date", "2026-09-26")
        self.assertEqual(code, 0)
        lab = self.root / "labs" / "2026-09-26-bb144-sweep"
        self.assertEqual(sorted(p.name for p in lab.iterdir()), [".gitignore", "PLAN.md", "REPORT.md", "lab.json"])
        record = json.loads((lab / "lab.json").read_text(encoding="utf-8"))
        self.assertEqual(record["stage"], "active")
        self.assertEqual(record["created"], "2026-09-26")
        self.assertEqual(record["parents"], [])
        self.assertFalse({"report", "plan", "readme"} & set(record))
        self.assertIn("# Plan: BB144 sweep", (lab / "PLAN.md").read_text(encoding="utf-8"))
        self.assertIn("labs/2026-09-26-bb144-sweep/scripts/", (lab / "REPORT.md").read_text(encoding="utf-8"))
        catalog = json.loads((self.root / "labs" / "labs.json").read_text(encoding="utf-8"))
        self.assertEqual([entry["id"] for entry in catalog["labs"]], ["2026-09-26-bb144-sweep"])
        spec = importlib.util.spec_from_file_location("labs_catalog", SCRIPT.parents[2] / "organize-lab" / "scripts" / "labs_catalog.py")
        assert spec and spec.loader
        catalog_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(catalog_module)
        self.assertEqual(catalog_module.validate_lab(lab)[1], [])

    @unittest.skipUnless(shutil.which("git") and REPO_GITIGNORE.is_file(), "needs git and the repository .gitignore")
    def test_lab_gitignore_tracks_numerical_evidence_under_the_repository_rules(self) -> None:
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        shutil.copy(REPO_GITIGNORE, self.root / ".gitignore")
        self.assertEqual(self.run_cli("--slug", "g", "--title", "G", "--summary", "S", "--date", "2026-09-26"), 0)
        # Repo .gitignore drops labs/**/data|logs and heavy blobs; slim results/figures stay tracked.
        tracked = ["lab.json", "PLAN.md", "REPORT.md", ".gitignore", "scripts/run.py", "notes/audit.md",
                   "results/summary.json", "results/p2/curve.csv", "figures/gap.png", "figures/sub/gap.png",
                   "checkpoints/m/card.md", "checkpoints/m/config.json"]
        ignored = ["scripts/__pycache__/run.cpython-311.pyc", "run.pid", "results/leaderboard.lock",
                   "data/spectrum.npz", "logs/dmrg.log", "data/state.mps.pkl.gz", ".cache/tmp"]
        lab = Path("labs") / "2026-09-26-g"
        for rel in tracked + ignored:
            path = self.root / lab / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                path.write_text("x\n", encoding="utf-8")

        def ignored_paths(rels: list[str]) -> set[str]:
            proc = subprocess.run(
                ["git", "-C", str(self.root), "check-ignore", "--no-index", *[str(lab / rel) for rel in rels]],
                capture_output=True, text=True,
            )
            return {Path(line).relative_to(lab).as_posix() for line in proc.stdout.splitlines()}

        self.assertEqual(ignored_paths(tracked), set())
        self.assertEqual(ignored_paths(ignored), set(ignored))

    def test_refuses_existing_lab_and_bad_input(self) -> None:
        args = ("--slug", "x", "--title", "X", "--summary", "S", "--date", "2026-09-26")
        self.assertEqual(self.run_cli(*args), 0)
        self.assertEqual(self.run_cli(*args), 2)
        self.assertEqual(self.run_cli("--slug", "Bad_Slug", "--title", "X", "--summary", "S"), 2)
        self.assertEqual(self.run_cli("--slug", "y", "--title", "X", "--summary", "S", "--date", "26-09-2026"), 2)

    def test_parent_lab_must_exist(self) -> None:
        self.assertEqual(
            self.run_cli("--slug", "child", "--title", "C", "--summary", "S", "--date", "2026-09-27",
                         "--parent", "2026-09-26-missing"),
            2,
        )
        self.assertEqual(
            self.run_cli("--slug", "base", "--title", "B", "--summary", "S", "--date", "2026-09-26"),
            0,
        )
        self.assertEqual(
            self.run_cli("--slug", "child", "--title", "C", "--summary", "S", "--date", "2026-09-27",
                         "--parent", "2026-09-26-base"),
            0,
        )
        child = json.loads((self.root / "labs" / "2026-09-27-child" / "lab.json").read_text(encoding="utf-8"))
        self.assertEqual(child["parents"], ["2026-09-26-base"])
        catalog = json.loads((self.root / "labs" / "labs.json").read_text(encoding="utf-8"))
        by_id = {e["id"]: e for e in catalog["labs"]}
        self.assertEqual(by_id["2026-09-27-child"]["parents"], ["2026-09-26-base"])

    def test_checks_reference_and_thread_ids(self) -> None:
        (self.root / "references" / "astra").mkdir(parents=True)
        (self.root / ".auto-research").mkdir(exist_ok=True)
        (self.root / ".auto-research" / "state.json").write_text(json.dumps({"threads": [{"id": "thread-001"}]}), encoding="utf-8")
        base = ("--slug", "z", "--title", "Z", "--summary", "S", "--date", "2026-09-26")
        self.assertEqual(self.run_cli(*base, "--reference", "nope"), 2)
        self.assertEqual(self.run_cli(*base, "--thread", "thread-002"), 2)
        self.assertFalse((self.root / "labs" / "2026-09-26-z").exists())
        self.assertEqual(self.run_cli(*base, "--reference", "astra", "--thread", "thread-001"), 0)

    def test_new_lab_fails_the_completion_lint_until_filled(self) -> None:
        self.run_cli("--slug", "w", "--title", "W", "--summary", "S", "--date", "2026-09-26")
        lint_path = Path(__file__).resolve().parents[2] / "organize-lab" / "scripts" / "lab_report_lint.py"
        spec = importlib.util.spec_from_file_location("lab_report_lint", lint_path)
        assert spec and spec.loader
        lint = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(lint)
        result = lint.lint_lab(self.root / "labs" / "2026-09-26-w", self.root)
        self.assertFalse(result["ok"])
        self.assertTrue(any("unfilled template marker" in e for e in result["errors"]))


if __name__ == "__main__":
    unittest.main()
