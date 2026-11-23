"""Tests for topic_alignment.py on a temporary reference collection.

Run: python3 -m unittest skills.discover-references.tests.test_topic_alignment
"""
from __future__ import annotations

import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "topic_alignment.py"
SPEC = importlib.util.spec_from_file_location("topic_alignment", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def catalog(root: Path, rows: list[tuple[str, str, str]]) -> None:
    entries = []
    for ref_id, title, abstract in rows:
        folder = root / "references" / ref_id
        folder.mkdir(parents=True)
        (folder / "provenance.json").write_text(json.dumps({
            "id": ref_id, "title": title, "abstract": abstract, "fetched_at": "2026-01-01T00:00:00Z",
        }), encoding="utf-8")
        entries.append({
            "id": ref_id, "title": title, "provenance": f"references/{ref_id}/provenance.json",
        })
    (root / "references").mkdir(exist_ok=True)
    (root / "references" / "references.json").write_text(
        json.dumps({"references": entries}), encoding="utf-8")


ENV = (
    "OPENAI_API_KEY",
    "OPENAI_CATALOG_SEARCH_ENABLED",
    "OPENAI_SEARCH_EMBEDDING_MODEL",
    "OPENAI_SEARCH_EMBEDDING_DIMENSIONS",
)


def enable_search(root: Path) -> None:
    frontend = root / "dashboard" / "frontend"
    frontend.mkdir(parents=True)
    (frontend / "site.json").write_text(json.dumps({
        "search": {"api_key": "sk-test", "embedding_model": "text-embedding-3-small"},
    }), encoding="utf-8")


def vectors_for(texts, *, key, model, dimensions):
    del key, model, dimensions
    vectors = []
    for text in texts:
        if "sourdough" in text.lower() or "rye" in text.lower():
            vectors.append([0.0, 1.0, 0.0])
        else:
            vectors.append([1.0, 0.0, 0.0])
    return vectors


class TopicAlignmentTests(unittest.TestCase):
    def setUp(self):
        self.saved_env = {name: os.environ.pop(name, None) for name in ENV}
        self.saved_fetch = MODULE.EMBED_FETCH
        MODULE.EMBED_FETCH = None

    def tearDown(self):
        MODULE.EMBED_FETCH = self.saved_fetch
        for name, value in self.saved_env.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    def test_overlap_prefers_the_shared_topic_and_grows(self):
        shared = "quantum ldpc decoder for circuit noise"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            catalog(root, [
                ("one", f"{shared} alpha", "A quantum ldpc decoder corrects circuit noise in a memory."),
                ("two", f"{shared} beta", "A quantum ldpc decoder corrects circuit noise at larger distance."),
            ])
            topic = MODULE.fit(MODULE.load_references(root))
            bread = MODULE.alignment("sourdough starter hydration and crumb structure for rye loaves", topic)
            candidate = MODULE.alignment(f"{shared}. A quantum ldpc decoder corrects circuit noise.", topic)
            self.assertGreater(candidate, bread)
            self.assertLess(bread, 0.2)
            self.assertGreater(candidate, 0.5)

    def test_a_term_in_one_reference_is_not_the_topic(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows = []
            for index in range(5):
                rows.append((
                    f"ref-{index}",
                    "quantum ldpc decoder",
                    "A quantum ldpc decoder corrects circuit noise." + ("" if index else " sourdough"),
                ))
            catalog(root, rows)
            topic = MODULE.fit(MODULE.load_references(root))
            self.assertNotIn("sourdough", topic.weights)
            self.assertIn("decoder", topic.weights)

    def test_score_command_reports_alignment(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            catalog(root, [
                ("one", "quantum ldpc decoder", "A quantum ldpc decoder corrects circuit noise."),
                ("two", "quantum ldpc decoder", "A quantum ldpc decoder corrects circuit noise at scale."),
            ])
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = MODULE.main(["--root", str(root), "score", "--title", "quantum ldpc decoder",
                                    "--abstract", "A new schedule for a quantum ldpc decoder."])
            self.assertEqual(code, 0)
            self.assertIn("embedding  unavailable (no search key)", buffer.getvalue())
            self.assertNotIn("request", buffer.getvalue())

    def test_an_explicit_subject_scores_the_request_not_the_standing_topic(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            catalog(root, [
                ("one", "quantum ldpc decoder", "A quantum ldpc decoder corrects circuit noise."),
                ("two", "quantum ldpc decoder", "A quantum ldpc decoder corrects circuit noise at scale."),
            ])
            subject = "sourdough hydration"
            bread = ["--title", "Sourdough", "--abstract",
                     "Sourdough starter hydration and crumb structure for rye loaves."]
            decoder = ["--title", "quantum ldpc decoder",
                       "--abstract", "A quantum ldpc decoder corrects circuit noise."]

            def run(extra):
                buffer = io.StringIO()
                with redirect_stdout(buffer):
                    code = MODULE.main(["--root", str(root), "score", "--topic", subject, *extra])
                self.assertEqual(code, 0)
                lines = {line.split()[0]: float(line.split()[1]) for line in buffer.getvalue().splitlines()
                         if line.startswith(("request", "alignment"))}
                return lines

            on_subject = run(bread)
            off_subject = run(decoder)
            self.assertEqual(on_subject["request"], 1.0)
            self.assertEqual(off_subject["request"], 0.0)
            self.assertGreater(on_subject["request"], on_subject["alignment"])
            self.assertGreater(off_subject["alignment"], off_subject["request"])

    def test_embedding_lifts_an_on_topic_candidate_above_the_word_score(self):
        shared = "quantum ldpc decoder for circuit noise"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            enable_search(root)
            catalog(root, [
                ("one", f"{shared} alpha", "A quantum ldpc decoder corrects circuit noise in a memory."),
                ("two", f"{shared} beta", "A quantum ldpc decoder corrects circuit noise at larger distance."),
            ])
            MODULE.EMBED_FETCH = vectors_for
            docs = MODULE.load_references(root)
            config = MODULE.load_embed_config(root)
            self.assertTrue(config.enabled)
            text = "A graph network schedule for memory experiments."
            words, embedded, note = MODULE.score_text(text, docs, config, MODULE._cache_path(root))
            bread_words, bread_embedded, _ = MODULE.score_text(
                "sourdough starter hydration and crumb structure for rye loaves",
                docs, config, MODULE._cache_path(root))
            self.assertEqual(note, "")
            self.assertEqual(embedded, 1.0)
            self.assertEqual(bread_embedded, 0.0)
            self.assertLess(words, 0.5)
            self.assertGreater(MODULE.blend(words, embedded), words)
            self.assertGreater(MODULE.blend(words, embedded), MODULE.blend(bread_words, bread_embedded))

    def test_a_failed_embedding_call_keeps_the_word_score(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            enable_search(root)
            catalog(root, [
                ("one", "quantum ldpc decoder", "A quantum ldpc decoder corrects circuit noise."),
                ("two", "quantum ldpc decoder", "A quantum ldpc decoder corrects circuit noise at scale."),
            ])

            def fail(texts, *, key, model, dimensions):
                del texts, key, model, dimensions
                raise RuntimeError("embedding request failed (401)")

            MODULE.EMBED_FETCH = fail
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = MODULE.main(["--root", str(root), "score", "--title", "quantum ldpc decoder",
                                    "--abstract", "A quantum ldpc decoder corrects circuit noise."])
            printed = buffer.getvalue()
            self.assertEqual(code, 0)
            self.assertIn("unavailable (embedding request failed)", printed)
            words = next(float(line.split()[1]) for line in printed.splitlines() if line.startswith("words"))
            alignment = next(float(line.split()[1]) for line in printed.splitlines() if line.startswith("alignment"))
            self.assertEqual(alignment, words)

    def test_compiled_wiki_pages_join_the_topic_and_records_do_not(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            catalog(root, [
                ("one", "quantum ldpc decoder", "A quantum ldpc decoder corrects circuit noise."),
                ("two", "quantum ldpc decoder", "A quantum ldpc decoder corrects circuit noise at scale."),
            ])
            wiki = root / "wiki"
            for index in range(5):
                folder = wiki / "concepts"
                folder.mkdir(parents=True, exist_ok=True)
                (folder / f"baking-{index}.md").write_text(
                    f"---\ntitle: Baking note {index}\n---\n\n# Baking note {index}\n\n"
                    "Sourdough hydration and crumb structure for rye loaves.\n",
                    encoding="utf-8")
            records = wiki / "records"
            records.mkdir()
            (records / "notarial.md").write_text("# Grain\n\nNotarial registers of the grain trade.\n", encoding="utf-8")
            pages = MODULE.load_wiki(root)
            self.assertEqual(len(pages), 5)
            self.assertTrue(all(page.kind == "wiki" for page in pages))
            bread = "sourdough starter hydration and crumb structure for rye loaves"
            refs_only = MODULE.alignment(bread, MODULE.fit(MODULE.load_references(root)))
            widened = MODULE.alignment(bread, MODULE.fit(MODULE.load_references(root) + pages))
            self.assertGreater(widened, refs_only)
            self.assertNotIn("notarial", MODULE.fit(MODULE.load_references(root) + pages).weights)

    def test_embeddings_are_cached(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            calls = []

            def fetch(texts, *, key, model, dimensions):
                del key, model, dimensions
                calls.append(list(texts))
                return [[1.0, 0.0] for _ in texts]

            config = MODULE.EmbedConfig(True, "sk-test", "text-embedding-3-small", 512, "")
            MODULE.EMBED_FETCH = fetch
            path = MODULE._cache_path(root)
            first = MODULE.embed_texts(["quantum ldpc decoder", "another decoder"], config, path)
            second = MODULE.embed_texts(["quantum ldpc decoder", "fresh abstract"], config, path)
            self.assertEqual(len(first), 2)
            self.assertEqual(len(second), 2)
            self.assertEqual(len(calls), 2)
            self.assertEqual(calls[1], ["fresh abstract"])


if __name__ == "__main__":
    unittest.main()
