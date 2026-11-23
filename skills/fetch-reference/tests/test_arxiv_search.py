from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import arxiv_search  # noqa: E402


def test_build_query_without_window_is_unchanged():
    assert arxiv_search.build_query("decoder", None) == "decoder"
    assert arxiv_search.build_query("decoder", ["quant-ph"]) == "(decoder) AND (cat:quant-ph)"


def test_build_query_adds_a_submission_window():
    now = datetime(2026, 9, 28, 12, 0, tzinfo=timezone.utc)
    q = arxiv_search.build_query("decoder", ["quant-ph"], since_days=7, now=now)
    assert q == "((decoder) AND (cat:quant-ph)) AND submittedDate:[202609211200 TO 202609281200]"


def test_window_switches_to_date_sort(monkeypatch):
    seen = {}

    def fake(query, *, max_results, sort):
        seen.update(query=query, sort=sort)
        return []

    monkeypatch.setattr(arxiv_search, "search_api", fake)
    arxiv_search.search_arxiv("decoder", since_days=3)
    assert seen["sort"] == "submittedDate" and "submittedDate:[" in seen["query"]
    arxiv_search.search_arxiv("decoder")
    assert seen["sort"] == "relevance"


def test_build_query_ands_bare_words_and_keeps_fielded_queries():
    assert arxiv_search.build_query("quantum LDPC decoder", None) == "all:quantum AND all:LDPC AND all:decoder"
    assert arxiv_search.build_query('ti:"relay BP"', None) == 'ti:"relay BP"'
    assert arxiv_search.build_query("abs:decoder AND cat:quant-ph", None) == "abs:decoder AND cat:quant-ph"
