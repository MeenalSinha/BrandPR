"""Local file storage for uploaded documents.

Files are stored under generated identifiers only. A client-supplied filename is never used to
build a path, and every resolved path is verified to stay inside the storage root.
"""
import os
import tempfile
import uuid
from pathlib import Path

from app.core.config import get_settings

EXTENSIONS = {"pdf": ".pdf", "text": ".txt", "csv": ".csv"}


class StorageError(Exception):
    pass


def _root() -> Path:
    root = Path(get_settings().storage_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def save(brand_id: uuid.UUID, document_id: uuid.UUID, data: bytes, source_type: str) -> str:
    """Write bytes atomically and return the relative storage key."""
    key = f"{brand_id}/{document_id}{EXTENSIONS[source_type]}"
    target = resolve(key)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=target.parent, prefix=".upload-")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.chmod(tmp, 0o640)
        os.replace(tmp, target)
    except Exception:
        Path(tmp).unlink(missing_ok=True)
        raise
    return key


def resolve(key: str) -> Path:
    root = _root()
    path = (root / key).resolve()
    if root != path and root not in path.parents:
        raise StorageError("Storage key escapes the storage root.")
    return path


def delete(key: str | None) -> None:
    if not key:
        return
    try:
        resolve(key).unlink(missing_ok=True)
    except StorageError:
        pass
