"""Lab output path discipline: layout, run identity, and write policy.

Three layers (use in this order, or call :func:`lab_output` for layout+identity):

1. **Layout** — :func:`lab_place` routes a path into the correct category under ``labs/<id>/``.
2. **Identity** — :func:`lab_run_file` builds a unique filename from the parameters that define a run.
3. **Policy** — :func:`truncate_for_run` (append-safe start) or :func:`require_absent` (no overwrite).

Typical driver (after adding ``labs/_tools`` to ``sys.path``)::

    from paths import lab_output, truncate_for_run, require_absent

    metrics = truncate_for_run(
        lab_output(HERE, "metrics", "jsonl", category="results", h=args.hidden_dim, seed=args.seed)
    )
"""

from __future__ import annotations

from pathlib import Path

__all__ = [
    "lab_place",
    "lab_run_file",
    "lab_output",
    "truncate_for_run",
    "require_absent",
    "CATEGORIES",
    "OUTPUT_CATEGORIES",
]

REPOSITORY = Path(__file__).resolve().parents[2]
LABS = REPOSITORY / "labs"
CATEGORIES = {"scripts", "results", "data", "figures", "notes", "logs", "configs"}
OUTPUT_CATEGORIES = {
    ".json": "results",
    ".csv": "results",
    ".tsv": "results",
    ".png": "figures",
    ".svg": "figures",
    ".pdf": "figures",
    ".md": "notes",
    ".txt": "notes",
    ".log": "logs",
    ".gz": "data",
    ".pkl": "data",
    ".npz": "data",
    ".npy": "data",
}


def lab_place(path, category=None, *, create_parent=False) -> Path:
    """Put a file under the correct ``labs/<id>/<category>/`` folder.

    **Layout step.** Relative paths resolve from the repository root (``REPOSITORY``). If the path
    already lies under ``labs/``, the category segment may be rewritten when it disagrees with
    ``category`` or with :data:`OUTPUT_CATEGORIES` for the file suffix — e.g.
    ``…/results/foo.pkl`` → ``…/data/foo.pkl``.

    Paths outside ``labs/`` are returned unchanged (aside from resolution to absolute).

    Args:
        path: Target file (relative to repo root or absolute).
        category: Force a category folder; when ``None``, infer from suffix unless already in ``data/``.
        create_parent: If true, create parent directories before returning.

    Returns:
        The resolved path (possibly with a different category directory).
    """
    path = Path(path)
    candidate = path if path.is_absolute() else REPOSITORY / path
    if candidate.is_relative_to(LABS):
        lab, current, *parts = candidate.relative_to(LABS).parts
        target = category or OUTPUT_CATEGORIES.get(path.suffix)
        if current in CATEGORIES and target and current != target:
            if current != "data" or category is not None:
                candidate = LABS.joinpath(lab, target, *parts)
        path = candidate
    if create_parent:
        path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _token(key: str, value) -> str:
    """Format one sorted filename segment: ``h64`` from ``h=64``."""
    if isinstance(value, float):
        text = f"{value:g}"
    else:
        text = str(value)
    safe = "".join(ch if (ch.isalnum() or ch in "-.") else "-" for ch in text)
    return f"{key}{safe}"


def lab_run_file(directory: str | Path, kind: str, ext: str, **params) -> Path:
    """Build a run-unique path inside an existing category directory.

    **Identity step.** Filename pattern: ``{kind}_{k1}{v1}_{k2}{v2}….{ext}`` with keys sorted
    lexicographically, so ``seed=1, h=64`` and ``h=64, seed=1`` yield the same name.

    Args:
        directory: Category folder (e.g. ``HERE / "results"``); created if missing.
        kind: Logical file role — ``"metrics"``, ``"ckpt"``, ``"ler"``, etc.
        ext: Extension without a dot.
        **params: Everything that varies between runs (``seed``, ``h``, ``beta``, …).

    Returns:
        Full path. Does not truncate or guard against overwrite — use :func:`truncate_for_run` or
        :func:`require_absent` after this.
    """
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    suffix = "".join(f"_{_token(k, params[k])}" for k in sorted(params))
    return directory / f"{kind}{suffix}.{ext}"


def lab_output(
    lab_dir: str | Path,
    kind: str,
    ext: str,
    *,
    category: str = "results",
    **params,
) -> Path:
    """Return the path for one run output: correct category + parametric filename.

    **Layout + identity.** Equivalent to :func:`lab_place` on ``lab_dir/<category>/`` followed by
    :func:`lab_run_file` in that directory. ``lab_dir`` is normally the dated lab folder
    (``HERE = Path(__file__).resolve().parents[1]``).

    Args:
        lab_dir: Dated lab root (``labs/YYYY-MM-DD-slug/``).
        kind, ext, **params: Passed through to :func:`lab_run_file`.
        category: Subfolder under the lab (default ``"results"``); must be one of :data:`CATEGORIES`
            for layout rules to apply.

    Returns:
        Full path to create or open; no write policy applied yet.
    """
    lab_dir = Path(lab_dir)
    placeholder = lab_dir / category / f"_layout.{ext.lstrip('.')}"
    placed = lab_place(placeholder, category=category, create_parent=False)
    return lab_run_file(placed.parent, kind, ext, **params)


def truncate_for_run(path: str | Path, *, resume: bool = False) -> Path:
    """Prepare a file for a new run by truncating it (unless continuing).

    **Policy step — append safety.** Use at startup for JSONL/CSV writers that open in append mode:
    without truncation, a rerun concatenates onto the previous run and looks like one long experiment.

    Creates parent directories. When ``resume`` is false, writes an empty file (or truncates an
    existing file). When ``resume`` is true, leaves existing content intact.

    Args:
        path: File to open for writing this run.
        resume: If true, do not clear existing content.

    Returns:
        ``path`` for convenience chaining.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not resume:
        path.write_text("")
    return path


def require_absent(path: str | Path) -> Path:
    """Refuse to clobber a file that may already be cited as a record of measure.

    **Policy step — overwrite guard.** Use for summaries, figures, or JSON metrics that ``REPORT.md``
    or the wiki already quotes. ``labs/**/results/`` is gitignored; overwriting there is not
    recoverable from version control.

    Do **not** use for scratch logs or streaming monitors where replacement is expected.

    Creates parent directories when the file is absent.

    Args:
        path: Intended output path.

    Returns:
        ``path`` if it does not exist yet.

    Raises:
        SystemExit: If ``path`` already exists, with a short message on what to do instead.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise SystemExit(
            f"{path} exists — this would overwrite a measured record, and labs/**/results/ is "
            f"gitignored so it could not be recovered. Pass a different output path, or move the "
            f"old file aside if it is genuinely superseded."
        )
    return path