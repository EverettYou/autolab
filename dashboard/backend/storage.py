"""Atomic writes shared by local dashboard features."""
from pathlib import Path
from tempfile import NamedTemporaryFile


def atomic_write(target, raw):
    with NamedTemporaryFile(dir=target.parent, delete=False) as stream:
        staged = Path(stream.name)
        try:
            stream.write(raw)
            stream.flush()
            if target.exists():
                staged.chmod(target.stat().st_mode & 0o777)
            else:
                staged.chmod(0o644)
            staged.replace(target)
        finally:
            staged.unlink(missing_ok=True)
