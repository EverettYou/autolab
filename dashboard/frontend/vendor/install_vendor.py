#!/usr/bin/env python3
"""Install pinned dashboard frontend vendor libraries from manifest.json.

Downloadable packages (mermaid, katex, pdfjs, marked, dompurify, highlight) are
not tracked in git. Project-owned trees (code-editor, fontawesome) stay in-repo.

Usage (from repo root or any cwd):
  python3 dashboard/frontend/vendor/install_vendor.py
  python3 dashboard/frontend/vendor/install_vendor.py --force
  python3 dashboard/frontend/vendor/install_vendor.py --check

Exit: 0 ok, 1 failure, 2 usage.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

VENDOR_DIR = Path(__file__).resolve().parent
MANIFEST_PATH = VENDOR_DIR / "manifest.json"
STAMP_NAME = ".installed"
UA = "autolab-install-vendor/1.0"


def die(msg: str, code: int = 1) -> None:
    print(f"install_vendor: {msg}", file=sys.stderr)
    raise SystemExit(code)


def load_manifest() -> dict:
    if not MANIFEST_PATH.is_file():
        die(f"missing {MANIFEST_PATH}")
    try:
        data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        die(f"cannot read manifest: {exc}")
    if not isinstance(data.get("packages"), dict) or not data["packages"]:
        die("manifest has no packages")
    return data


def manifest_digest(manifest: dict) -> str:
    """Stable hash of package pins (ignores description)."""
    payload = json.dumps(
        {"schema": manifest.get("schema"), "packages": manifest["packages"]},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def download(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            return resp.read()
    except (urllib.error.URLError, OSError) as exc:
        # macOS system Python often lacks certs; curl usually works.
        try:
            return subprocess.check_output(
                ["curl", "-fsSL", "--retry", "3", "-A", UA, url],
                timeout=180,
            )
        except (OSError, subprocess.CalledProcessError) as curl_exc:
            die(f"download failed for {url}: {exc}; curl fallback: {curl_exc}")


def markers_ok(pkg: dict) -> bool:
    for rel in pkg.get("markers") or []:
        path = VENDOR_DIR / rel
        if not path.is_file():
            return False
    return True


def stamp_path() -> Path:
    return VENDOR_DIR / STAMP_NAME


def stamp_ok(digest: str) -> bool:
    path = stamp_path()
    if not path.is_file():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return data.get("manifest_sha256") == digest


def write_stamp(digest: str, packages: list[str]) -> None:
    stamp_path().write_text(
        json.dumps(
            {"manifest_sha256": digest, "packages": packages},
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def write_file(rel: str, data: bytes) -> None:
    dest = VENDOR_DIR / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(dest)


def install_files(pkg: dict) -> None:
    for entry in pkg.get("files") or []:
        url = entry["url"]
        expected = entry["sha256"]
        rel = entry["path"]
        print(f"  fetch {rel}")
        data = download(url)
        got = sha256_bytes(data)
        if got != expected:
            die(f"hash mismatch for {rel}: expected {expected}, got {got}")
        write_file(rel, data)


def install_npm_tarball(pkg: dict) -> None:
    url = pkg["url"]
    expected = pkg["sha256"]
    print(f"  fetch tarball {url}")
    data = download(url)
    got = sha256_bytes(data)
    if got != expected:
        die(f"hash mismatch for {url}: expected {expected}, got {got}")

    with tempfile.TemporaryDirectory(prefix="autolab-vendor-") as tmp:
        tmp_path = Path(tmp)
        tgz = tmp_path / "pkg.tgz"
        tgz.write_bytes(data)
        extract_root = tmp_path / "extract"
        extract_root.mkdir()
        with tarfile.open(tgz, mode="r:gz") as tf:
            # Python 3.12+ supports filter=; use data filter when available.
            kwargs = {}
            if hasattr(tarfile, "data_filter"):
                kwargs["filter"] = "data"
            tf.extractall(extract_root, **kwargs)

        for mapping in pkg.get("map") or []:
            src = extract_root / mapping["from"]
            dest = VENDOR_DIR / mapping["to"]
            if not src.exists():
                die(f"extracted package missing {mapping['from']}")
            if dest.exists():
                if dest.is_dir():
                    shutil.rmtree(dest)
                else:
                    dest.unlink()
            dest.parent.mkdir(parents=True, exist_ok=True)
            print(f"  place {mapping['to']}")
            if src.is_dir():
                shutil.copytree(src, dest)
            else:
                shutil.copy2(src, dest)


def install_package(name: str, pkg: dict) -> None:
    kind = pkg.get("kind")
    print(f"install_vendor: {name} {pkg.get('version', '')}".rstrip())
    if kind == "files":
        install_files(pkg)
    elif kind == "npm_tarball":
        install_npm_tarball(pkg)
    else:
        die(f"unknown kind for {name}: {kind}")
    if not markers_ok(pkg):
        die(f"{name}: markers still missing after install")


def missing_packages(manifest: dict) -> list[str]:
    return [n for n, p in manifest["packages"].items() if not markers_ok(p)]


def run_check(manifest: dict) -> int:
    digest = manifest_digest(manifest)
    bad = []
    for name, pkg in manifest["packages"].items():
        if not markers_ok(pkg):
            bad.append(f"{name}: missing markers")
    if bad:
        for line in bad:
            print(f"install_vendor: check fail: {line}", file=sys.stderr)
        return 1
    if not stamp_ok(digest):
        # Markers present is enough for --check; stamp is a convenience for skip logic.
        print("install_vendor: check ok (stamp missing or stale; markers present)")
        return 0
    print("install_vendor: check ok")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="re-download every package")
    parser.add_argument("--check", action="store_true", help="verify install; do not download")
    args = parser.parse_args(argv)

    manifest = load_manifest()
    if args.check:
        return run_check(manifest)

    digest = manifest_digest(manifest)
    if args.force:
        todo = list(manifest["packages"])
    else:
        todo = missing_packages(manifest)
        if not todo:
            if not stamp_ok(digest):
                write_stamp(digest, sorted(manifest["packages"]))
                print("install_vendor: markers present; wrote stamp")
            else:
                print("install_vendor: already installed")
            return 0

    print(f"install_vendor: installing {', '.join(todo)}")
    try:
        for name in todo:
            install_package(name, manifest["packages"][name])
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 — surface any unexpected failure clearly
        die(str(exc))

    write_stamp(digest, sorted(manifest["packages"]))
    print("install_vendor: done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
