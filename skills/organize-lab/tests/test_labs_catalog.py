from __future__ import annotations

import importlib.util
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "labs_catalog.py"
SPEC = importlib.util.spec_from_file_location("labs_catalog", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def lab_record(lab_id: str, **overrides) -> dict:
    record = {
        "id": lab_id,
        "title": f"Title of {lab_id}",
        "stage": "active",
        "summary": "One sentence.",
        "current_focus": "Measuring.",
        "next_action": "Run the sweep.",
        "created": lab_id[:10],
        "updated": lab_id[:10],
        "references": [],
        "discussion": [],
        "parents": [],
    }
    record.update(overrides)
    return record


class CatalogTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "labs").mkdir()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def make_lab(self, lab_id: str, record: dict | None = None, files=("PLAN.md", "REPORT.md")) -> Path:
        lab = self.root / "labs" / lab_id
        lab.mkdir()
        for name in files:
            (lab / name).write_text(f"# {name}\n", encoding="utf-8")
        data = lab_record(lab_id) if record is None else record
        (lab / "lab.json").write_text(json.dumps(data), encoding="utf-8")
        return lab

    def run_cli(self, *args: str) -> tuple[int, str]:
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = MODULE.main(["--root", str(self.root), *args])
        return code, buf.getvalue()

    def errors(self, only=None) -> list[str]:
        _, findings = MODULE.validate_all(self.root, only)
        return [f"{f.lab}: {f.message}" for f in findings if f.level == "error"]

    def warnings(self, only=None) -> list[str]:
        _, findings = MODULE.validate_all(self.root, only)
        return [f"{f.lab}: {f.message}" for f in findings if f.level == "warning"]


class ValidateTests(CatalogTestCase):
    def test_valid_lab_has_no_errors(self) -> None:
        self.make_lab("2026-09-25-alpha")
        self.assertEqual(self.errors(), [])

    def test_missing_lab_json_is_an_error(self) -> None:
        (self.root / "labs" / "2026-09-25-bare").mkdir()
        self.assertEqual(self.errors(), ["2026-09-25-bare: lab.json is missing"])

    def test_invalid_json_is_an_error(self) -> None:
        lab = self.make_lab("2026-09-25-alpha")
        (lab / "lab.json").write_text("{not json", encoding="utf-8")
        self.assertTrue(any("not valid JSON" in e for e in self.errors()))

    def test_missing_keys_are_reported(self) -> None:
        record = lab_record("2026-09-25-alpha")
        del record["summary"], record["discussion"]
        self.make_lab("2026-09-25-alpha", record)
        self.assertIn("2026-09-25-alpha: missing keys: summary, discussion", self.errors())

    def test_id_must_match_directory(self) -> None:
        self.make_lab("2026-09-25-alpha", lab_record("2026-09-25-beta"))
        self.assertTrue(any("does not match the directory name" in e for e in self.errors()))

    def test_blocked_reason_is_allowed_and_expected(self) -> None:
        self.make_lab("2026-09-25-alpha", lab_record(
            "2026-09-25-alpha", stage="blocked", blocked_reason="Waiting on a platform fix."))
        self.make_lab("2026-09-24-beta", lab_record("2026-09-24-beta", stage="blocked"))
        self.assertEqual(self.errors(), [])
        self.assertTrue(any("blocked_reason is empty" in w for w in self.warnings()))
        self.assertFalse(any("unknown keys" in w for w in self.warnings()))

    def test_stage_must_be_known(self) -> None:
        self.make_lab("2026-09-25-alpha", lab_record("2026-09-25-alpha", stage="running"))
        self.assertTrue(any("stage 'running'" in e for e in self.errors()))

    def test_dates_must_be_iso_and_ordered(self) -> None:
        self.make_lab("2026-09-25-alpha", lab_record("2026-09-25-alpha", updated="25 Sep"))
        self.make_lab("2026-09-24-beta", lab_record("2026-09-24-beta", updated="2026-09-01"))
        errors = self.errors()
        self.assertTrue(any("updated must be an ISO date" in e for e in errors))
        self.assertTrue(any("earlier than created" in e for e in errors))

    def test_retired_file_pointer_keys_warn(self) -> None:
        self.make_lab("2026-09-25-alpha", lab_record("2026-09-25-alpha", report="report.md", plan=None, readme="README.md"))
        self.assertEqual(self.errors(), [])
        warnings = self.warnings()
        self.assertTrue(any("retired keys report, plan, readme" in w for w in warnings))
        self.assertFalse(any("unknown keys" in w for w in warnings))

    def test_complete_requires_a_report(self) -> None:
        self.make_lab("2026-09-25-alpha", lab_record("2026-09-25-alpha", stage="complete"), files=("PLAN.md",))
        self.assertIn("2026-09-25-alpha: stage is complete but the lab has no REPORT.md", self.errors())

    def test_legacy_report_name_counts_as_the_report(self) -> None:
        self.make_lab("2026-09-25-alpha", lab_record("2026-09-25-alpha", stage="complete"), files=("PLAN.md", "report.md"))
        self.assertEqual(self.errors(), ["2026-09-25-alpha: report.md should be named REPORT.md"])
        self.assertEqual(self.warnings(), [])

    def test_layout_findings_are_errors(self) -> None:
        lab = self.make_lab("2026-09-25-alpha", files=("README.md", "REPORT.md", "run.py", "notes.txt"))
        for name in ("results", "docs", "__pycache__"):
            (lab / name).mkdir()
        (lab / ".gitignore").write_text("/data/\n", encoding="utf-8")
        records, findings = MODULE.validate_all(self.root)
        self.assertIn("2026-09-25-alpha", records)
        self.assertEqual({f.level for f in findings}, {"error"})
        self.assertEqual({f.kind for f in findings}, {"layout"})
        self.assertEqual(
            [f.message for f in findings],
            [
                "PLAN.md is missing",
                "README.md is retired: move its content to notes/ (lab_layout.py tidy)",
                "2 file(s) in the lab root outside the layout: notes.txt, run.py",
                "1 directory(ies) outside the layout: docs/",
            ],
        )

    def test_files_in_the_wrong_directory_are_errors(self) -> None:
        lab = self.make_lab("2026-09-25-alpha")
        tracked = {
            "results/curve.png", "results/sub/notes.md", "results/run.log", "results/arr.npz",
            "results/ok.json", "notes/generate.py", "scripts/scratch.py.tmp", "figures/plot_data.json",
            "notes/theory/paper.tex", "notes/theory/compile.sh", "notes/theory/fontconfig/fonts.conf",
            "scripts/old_sub/output.png", "checkpoints/model/sha256", "figures/ok.png",
        }
        _, findings = MODULE.validate_lab(lab, tracked=tracked)
        messages = sorted(f.message for f in findings)
        self.assertEqual(messages, sorted([
            "1 misplaced: results/ holds figure files: results/curve.png -> figures/curve.png (lab_layout.py tidy)",
            "1 misplaced: results/ holds document files: results/sub/notes.md -> notes/sub/notes.md (lab_layout.py tidy)",
            "1 misplaced: results/ holds log files: results/run.log -> logs/run.log (lab_layout.py tidy)",
            "1 misplaced: results/ holds array data files: results/arr.npz -> data/arr.npz (lab_layout.py tidy)",
            "1 misplaced: notes/ holds code files: notes/generate.py -> scripts/generate.py (lab_layout.py tidy)",
            "1 misplaced: figures/ holds output files: figures/plot_data.json -> results/plot_data.json (lab_layout.py tidy)",
            "1 misplaced: no place in the layout for a .tmp file under scripts/: scripts/scratch.py.tmp (lab_layout.py tidy)",
        ]))

    def test_large_tracked_outputs_warn(self) -> None:
        lab = self.make_lab("2026-09-25-alpha")
        (lab / "results").mkdir()
        (lab / "results" / "big.json").write_bytes(b"0" * (MODULE.MAX_TRACKED_BYTES + 1))
        (lab / "results" / "small.json").write_bytes(b"{}")
        _, findings = MODULE.validate_lab(lab, tracked={"results/big.json", "results/small.json"})
        self.assertEqual(
            [f.message for f in findings],
            ["results/big.json is 1.0 MB; tracked outputs stay under 1 MB (move it to data/)"],
        )

    @unittest.skipUnless(shutil.which("git"), "git is not installed")
    def test_tracked_files_follow_the_gitignore_files(self) -> None:
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        (self.root / ".gitignore").write_text("labs/**/results/\nlabs/**/*.npz\n", encoding="utf-8")
        new = self.make_lab("2026-09-25-new")
        old = self.make_lab("2026-09-24-old")
        (new / ".gitignore").write_text("!/results/\n", encoding="utf-8")
        for lab in (new, old):
            (lab / "results").mkdir()
            (lab / "results" / "a.json").write_text("{}", encoding="utf-8")
            (lab / "results" / "b.npz").write_bytes(b"x")
        docs = {"PLAN.md", "REPORT.md", "lab.json"}
        self.assertEqual(MODULE.tracked_files(self.root),
                         {"2026-09-25-new": docs | {".gitignore", "results/a.json"}, "2026-09-24-old": docs})
        self.assertEqual(MODULE.tracked_files(self.root, ["2026-09-24-old"]), {"2026-09-24-old": docs})

    def test_tracked_files_without_git_is_none(self) -> None:
        self.assertIsNone(MODULE.tracked_files(self.root / "labs" / "missing"))

    def test_references_and_threads_are_checked_when_registries_exist(self) -> None:
        (self.root / "references" / "astra").mkdir(parents=True)
        (self.root / "references" / "references.json").write_text(
            json.dumps({"references": [{"id": "astra", "aliases": ["astra-gnn-bp-decoder"]}]}), encoding="utf-8"
        )
        (self.root / ".auto-research").mkdir(exist_ok=True)
        (self.root / ".auto-research" / "state.json").write_text(
            json.dumps({"threads": [{"id": "thread-001"}]}), encoding="utf-8"
        )
        self.make_lab(
            "2026-09-25-alpha",
            lab_record(
                "2026-09-25-alpha",
                references=["astra", "astra-gnn-bp-decoder", "nope"],
                discussion=["thread-001", "thread-999", "t1"],
            ),
        )
        errors = self.errors()
        self.assertIn("2026-09-25-alpha: unknown reference id: nope", errors)
        self.assertIn("2026-09-25-alpha: discussion entry is not a thread id: 't1'", errors)
        self.assertEqual(len(errors), 2)
        self.assertIn(
            "2026-09-25-alpha: discussion thread thread-999 is not in this checkout's threads store",
            self.warnings(),
        )

    def test_registries_are_optional(self) -> None:
        self.make_lab("2026-09-25-alpha", lab_record("2026-09-25-alpha", references=["x"], discussion=["thread-7"]))
        self.assertEqual(self.errors(), [])

    def test_helper_and_non_lab_directories(self) -> None:
        (self.root / "labs" / "_tools").mkdir()
        (self.root / "labs" / "scratch").mkdir()
        (self.root / "labs" / "README.md").write_text("# Labs\n", encoding="utf-8")
        self.make_lab("2026-09-25-alpha")
        _, findings = MODULE.validate_all(self.root)
        self.assertEqual([(f.level, f.lab) for f in findings], [("warning", "scratch")])

    def test_unknown_keys_warn_only(self) -> None:
        self.make_lab("2026-09-25-alpha", lab_record("2026-09-25-alpha", tags=["x"]))
        records, findings = MODULE.validate_all(self.root)
        self.assertIn("2026-09-25-alpha", records)
        self.assertEqual([f.level for f in findings], ["warning"])

    def test_validate_named_labs_only(self) -> None:
        self.make_lab("2026-09-25-alpha")
        (self.root / "labs" / "2026-09-24-broken").mkdir()
        self.assertEqual(self.errors(["2026-09-25-alpha"]), [])
        self.assertEqual(self.errors(["2026-09-20-missing"]), ["2026-09-20-missing: no such lab directory"])

    def test_validate_cli_exit_codes_and_json(self) -> None:
        self.make_lab("2026-09-25-alpha")
        code, out = self.run_cli("validate", "--json")
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(out)["ok"])
        (self.root / "labs" / "2026-09-24-broken").mkdir()
        code, _ = self.run_cli("validate")
        self.assertEqual(code, 1)

    def test_missing_labs_directory_is_a_usage_error(self) -> None:
        (self.root / "labs").rmdir()
        with redirect_stderr(io.StringIO()):
            code, _ = self.run_cli("validate")
        self.assertEqual(code, 2)


class RebuildTests(CatalogTestCase):
    def catalog(self) -> dict:
        return json.loads((self.root / "labs" / "labs.json").read_text(encoding="utf-8"))

    def test_rebuild_sorts_newest_first_with_catalog_fields(self) -> None:
        self.make_lab("2026-09-20-older", lab_record("2026-09-20-older", updated="2026-09-26"))
        self.make_lab("2026-09-25-newest-b")
        self.make_lab("2026-09-25-newest-a")
        code, _ = self.run_cli("rebuild")
        self.assertEqual(code, 0)
        labs = self.catalog()["labs"]
        self.assertEqual([lab["id"] for lab in labs], ["2026-09-25-newest-b", "2026-09-25-newest-a", "2026-09-20-older"])
        self.assertEqual(list(labs[0]), list(MODULE.CATALOG_KEYS))

    def test_rebuild_refuses_invalid_labs_without_force(self) -> None:
        self.make_lab("2026-09-25-alpha")
        (self.root / "labs" / "2026-09-24-broken").mkdir()
        code, out = self.run_cli("rebuild")
        self.assertEqual(code, 1)
        self.assertIn("not written", out)
        self.assertFalse((self.root / "labs" / "labs.json").exists())
        code, _ = self.run_cli("rebuild", "--force")
        self.assertEqual(code, 1)
        self.assertEqual([lab["id"] for lab in self.catalog()["labs"]], ["2026-09-25-alpha"])

    def test_check_detects_a_stale_catalog(self) -> None:
        self.make_lab("2026-09-25-alpha")
        self.assertEqual(self.run_cli("check")[0], 1)
        self.run_cli("rebuild")
        self.assertEqual(self.run_cli("check")[0], 0)
        lab_json = self.root / "labs" / "2026-09-25-alpha" / "lab.json"
        lab_json.write_text(json.dumps(lab_record("2026-09-25-alpha", stage="inactive")), encoding="utf-8")
        self.assertEqual(self.run_cli("check")[0], 1)

    def test_rebuild_output_is_stable(self) -> None:
        self.make_lab("2026-09-25-alpha", lab_record("2026-09-25-alpha", title="Kurzfassung \u00e4"))
        self.run_cli("rebuild")
        first = (self.root / "labs" / "labs.json").read_bytes()
        self.run_cli("rebuild")
        self.assertEqual(first, (self.root / "labs" / "labs.json").read_bytes())
        self.assertIn("\u00e4".encode(), first)
        self.assertTrue(first.endswith(b"\n"))


if __name__ == "__main__":
    unittest.main()
