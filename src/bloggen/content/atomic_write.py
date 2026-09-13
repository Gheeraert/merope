"""Small, GUI-independent primitives for crash-safe file replacement."""

from __future__ import annotations

import os
import stat
import tempfile
from pathlib import Path


def atomic_write_text(
    path: Path,
    text: str,
    *,
    encoding: str = "utf-8",
) -> None:
    """Write ``text`` completely before atomically replacing ``path``.

    The caller owns creation of the parent directory.  The temporary file is
    created beside the target so :func:`os.replace` stays on the same volume.
    """

    target = Path(path)
    try:
        target_mode = stat.S_IMODE(target.stat().st_mode)
    except FileNotFoundError:
        target_mode = None

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.tmp-",
        dir=target.parent,
    )
    temporary_path = Path(temporary_name)
    descriptor_open = True
    try:
        stream = os.fdopen(descriptor, "w", encoding=encoding)
        descriptor_open = False
        with stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())

        if target_mode is not None:
            os.chmod(temporary_path, target_mode)
        os.replace(temporary_path, target)
    finally:
        try:
            if descriptor_open:
                os.close(descriptor)
        finally:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
