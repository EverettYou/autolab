"""Project identity and dashboard port allocation from ``config.yml``.

Identity: ``config.yml`` → ``name`` (required slug). Display title lives only in
``dashboard/frontend/site.json``. Same ``name`` = same project across checkouts.

Port: unless overridden by env/config, ``hash(name)`` maps into ``[1024, 65535]``,
then linear-probe (+1, wrap) until free or reclaimable by the same ``name``.
"""
from __future__ import annotations

import hashlib
import json
import re
import socket
import urllib.error
import urllib.request
from pathlib import Path

NAME_RE = re.compile(r"^[a-z][a-z0-9-]{0,62}$")
PORT_MIN = 1024
PORT_MAX = 65535
PORT_SPAN = PORT_MAX - PORT_MIN + 1  # 64512
_YAML_UNSET = frozenset({"null", "none", "~", "true", "false"})


class ConfigError(ValueError):
    """Invalid or missing project config."""


def _grab(text: str, pattern: str, default: str = "") -> str:
    match = re.search(pattern, text, re.M)
    return match.group(1) if match else default


def read_config_text(root: Path) -> str:
    path = root / "config.yml"
    if not path.is_file():
        raise ConfigError(f"missing config.yml under {root}")
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"cannot read config.yml: {exc}") from exc


def project_name(root: Path | None = None, *, text: str | None = None) -> str:
    """Required stable project identity slug from ``config.yml`` → ``name``."""
    body = text if text is not None else read_config_text(Path(root or ".").resolve())
    raw = _grab(body, r"(?m)^\s*name:\s*[\"']?([A-Za-z][A-Za-z0-9_-]*)[\"']?\s*$").strip()
    name = raw.lower().replace("_", "-")
    if not name or name in _YAML_UNSET or not NAME_RE.match(name):
        raise ConfigError(
            "config.yml must set name: <slug> (lowercase letters, digits, hyphens; "
            "start with a letter; max 63 chars)"
        )
    return name


def env_prefix(name: str) -> str:
    """Derive env var prefix from ``name`` (not config). E.g. ``em-boundary`` → ``EM_BOUNDARY_DASHBOARD``."""
    stem = re.sub(r"[^A-Z0-9]+", "_", name.upper()).strip("_") or "LAB"
    return f"{stem}_DASHBOARD"


def optional_config_port(text: str) -> int | None:
    raw = _grab(text, r"(?m)^\s*port:\s*(\d+)\s*$")
    if not raw:
        return None
    port = int(raw)
    if port < 1 or port > 65535:
        raise ConfigError(f"config dashboard.port out of range: {port}")
    return port


def preferred_port(name: str) -> int:
    """Deterministic base port in ``[PORT_MIN, PORT_MAX]`` from project name."""
    digest = hashlib.sha256(name.encode("utf-8")).digest()
    value = int.from_bytes(digest[:8], "big")
    return PORT_MIN + (value % PORT_SPAN)


def _probe_target(host: str) -> tuple[str, int]:
    mapped = {"0.0.0.0": "127.0.0.1", "": "127.0.0.1", "::": "::1"}.get(host, host)
    family = socket.AF_INET6 if ":" in mapped else socket.AF_INET
    return mapped, family


def port_occupancy(host: str, port: int, name: str) -> str:
    """Classify a port relative to this project name.

    Returns:
      ``free`` — nothing listening
      ``ours`` — a lab dashboard health endpoint with the same ``name``
      ``other`` — listening but not reclaimable (other project or non-dashboard)
    """
    target, family = _probe_target(host)
    with socket.socket(family, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.4)
        if sock.connect_ex((target, port)) != 0:
            return "free"
    shown = f"[{target}]" if ":" in target else target
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(f"http://{shown}:{port}/api/health", timeout=1.5) as response:
            data = json.load(response)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError, ValueError):
        return "other"
    got = str(data.get("name") or "").strip().lower()
    if got and got == name:
        return "ours"
    return "other"


def resolve_port(name: str, host: str = "127.0.0.1", *, override: int | None = None) -> int:
    """Pick a port for this project: override if given, else hash + linear probe."""
    if override is not None:
        if override < 1 or override > 65535:
            raise ConfigError(f"port override out of range: {override}")
        kind = port_occupancy(host, override, name)
        if kind in {"free", "ours"}:
            return override
        raise ConfigError(
            f"port {override} is in use by another process (not project {name!r})"
        )
    base = preferred_port(name)
    for step in range(PORT_SPAN):
        port = PORT_MIN + ((base - PORT_MIN + step) % PORT_SPAN)
        kind = port_occupancy(host, port, name)
        if kind in {"free", "ours"}:
            return port
    raise ConfigError(f"no free dashboard port in {PORT_MIN}-{PORT_MAX} for project {name!r}")


def health_listener(host: str, port: int, name: str) -> int | None:
    """Return PID if ``port`` serves this project's dashboard; else None."""
    target, family = _probe_target(host)
    with socket.socket(family, socket.SOCK_STREAM) as sock:
        sock.settimeout(1.0)
        if sock.connect_ex((target, port)) != 0:
            return None
    shown = f"[{target}]" if ":" in target else target
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(f"http://{shown}:{port}/api/health", timeout=3) as response:
            data = json.load(response)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError, ValueError):
        return None
    got = str(data.get("name") or "").strip().lower()
    if got != name:
        return None
    pid = data.get("pid")
    return pid if isinstance(pid, int) else None
