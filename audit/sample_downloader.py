from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from collector.attachment_downloader import AttachmentDownloader
from collector.catalog import CatalogStore
from collector.http_client import PoliteHttpClient
from collector.models import Attachment, Post
from config.settings import Settings

from .reporting import write_json
from .store import HistoricalAuditStore


@dataclass(frozen=True)
class SampleDownloadResult:
    success: int
    failed: int
    deduplicated: int


class ParserSampleDownloader:
    def __init__(self, settings: Settings | None = None, client: PoliteHttpClient | None = None) -> None:
        self.settings = settings or Settings()
        self.client = client or PoliteHttpClient(
            user_agent=self.settings.user_agent,
            timeout=self.settings.timeout_seconds,
            delay=self.settings.request_delay_seconds,
            retries=self.settings.retries,
        )

    def run(self) -> SampleDownloadResult:
        manifest = json.loads(self.settings.parser_samples_path.read_text(encoding="utf-8"))
        historical = HistoricalAuditStore(self.settings.historical_catalog_path).load()
        current = CatalogStore(self.settings.catalog_path, self.settings.attachment_history_path).load()
        post_map = {post.post_id: post for post in historical}
        post_map.update({post.post_id: post for post in current})
        downloader = AttachmentDownloader(
            self.settings.sample_raw_root,
            self.client,
            storage_root=self.settings.project_root,
        )
        downloader.seed_hashes(current + self._downloaded_manifest_posts(manifest, post_map))
        success = failed = deduplicated = 0
        for sample in manifest:
            if self._existing_is_valid(sample):
                if sample.get("download_status") == "deduplicated":
                    deduplicated += 1
                else:
                    success += 1
                continue
            post = post_map.get(str(sample["post_id"]))
            source = next(
                (item for item in post.attachments if item.attachment_id == str(sample["attachment_id"])),
                None,
            ) if post else None
            if post is None or source is None:
                failed += 1
                sample["download_status"] = "failed"
                sample["error"] = "sample source metadata not found"
                self._record_failure(sample, sample["error"])
                continue
            attachment = deepcopy(source)
            attachment.status = "discovered"
            attachment.error = None
            attachment.sha256 = None
            attachment.local_path = None
            attachment.duplicate_of = None
            downloader.download(post, attachment)
            sample.update({
                "download_status": "deduplicated" if attachment.status == "duplicate" else attachment.status,
                "sha256": attachment.sha256,
                "local_path": attachment.local_path,
                "file_size": attachment.file_size,
                "mime_type": attachment.mime_type,
                "duplicate_of": attachment.duplicate_of,
            })
            if attachment.status == "failed":
                failed += 1
                sample["error"] = attachment.error
                self._record_failure(sample, attachment.error or "download failed")
            elif attachment.status == "duplicate":
                deduplicated += 1
            else:
                success += 1
            write_json(self.settings.parser_samples_path, manifest)
        write_json(self.settings.parser_samples_path, manifest)
        return SampleDownloadResult(success, failed, deduplicated)

    def _existing_is_valid(self, sample: dict[str, object]) -> bool:
        local_path = sample.get("local_path")
        expected = sample.get("sha256")
        if not local_path or not expected:
            return False
        path = self.settings.project_root / Path(*str(local_path).split("/"))
        if not path.is_file():
            return False
        return hashlib.sha256(path.read_bytes()).hexdigest() == expected

    def _downloaded_manifest_posts(
        self,
        manifest: list[dict[str, object]],
        post_map: dict[str, Post],
    ) -> list[Post]:
        results: list[Post] = []
        for sample in manifest:
            if not self._existing_is_valid(sample):
                continue
            source_post = post_map.get(str(sample["post_id"]))
            if source_post is None:
                continue
            attachment = Attachment(
                attachment_id=str(sample["attachment_id"]),
                original_filename=str(sample["filename"]),
                extension=str(sample["extension"]),
                download_url=str(sample["download_url"]),
                sha256=str(sample["sha256"]),
                local_path=str(sample["local_path"]),
                file_size=int(sample["file_size"]) if sample.get("file_size") is not None else None,
                status="downloaded" if sample.get("download_status") != "deduplicated" else "duplicate",
                duplicate_of=str(sample["duplicate_of"]) if sample.get("duplicate_of") else None,
            )
            post = deepcopy(source_post)
            post.attachments = [attachment]
            post.attachment_count = 1
            results.append(post)
        return results

    def _record_failure(self, sample: dict[str, object], error: str) -> None:
        path = self.settings.sample_download_failures_path
        path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "occurred_at": datetime.now().astimezone().isoformat(),
            "post_id": sample.get("post_id"),
            "attachment_id": sample.get("attachment_id"),
            "download_url": sample.get("download_url"),
            "error": error,
        }
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
