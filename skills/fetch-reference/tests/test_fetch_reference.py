from __future__ import annotations

import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import arxiv_http  # noqa: E402
import fetch_reference  # noqa: E402
import references_registry as reg  # noqa: E402

try:
    from pypdf import PdfWriter
except ImportError:  # pragma: no cover - depends on the interpreter
    PdfWriter = None

HAS_GIT = shutil.which("git") is not None


def make_pdf(path: Path, pages: int = 1) -> Path:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=200, height=200)
    with path.open("wb") as handle:
        writer.write(handle)
    return path


@unittest.skipIf(PdfWriter is None, "pypdf is not installed")
class FetchReferenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "repo"
        (self.root / "references").mkdir(parents=True)
        self.src = Path(self._tmp.name) / "src"
        self.src.mkdir()
        self._rate = arxiv_http.RATE_LIMIT_SEC
        arxiv_http.RATE_LIMIT_SEC = 0.0

    def tearDown(self) -> None:
        arxiv_http.RATE_LIMIT_SEC = self._rate
        self._tmp.cleanup()

    def run_cli(self, *args: str) -> tuple[int, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = fetch_reference.main(["--root", str(self.root), *args])
        return code, out.getvalue() + err.getvalue()

    def prov(self, ref_id: str) -> dict:
        return json.loads((self.root / "references" / ref_id / "provenance.json").read_text(encoding="utf-8"))

    def registry(self) -> dict:
        return json.loads((self.root / "references" / "references.json").read_text(encoding="utf-8"))

    def test_local_pdf_is_archived_and_registered(self) -> None:
        pdf = make_pdf(self.src / "a.pdf", pages=2)
        code, out = self.run_cli("paper", "--id", "demo-paper", "--pdf", str(pdf), "--title", "Demo", "--alias", "old-slug", "--note", "why")
        self.assertEqual(code, 0, out)
        prov = self.prov("demo-paper")
        self.assertEqual(prov["kind"], "paper")
        self.assertEqual(prov["status"], "fetched")
        self.assertEqual(prov["pages"], 2)
        self.assertEqual(prov["pdf"], "paper.pdf")
        self.assertEqual(prov["pdf_sha256"], reg.sha256_file(pdf))
        self.assertEqual(prov["metadata_source"], "local")
        self.assertEqual(prov["aliases"], ["old-slug"])
        self.assertEqual(prov["note"], "why")
        entry = self.registry()["references"][0]
        self.assertEqual(entry["id"], "demo-paper")
        self.assertTrue(entry["has_pdf"])
        self.assertEqual(entry["provenance"], "references/demo-paper/provenance.json")
        self.assertEqual(reg.validate(self.root, local=True), ([], []))
        self.assertEqual(reg.resolve(self.root, "old-slug"), ["demo-paper"])

    def test_archived_copy_is_never_silently_replaced(self) -> None:
        first = make_pdf(self.src / "a.pdf", pages=1)
        second = make_pdf(self.src / "b.pdf", pages=3)
        self.assertEqual(self.run_cli("paper", "--id", "p", "--pdf", str(first), "--title", "P")[0], 0)
        self.assertEqual(self.run_cli("paper", "--id", "p", "--pdf", str(first))[0], 0)
        code, out = self.run_cli("paper", "--id", "p", "--pdf", str(second))
        self.assertEqual(code, 4, out)
        self.assertEqual(self.prov("p")["pages"], 1)
        self.assertEqual(self.run_cli("paper", "--id", "p", "--pdf", str(second), "--force")[0], 0)
        self.assertEqual(self.prov("p")["pages"], 3)

    def test_unrecorded_existing_file_needs_adopt_or_force(self) -> None:
        ref = self.root / "references" / "hand"
        ref.mkdir()
        make_pdf(ref / "paper.pdf")
        self.assertEqual(self.run_cli("paper", "--id", "hand", "--pdf", str(make_pdf(self.src / "x.pdf")), "--title", "H")[0], 4)
        code, out = self.run_cli("paper", "--id", "hand", "--adopt", "--title", "Hand placed")
        self.assertEqual(code, 0, out)
        prov = self.prov("hand")
        self.assertEqual(prov["fetch_status"], "pdf:ok:adopted")
        self.assertEqual(prov["pdf_sha256"], reg.sha256_file(ref / "paper.pdf"))

    def test_invalid_pdf_leaves_nothing_behind(self) -> None:
        bad = self.src / "bad.pdf"
        bad.write_bytes(b"<html>not a pdf</html>")
        code, _ = self.run_cli("paper", "--id", "bad", "--pdf", str(bad), "--title", "Bad")
        self.assertEqual(code, 2)
        ref = self.root / "references" / "bad"
        self.assertFalse((ref / "paper.pdf").exists())
        self.assertFalse((ref / "paper.pdf.part").exists())
        self.assertFalse((ref / "provenance.json").exists())

    def test_status_and_checksum_verified_refetch(self) -> None:
        pdf = make_pdf(self.src / "a.pdf")
        self.run_cli("paper", "--id", "p", "--url", pdf.as_uri(), "--title", "P")
        prov = self.prov("p")
        self.assertEqual(prov["pdf_url"], pdf.as_uri())
        self.assertEqual(prov["metadata_source"], "url")
        self.assertEqual(self.run_cli("status", "p")[0], 0)

        local = self.root / "references" / "p" / "paper.pdf"
        local.unlink()
        self.assertEqual(self.run_cli("status", "p")[0], 1)
        code, out = self.run_cli("refetch", "p")
        self.assertEqual(code, 0, out)
        self.assertIn("restored", out)

        local.unlink()
        make_pdf(pdf, pages=4)  # upstream changed
        code, out = self.run_cli("refetch", "p")
        self.assertEqual(code, 2, out)
        self.assertFalse(local.exists())

        make_pdf(local, pages=5)  # a different local file
        self.assertEqual(self.run_cli("status", "p")[0], 2)
        self.assertEqual(self.run_cli("refetch", "p")[0], 2)

    def test_names_must_be_unique(self) -> None:
        pdf = make_pdf(self.src / "a.pdf")
        self.run_cli("paper", "--id", "first", "--pdf", str(pdf), "--title", "First", "--alias", "legacy")
        self.assertEqual(self.run_cli("register", "--id", "legacy", "--kind", "dataset", "--title", "X")[0], 4)
        self.assertEqual(self.run_cli("register", "--id", "second", "--kind", "dataset", "--title", "X", "--alias", "first")[0], 4)
        self.assertEqual(self.run_cli("register", "--id", "Bad_Id", "--kind", "dataset", "--title", "X")[0], 4)

    def test_register_dataset_records_tree_checksum(self) -> None:
        data = self.root / "references" / "zen" / "repos" / "zen-data"
        data.mkdir(parents=True)
        (data / "a.csv").write_text("1,2\n", encoding="utf-8")
        code, out = self.run_cli("register", "--id", "zen", "--kind", "dataset", "--title", "Zenodo set", "--url", "https://zenodo.org/records/1")
        self.assertEqual(code, 0, out)
        repo = self.prov("zen")["repos"][0]
        self.assertEqual((repo["name"], repo["path"], repo["files"]), ("zen-data", "repos/zen-data", 1))
        self.assertEqual(reg.validate(self.root, local=True)[0], [])
        (data / "a.csv").write_text("changed\n", encoding="utf-8")
        self.assertTrue(any("tree_sha256" in e for e in reg.validate(self.root, local=True)[0]))

    @unittest.skipUnless(HAS_GIT, "git is not installed")
    def test_repo_clone_is_recorded(self) -> None:
        upstream = self.src / "upstream"
        upstream.mkdir()
        env_args = ["-c", "user.name=t", "-c", "user.email=t@example.com"]
        subprocess.run(["git", "init", "-q", str(upstream)], check=True)
        (upstream / "README.md").write_text("hi\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(upstream), "add", "README.md"], check=True)
        subprocess.run(["git", *env_args, "-C", str(upstream), "commit", "-q", "-m", "init"], check=True)
        head = subprocess.run(["git", "-C", str(upstream), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()

        code, out = self.run_cli("repo", "--id", "tool", "--url", str(upstream), "--name", "tool-src", "--title", "Tool")
        self.assertEqual(code, 0, out)
        prov = self.prov("tool")
        self.assertEqual(prov["kind"], "repository")
        self.assertEqual(prov["repos"][0]["commit"], head)
        self.assertEqual(prov["repos"][0]["path"], "repos/tool-src")
        self.assertTrue((self.root / "references" / "tool" / "repos" / "tool-src" / "README.md").is_file())
        self.assertEqual(self.registry()["references"][0]["repos"], ["tool-src"])

        self.assertEqual(self.run_cli("repo", "--id", "tool", "--url", str(upstream), "--name", "tool-src")[0], 0)
        self.assertEqual(self.run_cli("repo", "--id", "tool", "--url", "https://example.com/other.git", "--name", "tool-src")[0], 4)
        self.assertEqual(len(self.prov("tool")["repos"]), 1)


class RegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "references").mkdir()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def add(self, ref_id: str, **fields) -> Path:
        ref = self.root / "references" / ref_id
        ref.mkdir()
        prov = reg.new_provenance(ref_id, "paper", ref_id.title())
        prov.update(fields)
        reg.save_provenance(ref, prov)
        return ref

    def test_rebuild_is_sorted_and_derived_from_provenance(self) -> None:
        self.add("zeta", arxiv_id="2401.00001", aliases=["z-old"])
        self.add("alpha", pdf="paper.pdf", pdf_sha256="0" * 64)
        self.assertEqual(reg.rebuild(self.root), [])
        entries = json.loads((self.root / "references" / "references.json").read_text())["references"]
        self.assertEqual([e["id"] for e in entries], ["alpha", "zeta"])
        self.assertEqual(list(entries[0]), list(reg.ENTRY_KEYS))
        self.assertTrue(entries[0]["has_pdf"])
        self.assertEqual(entries[1]["aliases"], ["z-old"])
        self.assertEqual(reg.resolve(self.root, "arXiv:2401.00001v3"), ["zeta"])

    def test_sync_mirrors_disk_and_validate_catches_drift(self) -> None:
        ref = self.add("demo")
        reg.rebuild(self.root)
        (ref / "attempts" / "try-1").mkdir(parents=True)
        (ref / "reproduce").mkdir()
        (ref / "reproduce" / "RESULT.json").write_text("{}", encoding="utf-8")
        errors, _ = reg.validate(self.root)
        self.assertTrue(any("attempts not recorded" in e for e in errors))
        self.assertTrue(any("reproduction field" in e for e in errors))
        changes = reg.sync_one(self.root, "demo")
        self.assertIn("status -> attempted", changes)
        reg.rebuild(self.root)
        errors, warnings = reg.validate(self.root)
        self.assertEqual(errors, [])
        self.assertTrue(any("has a reproduce/ record" in w for w in warnings))
        prov = reg.load_provenance(ref)
        self.assertEqual((prov["attempts"], prov["reproduction"]), (["try-1"], "reproduce/"))

    def test_validate_rejects_names_outside_the_layout(self) -> None:
        ref = self.add("demo")
        (ref / "paper.txt").write_text("notes", encoding="utf-8")
        reg.rebuild(self.root)
        errors, _ = reg.validate(self.root)
        self.assertTrue(any("paper.txt is outside the reference layout" in e for e in errors))

    def test_validate_rejects_loose_files_under_repos_and_attempts(self) -> None:
        ref = self.add("demo")
        (ref / "repos").mkdir()
        (ref / "repos" / "notes.txt").write_text("x", encoding="utf-8")
        (ref / "attempts").mkdir()
        (ref / "attempts" / "scratch.log").write_text("x", encoding="utf-8")
        reg.rebuild(self.root)
        errors, _ = reg.validate(self.root)
        self.assertTrue(any("repos/ holds notes.txt" in e for e in errors))
        self.assertTrue(any("attempts/ holds scratch.log" in e for e in errors))

    def test_attempts_are_kept_after_their_workspace_is_removed(self) -> None:
        ref = self.add("demo", attempts=["gone"])
        (ref / "attempts" / "new").mkdir(parents=True)
        reg.sync_one(self.root, "demo")
        self.assertEqual(reg.load_provenance(ref)["attempts"], ["gone", "new"])

    def test_validate_reports_schema_problems_and_stale_index(self) -> None:
        self.add("demo", kind="notes", status="done", pdf="paper.pdf")
        (self.root / "references" / "orphan").mkdir()
        errors, _ = reg.validate(self.root)
        joined = "\n".join(errors)
        for needle in ("kind 'notes'", "status 'done'", "without a valid pdf_sha256", "orphan: no provenance.json", "references.json is missing"):
            self.assertIn(needle, joined)

    def test_status_requires_a_record(self) -> None:
        self.add("demo", status="reproduced")
        self.assertTrue(any("no reproduce/ record" in e for e in reg.validate(self.root)[0]))

    def test_dispose_records_decision(self) -> None:
        ref = self.add("demo")
        (ref / "attempts" / "try-1").mkdir(parents=True)
        reg.dispose(self.root, "demo", "try-1", "dropped", "wrong noise model")
        self.assertEqual(reg.load_provenance(ref)["dispositions"]["try-1"]["decision"], "dropped")
        with self.assertRaises(ValueError):
            reg.dispose(self.root, "demo", "missing", "dropped", "x")


if __name__ == "__main__":
    unittest.main()
