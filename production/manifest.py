from __future__ import annotations

import json
from typing import Any

from audit.store import HistoricalAuditStore
from config.settings import Settings
from collector.normalizer import parse_year_month
from collector.models import Post

from .io import atomic_jsonl, read_jsonl


TARGET_ROLES = {"inmate", "mixed"}
TARGET_EXTENSIONS = {"xlsx", "xls"}


def build_excel_manifest(settings: Settings | None = None) -> list[dict[str, Any]]:
    settings = settings or Settings()
    existing = {
        (str(item["post_id"]), str(item["attachment_id"])): item
        for item in read_jsonl(settings.production_manifest_path)
    }
    sample_downloads = {}
    # Reuse current collector originals as well as representative samples.
    for value in read_jsonl(settings.catalog_path):
        post = Post.from_dict(value)
        for attachment in post.attachments:
            sample_downloads[(post.post_id, attachment.attachment_id)] = {
                **attachment.to_dict(), "filename": attachment.original_filename,
                "download_status": attachment.status,
            }
    if settings.parser_samples_path.exists():
        for item in json.loads(settings.parser_samples_path.read_text(encoding="utf-8")):
            sample_downloads[(str(item["post_id"]), str(item["attachment_id"]))] = item
    values = []
    for post in HistoricalAuditStore(settings.historical_catalog_path).load():
        for attachment in post.attachments:
            if attachment.document_role not in TARGET_ROLES or attachment.extension not in TARGET_EXTENSIONS:
                continue
            key = (post.post_id, attachment.attachment_id)
            old = existing.get(key, {})
            sample = sample_downloads.get(key, {})
            title_year, title_month = parse_year_month(post.title)
            filename_year, filename_month = parse_year_month(attachment.original_filename)
            values.append({
                **old,
                "document_id": f"{post.post_id}-{attachment.attachment_id}",
                "post_id": post.post_id,
                "attachment_id": attachment.attachment_id,
                "institution_id": post.institution_id,
                "institution_name": post.institution_name,
                "filename": attachment.original_filename,
                "declared_extension": attachment.extension,
                "extension": attachment.extension,
                "document_role": attachment.document_role,
                "source_title": post.title,
                "metadata_year_inferred": bool(post.meal_year and title_year is None),
                "period_metadata": {
                    "title_year": title_year, "title_month": title_month,
                    "filename_year": filename_year, "filename_month": filename_month,
                    "metadata_year_source": "title" if title_year else "publication_fallback",
                },
                "meal_year": post.meal_year,
                "meal_month": post.meal_month,
                "published_date": post.published_date,
                "post_url": post.post_url,
                "download_url": attachment.download_url,
                "download_status": old.get("download_status", sample.get("download_status", "pending")),
                "sha256": old.get("sha256", sample.get("sha256")),
                "file_size": old.get("file_size", sample.get("file_size")),
                "local_path": old.get("local_path", sample.get("local_path")),
                "duplicate_of": old.get("duplicate_of", sample.get("duplicate_of")),
                "parser_status": old.get("parser_status", "pending"),
                "production_status": old.get("production_status", "pending"),
                "error": old.get("error"),
            })
    values.sort(key=lambda item: (item["published_date"] or "", item["document_id"]), reverse=True)
    atomic_jsonl(settings.production_manifest_path, values)
    return values
