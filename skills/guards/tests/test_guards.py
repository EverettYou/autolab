"""Tests for rules_lint.py, reproduce_lint.sh, and gc_attempts.sh on temporary repositories.

Run: python3 -m unittest discover -s skills/guards/tests
"""
from __future__ import annotations

import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _fs_case_sensitive() -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "aBcDeFgH").write_text("x", encoding="utf-8")
        return not (root / "abcdefgh").exists()


_CASE_SENSITIVE = _fs_case_sensitive()


def load_rules_lint():
    spec = importlib.util.spec_from_file_location("rules_lint", SCRIPTS / "rules_lint.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


SKILL = "---\nname: {name}\ndescription: Does {name} things.\nusage: Use when working on {name}.\n---\n\n# {name}\n\nSteps.\n"


class RulesLintTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.lint = load_rules_lint()
        write(self.root / "skills" / "alpha" / "SKILL.md", SKILL.format(name="alpha"))
        write(self.root / "skills" / "README.md", "| [alpha](alpha/SKILL.md) | x | `SKILL.md` |\n")

    def tearDown(self):
        self.tmp.cleanup()

    def run_lint(self):
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(io.StringIO()):
            code = self.lint.main(["--root", str(self.root)])
        return code, out.getvalue()

    def test_clean_tree_passes(self):
        code, out = self.run_lint()
        self.assertEqual(code, 0, out)

    def test_tool_specific_and_retired_paths_fail(self):
        write(self.root / "skills" / "alpha" / "notes.md", "Run `/auto` then read TODO.md and sandbox/x.\n$CLAUDE_PROJECT_DIR\n")
        code, out = self.run_lint()
        self.assertEqual(code, 1)
        for rule in ("slash-command", "retired-path", "tool-specific"):
            self.assertIn(rule, out)

    def test_untracked_tool_local_config_is_allowed(self):
        write(self.root / ".claude" / "settings.local.json", "{}\n")
        code, out = self.run_lint()
        self.assertEqual(code, 0, out)
        self.assertNotIn("retired-path", out)

    def test_tracked_tool_local_files_warn(self):
        write(self.root / ".claude" / "commands" / "x.md", "x\n")
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        subprocess.run(["git", "-C", str(self.root), "add", "-f", ".claude/commands/x.md"], check=True)
        code, out = self.run_lint()
        self.assertEqual(code, 0, out)
        self.assertIn("retired-path", out)

    def test_legacy_paths_line_is_allowed(self):
        write(self.root / "skills" / "alpha" / "schema.md", '"legacy_paths": ["inbox/papers/x"]\n')
        code, out = self.run_lint()
        self.assertEqual(code, 0, out)

    def test_frontmatter_and_catalog(self):
        write(self.root / "skills" / "beta" / "SKILL.md", SKILL.format(name="gamma"))
        code, out = self.run_lint()
        self.assertEqual(code, 1)
        self.assertIn("differs from the directory", out)
        self.assertIn("skill 'beta' is not listed", out)

    def test_missing_script_and_broken_link(self):
        write(self.root / "skills" / "alpha" / "SKILL.md",
              SKILL.format(name="alpha") + "Run `bash skills/alpha/scripts/gone.sh` and see [x](references/none.md).\n")
        code, out = self.run_lint()
        self.assertEqual(code, 1)
        self.assertIn("missing-script", out)
        self.assertIn("broken-link", out)

    def test_lint_scripts_may_name_retired_things(self):
        write(self.root / "skills" / "alpha" / "scripts" / "fs_lint.py",
              'RETIRED = {"STEERING.md": "threads", "TODO.md": "tasks"}\nTOOL_LOCAL = (".claude",)\n'
              'ROOT_FILES = ("README.md", "CLAUDE.md")\nPHRASES = ("stop and report",)\n')
        code, out = self.run_lint()
        self.assertEqual(code, 0, out)
        write(self.root / "skills" / "alpha" / "scripts" / "fs_lint.py", 'ROOT = "$CLAUDE_PROJECT_DIR"\n')
        code, out = self.run_lint()
        self.assertEqual(code, 1)
        self.assertIn("tool-specific", out)

    def test_allow_marker_skips_line(self):
        write(self.root / "skills" / "alpha" / "history.md",
              "The old queue lived in TODO.md.  <!-- rules-lint: allow -->\n")
        code, out = self.run_lint()
        self.assertEqual(code, 0, out)

    def test_emoji_fails(self):
        write(self.root / "skills" / "alpha" / "extra.md", "Done \u2705\n")
        code, out = self.run_lint()
        self.assertEqual(code, 1)
        self.assertIn("emoji", out)


class ShellGuardTest(unittest.TestCase):
    """Copies the shell guards into a temporary repository so they resolve it as the root."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        scripts = self.root / "skills" / "guards" / "scripts"
        scripts.mkdir(parents=True)
        for name in ("reproduce_lint.sh", "gc_attempts.sh"):
            shutil.copy(SCRIPTS / name, scripts / name)

    def tearDown(self):
        self.tmp.cleanup()

    def run_script(self, name, *args):
        return subprocess.run(
            ["bash", str(self.root / "skills" / "guards" / "scripts" / name), *args],
            capture_output=True, text=True, timeout=120,
        )

    def record(self, ref_id, result, files=("run.sh",)):
        rec = self.root / "references" / ref_id / "reproduce"
        write(rec / "RESULT.json", json.dumps(result))
        for name in files:
            write(rec / name, "#!/usr/bin/env bash\n")
        return rec

    def test_reproduce_lint_recipe_tier(self):
        self.record("good", {"slug": "good"})
        proc = self.run_script("reproduce_lint.sh")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.record("thin", {"slug": "thin"}, files=())
        proc = self.run_script("reproduce_lint.sh")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("thin: RESULT.json only", proc.stdout)

    @unittest.skipUnless(
        _CASE_SENSITIVE,
        "needs a case-sensitive filesystem (result.json vs RESULT.json)",
    )
    def test_reproduce_lint_lowercase_result(self):
        rec = self.root / "references" / "low" / "reproduce"
        write(rec / "result.json", "{}")
        write(rec / "run.sh", "")
        proc = self.run_script("reproduce_lint.sh")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("lowercase result.json", proc.stdout)

    def test_reproduce_lint_attempt_cite(self):
        cite = "references/r/attempts/a1/driver.py"
        self.record("r", {"slug": "r", "run": cite})
        proc = self.run_script("reproduce_lint.sh")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("DANGLING-GONE(FAIL)", proc.stdout)
        self.record("r", {"slug": "r", "run": cite, "missing_artifacts": [cite]})
        proc = self.run_script("reproduce_lint.sh")
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.record("r", {"slug": "r", "run": cite}, files=("run.sh", "driver.py"))
        proc = self.run_script("reproduce_lint.sh")
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertIn("DANGLING-RENAMED", proc.stdout)

    def attempt(self, ref_id, slug, *, age_days=30, extra=None):
        base = self.root / "references" / ref_id / "attempts" / slug
        paths = [write(base / "run.py", "print(1)\n")]
        for rel in extra or ():
            paths.append(write(base / rel, "x"))
        old = time.time() - age_days * 86400
        for path in paths:
            os.utime(path, (old, old))
        return base

    def test_gc_attempts_verdicts_and_reclaim(self):
        self.record("r", {"attempt": "r-main"})
        write(self.root / "references" / "r" / "provenance.json",
              json.dumps({"id": "r", "dispositions": {"r-old": {"decision": "superseded", "note": "replaced"}}}))
        captured = self.attempt("r", "r-main")
        orphan = self.attempt("r", "r-side")
        dispositioned = self.attempt("r", "r-old")
        guarded = self.attempt("r", "r-ckpt", extra=("checkpoints/last.pt",))
        live = self.attempt("r", "r-live", age_days=0)
        ledger = self.root / "wiki" / "implementations" / "attempt-dispositions.md"
        write(ledger, "| slug | verdict | reason |\n|---|---|---|\n| `r-ledger` | dead-end | recorded elsewhere |\n")
        ledgered = self.attempt("r", "r-ledger")

        proc = self.run_script("gc_attempts.sh")
        out = proc.stdout
        self.assertEqual(proc.returncode, 0, out + proc.stderr)
        self.assertRegex(out, r"RECLAIMABLE\s+r/r-main")
        self.assertRegex(out, r"ORPHANED\s+r/r-side")
        self.assertRegex(out, r"DISPOSITIONED r/r-old .*superseded")
        self.assertRegex(out, r"DISPOSITIONED r/r-ledger .*dead-end")
        self.assertRegex(out, r"PROTECTED\s+r/r-ckpt")
        self.assertRegex(out, r"PROTECTED\s+r/r-live")
        self.assertTrue(captured.exists(), "dry run must not delete")

        proc = self.run_script("gc_attempts.sh", "--reclaim")
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertFalse(captured.exists())
        for kept in (orphan, dispositioned, guarded, live, ledgered):
            self.assertTrue(kept.exists(), kept.name)

    def test_gc_attempts_protects_newer_sources(self):
        self.record("r", {"slug": "r"})
        result = self.root / "references" / "r" / "reproduce" / "RESULT.json"
        old = time.time() - 40 * 86400
        os.utime(result, (old, old))
        self.attempt("r", "r", age_days=1)
        proc = self.run_script("gc_attempts.sh", "--reclaim")
        self.assertRegex(proc.stdout, r"PROTECTED\s+r/r .*newer")
        self.assertTrue((self.root / "references" / "r" / "attempts" / "r").exists())

    def test_gc_attempts_ambiguous_extension_is_not_captured(self):
        self.record("r", {"slug": "r"})
        self.attempt("r", "r-one")
        self.attempt("r", "r-two")
        proc = self.run_script("gc_attempts.sh")
        self.assertNotIn("RECLAIMABLE", proc.stdout)
        self.assertIn("0 reclaimable", proc.stdout)


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True,
                   env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})


def init_repo(root: Path) -> None:
    git(root, "init", "-q")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "init", "--allow-empty")


class CitedResultsLintTest(unittest.TestCase):
    """cited_results_lint.py on a temporary repository (full census and --changed)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.lab = self.root / "labs" / "2026-01-01-demo"
        write(self.lab / "results" / "kept.json", "{}")
        write(self.lab / "scripts" / "make.py", "OUT = 'results/regenerable_output.json'\n")
        write(self.lab / "REPORT.md", "See results/kept.json and results/regenerable_output.json.\n"
                                      "```\nresults/in_a_fence.json\n```\n"
                                      "Run with --out results/future.json.\n")
        init_repo(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def run_lint(self, *args):
        return subprocess.run([sys.executable, str(SCRIPTS / "cited_results_lint.py"), "--root", str(self.root), *args],
                              capture_output=True, text=True, timeout=120)

    def test_resolved_missing_and_excluded_citations_pass(self):
        proc = self.run_lint()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("doc_rel 1", proc.stdout)
        self.assertIn("not checked (results are gitignored by design): 1", proc.stdout)
        self.assertNotIn("in_a_fence", proc.stdout)
        self.assertNotIn("future.json", proc.stdout)

    def test_missing_result_is_counted_and_never_fails(self):
        write(self.root / "wiki" / "page.md", "Cites results/gone_forever.json.\n")
        proc = self.run_lint()
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertIn("not checked (results are gitignored by design): 2", proc.stdout)
        self.assertNotIn("FAIL", proc.stdout)

    def test_changed_checks_only_added_lines(self):
        bad = "deadbeef:labs/2026-01-01-demo/results/{}.json"
        write(self.root / "wiki" / "old.md", f"Pins {bad.format('old_pin')}.\n")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "old")
        self.assertEqual(self.run_lint().returncode, 1)
        proc = self.run_lint("--changed")
        self.assertEqual(proc.returncode, 0, proc.stdout)
        with open(self.root / "wiki" / "old.md", "a") as fh:
            fh.write(f"And {bad.format('new_pin')}.\n")
        proc = self.run_lint("--changed")
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("new_pin", proc.stdout)
        self.assertNotIn("old_pin", proc.stdout)

    def test_pinned_citation_resolves_through_git_history(self):
        path = "labs/2026-01-01-demo/results/deleted_later.json"
        write(self.root / path, "{}")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "add")
        sha = subprocess.run(["git", "-C", str(self.root), "rev-parse", "--short", "HEAD"],
                             capture_output=True, text=True, check=True).stdout.strip()
        (self.root / path).unlink()
        write(self.root / "wiki" / "page.md", f"Removed on purpose; it stays at {sha}:{path}.\n"
                                               f"A wrong pin: {sha}:labs/2026-01-01-demo/results/never.json.\n")
        proc = self.run_lint()
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("pinned to a commit: 1 of 2 found", proc.stdout)
        self.assertIn(f"FAIL {sha}:labs/2026-01-01-demo/results/never.json", proc.stdout)
        self.assertNotIn("deleted_later", proc.stdout.split("FAIL", 1)[-1])

    def test_lost_marker_counts_without_failing(self):
        write(self.root / "wiki" / "page.md", "Never saved: results/gone_forever.json <!-- lost-citation -->\n")
        proc = self.run_lint()
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertIn("marked lost: 1", proc.stdout)

    def test_lost_marker_does_not_hide_a_live_path_on_the_same_line(self):
        write(self.root / "labs" / "2026-01-01-demo" / "NOTE.md",
              "Kept results/kept.json; results/gone_forever.json was not saved. <!-- lost-citation -->\n")
        proc = self.run_lint("--json", str(self.root / "out.json"))
        report = json.loads((self.root / "out.json").read_text())
        self.assertEqual(report["lost"], ["results/gone_forever.json"], proc.stdout)
        self.assertEqual(report["counts"]["doc_rel"], 1, proc.stdout)

    def test_thread_entries_resolve_against_their_labs(self):
        threads = {"threads": [{"id": "thread-1", "related_labs": ["labs/2026-01-01-demo"],
                                "messages": [{"text": "output results/kept.json"}]},
                               {"id": "thread-2", "messages": [{"text": "see results/kept.json"}]}]}
        write(self.root / ".auto-research" / "state.json", json.dumps(threads))
        proc = self.run_lint("--json", str(self.root / "out.json"))
        report = json.loads((self.root / "out.json").read_text())
        self.assertEqual(report["counts"]["doc_rel"], 1, proc.stdout)


if __name__ == "__main__":
    unittest.main()


def test_cited_results_regex_keeps_jsonl_paths_whole():
    """A cited results/x.jsonl was read as results/x.json and reported missing (2026-10-09)."""
    spec = importlib.util.spec_from_file_location("cited_results_lint", SCRIPTS / "cited_results_lint.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    text = "see `results/e2_telescope_s3.jsonl` and results/table.json, not results/tablejson"
    assert mod.CITE.findall(text) == ["results/e2_telescope_s3.jsonl", "results/table.json"]
