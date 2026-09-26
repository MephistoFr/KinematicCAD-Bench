"""Flat, bounded ZIP transport. Untrusted archives are never passed to extractall."""

from __future__ import annotations

import io
import re
import stat
import zipfile
from pathlib import Path

LIMIT = 120_000_000
RESERVED = {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"} | {
    f"{prefix}{number}" for prefix in ("COM", "LPT") for number in range(1, 10)
}


def pack(root: Path) -> bytes:
    buffer = io.BytesIO()
    total = 0
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        for path in sorted(root.iterdir()):
            if path.is_symlink() or not path.is_file():
                raise ValueError("Only regular flat artifact files are permitted")
            total += path.stat().st_size
            if total > LIMIT:
                raise ValueError("Artifact quota exceeded")
            info = zipfile.ZipInfo(path.name, date_time=(1980, 1, 1, 0, 0, 0))
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(info, path.read_bytes())
    return buffer.getvalue()


def unpack(data: bytes, root: Path, *, candidate=False):
    if len(data) > LIMIT + 100_000:
        raise ValueError("Artifact archive too large")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        infos = archive.infolist()
        if len(infos) > 100 or sum(i.file_size for i in infos) > LIMIT:
            raise ValueError("Artifact quota exceeded")
        names = set()
        for info in infos:
            name = info.filename
            mode = info.external_attr >> 16
            if (
                not name
                or Path(name).name != name
                or any(c in name for c in "/\\:")
                or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,199}", name)
                or name.endswith(".")
                or name.split(".")[0].upper() in RESERVED
                or name.casefold() in names
                or stat.S_ISLNK(mode)
                or info.is_dir()
                or (stat.S_IFMT(mode) not in (0, stat.S_IFREG))
            ):
                raise ValueError("Unsafe artifact filename or type")
            if info.compress_type != zipfile.ZIP_STORED or info.file_size > 64_000_000:
                raise ValueError("Unexpected compression or oversized artifact")
            if candidate and name != "submission.json" and not name.endswith(".step"):
                raise ValueError("Candidate may return only STEP and submission.json")
            names.add(name.casefold())
        root.mkdir(parents=True, exist_ok=True)
        if any(root.iterdir()):
            raise ValueError("Artifact destination must be empty")
        for info in infos:
            (root / info.filename).write_bytes(archive.read(info))
