"""AST-based API extraction on the emb fixture package: nothing is imported."""
from __future__ import annotations

import sys

import pytest
from conftest import PACKAGE

from dashboard.backend.apidoc import ApiDocs


@pytest.fixture(scope="module")
def docs(repo_root) -> ApiDocs:
    return ApiDocs(PACKAGE, repo_root / "lib" / "src" / PACKAGE)


def test_package_is_parsed_not_imported(docs, repo_root):
    before = {name for name in sys.modules if name == PACKAGE or name.startswith(PACKAGE + ".")}
    for name in list(before):
        sys.modules.pop(name, None)
    tree = docs.tree(False, repo_root)
    assert tree["available"] is True
    assert tree["package"] == "emb"
    after = {name for name in sys.modules if name == PACKAGE or name.startswith(PACKAGE + ".")}
    assert not after, after


def test_tree_lists_core(docs, repo_root):
    public = docs.tree(False, repo_root)
    by_name = {module["name"]: module for module in public["modules"]}
    assert "emb" in by_name
    assert "emb.core" in by_name
    assert by_name["emb"]["is_package"] is True
    assert by_name["emb.core"]["classes"] >= 1
    assert by_name["emb.core"]["functions"] >= 1


def test_module_docstring_and_widget(docs, repo_root):
    core = docs.module("emb.core", False, repo_root)
    assert core["source"].endswith(f"lib/src/{PACKAGE}/core.py")
    assert "Widget" in core["summary"] or "widget" in core["summary"].casefold()
    widget = next(cls for cls in core["classes"] if cls["name"] == "Widget")
    assert "size" in (widget.get("signature") or "")
    methods = {method["name"] for method in widget.get("methods") or []}
    assert "double" in methods
    function_names = {fn["name"] for fn in core["functions"]}
    assert "make_widget" in function_names


def test_search_finds_widget(docs, repo_root):
    results = docs.search("widget", include_private=False, limit=20)
    assert results
    assert any("Widget" in item.get("qualname", "") or "widget" in item.get("qualname", "").casefold()
               for item in results)
