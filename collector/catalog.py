from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from .models import Post


class CatalogStore:
    """Validated, atomic JSONL catalog updates."""

    def __init__(self, path: Path, history_path: Path | None = None) -> None:
        self.path = path
        self.history_path = history_path or path.with_name("attachment_history.jsonl")

    def load(self) -> list[Post]:
        if not self.path.exists():
            return []
        posts: list[Post] = []
        with self.path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                try:
                    post = Post.from_dict(json.loads(line))
                    post.validate()
                    posts.append(post)
                except Exception as exc:
                    raise ValueError(f"invalid catalog line {line_number}: {exc}") from exc
        return posts

    def commit(self, new_posts: list[Post], *, existing_posts: list[Post] | None = None) -> None:
        current = {post.post_id: post for post in (existing_posts if existing_posts is not None else self.load())}
        changes: list[dict[str, str]] = []
        for post in new_posts:
            post.validate()
            existing = current.get(post.post_id)
            if existing:
                changes.extend(self._attachment_changes(existing, post))
                current[post.post_id] = self._merge_post(existing, post)
            else:
                current[post.post_id] = post
        ordered = sorted(current.values(), key=lambda p: ((p.published_date or ""), p.post_id), reverse=True)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        pending = self.path.with_suffix(self.path.suffix + ".pending")
        try:
            with pending.open("w", encoding="utf-8", newline="\n") as handle:
                for post in ordered:
                    handle.write(json.dumps(post.to_dict(), ensure_ascii=False, sort_keys=True) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            self._validate_file(pending)
            self._append_history(changes)
            os.replace(pending, self.path)
        finally:
            pending.unlink(missing_ok=True)

    @staticmethod
    def _merge_post(existing: Post, incoming: Post) -> Post:
        """Keep the first canonical download when a refresh only reconfirms it."""
        old_attachments = {item.attachment_id: item for item in existing.attachments}
        merged = []
        for item in incoming.attachments:
            old = old_attachments.get(item.attachment_id)
            failed_refresh = old and old.sha256 and old.local_path and item.status == "failed"
            same_canonical = (
                old
                and old.sha256
                and old.sha256 == item.sha256
                and old.status == "downloaded"
                and item.status == "duplicate"
            )
            if failed_refresh or same_canonical:
                merged.append(old)
            else:
                merged.append(item)
        incoming.attachments = merged
        incoming.attachment_count = len(merged)
        return incoming

    @staticmethod
    def _attachment_changes(existing: Post, incoming: Post) -> list[dict[str, str]]:
        old_attachments = {item.attachment_id: item for item in existing.attachments}
        detected_at = datetime.now().astimezone().isoformat()
        changes: list[dict[str, str]] = []
        for item in incoming.attachments:
            old = old_attachments.get(item.attachment_id)
            if (
                old is None
                or not old.sha256
                or not item.sha256
                or old.sha256 == item.sha256
                or item.status == "failed"
            ):
                continue
            changes.append({
                "detected_at": detected_at,
                "post_id": incoming.post_id,
                "attachment_id": item.attachment_id,
                "old_sha256": old.sha256,
                "new_sha256": item.sha256,
                "old_local_path": old.local_path or "",
                "new_local_path": item.local_path or "",
                "old_filename": old.original_filename,
                "new_filename": item.original_filename,
                "old_download_url": old.download_url,
                "new_download_url": item.download_url,
            })
        return changes

    def _append_history(self, changes: list[dict[str, str]]) -> None:
        if not changes:
            return
        existing_keys: set[tuple[str, str, str, str]] = set()
        if self.history_path.exists():
            with self.history_path.open("r", encoding="utf-8") as handle:
                for line_number, line in enumerate(handle, 1):
                    if not line.strip():
                        continue
                    try:
                        item = json.loads(line)
                        existing_keys.add(self._history_key(item))
                    except Exception as exc:
                        raise ValueError(f"invalid attachment history line {line_number}: {exc}") from exc
        unique = []
        for change in changes:
            key = self._history_key(change)
            if key not in existing_keys:
                unique.append(change)
                existing_keys.add(key)
        if not unique:
            return
        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        with self.history_path.open("a", encoding="utf-8", newline="\n") as handle:
            for change in unique:
                handle.write(json.dumps(change, ensure_ascii=False, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    @staticmethod
    def _history_key(item: dict[str, str]) -> tuple[str, str, str, str]:
        return (
            str(item["post_id"]),
            str(item["attachment_id"]),
            str(item["old_sha256"]),
            str(item["new_sha256"]),
        )

    @staticmethod
    def _validate_file(path: Path) -> None:
        seen: set[str] = set()
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                post = Post.from_dict(json.loads(line))
                post.validate()
                if post.post_id in seen:
                    raise ValueError(f"duplicate post_id: {post.post_id}")
                seen.add(post.post_id)

