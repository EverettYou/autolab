from __future__ import annotations

import importlib.util
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location("lab_report_lint", SCRIPTS / "lab_report_lint.py")
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

LAB_ID = "2026-09-25-alpha"

PLAN = """# Plan

## Question
Does A beat B on BB144?

## Success criterion
Disjoint 95% intervals at p = 0.003.
"""

REPORT = """# Alpha

## Question
Does A beat B? See [the plan](PLAN.md).

## Setting
BB144, circuit-level depolarizing, p = 0.003, 4096 shots, seed 1.

    .venv/bin/python labs/2026-09-25-alpha/scripts/run.py --p 0.003

## Results
| decoder | LER |
|---|---|
| A | 1e-3 |

Data: [results/summary.json](results/summary.json).

![LER curve](figures/ler.png)
*LER versus p from results/summary.json.*

## Interpretation
A converges more often.

## Verdict
Supported at p = 0.003.

## Next steps
None.
"""


class ReportLintTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.lab = self.root / "labs" / LAB_ID
        (self.lab / "results").mkdir(parents=True)
        (self.lab / "figures").mkdir()
        (self.lab / "results" / "summary.json").write_text("{}", encoding="utf-8")
        (self.lab / "figures" / "ler.png").write_bytes(b"png")
        (self.lab / "PLAN.md").write_text(PLAN, encoding="utf-8")
        (self.lab / "REPORT.md").write_text(REPORT, encoding="utf-8")
        record = {
            "id": LAB_ID, "title": "Alpha", "stage": "active", "summary": "One sentence.",
            "current_focus": "Writing up.", "next_action": "Finalize.", "created": "2026-09-25",
            "updated": "2026-09-25", "references": [], "discussion": [], "parents": [],
        }
        (self.lab / "lab.json").write_text(json.dumps(record), encoding="utf-8")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def lint(self) -> dict:
        return MODULE.lint_lab(self.lab, self.root)

    def rewrite(self, old: str, new: str, name: str = "REPORT.md") -> None:
        path = self.lab / name
        text = path.read_text(encoding="utf-8")
        self.assertIn(old, text)
        path.write_text(text.replace(old, new), encoding="utf-8")

    def test_conforming_lab_passes(self) -> None:
        result = self.lint()
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["warnings"], [])
        self.assertTrue(result["ok"])
        self.assertTrue(any("stage is active" in n for n in result["notes"]))

    def test_missing_section(self) -> None:
        self.rewrite("## Interpretation\nA converges more often.\n\n", "")
        self.assertIn("REPORT.md is missing the '## Interpretation' section", self.lint()["errors"])

    def test_sections_out_of_order(self) -> None:
        self.rewrite("## Verdict\nSupported at p = 0.003.\n\n", "")
        self.rewrite("## Question\n", "## Verdict\nSupported.\n\n## Question\n")
        self.assertTrue(any("out of order" in e for e in self.lint()["errors"]))

    def test_heading_prefix_matches(self) -> None:
        self.rewrite("## Next steps", "## Next steps (planned)")
        self.assertTrue(self.lint()["ok"])

    def test_broken_and_absolute_links(self) -> None:
        self.rewrite("None.", "See [gone](results/gone.json) and [abs](/etc/passwd).")
        errors = self.lint()["errors"]
        self.assertTrue(any("broken link target results/gone.json" in e for e in errors))
        self.assertTrue(any("absolute link target /etc/passwd" in e for e in errors))

    def test_links_in_code_fences_are_ignored(self) -> None:
        self.rewrite("None.", "None.\n\n```\n[x](missing.json)\n## Question\n```\n")
        self.assertTrue(self.lint()["ok"])

    def test_results_must_cite_an_artifact(self) -> None:
        self.rewrite("Data: [results/summary.json](results/summary.json).", "Data: see above.")
        self.rewrite("*LER versus p from results/summary.json.*", "*LER versus p.*")
        self.assertTrue(any("machine-readable artifact" in e for e in self.lint()["errors"]))

    def test_inline_code_artifact_counts(self) -> None:
        self.rewrite("Data: [results/summary.json](results/summary.json).", "Data: `results/fixed_*.json`.")
        self.assertTrue(self.lint()["ok"])

    def test_empty_verdict(self) -> None:
        self.rewrite("Supported at p = 0.003.", "<!-- later -->")
        self.assertIn("REPORT.md: Verdict section is empty", self.lint()["errors"])

    def test_template_marker(self) -> None:
        self.rewrite("None.", "<!-- fill: follow-ups -->")
        line = REPORT.splitlines().index("None.") + 1
        self.assertIn(f"REPORT.md:{line}: unfilled template marker", self.lint()["errors"])

    def test_plan_needs_success_criterion(self) -> None:
        self.rewrite("## Success criterion", "## Criteria", name="PLAN.md")
        self.assertIn("PLAN.md has no 'Success criterion' heading", self.lint()["errors"])

    def test_missing_report(self) -> None:
        (self.lab / "REPORT.md").unlink()
        result = self.lint()
        self.assertFalse(result["ok"])
        self.assertIn("REPORT.md is missing", result["errors"])

    def test_legacy_report_name_is_a_layout_error(self) -> None:
        (self.lab / "REPORT.md").rename(self.lab / "report.md")
        result = self.lint()
        self.assertFalse(result["ok"])
        self.assertIn("layout: report.md should be named REPORT.md", result["errors"])
        self.rewrite("Supported at p = 0.003.", "", name="report.md")
        self.assertIn("report.md: Verdict section is empty", self.lint()["errors"])

    def test_setting_without_a_scripts_command_warns(self) -> None:
        self.rewrite("    .venv/bin/python labs/2026-09-25-alpha/scripts/run.py --p 0.003\n", "")
        result = self.lint()
        self.assertTrue(result["ok"])
        self.assertTrue(any("Setting names no scripts/ command" in w for w in result["warnings"]))

    def test_plan_links_are_errors_and_notes_links_are_warnings(self) -> None:
        (self.lab / "notes").mkdir()
        (self.lab / "notes" / "audit.md").write_text("[ok](../PLAN.md) and [gone](missing.md)\n", encoding="utf-8")
        self.rewrite("Does A beat B on BB144?", "Does A beat B on BB144? See [old](notes/gone.md).", name="PLAN.md")
        result = self.lint()
        self.assertIn("PLAN.md:4: broken link target notes/gone.md", result["errors"])
        self.assertIn("notes/audit.md:1: broken link target missing.md", result["warnings"])

    def test_layout_findings_are_errors(self) -> None:
        (self.lab / "run.py").write_text("print(1)\n", encoding="utf-8")
        result = self.lint()
        self.assertFalse(result["ok"])
        self.assertEqual(result["errors"], ["layout: 1 file(s) in the lab root outside the layout: run.py"])

    def test_uncaptioned_figure_and_line_budget_warn(self) -> None:
        self.rewrite("*LER versus p from results/summary.json.*\n", "")
        result = MODULE.lint_lab(self.lab, self.root, max_lines=10)
        self.assertTrue(result["ok"])
        self.assertTrue(any("no italic caption" in w for w in result["warnings"]))
        self.assertTrue(any("budget 10" in w for w in result["warnings"]))

    def test_cli_resolves_lab_id(self) -> None:
        with redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()):
            self.assertEqual(MODULE.main([LAB_ID, "--root", str(self.root), "--json"]), 0)
            self.assertEqual(MODULE.main(["2026-01-01-none", "--root", str(self.root)]), 2)
        self.assertTrue(json.loads(out.getvalue())["ok"])


if __name__ == "__main__":
    unittest.main()
