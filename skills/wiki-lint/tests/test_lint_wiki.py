from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "lint_wiki.py"
SPEC = importlib.util.spec_from_file_location("lint_wiki", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


TAXONOMY = """scope: project
allowed_source_prefixes: []
citable_wiki_prefixes:
  - wiki/records/
  - wiki/models/
record_folders:
  - records
page_types:
  concept: {folder: concepts, requires: topics}
  model: {folder: models, requires: topics}
  question: {folder: questions, requires: topics}
  technique: {folder: techniques, requires: either}
  project: {folder: project, requires: project_topics}
  package: {folder: package, requires: project_topics}
  thesis: {folder: ".", requires: none}
statuses:
  - provisional
  - active
  - settled
topics:
  - Quantum Error Correction
  - Decoders
project_topics:
  - Research Pipeline
  - Knowledge Systems
  - Lab OS Architecture
"""

OVERVIEW = """---
title: Project overview
page_type: project
status: active
updated: 2026-09-03
source_refs:
- README.md
idea_ids: []
project_topics:
- Research Pipeline
---

# Project overview

**Summary**: The project wiki compiles reusable knowledge from papers, code, and labs.

**Sources**: [README](../../README.md)

**Last updated**: 2026-09-03

The wiki cites canonical sources rather than copying them.

## Related pages
"""

PAGE = """---
title: {title}
page_type: {page_type}
status: {status}
updated: 2026-09-03
source_refs:
{refs}
idea_ids: []
{topics}
---

# {title}

**Summary**: A page used by the tests.

**Sources**: [README](../../README.md)

**Last updated**: 2026-09-03

{body}

## Related pages

- [[project/overview|Project overview]]
"""


def page(
    title: str,
    *,
    page_type: str = "model",
    status: str = "provisional",
    refs: tuple[str, ...] = ("README.md",),
    topics: str = "topics:\n- Decoders",
    body: str = "Body text.",
) -> str:
    return PAGE.format(
        title=title,
        page_type=page_type,
        status=status,
        refs="\n".join(f"- {ref}" for ref in refs) if refs else "[]",
        topics=topics,
        body=body,
    )


class ResolverCitationTests(unittest.TestCase):
    def resolver_ids(self, text: str) -> list[str]:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "page.md"
            path.write_text(text, encoding="utf-8")
            return MODULE.resolver_citation_ids(path)

    def test_detects_bare_and_backticked_resolver_ids(self) -> None:
        ids = self.resolver_ids(
            "**Sources**: `global:paper:example`; `benchmark:task`; source:registry-item\n"
        )
        self.assertEqual(
            ids,
            ["global:paper:example", "benchmark:task", "source:registry-item"],
        )

    def test_ignores_fenced_documentation_examples(self) -> None:
        ids = self.resolver_ids(
            "```text\n**Sources**: `global:paper-id`; `benchmark:task`\n```\n"
            "[Readable source](../../references/example/paper.pdf#page=2)\n"
        )
        self.assertEqual(ids, [])


class TextScanningTests(unittest.TestCase):
    def test_code_parameters_are_not_wikilinks(self) -> None:
        for body in ("144,12,12", "1122, 148, ≤20", "n,k,d", "72", "2d²+2d, 4, d"):
            self.assertIsNone(MODULE.wikilink_target(body), body)
        self.assertEqual(MODULE.wikilink_target("models/relay-bp|QOS"), "models/relay-bp")
        self.assertEqual(MODULE.wikilink_target("thesis#open-questions|Thesis"), "thesis")

    def test_code_span_labels_do_not_hide_links(self) -> None:
        scanned = MODULE.scan_text("See [`records/a.md`](../records/a.md) and `[not](a-link.md)`.\n")
        self.assertEqual(MODULE.markdown_link_targets(scanned), [(1, "../records/a.md")])

    def test_fenced_code_is_ignored_including_inside_blockquotes(self) -> None:
        scanned = MODULE.scan_text("> **Note:**\n>\n> ```python\n> x = [[a]]\n> ```\n[[b]]\n")
        self.assertEqual([body for _, body in MODULE.wikilink_bodies(scanned)], ["b"])


class StructuralLintTests(unittest.TestCase):
    def make_wiki(self, root: Path) -> Path:
        wiki = root / "wiki"
        wiki.mkdir()
        (wiki / "README.md").write_text("# Wiki schema\n", encoding="utf-8")
        (wiki / "taxonomy.yml").write_text(TAXONOMY, encoding="utf-8")
        (wiki / "index.md").write_text(
            "# Knowledge map\n\n"
            "- [Project manual](project/index.md)\n"
            "- [[thesis|Project thesis]]\n",
            encoding="utf-8",
        )
        (wiki / "thesis.md").write_text(
            "---\n"
            "title: Project thesis\n"
            "page_type: thesis\n"
            "status: provisional\n"
            "updated: 2026-09-03\n"
            "source_refs:\n"
            "- README.md\n"
            "idea_ids: []\n"
            "---\n\n"
            "# Project thesis\n\n"
            "**Summary**: Compile knowledge once.\n\n"
            "**Sources**: [README](../README.md)\n\n"
            "**Last updated**: 2026-09-03\n\n"
            "## Related pages\n\n"
            "- [Project manual](project/index.md)\n",
            encoding="utf-8",
        )
        (wiki / "records").mkdir()
        (wiki / "records" / "log.md").write_text(
            "# Wiki log\n\n## [2026-09-03] ingest | wiki initialized\n\n- Created the wiki.\n",
            encoding="utf-8",
        )
        (wiki / "sources.yml").write_text("version: 1\nsources: []\n", encoding="utf-8")
        project = wiki / "project"
        project.mkdir()
        (project / "overview.md").write_text(OVERVIEW, encoding="utf-8")
        (project / "index.md").write_text(
            "# Project manual\n\n- [[project/overview|Project overview]]\n",
            encoding="utf-8",
        )
        (root / "README.md").write_text("# Project\n", encoding="utf-8")
        return wiki

    def add_page(self, wiki: Path, relative: str, text: str, *, listed: bool = True) -> None:
        path = wiki / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        if listed:
            guide = path.parent / "index.md"
            if not guide.is_file():
                guide.write_text(f"# {path.parent.name}\n\n", encoding="utf-8")
            with guide.open("a", encoding="utf-8") as handle:
                handle.write(f"- [[{relative.removesuffix('.md')}|{relative}]]\n")

    def lint(self, root: Path) -> tuple[list[str], list[str]]:
        return MODULE.lint(root)

    def test_valid_wiki_has_no_errors(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_wiki(root)
            errors, warnings = self.lint(root)
            self.assertEqual(errors, [])
            self.assertEqual(warnings, [])

    def test_question_shaped_title_outside_questions_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            wiki = self.make_wiki(root)
            self.add_page(wiki, "models/what-the-dem-hides.md", page("What the sketch hides"))
            errors, warnings = self.lint(root)
            self.assertTrue(any("must name the topic" in error and "what-the-dem-hides" in error for error in errors))
            self.assertEqual(warnings, [])

    def test_trailing_punctuation_in_a_title_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            wiki = self.make_wiki(root)
            self.add_page(wiki, "models/relay-bp.md", page("QOS."))
            errors, _warnings = self.lint(root)
            self.assertTrue(any("must name the topic" in error and "relay-bp" in error for error in errors))

    def test_question_title_in_questions_is_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            wiki = self.make_wiki(root)
            self.add_page(
                wiki,
                "questions/does-beam-beat-bposd.md",
                page("Does QOS ridge beat classical ridge?", page_type="question"),
            )
            errors, warnings = self.lint(root)
            self.assertEqual(errors, [])
            self.assertEqual(warnings, [])

    def test_leading_article_is_a_warning(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            wiki = self.make_wiki(root)
            self.add_page(wiki, "models/scout-query-shape.md", page("The shape of a scout query"))
            errors, warnings = self.lint(root)
            self.assertEqual(errors, [])
            self.assertTrue(any("starts with an article" in warning for warning in warnings))

    def test_valid_category_page_passes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            wiki = self.make_wiki(root)
            self.add_page(wiki, "models/relay-bp.md", page("QOS"))
            errors, warnings = self.lint(root)
            self.assertEqual(errors, [])
            self.assertEqual(warnings, [])

    def test_records_are_exempt_from_the_page_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            wiki = self.make_wiki(root)
            self.add_page(
                wiki,
                "records/design/2026-06-01-Plan_Notes.md",
                "# Design note - 2026-06-01\n\nNo frontmatter, no visible fields.\n",
                listed=False,
            )
            errors, warnings = self.lint(root)
            self.assertEqual(errors, [])
            self.assertEqual(warnings, [])

    def test_broken_links_in_records_are_warnings(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            wiki = self.make_wiki(root)
            self.add_page(
                wiki,
                "records/audits/2026-06-02-audit.md",
                "# Audit\n\n[gone](../../../labs/2026-01-01-gone/report.md) and [[no-such-page]].\n",
                listed=False,
            )
            errors, warnings = self.lint(root)
            self.assertEqual(errors, [])
            self.assertTrue(any("broken local link in wiki/records/audits/2026-06-02-audit.md:3" in w for w in warnings))
            self.assertTrue(any("broken Obsidian wikilink" in w and "[[no-such-page]]" in w for w in warnings))

    def test_links_outside_wiki_must_exist(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            wiki = self.make_wiki(root)
            (root / "labs" / "2026-09-01-real").mkdir(parents=True)
            (root / "labs" / "2026-09-01-real" / "report.md").write_text("# Report\n", encoding="utf-8")
            body = (
                "[real](../../labs/2026-09-01-real/report.md#results) "
                "[folder](../../labs/2026-09-01-real/) "
                "[`gone`](../../lib/src/mypkg/gone.py) "
                "[also gone](../../labs/missing-lab/results/missing.json)"
            )
            self.add_page(wiki, "models/relay-bp.md", page("QOS", body=body))
            errors, _ = self.lint(root)
            self.assertEqual(
                sorted(error.split(":", 2)[-1].strip() for error in errors),
                ["../../labs/missing-lab/results/missing.json", "../../lib/src/mypkg/gone.py"],
            )

    def test_gitignored_missing_target_is_a_warning(self) -> None:
        if shutil.which("git") is None:
            self.skipTest("git is not installed")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            (root / ".gitignore").write_text("references/*/paper.pdf\n", encoding="utf-8")
            wiki = self.make_wiki(root)
            self.add_page(
                wiki,
                "models/relay-bp.md",
                page(
                    "QOS",
                    refs=("README.md", "references/relay-bp/paper.pdf"),
                    body="[PDF](../../references/relay-bp/paper.pdf#page=3)",
                ),
            )
            errors, warnings = self.lint(root)
            self.assertEqual(errors, [])
            self.assertEqual(len([w for w in warnings if w.startswith("local-only")]), 2)

    def test_wikilinks_resolve_and_bare_names_warn(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            wiki = self.make_wiki(root)
            self.add_page(wiki, "models/relay-bp.md", page("QOS"))
            body = (
                "Qualified [[models/relay-bp|QOS]], parameters [[144,12,12]] and [[n,k,d]], "
                "bare [[relay-bp]], missing [[models/no-such]]."
            )
            self.add_page(wiki, "concepts/beta.md", page("Beta", page_type="concept", body=body))
            errors, warnings = self.lint(root)
            self.assertEqual(len(errors), 1)
            self.assertIn("broken Obsidian wikilink in wiki/concepts/beta.md", errors[0])
            self.assertIn("[[models/no-such]]", errors[0])
            self.assertEqual([w for w in warnings if "bare Obsidian wikilink" in w][0].split(": ", 1)[1][:12], "[[relay-bp]]")

    def test_page_type_must_match_folder_and_topics_are_required(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            wiki = self.make_wiki(root)
            self.add_page(wiki, "models/wrong-type.md", page("Wrong type", page_type="concept"))
            self.add_page(wiki, "models/no-topics.md", page("No topics", topics=""))
            self.add_page(wiki, "package/guide.md", page("Package guide", page_type="package"))
            self.add_page(
                wiki,
                "techniques/ops.md",
                page("Ops", page_type="technique", topics="project_topics:\n- Research Pipeline"),
            )
            self.add_page(wiki, "codecs/orphan-type.md", page("Unknown folder", page_type="model"))
            errors, _ = self.lint(root)
            joined = "\n".join(errors)
            self.assertIn("page_type 'concept' in wiki/models/wrong-type.md does not match", joined)
            self.assertIn("topic-indexed page needs one to three controlled topics in wiki/models/no-topics.md", joined)
            self.assertIn("package page needs one to three controlled project_topics in wiki/package/guide.md", joined)
            self.assertIn("unknown wiki category folder for wiki/codecs/orphan-type.md", joined)
            self.assertNotIn("techniques/ops.md", joined)

    def test_controlled_status_and_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            wiki = self.make_wiki(root)
            self.add_page(wiki, "models/odd.md", page("Odd", status="finished", topics="topics:\n- Astrology"))
            errors, _ = self.lint(root)
            joined = "\n".join(errors)
            self.assertIn("status 'finished' in wiki/models/odd.md", joined)
            self.assertIn("topics must list one to three controlled values in wiki/models/odd.md", joined)

    def test_source_refs_may_cite_records_and_ledgers_but_not_synthesis(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            wiki = self.make_wiki(root)
            self.add_page(wiki, "records/design/2026-06-01-plan.md", "# Plan\n", listed=False)
            self.add_page(wiki, "models/relay-bp.md", page("QOS"))
            self.add_page(wiki, "concepts/alpha.md", page("Alpha", page_type="concept"))
            refs = ("wiki/records/design/2026-06-01-plan.md", "wiki/models/relay-bp.md", "wiki/concepts/alpha.md")
            self.add_page(wiki, "concepts/beta.md", page("Beta", page_type="concept", refs=refs))
            errors, _ = self.lint(root)
            self.assertEqual(len(errors), 1)
            self.assertIn("source_ref cites a compiled wiki page in wiki/concepts/beta.md: wiki/concepts/alpha.md", errors[0])

    def test_myst_syntax_is_rejected_outside_code(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            wiki = self.make_wiki(root)
            body = (
                "See {doc}`../concepts/noise` and {py:class}`~emb.models.Hamiltonian`.\n\n"
                "```{note}\nA note.\n```\n\n"
                "(my-label)=\n## Heading\n\n"
                "Mentioning `{doc}` in code is fine.\n\n"
                "````markdown\n```{toctree}\nexample\n```\n````\n"
            )
            self.add_page(wiki, "package/guide.md", page("Guide", page_type="package",
                                                          topics="project_topics:\n- Lab OS Architecture",
                                                          body=body))
            errors, _ = self.lint(root)
            myst = [error for error in errors if "MyST" in error]
            self.assertEqual(len(myst), 3, myst)
            self.assertIn("{doc}, {py:class}", next(error for error in myst if "role" in error))

    def test_related_pages_must_be_last_and_dates_agree(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            wiki = self.make_wiki(root)
            text = page("QOS").replace("**Last updated**: 2026-09-03", "**Last updated**: 2026-09-04")
            text += "\n## Appendix\n\nMore text.\n"
            self.add_page(wiki, "models/relay-bp.md", text)
            errors, warnings = self.lint(root)
            self.assertIn("'## Related pages' must be the last section in wiki/models/relay-bp.md", errors)
            self.assertTrue(any("differs from frontmatter" in warning for warning in warnings))

    def test_unlisted_pages_and_guides(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            wiki = self.make_wiki(root)
            self.add_page(wiki, "models/relay-bp.md", page("QOS"), listed=False)
            self.add_page(wiki, "models/index.md", "# Decoder pages\n\nA folder guide.\n", listed=False)
            errors, warnings = self.lint(root)
            self.assertEqual(errors, [])
            self.assertEqual(
                warnings,
                ["compiled page not listed in wiki/models/index.md: wiki/models/relay-bp.md"],
            )

    def test_root_index_rejects_leaf_links(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            wiki = self.make_wiki(root)
            self.add_page(wiki, "models/relay-bp.md", page("QOS"))
            with (wiki / "index.md").open("a", encoding="utf-8") as handle:
                handle.write("- [[models/relay-bp|QOS]]\n")
            _, warnings = self.lint(root)
            self.assertTrue(
                any("root index should link classifiers/sub-indexes" in w for w in warnings),
                warnings,
            )

    def test_log_accepts_reorganize_entries(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            wiki = self.make_wiki(root)
            with (wiki / "records" / "log.md").open("a", encoding="utf-8") as handle:
                handle.write("\n## [2026-09-26] reorganize | knowledge folded into the wiki\n")
                handle.write("\n## [2026-09-26] rename | not a known kind\n")
            errors, _ = self.lint(root)
            self.assertEqual(errors, ["malformed wiki log heading: ## [2026-09-26] rename | not a known kind"])

    def test_check_paths_flags_retired_and_missing_code_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            wiki = self.make_wiki(root)
            (wiki / "taxonomy.yml").write_text(
                TAXONOMY + "retired_path_prefixes:\n  - inbox/\n", encoding="utf-8"
            )
            (root / "labs").mkdir()
            body = "Old `inbox/papers/x/paper.pdf`, missing `labs/2026-01-01-gone/report.md`, fine `README.md`."
            self.add_page(wiki, "models/relay-bp.md", page("QOS", body=body))
            _, plain = self.lint(root)
            _, checked = MODULE.lint(root, check_paths=True)
            self.assertEqual(plain, [])
            self.assertEqual(len(checked), 2)
            self.assertTrue(any("retired path" in warning and "inbox/papers/x/paper.pdf" in warning for warning in checked))

    def test_labelled_wikilinks_in_table_rows_warn_and_still_resolve(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            wiki = self.make_wiki(root)
            self.add_page(wiki, "models/relay-bp.md", page("QOS"))
            body = (
                "| Decoder | Page |\n| --- | --- |\n"
                "| relay | [[models/relay-bp|QOS]] |\n"
                "| escaped | [[models/relay-bp\\|QOS]] |\n"
                "| plain | [QOS](relay-bp.md) |\n\n"
                "Outside a table, [[models/relay-bp|QOS]] is fine."
            )
            self.add_page(wiki, "models/table.md", page("Table", body=body))
            errors, warnings = self.lint(root)
            self.assertEqual(errors, [])
            table_warnings = [warning for warning in warnings if "table row" in warning]
            self.assertEqual(len(table_warnings), 2)
            self.assertTrue(all("models/table.md" in warning for warning in table_warnings))

    def test_wikilink_labels_cannot_hold_square_brackets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            wiki = self.make_wiki(root)
            self.add_page(wiki, "models/relay-bp.md", page("QOS"))
            body = (
                "Bad: [[models/relay-bp|QOS on `[[144,12,12]]`]].\n\n"
                "Good: [[models/relay-bp|QOS on ⟦144,12,12⟧]] and `[[models/relay-bp|x [y]]]` in code."
            )
            self.add_page(wiki, "models/labels.md", page("Labels", body=body))
            errors, _ = self.lint(root)
            self.assertEqual(len(errors), 1)
            self.assertIn("square brackets", errors[0])
            self.assertIn("models/labels.md", errors[0])

    def test_check_paths_ignores_symbol_line_and_anchor_suffixes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            wiki = self.make_wiki(root)
            (root / "labs" / "2026-01-01-lab").mkdir(parents=True)
            (root / "labs" / "2026-01-01-lab" / "train.py").write_text("", encoding="utf-8")
            body = (
                "See `labs/2026-01-01-lab/train.py::adaptive_pos_weight`, "
                "`labs/2026-01-01-lab/train.py:12`, and `labs/2026-01-01-lab/train.py#L3`."
            )
            self.add_page(wiki, "models/relay-bp.md", page("QOS", body=body))
            _, checked = MODULE.lint(root, check_paths=True)
            self.assertEqual(checked, [])

    def test_repo_root_is_found_from_the_script_location(self) -> None:
        root = MODULE.find_repo_root()
        self.assertTrue((root / "wiki" / "README.md").is_file())
        self.assertEqual(root / "skills" / "wiki-lint" / "scripts" / "lint_wiki.py", SCRIPT)


if __name__ == "__main__":
    unittest.main()
