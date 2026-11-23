"""Tests for skills/auto-research/scripts/fs_health_lint.py (run with .venv/bin/pytest)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "fs_health_lint.py"

spec = importlib.util.spec_from_file_location("fs_health_lint", SCRIPT)
lint = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lint)


def touch(root: Path, rel: str) -> None:
    path = root / rel
    if rel.endswith("/"):
        path.mkdir(parents=True, exist_ok=True)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x\n", encoding="utf-8")


@pytest.fixture
def root(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setattr(lint, "tracked", lambda root, names: {})
    for rel in ("README.md", "labs/", "wiki/", ".auto-research/", "skills/",
                "references/", "notes/", "dashboard/", ".claude/settings.local.json",
                "lib/README.md", "lib/pyproject.toml", "lib/hatch_build.py",
                "lib/uv.lock", "lib/tests/test_x.py", "lib/src/mypkg/__init__.py",
                "lib/src/mypkg/algorithms/_data/bb.txt",
                "lib/src/mypkg/solvers/__pycache__/results/", "lib/mypkg.egg-info/"):
        touch(tmp_path, rel)
    return tmp_path


def run(root: Path, capsys) -> tuple[int, str]:
    code = lint.main(["--root", str(root)])
    return code, capsys.readouterr().out


def test_clean_tree_passes(root, capsys):
    code, out = run(root, capsys)
    assert code == 0, out
    assert "fs_health_lint: PASS" in out and "WARN" not in out


@pytest.mark.parametrize("planted, message", [
    ("project.json", "project.json is retired"),
    ("run_dashboard.sh", "run_dashboard.sh is retired"),
    ("TODO.md", "TODO.md is retired"),
    ("STEERING.md", "STEERING.md is retired"),
    ("VERSION", "VERSION is retired"),
    ("discussion/", "discussion/ is retired"),
    ("archive/old.md", "archive/ is retired"),
    ("lab/2026-01-01-x/README.md", "lab/ is retired"),
    ("projects/qecbench/README.md", "projects/ is retired"),
    ("scripts/cleanup.sh", "root scripts/ holds cleanup.sh"),
    ("lib/scripts/run_all.py", "lib/scripts/ exists"),
    ("lib/docs/index.md", "package documentation lives in wiki/"),
    ("lib/stray.py", "stray .py under lib/"),
    ("lib/src/mypkg/solvers/run.py", "experiment script inside the package"),
    ("lib/src/mypkg/training/report.md", "report inside the package"),
    ("lib/src/mypkg/solvers/results/", "experiment output directory"),
    ("lib/src/mypkg/evaluators/data/", "data/ directory inside the package"),
    ("lib/src/mypkg/solvers/model.pt", "model weights inside the package"),
    ("lib/src/mypkg/evaluators/bayesian/priors/graphmp_oneshot_lp20_v1.json", "non-source file inside the package"),
])
def test_violations_fail(root, capsys, planted, message):
    touch(root, planted)
    code, out = run(root, capsys)
    assert code == 1
    assert message in out and "fs_health_lint: FAIL (1 violation(s))" in out


def test_unknown_entries_only_warn(root, capsys):
    touch(root, "results/")
    touch(root, "lib/notebooks/")
    code, out = run(root, capsys)
    assert code == 0
    assert "WARN: non-standard top-level entry: results/" in out
    assert "WARN: non-standard entry under lib/: notebooks" in out


def test_tracked_tool_local_files_fail(root, capsys, monkeypatch):
    monkeypatch.setattr(lint, "tracked", lambda root, names: {".claude": 3})
    code, out = run(root, capsys)
    assert code == 1 and ".claude/ has 3 tracked file(s)" in out


def test_absent_lib_is_optional_warning(root, capsys):
    import shutil
    shutil.rmtree(root / "lib")
    code, out = run(root, capsys)
    assert code == 0
    assert "lib/ is absent" in out


def test_empty_src_passes(root, capsys):
    import shutil
    shutil.rmtree(root / "lib" / "src" / "mypkg")
    touch(root, "lib/src/.gitkeep")
    code, out = run(root, capsys)
    assert code == 0, out
    assert "lib/src/ is empty" in out


def test_bundled_code_data_and_build_files_pass(root, capsys):
    for rel in ("lib/src/mypkg/algorithms/_data/table.json", "lib/src/mypkg/solvers/_k.pyx",
                "lib/src/mypkg/solvers/_k.c", "lib/src/mypkg/py.typed"):
        touch(root, rel)
    code, out = run(root, capsys)
    assert code == 0, out
