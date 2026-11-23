#!/usr/bin/env python3
"""Check labs against the layout and move stray files into place.

    python3 skills/organize-lab/scripts/lab_layout.py check [LAB_ID ...] [--links] [--imports] [--json]
    python3 skills/organize-lab/scripts/lab_layout.py tidy LAB_ID [LAB_ID ...] [--apply] [--rename-only]
    python3 skills/organize-lab/scripts/lab_layout.py move LAB_ID SRC DST [--apply]
    python3 skills/organize-lab/scripts/lab_layout.py track LAB_ID PATH [PATH ...]

check  Report labs that differ from the layout in ../references/report-contract.md; exit 1 when any
       does. --links also lists references to lab files, anywhere in the repository, that do not
       resolve; --imports lists Python imports that neither the virtual environment nor the
       directories the file puts on sys.path provide.
tidy   Plan the moves that bring a lab into the layout and print them. With --apply, perform them:
       git mv for tracked files, adjust __file__-based paths in moved scripts, rewrite references to
       the moved files across the repository, keep moved tracked files tracked through the lab's
       .gitignore, drop retired lab.json keys, and rebuild labs/labs.json. --rename-only limits the
       plan to report.md -> REPORT.md. In any Python file, sys.path entries that name a lab root
       whose code is now in scripts/ are pointed at scripts/.
move   Move one file or directory inside a lab (for example a design note promoted to PLAN.md) and
       rewrite the references to it.
track  Add exceptions to the lab's .gitignore so that the named lab files are tracked.

tidy and move refuse a lab while it runs: a live process names it, or a file in it changed in the
last 30 minutes (--allow-recent skips the second test). --apply needs a preview first (the same
command without --apply) and skips files that changed after the preview. Files inside --protect
labs and under notes/ are never edited; references there that would change are listed instead.
Lines that cannot be adjusted safely are printed for review.

Exit codes: 0 ok, 1 findings, refusals, or review items, 2 usage error.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import posixpath
import re
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path, PurePosixPath
from urllib.parse import unquote

sys.path.insert(0, str(Path(__file__).resolve().parent))
import labs_catalog  # noqa: E402

RECENT_SECONDS = 30 * 60
MAX_TEXT_BYTES = 8 << 20
NEVER_EDIT = ("notes/",)
NOTES = "notes"

CODE_SUFFIXES = frozenset({".py", ".sh", ".bash", ".g", ".jl", ".ipynb", ".sage"})
DOC_SUFFIXES = frozenset({".md", ".tex", ".bib", ".pdf", ".rst"})
LOG_SUFFIXES = frozenset({".log", ".out", ".err", ".pid", ".lock"})
FIGURE_SUFFIXES = frozenset({".png", ".svg", ".jpg", ".jpeg", ".gif"})
WEIGHT_SUFFIXES = frozenset({".pt", ".pth", ".ckpt", ".safetensors"})
CONFIG_SUFFIXES = frozenset({".yaml", ".yml", ".toml", ".ini", ".cfg"})
OUTPUT_SUFFIXES = frozenset({".json", ".jsonl", ".csv", ".tsv", ".txt", ".npz", ".npy", ".h5", ".parquet", ".pkl"})
RECORD_DIRS = frozenset({"results", "data", "logs", "checkpoints"})
RECORD_SUFFIXES = LOG_SUFFIXES | {".csv", ".tsv", ".jsonl"}
TRANSCRIPTION_MARK = "> Transcribed verbatim"
CONFIG_NAME_RE = re.compile(r"(^|[_-])(queue|mix\d*|candidates|requirements)([_-]|$)", re.IGNORECASE)

DOC_MERGE_DIRS = frozenset({"docs", "doc", "note"})
DOC_UNIT_DIRS = frozenset({"design", "theory", "paper", "writeup", "draft"})
WEIGHT_DIRS = frozenset({"weights", "models", "ckpt", "ckpts"})
RESULT_DIRS = frozenset({"registry_payloads", "outputs", "output", "out"})
CONFIG_DIRS = frozenset({"anchors", "queues"})
CODE_DIRS = frozenset({"src", "lib", "tools", "utils", "search", "solvers", "simulators", "ref"})

LAB_ID_TOKEN = re.compile(r"(?<![\w.-])(?P<id>\d{4}-\d{2}-\d{2}-[A-Za-z0-9._-]+?)/(?P<path>[^\s'\"`()<>\[\]{}|,;:#*?]+)")
MD_LINK = re.compile(r"(?P<head>!?\[[^\]]*\]\(\s*<?)(?P<target>[^)\s>]+)(?P<tail>>?(?:\s+\"[^\"]*\")?\s*\))")
MD_REFDEF = re.compile(r"^(?P<head>\s{0,3}\[[^\]]+\]:\s*<?)(?P<target>[^\s>]+)(?P<tail>.*)$")
FENCE = re.compile(r"^\s*(```|~~~)")

PY_ANCHOR = re.compile(
    r"(?P<base>(?:pathlib\.|__import__\(\s*['\"]pathlib['\"]\s*\)\.)?Path\(\s*__file__\s*\)"
    r"(?:\.resolve\(\s*\)|\.absolute\(\s*\))*)"
    r"(?P<nav>\.parents\[\s*(?P<n>\d+)\s*\]|(?:\.parent(?![\w(]))+)?"
)
PY_WITH_NAME = re.compile(r"\.with_name\(\s*(?P<q>['\"])(?P<name>[^'\"]+)(?P=q)\s*\)")
OS_ANCHOR = re.compile(r"os\.path\.dirname\(\s*(?:__file__|os\.path\.(?:abspath|realpath)\(\s*__file__\s*\))\s*\)")
OS_ROOT_RHS = re.compile(r"^((?:os\.path\.dirname\(\s*)+)(?:__file__|os\.path\.(?:abspath|realpath)\(\s*__file__\s*\))(\s*\))+$")
BARE_FILE = re.compile(r"(?<![\w.])__file__")
PY_ASSIGN = re.compile(r"^\s*(?P<var>[A-Za-z_]\w*)\s*(?::[^=]+)?=\s*(?P<rhs>[^#\n]+?)\s*(?:#.*)?$")

SH_SELF = r"(?:\"\$(?:0|\{0\}|\{BASH_SOURCE(?:\[0\])?\}|BASH_SOURCE(?:\[0\])?)\"|\$(?:0|\{0\}|\{BASH_SOURCE(?:\[0\])?\}|BASH_SOURCE(?:\[0\])?))"
SH_DIRNAME = re.compile(r"(?P<core>\$\(\s*dirname\s+" + SH_SELF + r"\s*\))(?P<ups>(?:/\.\.)*)")
SH_ASSIGN = re.compile(r"^\s*(?:export\s+|local\s+|readonly\s+)?(?P<var>[A-Za-z_]\w*)=(?P<val>.*)$")
SH_PATH_CHARS = r"[^\s\"'`;|&()<>$]+"
SH_CD = re.compile(r"(?:^|&&|;|\|\||\()\s*cd\s+")
SH_ARG_END = r"['\"]?(?=\s|$|;|&|\||\))"
SH_BARE = re.compile(r"(?<![\w/.$}{-])(?P<lit>[\w.-]+(?:/[\w.-]+)*)(?![\w/.-])")
# Templates over the names of variables that hold __file__-based directories ({names}).
PY_VAR_NAV = (r"(?<![\w.])(?P<var>{names})(?P<res>(?:\.resolve\(\s*\)|\.absolute\(\s*\))*)"
              r"(?P<nav>\.parents\[\s*(?P<n>\d+)\s*\]|(?:\.parent(?![\w(]))+)")
PY_VAR_PLAIN = r"(?P<pre>(?:os\.path\.dirname\(\s*)*)(?P<var>{names})(?:\.resolve\(\s*\)|\.absolute\(\s*\))*(?:\s*\))*"
OS_VAR_DIRNAME = r"(?P<pre>(?:os\.path\.dirname\(\s*)+)(?P<var>{names})(?=\s*\))"
SH_VAR_UPS = r"\$(?:\{{(?P<v1>{names})\}}|(?P<v2>{names})(?!\w))(?P<ups>(?:/\.\.)+)"


@dataclass(frozen=True)
class Move:
    src: str  # lab-relative
    dst: str
    reason: str
    is_dir: bool = False


@dataclass
class Outcome:
    moved: dict[str, list[Move]] = field(default_factory=dict)
    refused: dict[str, list[str]] = field(default_factory=dict)
    review: list[str] = field(default_factory=list)
    edited: dict[str, int] = field(default_factory=dict)
    left: list[str] = field(default_factory=list)
    tracked: dict[str, list[str]] = field(default_factory=dict)


# --- git and file helpers ---------------------------------------------------------------------

def git(repo: Path, *args: str, stdin: bytes | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], input=stdin, capture_output=True, check=True)


def ls_files(repo: Path, *args: str) -> list[str]:
    try:
        out = git(repo, "ls-files", "-z", *args).stdout.decode("utf-8", "surrogateescape")
    except (OSError, subprocess.CalledProcessError):
        return []
    return [p for p in out.split("\0") if p]


def ignored(repo: Path, paths: list[str]) -> set[str]:
    """Which repo-relative paths the ignore rules exclude (tracked or not)."""
    if not paths:
        return set()
    proc = subprocess.run(
        ["git", "-C", str(repo), "check-ignore", "--no-index", "--stdin", "-z"],
        input="\0".join(paths).encode("utf-8", "surrogateescape"), capture_output=True,
    )
    return {p for p in proc.stdout.decode("utf-8", "surrogateescape").split("\0") if p}


def state_dir(repo: Path) -> Path:
    return repo / ".tmp" / "lab-layout"


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def record_own_write(repo: Path, rel: str) -> None:
    path = state_dir(repo) / "own-writes.json"
    data = load_json(path, {})
    try:
        data[rel] = (repo / rel).stat().st_mtime_ns
    except OSError:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1, sort_keys=True), encoding="utf-8")


def write_text(repo: Path, rel: str, text: str) -> None:
    (repo / rel).write_text(text, encoding="utf-8")
    record_own_write(repo, rel)


def read_text(path: Path) -> str | None:
    try:
        if path.stat().st_size > MAX_TEXT_BYTES:
            return None
        raw = path.read_bytes()
    except OSError:
        return None
    if b"\0" in raw[:8192]:
        return None
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return None


def depth(rel: str) -> int:
    """Number of directories between the lab root and a lab-relative file."""
    return len(PurePosixPath(rel).parent.parts)


def signature(path: Path) -> str:
    if path.is_dir():
        files = [p for p in path.rglob("*") if p.is_file()]
        newest = max((p.stat().st_mtime_ns for p in files), default=0)
        return f"dir:{len(files)}:{sum(p.stat().st_size for p in files)}:{newest}"
    return hashlib.sha256(path.read_bytes()).hexdigest()


# --- planning ---------------------------------------------------------------------------------

def file_destination(path: Path, names: set[str]) -> tuple[str | None, str]:
    name, suffix = path.name, path.suffix.lower()
    if name == "README.md":
        return f"{NOTES}/overview.md", "README retired"
    if name.lower() == "plan.md" and labs_catalog.PLAN not in names:
        return labs_catalog.PLAN, "plan name"
    if suffix in DOC_SUFFIXES:
        return f"{NOTES}/{name}", "document"
    if suffix in CODE_SUFFIXES:
        return f"scripts/{name}", "code"
    if suffix in LOG_SUFFIXES:
        return f"logs/{name}", "log"
    if suffix in FIGURE_SUFFIXES:
        return f"figures/{name}", "figure"
    if suffix in WEIGHT_SUFFIXES or name.endswith((".pt.bak", ".pth.bak")):
        return f"checkpoints/{name}", "weights"
    if suffix in CONFIG_SUFFIXES or (suffix in OUTPUT_SUFFIXES and CONFIG_NAME_RE.search(path.stem)):
        return f"configs/{name}", "input"
    if suffix in OUTPUT_SUFFIXES:
        if path.stat().st_size > labs_catalog.MAX_TRACKED_BYTES:
            return f"data/{name}", "output over 1 MB"
        return f"results/{name}", "output"
    return None, "unknown file type"


def dir_destination(path: Path, names: set[str]) -> tuple[str, str]:
    name = path.name
    if name in DOC_MERGE_DIRS:
        return NOTES, "documents"
    if name in DOC_UNIT_DIRS:
        return f"{NOTES}/{name}", "documents"
    if name in WEIGHT_DIRS:
        return ("checkpoints" if "checkpoints" not in names else f"checkpoints/{name}"), "weights"
    if name in RESULT_DIRS:
        return f"results/{name}", "outputs"
    if name in CONFIG_DIRS:
        return f"configs/{name}", "inputs"
    files = [p for p in path.rglob("*") if p.is_file() and "__pycache__" not in p.parts]
    if name in CODE_DIRS or any(p.suffix.lower() in CODE_SUFFIXES for p in files):
        return f"scripts/{name}", "code" if all(p.suffix.lower() in CODE_SUFFIXES for p in files) else "sub-experiment with code"
    return f"data/{name}", "generated data"


def plan_lab(lab_dir: Path, *, rename_only: bool = False,
             tracked: set[str] | None = None) -> tuple[list[Move], list[str]]:
    """Moves that bring one lab into the layout, and lines left for review.

    Root entries outside the layout move to their directory. ``tracked`` (lab-relative files git
    tracks or would track) adds the files that break their directory's content rule, such as a
    figure under results/; each keeps its path below the directory it moves to.
    """
    entries = sorted(lab_dir.iterdir(), key=lambda p: p.name)
    names = {p.name for p in entries}
    moves: list[Move] = []
    review: list[str] = []
    claimed: set[str] = set()

    def claim(src: str, dst: str, reason: str, is_dir: bool = False) -> None:
        if dst in claimed or (lab_dir / dst).exists():
            review.append(f"{lab_dir.name}/{src}: {dst} already exists; left in place")
            return
        claimed.add(dst)
        moves.append(Move(src, dst, reason, is_dir))

    if labs_catalog.LEGACY_REPORT in names:
        if labs_catalog.REPORT in names:
            review.append(f"{lab_dir.name}: both report.md and REPORT.md exist; merge them by hand")
        else:
            claim(labs_catalog.LEGACY_REPORT, labs_catalog.REPORT, "report name")
    if rename_only:
        return moves, review
    for path in entries:
        name = path.name
        if name in labs_catalog.ROOT_FILES or name in labs_catalog.TRANSIENT or name == labs_catalog.LEGACY_REPORT:
            continue
        if path.is_symlink():
            review.append(f"{lab_dir.name}/{name}: symlink left in place")
            continue
        if path.is_dir():
            if name in labs_catalog.LAB_DIRS:
                continue
            dst, reason = dir_destination(path, names)
            if dst == NOTES and (NOTES in names or NOTES in claimed):
                for child in sorted(path.iterdir(), key=lambda p: p.name):
                    if child.name not in labs_catalog.TRANSIENT:
                        claim(f"{name}/{child.name}", f"{NOTES}/{child.name}", reason, child.is_dir())
            else:
                claim(name, dst, reason, True)
            continue
        dst, reason = file_destination(path, names)
        if dst is None:
            review.append(f"{lab_dir.name}/{name}: {reason}; left in place")
        else:
            claim(name, dst, reason)
    folders = labs_catalog.folder_suffixes(tracked or ())
    for rel in sorted(tracked or ()):
        placed = labs_catalog.content_destination(rel, labs_catalog._ancestor_suffixes(rel, folders))
        if placed is None or not (lab_dir / rel).is_file() or (lab_dir / rel).is_symlink():
            continue
        dst, reason = placed
        if dst is None:
            review.append(f"{lab_dir.name}/{rel}: {reason}; delete it or move it by hand")
        else:
            claim(rel, dst, f"{reason} under {PurePosixPath(rel).parts[0]}/")
    return moves, review


# --- move maps --------------------------------------------------------------------------------

class MoveMap:
    """Old -> new repo-relative paths for every move applied in one run."""

    def __init__(self) -> None:
        self.files: dict[str, str] = {}
        self.dirs: list[tuple[str, str]] = []
        self.by_lab: dict[str, list[tuple[str, str]]] = {}

    def add(self, lab_id: str, move: Move) -> None:
        old, new = f"labs/{lab_id}/{move.src}", f"labs/{lab_id}/{move.dst}"
        (self.dirs.append((old, new)) if move.is_dir else self.files.__setitem__(old, new))
        self.by_lab.setdefault(lab_id, []).append((move.src, move.dst))
        self.dirs.sort(key=lambda pair: len(pair[0]), reverse=True)
        self.by_lab[lab_id].sort(key=lambda pair: len(pair[0]), reverse=True)

    def __bool__(self) -> bool:
        return bool(self.files or self.dirs)

    def map(self, path: str) -> str:
        if path in self.files:
            return self.files[path]
        for old, new in self.dirs:
            if path == old or path.startswith(old + "/"):
                return new + path[len(old):]
        return path

    def inverse(self, path: str) -> str:
        for old, new in self.files.items():
            if new == path:
                return old
        for old, new in self.dirs:
            if path == new or path.startswith(new + "/"):
                return old + path[len(new):]
        return path

    def map_lab(self, lab_id: str, rel: str) -> str:
        rel = rel[2:] if rel.startswith("./") else rel
        for old, new in self.by_lab.get(lab_id, ()):
            if rel == old or rel.startswith(old + "/"):
                return new + rel[len(old):]
        return rel


# --- anchor patching for moved code -----------------------------------------------------------

def _alt(names) -> str:
    return "|".join(sorted(map(re.escape, names), key=len, reverse=True))


def _nav_levels(m: re.Match) -> int:
    if m.group("n") is not None:
        return int(m.group("n")) + 1
    return (m.group("nav") or "").count(".parent")


def _with_levels(m: re.Match, head: str, levels: int) -> str:
    return head + (f".parents[{levels - 1}]" if m.group("n") is not None else ".parent" * levels)


def _dirname_depth(s: str, start: int) -> int:
    """How many os.path.dirname( calls directly enclose position start."""
    n = 0
    while (m := re.search(r"os\.path\.dirname\(\s*$", s[:start])):
        n, start = n + 1, m.start()
    return n


def _closing(s: str, pos: int, count: int) -> int | None:
    """Position after `count` closing parentheses that follow pos."""
    for _ in range(count):
        m = re.compile(r"\s*\)").match(s, pos)
        if m is None:
            return None
        pos = m.end()
    return pos


def _note_py_levels(line: str, levels_of: dict[str, int]) -> None:
    """Record, from an assignment, how many levels above the file a variable pointed."""
    m = PY_ASSIGN.match(line)
    if not m:
        return
    var, rhs = m.group("var"), m.group("rhs").strip()
    names = _alt(levels_of) if levels_of else None
    if (am := PY_ANCHOR.fullmatch(rhs)):
        levels_of[var] = _nav_levels(am)
    elif (om := OS_ROOT_RHS.match(rhs)):
        levels_of[var] = om.group(1).count("os.path.dirname(")
    elif names and (dm := re.fullmatch(PY_VAR_NAV.format(names=names), rhs)):
        levels_of[var] = levels_of[dm.group("var")] + _nav_levels(dm)
    elif names and (dm := re.fullmatch(PY_VAR_PLAIN.format(names=names), rhs)):
        levels_of[var] = levels_of[dm.group("var")] + dm.group("pre").count("os.path.dirname(")
    else:
        levels_of.pop(var, None)


def _patch_py_derived(line: str, levels_of: dict[str, int], k: int, keep: int) -> str:
    """Navigation from a variable that stayed inside the moved directory but climbs out of it."""
    names = _alt(levels_of)

    def nav_sub(m: re.Match) -> str:
        c, n = levels_of[m.group("var")], _nav_levels(m)
        return _with_levels(m, m.group("var") + m.group("res"), n + k) if c <= keep < c + n else m.group(0)

    line = re.sub(PY_VAR_NAV.format(names=names), nav_sub, line)
    out, pos = [], 0
    for m in re.finditer(OS_VAR_DIRNAME.format(names=names), line):
        c, n = levels_of[m.group("var")], m.group("pre").count("os.path.dirname(")
        end = _closing(line, m.end(), n)
        if end is None or m.start() < pos or not c <= keep < c + n:
            continue
        out.append(line[pos:m.start()] + "os.path.dirname(" * k + line[m.start():end] + ")" * k)
        pos = end
    return "".join(out) + line[pos:]


def patch_python(text: str, k: int, new_rel: str, old_rel: str, lab_map, keep: int = 0) -> tuple[str, int, list[str]]:
    """Keep __file__-based paths pointing where they pointed before the file moved k levels down.

    A file that moved with its directory keeps the paths that stay inside that directory (`keep`
    levels up or fewer); navigation from a variable holding such a path is adjusted once it
    climbs out."""
    lines = text.splitlines(keepends=True)
    changes = 0
    review: list[str] = []
    new_depth = depth(new_rel)
    levels_of: dict[str, int] = {}
    for i, line in enumerate(lines):
        new = line
        in_sys_path = "sys.path" in line

        def py_sub(m: re.Match) -> str:
            nav = m.group("nav")
            if not nav:
                return m.group(0)
            levels = _nav_levels(m)
            if levels <= keep:
                return m.group(0)
            if in_sys_path and levels == 1 and m.string[m.end():].lstrip().startswith(")"):
                if depth(old_rel) == 0 and posixpath.dirname(new_rel) == "tests":
                    base = m.group("base") if m.group("base").endswith(".resolve()") else m.group("base") + ".resolve()"
                    return f'{base}.parents[{new_depth}] / "scripts"'
                return m.group(0)
            return _with_levels(m, m.group("base"), levels + k)

        def os_sub(m: re.Match) -> str:
            nested = m.string[: m.start()].rstrip().endswith("os.path.dirname(")
            if 1 + _dirname_depth(m.string, m.start()) <= keep:
                return m.group(0)
            if in_sys_path and not nested and m.string[m.end():].lstrip().startswith(")"):
                return m.group(0)
            out = m.group(0)
            for _ in range(k):
                out = f"os.path.dirname({out})"
            return out

        def with_name(m: re.Match) -> str:
            old_target = posixpath.normpath(posixpath.join(posixpath.dirname(old_rel), m.group("name")))
            new_target = lab_map(old_target)
            if posixpath.dirname(new_target) == posixpath.dirname(new_rel):
                return m.group(0)
            base = m.group("base") if m.group("base").endswith(".resolve()") else m.group("base") + ".resolve()"
            return f'{base}.parents[{new_depth}] / "{new_target}"'

        if "__file__" in line:
            new = PY_ANCHOR.sub(py_sub, line)
            new = OS_ANCHOR.sub(os_sub, new)
            new = re.sub(PY_ANCHOR.pattern + PY_WITH_NAME.pattern, with_name, new)
            handled = [m.span() for rx in (PY_ANCHOR, OS_ANCHOR) for m in rx.finditer(new)]
            if any(not any(a <= m.start() < b for a, b in handled) for m in BARE_FILE.finditer(new)):
                review.append(f"{new_rel}:{i + 1}: __file__ use not adjusted: {line.strip()[:160]}")
        if levels_of:
            new = _patch_py_derived(new, levels_of, k, keep)
        _note_py_levels(line, levels_of)
        if new != line:
            lines[i] = new
            changes += 1
    return "".join(lines), changes, review


def patch_shell(text: str, k: int, new_rel: str, keep: int = 0) -> tuple[str, int, list[str]]:
    """The shell counterpart of patch_python, for $(dirname "$0") paths and variables holding them."""
    lines = text.splitlines(keepends=True)
    changes = 0
    review: list[str] = []
    levels_of: dict[str, int] = {}

    def own_sub(m: re.Match) -> str:
        if 1 + m.group("ups").count("/..") <= keep:
            return m.group(0)
        return m.group("core") + m.group("ups") + "/.." * k

    def var_sub(m: re.Match) -> str:
        c, n = levels_of[m.group("v1") or m.group("v2")], m.group("ups").count("/..")
        return m.group(0) + "/.." * k if c <= keep < c + n else m.group(0)

    for i, line in enumerate(lines):
        new = line
        if SH_DIRNAME.search(line):
            new = SH_DIRNAME.sub(own_sub, line)
        elif re.search(r"\$\{?(0|BASH_SOURCE)", line) and re.search(r"dirname|readlink|realpath|cd\s", line):
            review.append(f"{new_rel}:{i + 1}: script-relative path not adjusted: {line.strip()[:160]}")
        names = _alt(levels_of) if levels_of else None
        if names:
            new = re.sub(SH_VAR_UPS.format(names=names), var_sub, new)
        if (a := SH_ASSIGN.match(line)):
            val = a.group("val").split(" #", 1)[0].strip()
            dm = SH_DIRNAME.search(val)
            vm = re.search(SH_VAR_UPS.format(names=names), val) if names else None
            if dm and not re.match(r"/[\w.]", val[dm.end():]):
                levels_of[a.group("var")] = 1 + dm.group("ups").count("/..")
            elif vm and not re.match(r"/[\w.]", val[vm.end():]):
                levels_of[a.group("var")] = levels_of[vm.group("v1") or vm.group("v2")] + vm.group("ups").count("/..")
            else:
                levels_of.pop(a.group("var"), None)
        if new != line:
            lines[i] = new
            changes += 1
    return "".join(lines), changes, review


# --- lab-relative literals in lab code --------------------------------------------------------

def _py_levels(m: re.Match) -> int | None:
    nav = m.group("nav")
    if not nav:
        return None
    return int(m.group("n")) + 1 if m.group("n") is not None else nav.count(".parent")


def rewrite_python_literals(text: str, file_rel: str, map_rel) -> tuple[str, int]:
    """Rewrite 'LAB / "old"' style literals, where LAB is the lab root, to the moved paths."""
    root_level = depth(file_rel) + 1
    root_vars: set[str] = set()
    for line in text.splitlines():
        m = PY_ASSIGN.match(line)
        if not m:
            continue
        rhs = m.group("rhs").strip()
        am = PY_ANCHOR.fullmatch(rhs)
        if am and _py_levels(am) == root_level:
            root_vars.add(m.group("var"))
        om = OS_ROOT_RHS.match(rhs)
        if om and om.group(1).count("os.path.dirname(") == root_level:
            root_vars.add(m.group("var"))
    changes = 0

    def swap(m: re.Match) -> str:
        nonlocal changes
        lit = m.group("lit")
        new = map_rel(lit)
        if new == (lit[2:] if lit.startswith("./") else lit):
            return m.group(0)
        changes += 1
        return m.group(0)[: m.start("lit") - m.start()] + new + m.group(0)[m.end("lit") - m.start():]

    lit = r"(?P<q>['\"])(?P<lit>[^'\"\n{}]+)(?P=q)"
    if root_vars:
        alt = "|".join(sorted(map(re.escape, root_vars), key=len, reverse=True))
        text = re.sub(rf"\b(?:{alt})\b\s*/\s*{lit}", swap, text)
        text = re.sub(rf"os\.path\.join\(\s*(?:{alt})\s*,\s*{lit}", swap, text)
        text = re.sub(rf"\b(?:{alt})\b\.joinpath\(\s*{lit}", swap, text)

    def inline(m: re.Match) -> str:
        return swap(m) if _py_levels(m) == root_level else m.group(0)

    text = re.sub(PY_ANCHOR.pattern + rf"\s*/\s*{lit}", inline, text)
    return text, changes


def rewrite_shell_literals(text: str, file_rel: str, lab_id: str, map_rel) -> tuple[str, int]:
    root_ups = depth(file_rel)
    root_vars: set[str] = set()
    lab_tail = re.compile(r"labs?/" + re.escape(lab_id) + r"/?[\"']?\s*$")
    for line in text.splitlines():
        m = SH_ASSIGN.match(line)
        if not m:
            continue
        val = m.group("val").split(" #", 1)[0].strip()
        dm = SH_DIRNAME.search(val)
        if dm and dm.group("ups").count("/..") == root_ups and not re.match(r"/[\w.]", val[dm.end():]):
            root_vars.add(m.group("var"))
        elif lab_tail.search(val):
            root_vars.add(m.group("var"))
    changes = 0

    def swap(m: re.Match) -> str:
        nonlocal changes
        lit = m.group("lit")
        core = lit.rstrip(".")
        new = map_rel(core)
        if new == core:
            return m.group(0)
        changes += 1
        return m.group(0)[: m.start("lit") - m.start()] + new + lit[len(core):]

    if root_vars:
        alt = "|".join(sorted(map(re.escape, root_vars), key=len, reverse=True))
        text = re.sub(rf"\$(?:\{{(?:{alt})\}}|(?:{alt})(?!\w))/(?P<lit>{SH_PATH_CHARS})", swap, text)

    def inline(m: re.Match) -> str:
        if m.group("ups").count("/..") != root_ups:
            return m.group(0)
        return swap(m)

    text = re.sub(SH_DIRNAME.pattern + rf"/(?P<lit>{SH_PATH_CHARS})", inline, text)

    def cd_target(line: str, pos: int) -> tuple[bool, int]:
        """Whether the cd argument at pos is the lab root, and where the argument ends."""
        if (m := re.compile(r"['\"]?\$\{?(\w+)\}?" + SH_ARG_END).match(line, pos)):
            return m.group(1) in root_vars, m.end()
        if (m := re.compile(r"['\"]?" + SH_DIRNAME.pattern + SH_ARG_END).match(line, pos)):
            return m.group("ups").count("/..") == root_ups, m.end()
        m = re.compile(r"\S*").match(line, pos)
        return False, m.end()

    def bare(m: re.Match) -> str:
        return swap(m) if ("." in m.group("lit") or "/" in m.group("lit")) else m.group(0)

    out, in_root = [], False
    for line in text.splitlines(keepends=True):
        start = 0
        for m in SH_CD.finditer(line):
            in_root, start = cd_target(line, m.end())
        if in_root and not line.lstrip().startswith("#") and not re.search(r"\b(pgrep|pkill|pidof|grep)\b", line):
            line = line[:start] + SH_BARE.sub(bare, line[start:])
        out.append(line)
    return "".join(out), changes


# --- path expressions in Python code, evaluated statically ------------------------------------

PATH_TYPES = frozenset({"Path", "PurePath", "PosixPath", "PurePosixPath"})


def _dotted(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        head = _dotted(node.value)
        return f"{head}.{node.attr}" if head else None
    return None


class PyPaths:
    """Evaluate the simple path expressions of one Python file to repository-relative paths.

    A value is (kind, path): kind "str" or "path" for a place in the repository ("" is its root),
    or "frag" for a relative string literal, which only means something once joined."""

    def __init__(self, repo: Path, rel: str, tree: ast.AST) -> None:
        self.prefix = repo.as_posix().rstrip("/") + "/"
        self.rel = rel
        self.assigned: dict[str, list[tuple[int, ast.AST]]] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                self.assigned.setdefault(node.targets[0].id, []).append((node.lineno, node.value))
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None:
                self.assigned.setdefault(node.target.id, []).append((node.lineno, node.value))
        for items in self.assigned.values():
            items.sort(key=lambda item: item[0])

    @staticmethod
    def norm(path: str) -> str | None:
        path = posixpath.normpath(path) if path else "."
        if path == ".":
            return ""
        return None if path == ".." or path.startswith(("../", "/")) else path

    def value(self, node: ast.AST | None, line: int, seen: int = 0) -> tuple[str, str] | None:
        if node is None or seen > 30:
            return None
        v = lambda n: self.value(n, line, seen + 1)  # noqa: E731
        if isinstance(node, ast.Name):
            if node.id == "__file__":
                return ("str", self.rel)
            items = self.assigned.get(node.id, [])
            before = [item for item in items if item[0] < line] or (items if len(items) == 1 else [])
            return self.value(before[-1][1], before[-1][0], seen + 1) if before else None
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if not node.value.startswith("/"):
                return ("frag", node.value)
            if not (node.value + "/").startswith(self.prefix):
                return None
            path = self.norm(node.value[len(self.prefix):])
            return None if path is None else ("str", path)
        if isinstance(node, ast.Call):
            name, args = _dotted(node.func), node.args
            if name in ("str", "os.fspath") and len(args) == 1:
                x = v(args[0])
                return x if x is None or x[0] == "frag" else ("str", x[1])
            if (name in PATH_TYPES or name in {f"pathlib.{t}" for t in PATH_TYPES}) and len(args) == 1:
                x = v(args[0])
                if x is None or (x[0] == "frag" and not x[1].startswith("labs/")):
                    return None
                path = self.norm(x[1])
                return None if path is None else ("path", path)
            if name in ("os.path.dirname", "os.path.abspath", "os.path.realpath", "os.path.normpath") and len(args) == 1:
                x = v(args[0])
                if x is None or x[0] == "frag":
                    return None
                if name == "os.path.dirname":
                    return None if x[1] == "" else ("str", posixpath.dirname(x[1]))
                return ("str", x[1])
            if name == "os.path.join" and args:
                return self.join(v(args[0]), args[1:], line, seen, "str")
            if isinstance(node.func, ast.Attribute) and node.func.attr in ("resolve", "absolute", "expanduser") and not args:
                return v(node.func.value)
            if isinstance(node.func, ast.Attribute) and node.func.attr == "joinpath":
                return self.join(v(node.func.value), args, line, seen, "path")
            return None
        if isinstance(node, ast.Attribute) and node.attr == "parent":
            x = v(node.value)
            return None if x is None or x[0] == "frag" or x[1] == "" else ("path", posixpath.dirname(x[1]))
        if (isinstance(node, ast.Subscript) and isinstance(node.value, ast.Attribute) and node.value.attr == "parents"
                and isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, int)):
            x = v(node.value.value)
            if x is None or x[0] == "frag":
                return None
            path = x[1]
            for _ in range(node.slice.value + 1):
                if path == "":
                    return None
                path = posixpath.dirname(path)
            return ("path", path)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            return self.join(v(node.left), [node.right], line, seen, "path")
        return None

    def join(self, base, parts: list[ast.AST], line: int, seen: int, kind: str) -> tuple[str, str] | None:
        if base is None or base[0] == "frag":
            return None
        path: str | None = base[1]
        for part in parts:
            x = self.value(part, line, seen + 1)
            if x is None:
                return None
            path = self.norm(posixpath.join(path, x[1]) if x[0] == "frag" else x[1])
            if path is None:
                return None
        return (kind, path)


def sys_path_entries(tree: ast.AST) -> list[ast.AST]:
    """Expressions a file adds to sys.path, counting each item of a for loop that adds its variable
    and the x of an `if x not in sys.path:` guard around an addition."""
    def entry(node: ast.AST) -> ast.AST | None:
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and _dotted(node.func.value) == "sys.path"):
            return None
        if node.func.attr == "insert" and len(node.args) == 2:
            return node.args[1]
        return node.args[0] if node.func.attr == "append" and len(node.args) == 1 else None

    def bare(node: ast.AST) -> ast.AST:
        if isinstance(node, ast.Call) and _dotted(node.func) in ("str", "os.fspath") and len(node.args) == 1:
            return node.args[0]
        return node

    entries: list[ast.AST] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.For) and isinstance(node.target, ast.Name) and isinstance(node.iter, (ast.Tuple, ast.List)):
            for sub in ast.walk(node):
                e = entry(sub)
                if e is not None and isinstance(bare(e), ast.Name) and bare(e).id == node.target.id:
                    entries.extend(node.iter.elts)
                    break
        if (isinstance(node, ast.If) and isinstance(node.test, ast.Compare) and len(node.test.ops) == 1
                and isinstance(node.test.ops[0], (ast.NotIn, ast.In))
                and _dotted(node.test.comparators[0]) == "sys.path"
                and any(entry(sub) is not None for stmt in node.body for sub in ast.walk(stmt))):
            entries.append(node.test.left)
        if (e := entry(node)) is not None:
            entries.append(e)
    return entries


def is_lab_root(path: str) -> bool:
    parts = path.split("/")
    return len(parts) == 2 and parts[0] == "labs" and bool(labs_catalog.LAB_DIR_RE.match(parts[1]))


def migrated_root(repo: Path, path: str) -> bool:
    """A lab root whose code now lives in scripts/."""
    lab = repo / path
    return is_lab_root(path) and (lab / "scripts").is_dir() and not any(lab.glob("*.py"))


def top_level_imports(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    return names


class Source:
    """Character offsets for ast positions (whose columns count UTF-8 bytes)."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.lines = text.split("\n")
        self.starts = [0]
        for line in self.lines:
            self.starts.append(self.starts[-1] + len(line) + 1)

    def offset(self, lineno: int, col: int) -> int:
        return self.starts[lineno - 1] + len(self.lines[lineno - 1].encode("utf-8")[:col].decode("utf-8", "ignore"))

    def span(self, node: ast.AST) -> tuple[int, int]:
        return self.offset(node.lineno, node.col_offset), self.offset(node.end_lineno, node.end_col_offset)

    def literal(self, node: ast.AST) -> tuple[int, int, str] | None:
        """(start, end, quote) of a plain one-line string literal whose text is its value."""
        start, end = self.span(node)
        m = re.fullmatch(r"(['\"])([^'\"\\\n]*)\1", self.text[start:end])
        return (start, end, m.group(1)) if m and m.group(2) == node.value else None


def rewrite_python_paths(repo: Path, rel: str, text: str, mmap: MoveMap) -> tuple[str, int, list[str]]:
    """Point sys.path entries that name a lab root at its scripts/ when that is where the modules
    the file imports now are, and re-express joins onto moved paths (DEMO / "common.py", where
    DEMO is another lab's root)."""
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return text, 0, []
    ev, src = PyPaths(repo, rel, tree), Source(text)
    edits: list[tuple[int, int, str]] = []
    review: list[str] = []
    imported = top_level_imports(tree)
    imports_os = any(isinstance(n, ast.Import) and any(a.name == "os" for a in n.names) for n in ast.walk(tree))
    entries = [(e, ev.value(e, e.lineno)) for e in sys_path_entries(tree)]
    reached = {posixpath.dirname(rel)} | {v[1] for _, v in entries if v is not None and v[0] != "frag"}

    for e, val in entries:
        if val is None or val[0] == "frag" or not is_lab_root(val[1]):
            continue
        root = repo / val[1]
        others = reached - {val[1]}
        needed = [n for n in imported if has_module(root / "scripts", n)
                  and not any(has_module(repo / d, n) for d in others)]
        if not needed or any(has_module(root, n) for n in imported):
            continue
        inner = e.args[0] if isinstance(e, ast.Call) and _dotted(e.func) in ("str", "os.fspath") else e
        inner_val = ev.value(inner, e.lineno)
        start, end = src.span(inner)
        if inner_val and inner_val[0] == "path":
            edits.append((end, end, ' / "scripts"'))
        elif isinstance(inner, ast.Constant) and (lit := src.literal(inner)):
            edits.append((lit[0], lit[1], f'{lit[2]}{inner.value.rstrip("/")}/scripts{lit[2]}'))
        elif imports_os:
            edits.append((start, end, f'os.path.join({text[start:end]}, "scripts")'))
        else:
            review.append(f"{rel}:{e.lineno}: sys.path names {val[1]}, whose code is now in scripts/")

    if mmap:
        for node in ast.walk(tree):
            if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
                base, parts = node.left, [node.right]
            elif isinstance(node, ast.Call) and _dotted(node.func) == "os.path.join" and node.args:
                base, parts = node.args[0], node.args[1:]
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "joinpath":
                base, parts = node.func.value, node.args
            else:
                continue
            bval = ev.value(base, node.lineno)
            if bval is None or bval[0] == "frag" or mmap.map(bval[1]) != bval[1]:
                continue
            cum = bval[1]
            for part in parts:
                if not (isinstance(part, ast.Constant) and isinstance(part.value, str)):
                    other = cum.split("/")[1] if migrated_root(repo, cum) else None
                    if other and other != lab_of(rel) and mmap.by_lab.get(other):
                        review.append(f"{rel}:{node.lineno}: path built from a computed name under {cum}")
                    break
                nxt = PyPaths.norm(posixpath.join(cum, part.value))
                if nxt is None:
                    break
                new = mmap.map(nxt)
                if new != nxt:
                    frag = posixpath.relpath(new, cum or ".")
                    lit = src.literal(part)
                    if frag.startswith("..") or lit is None:
                        review.append(f"{rel}:{node.lineno}: {nxt} moved to {new}; not rewritten")
                    else:
                        edits.append((lit[0], lit[1], f"{lit[2]}{frag}{lit[2]}"))
                    break
                cum = nxt

    out, last = text, None
    for start, end, repl in sorted(set(edits), reverse=True):
        if last is not None and end > last:
            continue
        out, last = out[:start] + repl + out[end:], start
    return out, len(edits), review


# --- repository-wide references ---------------------------------------------------------------

def rewrite_ids(text: str, mmap: MoveMap) -> tuple[str, int]:
    changes = 0

    def swap(m: re.Match) -> str:
        nonlocal changes
        lab_id, token = m.group("id"), m.group("path")
        if lab_id not in mmap.by_lab:
            return m.group(0)
        trail = len(token) - len(token.rstrip("."))
        core = token[: len(token) - trail] if trail else token
        new = mmap.map_lab(lab_id, core)
        if new == core:
            return m.group(0)
        changes += 1
        return f"{lab_id}/{new}{token[len(core):]}"

    return LAB_ID_TOKEN.sub(swap, text), changes


def split_target(target: str) -> tuple[str, str]:
    for sep in ("#", "?"):
        if sep in target:
            head, tail = target.split(sep, 1)
            return head, sep + tail
    return target, ""


def rewrite_md_links(text: str, new_path: str, old_path: str, mmap: MoveMap) -> tuple[str, int]:
    """Re-express relative Markdown links so they reach the same (possibly moved) targets."""
    old_dir, new_dir = posixpath.dirname(old_path), posixpath.dirname(new_path)
    changes = 0

    def fix(target: str) -> str:
        nonlocal changes
        if "://" in target or target.startswith(("mailto:", "#", "/")):
            return target
        path, suffix = split_target(target)
        if not path:
            return target
        old_abs = posixpath.normpath(posixpath.join(old_dir, unquote(path)))
        if old_abs.startswith(".."):
            return target
        new_abs = mmap.map(old_abs)
        if new_abs == old_abs and old_dir == new_dir:
            return target
        rel = posixpath.relpath(new_abs, new_dir or ".")
        if path.endswith("/") and not rel.endswith("/"):
            rel += "/"
        if rel == path:
            return target
        changes += 1
        return rel + suffix

    out: list[str] = []
    in_fence = False
    for line in text.splitlines(keepends=True):
        if FENCE.match(line):
            in_fence = not in_fence
            out.append(line)
            continue
        if in_fence:
            out.append(line)
            continue
        line = MD_LINK.sub(lambda m: m.group("head") + fix(m.group("target")) + m.group("tail"), line)
        ref = MD_REFDEF.match(line.rstrip("\n"))
        if ref:
            ending = line[len(line.rstrip("\n")):]
            line = ref.group("head") + fix(ref.group("target")) + ref.group("tail") + ending
        out.append(line)
    return "".join(out), changes


def lab_of(path: str) -> str | None:
    parts = PurePosixPath(path).parts
    return parts[1] if len(parts) > 2 and parts[0] == "labs" else None


def is_record(rel: str) -> bool:
    """Output of a past run (a lab's results, data, logs, checkpoints; logs and tables anywhere).
    Its text records what happened, so paths in it are never rewritten or checked."""
    parts = rel.split("/")
    if len(parts) > 3 and parts[0] == "labs" and parts[2] in RECORD_DIRS:
        return True
    return PurePosixPath(rel).suffix.lower() in RECORD_SUFFIXES


def is_transcription(rel: str, text: str) -> bool:
    """A note copied verbatim from outside the repository or from git history (reconstruct.md)."""
    return rel.endswith(".md") and any(line.startswith(TRANSCRIPTION_MARK) for line in text.splitlines()[:12])


def rewrite_repository(repo: Path, mmap: MoveMap, code_moves: dict[str, tuple[str, int, int]],
                       protect: set[str], apply: bool, outcome: Outcome) -> None:
    """Rewrite references to moved paths in every tracked or unignored text file except records
    and verbatim transcriptions."""
    files = sorted(set(ls_files(repo, "--cached", "--others", "--exclude-standard")))
    for rel in files:
        path = repo / rel
        if is_record(rel) or not path.is_file() or path.is_symlink():
            continue
        text = read_text(path)
        if text is None or is_transcription(rel, text):
            continue
        lab = lab_of(rel)
        old_rel = mmap.inverse(rel)
        new_text, count = text, 0
        suffix = path.suffix.lower()
        if lab in mmap.by_lab and suffix in (".py", ".sh", ".bash"):
            lab_rel = rel.split("/", 2)[2]

            def mapper(p: str, lab: str = lab) -> str:
                return mmap.map_lab(lab, p)

            src_lab_rel, k, keep = code_moves.get(rel, (lab_rel, 0, 0))
            if k and suffix == ".py":
                new_text, n, review = patch_python(new_text, k, lab_rel, src_lab_rel, mapper, keep)
            elif k:
                new_text, n, review = patch_shell(new_text, k, lab_rel, keep)
            else:
                n, review = 0, []
            count += n
            outcome.review += [f"labs/{lab}/{r}" for r in review]
            if suffix == ".py":
                new_text, n = rewrite_python_literals(new_text, lab_rel, mapper)
            else:
                new_text, n = rewrite_shell_literals(new_text, lab_rel, lab, mapper)
            count += n
        if suffix == ".py":
            new_text, n, review = rewrite_python_paths(repo, rel, new_text, mmap)
            count += n
            if not (rel.startswith(NEVER_EDIT) or (lab and lab in protect)):
                outcome.review += review
        if suffix == ".md" and (old_rel != rel or lab in mmap.by_lab):
            new_text, n = rewrite_md_links(new_text, rel, old_rel, mmap)
            count += n
        new_text, n = rewrite_ids(new_text, mmap)
        count += n
        if not count or new_text == text:
            continue
        if rel.startswith(NEVER_EDIT) or (lab and lab in protect):
            for a, b in zip(text.splitlines(), new_text.splitlines()):
                if a != b:
                    outcome.left.append(f"{rel}: {a.strip()[:140]}")
            continue
        outcome.edited[rel] = count
        if apply:
            write_text(repo, rel, new_text)


# --- tracking ---------------------------------------------------------------------------------

def exception_lines(repo: Path, lab_id: str, rels: list[str]) -> list[str]:
    """.gitignore lines that re-include the given lab-relative files, parents first."""
    lines: list[str] = []
    for rel in sorted(rels):
        parts = PurePosixPath(rel).parts
        dirs = ["/".join(parts[:i]) for i in range(1, len(parts))]
        blocked = ignored(repo, [f"labs/{lab_id}/{d}/" for d in dirs])
        start = next((i for i, d in enumerate(dirs) if f"labs/{lab_id}/{d}/" in blocked), None)
        if start is not None:
            for d in dirs[start:]:
                lines += [f"!/{d}/", f"/{d}/*"]
        lines.append(f"!/{rel}")
    seen: set[str] = set()
    return [line for line in lines if not (line in seen or seen.add(line))]


def ensure_tracked(repo: Path, lab_id: str, rels: list[str], apply: bool) -> tuple[list[str], list[str]]:
    """Add .gitignore exceptions so the lab files stay tracked. Returns (added lines, still ignored)."""
    blocked = ignored(repo, [f"labs/{lab_id}/{r}" for r in rels])
    need = sorted(r for r in rels if f"labs/{lab_id}/{r}" in blocked)
    if not need:
        return [], []
    gi_rel = f"labs/{lab_id}/.gitignore"
    gi = repo / gi_rel
    existing = gi.read_text(encoding="utf-8").splitlines() if gi.is_file() else []
    lines = [line for line in exception_lines(repo, lab_id, need) if line not in existing]
    if apply and lines:
        header = ["", "# Tracked files kept tracked when the lab moved to the standard layout."] if existing else [
            "# What git tracks in this lab beyond the repository .gitignore",
            "# (skills/organize-lab/references/report-contract.md, Git policy).",
        ]
        write_text(repo, gi_rel, "\n".join(existing + header + lines) + "\n")
    if not apply:
        return lines, []
    blocked = ignored(repo, [f"labs/{lab_id}/{r}" for r in need])
    return lines, sorted(r for r in need if f"labs/{lab_id}/{r}" in blocked)


# --- guards -----------------------------------------------------------------------------------

def live_reasons(repo: Path, lab_dir: Path, allow_recent: bool = False) -> list[str]:
    reasons: list[str] = []
    lab_abs = str(lab_dir.resolve())
    proc = Path("/proc")
    if proc.is_dir():
        for pid_dir in proc.iterdir():
            if not pid_dir.name.isdigit() or pid_dir.name == str(os.getpid()):
                continue
            try:
                cmd = (pid_dir / "cmdline").read_bytes().replace(b"\0", b" ").decode("utf-8", "replace").strip()
            except OSError:
                continue
            try:
                cwd = os.readlink(pid_dir / "cwd")
            except OSError:
                cwd = ""
            if lab_dir.name in cmd and "lab_layout.py" not in cmd:
                reasons.append(f"process {pid_dir.name} runs: {cmd[:120]}")
            elif cwd == lab_abs or cwd.startswith(lab_abs + "/"):
                reasons.append(f"process {pid_dir.name} works in the lab")
    if not allow_recent:
        own = load_json(state_dir(repo) / "own-writes.json", {})
        now = time.time()
        for path in lab_dir.rglob("*"):
            if "__pycache__" in path.parts or not path.is_file():
                continue
            stat = path.stat()
            rel = path.relative_to(repo).as_posix()
            if now - stat.st_mtime < RECENT_SECONDS and own.get(rel) != stat.st_mtime_ns:
                reasons.append(f"{rel} changed {int((now - stat.st_mtime) // 60)} min ago")
                break
    return reasons


# --- commands ---------------------------------------------------------------------------------

def preview_path(repo: Path, lab_id: str) -> Path:
    return state_dir(repo) / "preview" / f"{lab_id}.json"


def lab_dir_for(repo: Path, lab_id: str) -> Path | None:
    path = repo / "labs" / lab_id
    return path if path.is_dir() and labs_catalog.LAB_DIR_RE.match(lab_id) else None


def run_moves(repo: Path, plans: dict[str, list[Move]], *, apply: bool, protect: set[str],
              allow_recent: bool, outcome: Outcome) -> None:
    """Preview or apply planned moves for several labs, then rewrite references once."""
    mmap = MoveMap()
    code_moves: dict[str, tuple[str, int]] = {}
    moved_tracked: dict[str, list[str]] = {}
    for lab_id, moves in plans.items():
        lab_dir = repo / "labs" / lab_id
        if lab_id in protect:
            outcome.refused[lab_id] = ["protected"]
            continue
        reasons = live_reasons(repo, lab_dir, allow_recent)
        if reasons:
            outcome.refused[lab_id] = reasons
            continue
        prev_file = preview_path(repo, lab_id)
        if not apply:
            prev_file.parent.mkdir(parents=True, exist_ok=True)
            sig = {m.src: signature(lab_dir / m.src) for m in moves}
            prev_file.write_text(json.dumps({"moves": [asdict(m) for m in moves], "signatures": sig}, indent=1), encoding="utf-8")
            for move in moves:
                mmap.add(lab_id, move)
            outcome.moved[lab_id] = moves
            continue
        preview = load_json(prev_file, None)
        if preview is None:
            outcome.refused[lab_id] = ["no preview; run the same command without --apply first"]
            continue
        if [Move(**m) for m in preview["moves"]] != moves:
            outcome.refused[lab_id] = ["the plan changed since the preview; preview again"]
            continue
        tracked = set(ls_files(repo, "--cached", "--", f"labs/{lab_id}"))
        done: list[Move] = []
        for move in moves:
            src, dst = lab_dir / move.src, lab_dir / move.dst
            if not src.exists():
                outcome.review.append(f"labs/{lab_id}/{move.src}: no longer exists; skipped")
                continue
            if signature(src) != preview["signatures"].get(move.src):
                outcome.review.append(f"labs/{lab_id}/{move.src}: changed after the preview; skipped")
                continue
            if dst.exists() and not (src.samefile(dst) and move.src.lower() == move.dst.lower()):
                outcome.review.append(f"labs/{lab_id}/{move.dst}: already exists; {move.src} skipped")
                continue
            src_rel, dst_rel = f"labs/{lab_id}/{move.src}", f"labs/{lab_id}/{move.dst}"
            inside = [t for t in tracked if t == src_rel or t.startswith(src_rel + "/")]
            dst.parent.mkdir(parents=True, exist_ok=True)
            try:
                if inside:
                    git(repo, "mv", src_rel, dst_rel)
                else:
                    src.rename(dst)
            except (OSError, subprocess.CalledProcessError) as exc:
                detail = exc.stderr.decode().strip() if isinstance(exc, subprocess.CalledProcessError) else str(exc)
                outcome.review.append(f"{src_rel}: move failed ({detail}); skipped")
                continue
            done.append(move)
            mmap.add(lab_id, move)
            moved_tracked.setdefault(lab_id, []).extend(move.dst + t[len(src_rel):] for t in inside)
            for code in ([dst] if not move.is_dir else [p for p in dst.rglob("*") if p.is_file()]):
                if code.suffix.lower() in (".py", ".sh", ".bash"):
                    new_lab_rel = code.relative_to(lab_dir).as_posix()
                    old_lab_rel = move.src + new_lab_rel[len(move.dst):]
                    keep = depth(old_lab_rel) - depth(move.src) if move.is_dir else 0
                    code_moves[f"labs/{lab_id}/{new_lab_rel}"] = (old_lab_rel, depth(new_lab_rel) - depth(old_lab_rel), keep)
        for move in done:
            parent = (lab_dir / move.src).parent
            if parent != lab_dir and parent.is_dir() and all(p.name in labs_catalog.TRANSIENT for p in parent.iterdir()):
                shutil.rmtree(parent)
        outcome.moved[lab_id] = done
        prev_file.unlink()
        drop_retired_keys(repo, lab_id)
    if not mmap:
        return
    rewrite_repository(repo, mmap, code_moves, protect, apply, outcome)
    if not apply:
        return
    for lab_id, rels in moved_tracked.items():
        lines, still = ensure_tracked(repo, lab_id, rels, apply=True)
        if lines:
            outcome.tracked[lab_id] = lines
        outcome.review += [f"labs/{lab_id}/{r}: still ignored after the .gitignore update" for r in still]


def drop_retired_keys(repo: Path, lab_id: str) -> None:
    rel = f"labs/{lab_id}/lab.json"
    path = repo / rel
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if isinstance(data, dict) and any(k in data for k in labs_catalog.RETIRED_KEYS):
        for key in labs_catalog.RETIRED_KEYS:
            data.pop(key, None)
        write_text(repo, rel, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def print_outcome(outcome: Outcome, apply: bool, as_json: bool) -> None:
    if as_json:
        payload = asdict(outcome)
        payload["moved"] = {k: [asdict(m) for m in v] for k, v in outcome.moved.items()}
        print(json.dumps(payload, indent=2))
        return
    verb = "moved" if apply else "would move"
    for lab_id, moves in outcome.moved.items():
        for m in moves:
            print(f"{verb}  labs/{lab_id}/{m.src} -> {m.dst}  ({m.reason})")
    for lab_id, reasons in outcome.refused.items():
        print(f"REFUSED labs/{lab_id}: {'; '.join(reasons)}")
    for rel, n in sorted(outcome.edited.items()):
        print(f"{'edited' if apply else 'would edit'}  {rel} ({n})")
    for lab_id, lines in outcome.tracked.items():
        print(f"tracked labs/{lab_id}/.gitignore: {len(lines)} exception lines")
    for line in outcome.left:
        print(f"LEFT    {line}")
    for line in outcome.review:
        print(f"REVIEW  {line}")
    n_moves = sum(len(v) for v in outcome.moved.values())
    print(f"lab_layout: {n_moves} moves {'applied' if apply else 'planned'} in {len(outcome.moved)} labs, "
          f"{len(outcome.edited)} files {'edited' if apply else 'to edit'}, {len(outcome.refused)} refused, "
          f"{len(outcome.left)} left, {len(outcome.review)} to review")


def broken_references(repo: Path) -> list[str]:
    """References to lab files, anywhere in tracked or unignored text except records and verbatim
    transcriptions, that do not resolve."""
    labs = {p.name for p in (repo / "labs").iterdir() if p.is_dir() and labs_catalog.LAB_DIR_RE.match(p.name)}
    found: list[str] = []
    for rel in sorted(set(ls_files(repo, "--cached", "--others", "--exclude-standard"))):
        if is_record(rel):
            continue
        text = read_text(repo / rel)
        if text is None or is_transcription(rel, text):
            continue
        for n, line in enumerate(text.splitlines(), 1):
            for m in LAB_ID_TOKEN.finditer(line):
                token = m.group("path").rstrip(".")
                if m.group("id") not in labs or not token or "<" in token or "$" in token:
                    continue
                if not (repo / "labs" / m.group("id") / token).exists():
                    found.append(f"{rel}:{n}: labs/{m.group('id')}/{token}")
            if rel.endswith(".md") and lab_of(rel):
                for m in MD_LINK.finditer(line):
                    path, _ = split_target(m.group("target"))
                    if not path or "://" in path or path.startswith(("mailto:", "#", "/")):
                        continue
                    if not (repo / posixpath.dirname(rel) / unquote(path)).exists():
                        found.append(f"{rel}:{n}: {path}")
    return found


def site_dirs(repo: Path) -> list[Path]:
    """Where the repository's virtual environment finds installed modules."""
    dirs: list[Path] = []
    for site in sorted((repo / ".venv" / "lib").glob("python3*/site-packages")):
        dirs.append(site)
        for pth in site.glob("*.pth"):
            for line in pth.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if line and not line.startswith(("#", "import ")) and Path(line).is_dir():
                    dirs.append(Path(line))
    return dirs


def has_module(directory: Path, name: str) -> bool:
    return ((directory / f"{name}.py").is_file() or (directory / name).is_dir()
            or any(directory.glob(f"{name}.*.so")))


def optional_imports(tree: ast.AST) -> set[int]:
    """Nodes inside `try` blocks that handle ImportError, or under `if TYPE_CHECKING`."""
    catches = {"ImportError", "ModuleNotFoundError", "Exception", "BaseException"}
    out: set[int] = set()
    for node in ast.walk(tree):
        body: list[ast.stmt] = []
        if isinstance(node, ast.Try):
            for h in node.handlers:
                types = h.type.elts if isinstance(h.type, ast.Tuple) else [h.type]
                if h.type is None or any(_dotted(t) in catches for t in types):
                    body = node.body
        elif isinstance(node, ast.If) and _dotted(node.test) in ("TYPE_CHECKING", "typing.TYPE_CHECKING"):
            body = node.body
        out.update(id(sub) for stmt in body for sub in ast.walk(stmt))
    return out


def unresolved_imports(repo: Path) -> list[str]:
    """Imports that neither the environment nor the directories the file puts on sys.path provide."""
    known = set(getattr(sys, "stdlib_module_names", ())) | set(sys.builtin_module_names) | {"__future__"}
    sites = site_dirs(repo)
    installed: dict[str, bool] = {}
    found: list[str] = []
    for rel in sorted(set(ls_files(repo, "--cached", "--others", "--exclude-standard"))):
        if not rel.endswith(".py") or is_record(rel):
            continue
        text = read_text(repo / rel)
        try:
            tree = ast.parse(text or "")
        except (SyntaxError, ValueError):
            continue
        ev = PyPaths(repo, rel, tree)
        dirs = {posixpath.dirname(rel)}
        for e in sys_path_entries(tree):
            val = ev.value(e, e.lineno)
            path = None if val is None else (PyPaths.norm(val[1]) if val[0] == "frag" else val[1])
            if path is not None:
                dirs.add(path)
        skip = optional_imports(tree)
        for node in ast.walk(tree):
            if id(node) in skip:
                continue
            if isinstance(node, ast.Import):
                names = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module.split(".")[0]]
            else:
                continue
            for name in names:
                if name in known:
                    continue
                if name not in installed:
                    installed[name] = any(has_module(d, name) for d in sites)
                if not installed[name] and not any(has_module(repo / d, name) for d in dirs):
                    found.append(f"{rel}:{node.lineno}: import {name}")
    return found


def cmd_check(repo: Path, args) -> int:
    dirs, _ = labs_catalog.lab_dirs(repo)
    if args.labs:
        dirs = [d for d in dirs if d.name in set(args.labs)]
    tracked = labs_catalog.tracked_files(repo, [d.name for d in dirs] if args.labs else None) or {}
    problems = {d.name: labs_catalog.layout_problems(d, tracked.get(d.name)) for d in dirs}
    problems = {k: v for k, v in problems.items() if v}
    links = broken_references(repo) if args.links else []
    imports = unresolved_imports(repo) if args.imports else []
    if args.labs:
        imports = [line for line in imports if lab_of(line.split(":", 1)[0]) in set(args.labs)]
    if args.as_json:
        print(json.dumps({"layout": problems, "broken_references": links, "unresolved_imports": imports}, indent=2))
    else:
        for lab_id, items in problems.items():
            for item in items:
                print(f"LAYOUT  {lab_id}: {item}")
        for line in links:
            print(f"BROKEN  {line}")
        for line in imports:
            print(f"IMPORT  {line}")
        print(f"lab_layout: {len(dirs) - len(problems)} of {len(dirs)} labs match the layout"
              + (f", {len(links)} unresolved lab references" if args.links else "")
              + (f", {len(imports)} unresolved imports" if args.imports else ""))
    return 1 if problems or links or imports else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=None, help="repository root (default: located from this file)")
    sub = parser.add_subparsers(dest="command", required=True)
    p_check = sub.add_parser("check", help="layout findings (and unresolved lab references)")
    p_check.add_argument("labs", nargs="*")
    p_check.add_argument("--links", action="store_true", help="also list unresolved references to lab files")
    p_check.add_argument("--imports", action="store_true", help="also list Python imports that do not resolve")
    p_check.add_argument("--json", action="store_true", dest="as_json")
    for name in ("tidy", "move"):
        p = sub.add_parser(name)
        if name == "tidy":
            p.add_argument("labs", nargs="+")
            p.add_argument("--rename-only", action="store_true", help="only report.md -> REPORT.md")
        else:
            p.add_argument("lab")
            p.add_argument("src")
            p.add_argument("dst")
        p.add_argument("--apply", action="store_true")
        p.add_argument("--protect", nargs="*", default=[], metavar="LAB_ID", help="labs whose files are never edited")
        p.add_argument("--allow-recent", action="store_true", help="skip the recent-write test (process test still applies)")
        p.add_argument("--json", action="store_true", dest="as_json")
    p_track = sub.add_parser("track", help="keep lab files tracked through the lab .gitignore")
    p_track.add_argument("lab")
    p_track.add_argument("paths", nargs="+")
    args = parser.parse_args(argv)

    repo = (args.root or labs_catalog.default_root()).resolve()
    if args.command == "check":
        return cmd_check(repo, args)
    if args.command == "track":
        if lab_dir_for(repo, args.lab) is None:
            print(f"lab_layout: no lab {args.lab!r}", file=sys.stderr)
            return 2
        missing = [p for p in args.paths if not (repo / "labs" / args.lab / p).is_file()]
        if missing:
            print(f"lab_layout: not files in the lab: {', '.join(missing)}", file=sys.stderr)
            return 2
        lines, still = ensure_tracked(repo, args.lab, args.paths, apply=True)
        for line in lines:
            print(f"added   {line}")
        for rel in still:
            print(f"REVIEW  {rel}: still ignored")
        return 1 if still else 0

    outcome = Outcome()
    plans: dict[str, list[Move]] = {}
    lab_ids = args.labs if args.command == "tidy" else [args.lab]
    tracked = labs_catalog.tracked_files(repo, lab_ids) or {} if args.command == "tidy" else {}
    for lab_id in lab_ids:
        lab_dir = lab_dir_for(repo, lab_id)
        if lab_dir is None:
            print(f"lab_layout: no lab {lab_id!r}", file=sys.stderr)
            return 2
        if args.command == "tidy":
            moves, review = plan_lab(lab_dir, rename_only=args.rename_only, tracked=tracked.get(lab_id))
            outcome.review += review
        else:
            src = PurePosixPath(args.src).as_posix().strip("/")
            dst = PurePosixPath(args.dst).as_posix().strip("/")
            if ".." in PurePosixPath(src).parts or ".." in PurePosixPath(dst).parts or not (lab_dir / src).exists():
                print(f"lab_layout: {src!r} is not a path inside labs/{lab_id}", file=sys.stderr)
                return 2
            moves = [Move(src, dst, "requested", (lab_dir / src).is_dir())]
        plans[lab_id] = moves
    run_moves(repo, plans, apply=args.apply, protect=set(args.protect), allow_recent=args.allow_recent, outcome=outcome)
    if args.apply and outcome.moved:
        labs_catalog.main(["--root", str(repo), "rebuild", "--force", "-q"])
    print_outcome(outcome, args.apply, args.as_json)
    return 1 if outcome.refused or outcome.review else 0


if __name__ == "__main__":
    raise SystemExit(main())
