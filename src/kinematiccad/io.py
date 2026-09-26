"""Canonical, finite JSON and bounded file access at trust boundaries."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


def canonical(value) -> bytes:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("utf-8")


def digest(value) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical(value) + b"\n")


def read_json(path: Path, limit: int = 16_000_000):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
        raise ValueError(f"Not a regular bounded JSON file: {path.name}")

    def reject(value):
        raise ValueError(f"Non-finite JSON value: {value}")

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Duplicate JSON key: {key}")
            result[key] = value
        return result

    return json.loads(path.read_bytes(), parse_constant=reject, object_pairs_hook=unique)


def confined_file(root: Path, name: str, limit: int = 40_000_000) -> Path:
    """No subdirectories, links, devices, absolute paths or traversal in asset names."""
    if not name or Path(name).name != name or any(c in name for c in "/\\:"):
        raise ValueError("Asset must be a plain filename")
    path = root / name
    if path.is_symlink() or not path.is_file() or path.resolve().parent != root.resolve():
        raise ValueError(f"Unsafe asset: {name}")
    if path.stat().st_size > limit:
        raise ValueError(f"Oversized asset: {name}")
    return path
