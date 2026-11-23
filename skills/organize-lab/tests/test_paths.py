"""Tests for labs/_tools/paths.py."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
TOOLS = ROOT / "labs" / "_tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import paths  # noqa: E402


@pytest.fixture()
def repo(tmp_path, monkeypatch):
    lab = tmp_path / "labs" / "2026-01-01-alpha"
    (lab / "results").mkdir(parents=True)
    monkeypatch.setattr(paths, "REPOSITORY", tmp_path)
    monkeypatch.setattr(paths, "LABS", tmp_path / "labs")
    return tmp_path, lab


def test_lab_place_routes_pkl_to_data(repo):
    root, lab = repo
    src = lab / "results" / "weights.pkl"
    out = paths.lab_place(src, create_parent=True)
    assert out == root / "labs" / "2026-01-01-alpha" / "data" / "weights.pkl"
    assert out.parent.is_dir()


def test_lab_run_file_sorts_params(repo):
    _, lab = repo
    out = paths.lab_run_file(lab / "results", "metrics", "jsonl", seed=1, h=64)
    assert out.name == "metrics_h64_seed1.jsonl"


def test_lab_output_combines_layout_and_name(repo):
    root, lab = repo
    out = paths.lab_output(lab, "metrics", "jsonl", category="results", seed=2, h=8)
    assert out.parent == root / "labs" / "2026-01-01-alpha" / "results"
    assert out.name == "metrics_h8_seed2.jsonl"


def test_truncate_for_run_clears(tmp_path):
    path = tmp_path / "out.jsonl"
    path.write_text("old\n")
    paths.truncate_for_run(path)
    assert path.read_text() == ""
    path.write_text("kept\n")
    paths.truncate_for_run(path, resume=True)
    assert path.read_text() == "kept\n"


def test_require_absent_refuses_existing(tmp_path):
    path = tmp_path / "summary.json"
    path.write_text("{}")
    with pytest.raises(SystemExit):
        paths.require_absent(path)