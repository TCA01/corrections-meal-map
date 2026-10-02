from __future__ import annotations

import hashlib
import mimetypes
import os
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from .http_client import PoliteHttpClient
from .models import Attachment, Post
from .normalizer import safe_filename, slugify_institution


class AttachmentDownloader:
    def __init__(self, raw_root: Path, client: PoliteHttpClient, *, storage_root: Path | None = None) -> None:
        self.raw_root = raw_root
        self.storage_root = storage_root or raw_root
        self.client = client
        self.hash_index: dict[str, str] = {}

    def seed_hashes(self, posts: list[Post]) -> None:
        available: dict[str, list[Attachment]] = defaultdict(list)
        for post in posts:
            for item in post.attachments:
                if item.sha256 and item.local_path:
                    local_file = self.resolve_storage_path(item.local_path)
                    if local_file.is_file():
                        try:
                            item.local_path = self.storage_key(local_file)
                        except ValueError:
                            continue
                        item.content_type_mismatch = self._mime_mismatch(item.extension, item.mime_type)
                        if item.duplicate_of:
                            duplicate_file = self.resolve_storage_path(item.duplicate_of)
                            if duplicate_file.is_file():
                                try:
                                    item.duplicate_of = self.storage_key(duplicate_file)
                                except ValueError:
                                    pass
                        available[item.sha256].append(item)
        for sha256, items in available.items():
            canonical = next((item for item in items if item.status == "downloaded"), None)
            if canonical is None:
                # Repair catalogs written by the pre-1.1 refresh bug: every
                # record for a hash could have been overwritten as duplicate.
                canonical = items[0]
                canonical.status = "downloaded"
                canonical.duplicate_of = None
            self.hash_index[sha256] = canonical.local_path or ""

    def download(self, post: Post, attachment: Attachment) -> Attachment:
        year = post.meal_year or (int(post.published_date[:4]) if post.published_date else 0)
        month = post.meal_month or (int(post.published_date[5:7]) if post.published_date else 0)
        directory = self.raw_root / slugify_institution(post.institution_name) / f"{year:04d}" / f"{month:02d}"
        directory.mkdir(parents=True, exist_ok=True)
        target = self._available_path(directory / safe_filename(attachment.original_filename))
        temporary = target.with_suffix(target.suffix + ".part")
        digest = hashlib.sha256()
        size = 0
        try:
            response = self.client.get(attachment.download_url, stream=True)
            content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip() or None
            with temporary.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=64 * 1024):
                    if chunk:
                        handle.write(chunk)
                        digest.update(chunk)
                        size += len(chunk)
                handle.flush()
                os.fsync(handle.fileno())
            sha256 = digest.hexdigest()
            attachment.mime_type = content_type
            attachment.file_size = size
            attachment.sha256 = sha256
            attachment.downloaded_at = datetime.now().astimezone().isoformat()
            attachment.content_type_mismatch = self._mime_mismatch(attachment.extension, content_type)
            if sha256 in self.hash_index:
                attachment.duplicate_of = self.hash_index[sha256]
                attachment.local_path = self.hash_index[sha256]
                attachment.status = "duplicate"
                temporary.unlink(missing_ok=True)
            else:
                os.replace(temporary, target)
                attachment.local_path = self.storage_key(target)
                attachment.status = "downloaded"
                self.hash_index[sha256] = attachment.local_path
        except Exception as exc:
            temporary.unlink(missing_ok=True)
            attachment.status = "failed"
            attachment.error = str(exc)
        return attachment

    def storage_key(self, path: Path) -> str:
        """Return a POSIX-style path relative to the configured project/storage root."""
        resolved = path.resolve()
        root = self.storage_root.resolve()
        try:
            return resolved.relative_to(root).as_posix()
        except ValueError as exc:
            raise ValueError(f"raw file is outside storage root: {resolved}") from exc

    def resolve_storage_path(self, value: str) -> Path:
        path = Path(value)
        return path if path.is_absolute() else self.storage_root / Path(*value.split("/"))

    @staticmethod
    def _available_path(target: Path) -> Path:
        if not target.exists():
            return target
        counter = 2
        while True:
            candidate = target.with_name(f"{target.stem}-{counter}{target.suffix}")
            if not candidate.exists():
                return candidate
            counter += 1

    @staticmethod
    def _mime_mismatch(extension: str, content_type: str | None) -> bool:
        generic_types = {
            "application/octet-stream",
            "application/x-msdownload",
            "application/download",
            "application/force-download",
            "binary/octet-stream",
        }
        if extension == "unknown" or not content_type or content_type.lower() in generic_types:
            return False
        expected, _ = mimetypes.guess_type(f"file.{extension}")
        aliases = {
            "application/vnd.hancom.hwp": {"application/x-hwp", "application/haansofthwp"},
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {"application/zip"},
        }
        return content_type != expected and content_type not in aliases.get(expected or "", set())

