"""Semantic search stays off unless configured; failures keep keyword groups."""
from __future__ import annotations

import json

from dashboard.backend.semantic import hybrid_score, is_complex_query, lexical_score


def test_complex_query_needs_length_and_a_relation():
    assert is_complex_query("alpha") is False
    assert is_complex_query("which boundary transition should we trust on this evidence") is True
    assert is_complex_query("比较这两种边界模型在同一有限尺寸下的结果") is True


def test_hybrid_score_lets_a_conceptual_match_beat_a_weak_keyword():
    conceptual = hybrid_score(0.82, lexical_score("boundary", "unrelated title"))
    keyword = hybrid_score(0.2, lexical_score("boundary", "boundary"))
    assert conceptual > keyword


def test_search_runtime_prefers_env_when_site_key_empty(tmp_path, monkeypatch):
    from dashboard.backend import catalog, site

    monkeypatch.setenv("OPENAI_API_KEY", "sk-from-env")
    monkeypatch.setenv("OPENAI_CATALOG_SEARCH_ENABLED", "1")
    monkeypatch.setattr(catalog, "ROOT", tmp_path)
    cache = tmp_path / ".cache/dashboard"
    cache.mkdir(parents=True)
    (cache / "site.json").write_text(json.dumps({"search": {"api_key": ""}}), encoding="utf-8")
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "site.defaults.json").write_text(json.dumps({
        "title": "t", "intro": "i", "search": {"api_key": ""},
        "pages": {}, "home": {}, "search_hits": {}, "wiki_folder_page": 40,
        "json_table_height": "1px",
    }), encoding="utf-8")
    monkeypatch.setattr(site, "FRONTEND", frontend)
    runtime = site.search_runtime()
    assert runtime.key == "sk-from-env"
    assert runtime.key_source == "default"
    assert runtime.enabled is True


def test_keyword_search_reports_local_mode(client):
    payload = client.get_json("/api/search?q=alpha")
    assert payload["mode"] == "local"
    assert payload["complex_query"] is False
    assert payload["total"] >= 1
    assert "semantic_enabled" in payload


def test_embedding_failure_keeps_the_keyword_groups(client, monkeypatch):
    monkeypatch.setenv("OPENAI_CATALOG_SEARCH_ENABLED", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    def fail(*_args, **_kwargs):
        raise RuntimeError("embeddings are down")

    monkeypatch.setattr("dashboard.backend.semantic._embed_texts", fail)
    payload = client.get_json("/api/search?q=alpha&stage=hybrid")
    assert payload["mode"] == "local"
    assert payload["pending"] == []
    groups = {group["key"]: group for group in payload["groups"]}
    assert groups["references"]["total"] >= 1 or groups["labs"]["total"] >= 1


def test_word_matches_do_not_wait_for_embeddings(client, monkeypatch):
    monkeypatch.setenv("OPENAI_CATALOG_SEARCH_ENABLED", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    def fail(*_args, **_kwargs):
        raise AssertionError("word matching must not call the embedding API")

    monkeypatch.setattr("dashboard.backend.semantic._embed_texts", fail)
    payload = client.get_json("/api/search?q=alpha&stage=lexical")
    assert payload["mode"] == "local"
    assert payload["semantic_enabled"] is True
    assert "hybrid" in payload["pending"]
    assert client.request("/api/search?q=alpha&stage=sideways").status == 400


def test_notes_appear_in_search_scope(client):
    payload = client.get_json("/api/search?q=Boundary&scope=notes")
    assert payload["scope"] == "notes"
    groups = {group["key"]: group for group in payload["groups"]}
    assert "notes" in groups
    assert groups["notes"]["total"] >= 1
