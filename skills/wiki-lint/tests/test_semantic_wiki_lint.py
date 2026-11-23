from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_ROOT = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

from llm import StructuredResult
from semantic_wiki_lint import build_packet, load_pages, semantic_lint


PAGE = """---
title: {title}
page_type: concept
status: active
updated: 2026-09-03
source_refs:
- references/example/paper.pdf
idea_ids: []
topics:
- Quantum Error Correction
---

# {title}

**Summary**: {summary}

**Sources**: source

**Last updated**: 2026-09-03

{body}

## Related pages
"""


class FakeSemanticLLM:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def run(self, **kwargs):
        self.calls.append(kwargs)
        return StructuredResult(
            data={
                "findings": [
                    {
                        "kind": "unsupported_claim",
                        "severity": "warning",
                        "confidence": 0.9,
                        "path": "wiki/concepts/alpha.md",
                        "line": 20,
                        "claim": "Alpha always recovers beta.",
                        "evidence_paths": ["wiki/concepts/alpha.md"],
                        "reason": "The consequential claim has no nearby evidence.",
                        "suggested_action": "Review the source or mark this as an inference.",
                    },
                    {
                        "kind": "unsupported_claim",
                        "severity": "warning",
                        "confidence": 0.4,
                        "path": "wiki/concepts/alpha.md",
                        "line": 20,
                        "claim": "Low confidence",
                        "evidence_paths": [],
                        "reason": "Speculative.",
                        "suggested_action": "Ignore.",
                    },
                    {
                        "kind": "duplicate_terminology",
                        "severity": "warning",
                        "confidence": 0.99,
                        "path": "wiki/concepts/alpha.md",
                        "line": 22,
                        "claim": "A duplicated navigation entry.",
                        "evidence_paths": ["wiki/concepts/alpha.md:21", "wiki/concepts/alpha.md:22"],
                        "reason": "Same-page duplication is not semantic terminology drift.",
                        "suggested_action": "Ignore.",
                    },
                ]
            },
            cached=False,
            model="test-model",
            input_tokens=100,
            output_tokens=20,
            total_tokens=120,
        )


class SemanticWikiLintTests(unittest.TestCase):
    def make_scope(self, root: Path) -> None:
        concepts = root / "wiki" / "concepts"
        concepts.mkdir(parents=True)
        (concepts / "alpha.md").write_text(
            PAGE.format(
                title="Alpha recovery",
                summary="Alpha is a recovery construction.",
                body="Alpha always recovers beta. [[concepts/beta|Beta]]",
            ),
            encoding="utf-8",
        )
        (concepts / "beta.md").write_text(
            PAGE.format(
                title="Beta recovery",
                summary="Beta is a related recovery construction.",
                body="Beta is supported by a source.",
            ),
            encoding="utf-8",
        )
        (root / "wiki" / "sources.yml").write_text("version: 1\nsources: []\n", encoding="utf-8")

    def test_packet_contains_numbered_primary_and_related_summary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_scope(root)
            pages = load_pages(root)
            packet = build_packet(
                [pages[0]],
                related={pages[0].relative: [pages[1]]},
                sources={},
            )
            self.assertIn('primary-page path="wiki/concepts/alpha.md"', packet)
            self.assertIn("Alpha always recovers beta", packet)
            self.assertIn("path=wiki/concepts/beta.md", packet)

    def test_semantic_lint_filters_low_confidence_findings(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_scope(root)
            llm = FakeSemanticLLM()
            findings, stats = semantic_lint(root, llm)
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0]["confidence"], 0.9)
            self.assertEqual(stats.pages, 2)
            self.assertEqual(stats.total_tokens, 120)
            self.assertEqual(len(llm.calls), 1)

    def test_records_and_folder_guides_are_not_loaded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_scope(root)
            records = root / "wiki" / "records" / "design"
            records.mkdir(parents=True)
            (records / "2026-06-01-plan.md").write_text("# Plan\n\nImmutable history.\n", encoding="utf-8")
            (root / "wiki" / "concepts" / "index.md").write_text("# Concept pages\n", encoding="utf-8")
            package = root / "wiki" / "package"
            package.mkdir()
            (package / "index.md").write_text("# Package pages\n", encoding="utf-8")
            (package / "overview.md").write_text(
                PAGE.format(title="Package manual", summary="Entry page.", body="Body."),
                encoding="utf-8",
            )
            relatives = [page.relative for page in load_pages(root)]
            self.assertEqual(
                relatives,
                ["wiki/concepts/alpha.md", "wiki/concepts/beta.md", "wiki/package/overview.md"],
            )


if __name__ == "__main__":
    unittest.main()
