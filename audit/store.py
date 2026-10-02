from __future__ import annotations

import json
import os
from pathlib import Path

from collector.models import Post


class HistoricalAuditStore:
    def __init__(self, path: Path) -> None:
        self.path = path

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
                    raise ValueError(f"invalid historical catalog line {line_number}: {exc}") from exc
        return posts

    def commit(self, new_posts: list[Post]) -> None:
        current = {post.post_id: post for post in self.load()}
        for post in new_posts:
            post.validate()
            current[post.post_id] = post
        ordered = sorted(current.values(), key=lambda post: (post.published_date or "", post.post_id), reverse=True)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        pending = self.path.with_suffix(self.path.suffix + ".pending")
        try:
            with pending.open("w", encoding="utf-8", newline="\n") as handle:
                for post in ordered:
                    handle.write(json.dumps(post.to_dict(), ensure_ascii=False, sort_keys=True) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            # Re-read before replacing the last known-good audit catalog.
            with pending.open("r", encoding="utf-8") as handle:
                for line in handle:
                    Post.from_dict(json.loads(line)).validate()
            os.replace(pending, self.path)
        finally:
            pending.unlink(missing_ok=True)

