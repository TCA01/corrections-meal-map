from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from audit.store import HistoricalAuditStore
from collector.attachment_downloader import AttachmentDownloader
from collector.http_client import PoliteHttpClient
from collector.models import Attachment, Post
from config.settings import Settings

from .io import atomic_json, atomic_jsonl, read_jsonl, verified_file


@dataclass(frozen=True)
class ProductionDownloadResult:
    target: int
    success: int
    reused: int
    deduplicated: int
    failed: int
    next_index: int
    completed: bool


class ProductionExcelDownloader:
    """Sequential, resumable downloader for the production Excel manifest."""

    def __init__(self, settings: Settings | None = None, client: PoliteHttpClient | None = None) -> None:
        self.settings = settings or Settings()
        self.client = client or PoliteHttpClient(
            user_agent=self.settings.user_agent,
            timeout=self.settings.timeout_seconds,
            delay=self.settings.request_delay_seconds,
            retries=self.settings.retries,
        )

    def run(self, *, resume: bool = True, limit: int | None = None,
            from_checkpoint: int | None = None) -> ProductionDownloadResult:
        manifest = read_jsonl(self.settings.production_manifest_path)
        historical = HistoricalAuditStore(self.settings.historical_catalog_path).load()
        post_map = {post.post_id: post for post in historical}
        checkpoint = self._checkpoint() if resume else {}
        input_version = hashlib.sha256(json.dumps([
            [i["document_id"], i["download_url"]] for i in manifest
        ]).encode()).hexdigest()
        if checkpoint.get("input_version") and checkpoint["input_version"] != input_version:
            raise ValueError("download manifest order/source changed; use --no-resume")
        start = int(from_checkpoint if from_checkpoint is not None else checkpoint.get("next_index", 0))
        start = max(0, min(start, len(manifest)))
        stop = len(manifest) if limit is None else min(len(manifest), start + max(limit, 0))

        downloader = AttachmentDownloader(
            self.settings.production_raw_root, self.client, storage_root=self.settings.project_root
        )
        downloader.seed_hashes(self._seed_posts(manifest, post_map))
        for index in range(start, stop):
            item = manifest[index]
            if self._existing_is_valid(item):
                item["download_status"] = "reused"
                item["error"] = None
            else:
                self._download_one(item, post_map, downloader)
            atomic_jsonl(self.settings.production_manifest_path, manifest)
            atomic_json(self.settings.production_download_checkpoint_path, {
                "next_index": index + 1,
                "input_version": input_version,
                "target": len(manifest),
                "completed": index + 1 >= len(manifest),
                "updated_at": datetime.now().astimezone().isoformat(),
            })
            if (index + 1) % 50 == 0:
                print(f"Downloaded/checked {index + 1}/{len(manifest)}", flush=True)
        if start == stop:
            atomic_json(self.settings.production_download_checkpoint_path, {
                "next_index": stop,
                "input_version": input_version,
                "target": len(manifest),
                "completed": stop >= len(manifest),
                "updated_at": datetime.now().astimezone().isoformat(),
            })
        return self._summarize(manifest, stop)

    def _download_one(self, item: dict[str, Any], post_map: dict[str, Post],
                      downloader: AttachmentDownloader) -> None:
        post = post_map.get(str(item["post_id"]))
        source = next((a for a in post.attachments
                       if a.attachment_id == str(item["attachment_id"])), None) if post else None
        if post is None or source is None:
            item.update(download_status="failed", error="source metadata not found")
            self._record_failure(item)
            return
        attachment = deepcopy(source)
        attachment.status = "discovered"
        attachment.error = attachment.sha256 = attachment.local_path = attachment.duplicate_of = None
        downloader.download(post, attachment)
        item.update({
            "download_status": "deduplicated" if attachment.status == "duplicate" else attachment.status,
            "sha256": attachment.sha256,
            "local_path": attachment.local_path,
            "file_size": attachment.file_size,
            "mime_type": attachment.mime_type,
            "duplicate_of": attachment.duplicate_of,
            "downloaded_at": attachment.downloaded_at,
            "error": attachment.error,
        })
        if attachment.status == "failed":
            self._record_failure(item)

    def _seed_posts(self, manifest: list[dict[str, Any]], post_map: dict[str, Post]) -> list[Post]:
        posts: list[Post] = []
        for value in read_jsonl(self.settings.catalog_path):
            post = Post.from_dict(value)
            post.attachments = [a for a in post.attachments if verified_file(self.settings.project_root, a.to_dict())]
            if post.attachments:
                posts.append(post)
        for item in manifest:
            if not self._existing_is_valid(item):
                continue
            source = post_map.get(str(item["post_id"]))
            if source is None:
                continue
            post = deepcopy(source)
            post.attachments = [Attachment(
                attachment_id=str(item["attachment_id"]),
                original_filename=str(item["filename"]),
                extension=str(item["extension"]),
                download_url=str(item["download_url"]),
                sha256=str(item["sha256"]),
                local_path=str(item["local_path"]),
                file_size=int(item["file_size"]) if item.get("file_size") is not None else None,
                status="downloaded",
            )]
            post.attachment_count = 1
            posts.append(post)
        return posts

    def _existing_is_valid(self, item: dict[str, Any]) -> bool:
        return verified_file(self.settings.project_root, item)

    def _checkpoint(self) -> dict[str, Any]:
        path = self.settings.production_download_checkpoint_path
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    def _record_failure(self, item: dict[str, Any]) -> None:
        path = self.settings.production_root / "reports" / "excel_download_failures.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "occurred_at": datetime.now().astimezone().isoformat(),
            "post_id": item.get("post_id"), "attachment_id": item.get("attachment_id"),
            "download_url": item.get("download_url"), "error": item.get("error") or "download failed",
        }
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    @staticmethod
    def _summarize(manifest: list[dict[str, Any]], next_index: int) -> ProductionDownloadResult:
        statuses = [item.get("download_status") for item in manifest]
        return ProductionDownloadResult(
            target=len(manifest), success=statuses.count("downloaded"), reused=statuses.count("reused"),
            deduplicated=statuses.count("deduplicated"), failed=statuses.count("failed"),
            next_index=next_index, completed=next_index >= len(manifest),
        )
