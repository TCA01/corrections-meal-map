from __future__ import annotations

import json
import logging
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime

from config.settings import Settings

from .attachment_downloader import AttachmentDownloader
from .catalog import CatalogStore
from .http_client import PoliteHttpClient
from .models import Post
from .site_adapter import CorrectionsSiteAdapter


@dataclass(frozen=True)
class CollectionRunResult:
    posts: list[Post]
    status: str
    failure_count: int = 0
    fatal_error: str | None = None
    posts_checked: int | None = None

    @property
    def exit_code(self) -> int:
        return {"success": 0, "partial": 1, "fatal": 2}[self.status]


class CorrectionsCrawler:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()
        self.adapter = CorrectionsSiteAdapter()
        self.client = PoliteHttpClient(
            user_agent=self.settings.user_agent,
            timeout=self.settings.timeout_seconds,
            delay=self.settings.request_delay_seconds,
            retries=self.settings.retries,
        )
        self.catalog = CatalogStore(
            self.settings.catalog_path,
            self.settings.attachment_history_path,
        )
        self.downloader = AttachmentDownloader(
            self.settings.raw_root,
            self.client,
            storage_root=self.settings.project_root,
        )

    def collect(
        self,
        *,
        pages: int = 1,
        latest_only: bool = False,
        refresh_recent: int = 0,
        dry_run: bool = False,
    ) -> CollectionRunResult:
        existing = self.catalog.load()
        existing_ids = {post.post_id for post in existing}
        self.downloader.seed_hashes(existing)
        discovered: list[Post] = []
        failure_count = 0
        meal_position = 0
        refreshed_existing = 0
        seen_post_ids: set[str] = set()
        posts_checked = 0
        try:
            initial_response = self.client.get(self.settings.start_url)
            # Pass bytes so BeautifulSoup can honor the document's own encoding
            # instead of a occasionally incorrect HTTP charset declaration.
            initial_html = initial_response.content
        except Exception as exc:
            self._record_failure("list", self.settings.start_url, exc)
            return CollectionRunResult([], "fatal", failure_count=1, fatal_error=str(exc))
        refresh_mode = latest_only and refresh_recent > 0
        max_pages = max(pages, self.settings.refresh_max_pages if refresh_mode else pages)
        page = 1
        while page <= max_pages:
            list_url, form_data = self.adapter.list_request(initial_html, self.settings.start_url, page)
            try:
                if page == 1:
                    list_html = initial_html
                else:
                    response = self.client.post(list_url, data=form_data or {})
                    list_html = response.content
                candidates = self.adapter.parse_list(list_html, list_url)
            except Exception as exc:
                self._record_failure("list", list_url, exc)
                failure_count += 1
                page += 1
                continue
            if not candidates:
                break
            for candidate in candidates:
                if not candidate.is_meal_plan or candidate.post_id in seen_post_ids:
                    continue
                seen_post_ids.add(candidate.post_id)
                meal_position += 1
                if candidate.post_id in existing_ids and latest_only:
                    if not self._should_refresh_existing(
                        candidate.post_id,
                        existing_ids,
                        latest_only,
                        refresh_recent,
                        refreshed_existing,
                    ):
                        continue
                    refreshed_existing += 1
                try:
                    posts_checked += 1
                    detail_url, detail_data = self.adapter.detail_request(list_html, candidate)
                    detail = self.client.post(detail_url, data=detail_data)
                    post = self.adapter.parse_detail(detail.content, candidate)
                except Exception as exc:
                    self._record_failure("detail", candidate.post_url, exc, candidate.post_id)
                    failure_count += 1
                    continue
                if not dry_run:
                    for attachment in post.attachments:
                        self.downloader.download(post, attachment)
                        if attachment.status == "failed":
                            self._record_failure("attachment", attachment.download_url, RuntimeError(attachment.error or "download failed"), post.post_id)
                            failure_count += 1
                discovered.append(post)
            if page >= pages and (not refresh_mode or refreshed_existing >= refresh_recent):
                break
            page += 1
        if not dry_run and discovered:
            try:
                # Keep run outcomes intact: merging may preserve an old canonical
                # attachment, but operations must still observe the failed refresh.
                self.catalog.commit(deepcopy(discovered), existing_posts=existing)
            except Exception as exc:
                self._record_failure("catalog", str(self.settings.catalog_path), exc)
                failure_count += 1
        status = "partial" if failure_count else "success"
        return CollectionRunResult(discovered, status, failure_count=failure_count, posts_checked=posts_checked)

    @staticmethod
    def _should_refresh_existing(
        post_id: str,
        existing_ids: set[str],
        latest_only: bool,
        refresh_recent: int,
        refreshed_existing: int,
    ) -> bool:
        if post_id not in existing_ids or not latest_only:
            return True
        return refresh_recent > 0 and refreshed_existing < refresh_recent

    def _record_failure(self, stage: str, url: str, exc: Exception, post_id: str | None = None) -> None:
        logging.error("%s failed for %s: %s", stage, url, exc)
        path = self.settings.failures_path
        path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "occurred_at": datetime.now().astimezone().isoformat(),
            "stage": stage,
            "url": url,
            "post_id": post_id,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

