from __future__ import annotations

import json
import hashlib
import os
import time
from pathlib import Path
from typing import Any


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix(path.suffix + ".pending")
    try:
        with pending.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        _replace_with_retry(pending, path)
    finally:
        pending.unlink(missing_ok=True)


def atomic_jsonl(path: Path, values: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix(path.suffix + ".pending")
    try:
        with pending.open("w", encoding="utf-8", newline="\n") as handle:
            for value in values:
                handle.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        _replace_with_retry(pending, path)
    finally:
        pending.unlink(missing_ok=True)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def verified_file(root: Path, item: dict[str, Any]) -> bool:
    if not item.get("local_path") or not item.get("sha256"):
        return False
    path = (root / Path(*str(item["local_path"]).split("/"))).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        return False
    if item.get("file_size") is not None and path.stat().st_size != int(item["file_size"]):
        return False
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest() == item["sha256"]


def _replace_with_retry(source: Path, target: Path, attempts: int = 8) -> None:
    """Keep atomic replacement reliable during brief Windows reader/AV locks."""
    for attempt in range(attempts):
        try:
            os.replace(source, target)
            return
        except PermissionError:
            if attempt + 1 == attempts:
                raise
            time.sleep(0.05 * (attempt + 1))
