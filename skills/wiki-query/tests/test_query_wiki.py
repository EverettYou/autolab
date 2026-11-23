from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "query_wiki.py"
SPEC = importlib.util.spec_from_file_location("query_wiki", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def write(root: Path, relative: str, text: str) -> None:
    path = root / "wiki" / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def page(title: str, summary: str, *, page_type: str = "model", status: str = "active", topics: str = "Boundary Models") -> str:
    quoted = '"' + title.replace('"', '\\"') + '"'
    return (
        f"---\ntitle: {quoted}\npage_type: {page_type}\nstatus: {status}\n"
        f"updated: 2026-09-29\nsource_refs: []\nidea_ids: []\ntopics:\n- {topics}\n---\n\n"
        f"# {title}\n\n**Summary**: {summary}\n\n**Sources**: none\n\n**Last updated**: 2026-09-29\n"
    )


class QueryWikiTests(unittest.TestCase):
    def wiki(self, root: Path) -> None:
        (root / "wiki").mkdir()
        (root / "wiki" / "README.md").write_text("# Wiki schema\n", encoding="utf-8")
        write(root, "models/ising-boundary.md", page("Ising boundary", "A boundary Hamiltonian family."))
        write(
            root,
            "models/other.md",
            page("Other model", "Uses ising-boundary only as a cited baseline."),
        )
        write(
            root,
            "dead-ends/masked-diffusion.md",
            page("Dead end: masked diffusion", "Does not reproduce.", page_type="dead-end", status="settled")
            + "\n## Revisit if\n\nAuthors release code and weights.\n\n## Related pages\n",
        )
        write(
            root,
            "questions/open-one.md",
            page("Does beam selection beat BP+OSD?", "Still open.", page_type="question", status="provisional"),
        )
        write(
            root,
            "questions/closed-one.md",
            page("Closed beam question", "Settled no.", page_type="question", status="closed"),
        )
        write(root, "records/synthesis/2026-09-01-note.md", "# Synthesis\n\nIsing boundary was discussed here only.\n")

    def test_title_match_ranks_above_a_summary_mention(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.wiki(root)
            text = MODULE.render(root, ["ising-boundary"])
            self.assertLess(text.index("wiki/models/ising-boundary.md"), text.index("wiki/models/other.md"))
            self.assertNotIn("records/synthesis", text)

    def test_dead_end_revisit_and_open_question_are_separated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.wiki(root)
            text = MODULE.render(root, ["beam", "diffusion"])
            dead = text.split("## Dead ends", 1)[1].split("## Open questions", 1)[0]
            questions = text.split("## Open questions", 1)[1]
            self.assertIn("wiki/dead-ends/masked-diffusion.md", dead)
            self.assertIn("Authors release code and weights.", dead)
            self.assertIn("wiki/questions/open-one.md", questions)
            self.assertNotIn("wiki/questions/closed-one.md", questions)

    def test_hyphen_and_space_match(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.wiki(root)
            text = MODULE.render(root, ["ising boundary"])
            self.assertIn("wiki/models/ising-boundary.md", text)

    def test_no_match_names_where_to_look_next(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.wiki(root)
            text = MODULE.render(root, ["quaternary-lattice"])
            self.assertIn("No compiled page matches these terms. Look in labs/ and references/.", text)

    def test_blank_terms_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.wiki(root)
            with self.assertRaises(ValueError):
                MODULE.render(root, ["  "])
