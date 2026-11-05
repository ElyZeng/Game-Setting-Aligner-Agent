"""Crash-safe file writes for game configuration files.

Every write goes to a temporary file in the same directory, is flushed to
disk, and then atomically replaces the target with ``os.replace``.  A crash,
power loss or exception in the middle of a write therefore leaves either the
old file or the new file on disk, never a truncated mix of both.

Text writes also keep the target's existing line endings and UTF-8 BOM, so a
file that used LF does not silently become CRLF (or the reverse) just because
Game Tuner touched one value in it.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
import time
from pathlib import Path
from typing import Optional, Union

PathLike = Union[str, "os.PathLike[str]"]

UTF8_BOM = b"\xef\xbb\xbf"

# Windows can briefly refuse os.replace while an antivirus scanner or the
# search indexer holds the target open.  Retry a few times before giving up.
_REPLACE_RETRIES = 5
_REPLACE_DELAY_SECONDS = 0.1


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def detect_newline(data: bytes) -> Optional[str]:
    """Return the dominant line ending in *data*, or ``None`` if it has none."""
    crlf = data.count(b"\r\n")
    lf = data.count(b"\n") - crlf
    if crlf == 0 and lf == 0:
        return None
    return "\r\n" if crlf >= lf else "\n"


def atomic_write_bytes(path: PathLike, data: bytes) -> None:
    """Atomically replace *path* with *data* (creating parent folders)."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".gt-tmp", dir=str(target.parent)
    )
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if target.exists():
            try:
                os.chmod(tmp_name, target.stat().st_mode & 0o7777)
            except OSError:
                pass
        last_error: Optional[OSError] = None
        for attempt in range(_REPLACE_RETRIES):
            try:
                os.replace(tmp_name, target)
                last_error = None
                break
            except PermissionError as exc:  # pragma: no cover - Windows timing
                last_error = exc
                time.sleep(_REPLACE_DELAY_SECONDS * (attempt + 1))
        if last_error is not None:
            raise last_error
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def encode_like_existing(path: PathLike, content: str) -> bytes:
    """Encode *content* as UTF-8 using the line endings and BOM of *path*.

    If *path* does not exist yet, the platform line ending is used (the same
    result the old ``open(path, "w")`` code produced).
    """
    target = Path(path)
    existing: Optional[bytes] = None
    if target.is_file():
        try:
            existing = target.read_bytes()
        except OSError:
            existing = None

    newline = detect_newline(existing) if existing is not None else None
    if newline is None:
        newline = os.linesep
    normalized = content.replace("\r\n", "\n")
    if newline != "\n":
        normalized = normalized.replace("\n", newline)

    data = normalized.encode("utf-8")
    has_bom_char = normalized.startswith("\ufeff")
    if existing is not None and existing.startswith(UTF8_BOM) and not has_bom_char:
        data = UTF8_BOM + data
    return data


def atomic_write_text(path: PathLike, content: str) -> None:
    """Atomically write *content*, preserving the target's newline/BOM style."""
    atomic_write_bytes(path, encode_like_existing(path, content))
