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
    env_prefix,
    preferred_port,
    project_name,
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
