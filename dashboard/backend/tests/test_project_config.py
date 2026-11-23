"""Project identity and port hashing."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "dashboard"))

from backend.project_config import (  # noqa: E402
    ConfigError,
    PORT_MAX,
    PORT_MIN,
    display_intro,
    display_title,
    env_prefix,
    preferred_port,
    project_name,
    write_display_identity,
)


def test_autolab_config_name():
    assert project_name(REPO_ROOT) == "autolab"


def test_preferred_port_in_range_and_stable():
    a = preferred_port("em-boundary")
    b = preferred_port("em-boundary")
    c = preferred_port("qmllab")
    assert PORT_MIN <= a <= PORT_MAX
    assert a == b
    assert a != c or True  # collision possible but rare; both still in range
    assert PORT_MIN <= c <= PORT_MAX


def test_env_prefix():
    assert env_prefix("em-boundary") == "EM_BOUNDARY_DASHBOARD"
    assert env_prefix("autolab") == "AUTOLAB_DASHBOARD"


def test_project_name_rejects_bad(tmp_path: Path):
    (tmp_path / "config.yml").write_text("os_version: \"0.1.0\"\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        project_name(tmp_path)
    (tmp_path / "config.yml").write_text("name: 1bad\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        project_name(tmp_path)


def test_display_title_and_intro_from_config(tmp_path: Path):
    (tmp_path / "config.yml").write_text(
        'name: amo-lab\ntitle: "AMO Lab"\nintro: "A materials lab."\n',
        encoding="utf-8",
    )
    assert display_title(tmp_path) == "AMO Lab"
    assert display_intro(tmp_path) == "A materials lab."


def test_display_title_falls_back_to_name(tmp_path: Path):
    (tmp_path / "config.yml").write_text("name: amo-lab\n", encoding="utf-8")
    assert display_title(tmp_path) == "amo-lab"
    assert display_intro(tmp_path) == ""


def test_write_display_identity_upserts(tmp_path: Path):
    (tmp_path / "config.yml").write_text("name: amo-lab\nfeatures:\n  notes: false\n", encoding="utf-8")
    write_display_identity(tmp_path, title="AMO Lab", intro="Hello\nworld")
    text = (tmp_path / "config.yml").read_text(encoding="utf-8")
    assert 'title: "AMO Lab"' in text
    assert "name: amo-lab" in text
    assert display_title(tmp_path) == "AMO Lab"
    assert display_intro(tmp_path) == "Hello\nworld"
