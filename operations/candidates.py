from __future__ import annotations

from audit.document_roles import classify_document_role
from collector.models import Post
from collector.normalizer import parse_year_month
from production.io import atomic_jsonl, read_jsonl


def candidate_manifest(posts, baseline, master):
    result = []
    seen = set()
    old_posts = {key.split("-", 1)[0] for key in baseline}
    for post in posts:
        institution = master.resolve_post(post.institution_name, post.title)
        for attachment in post.attachments:
            document_id = f"{post.post_id}-{attachment.attachment_id}"
            if document_id in seen:
                continue
            seen.add(document_id)
            old = baseline.get(document_id)
            change = ("NEW_POST" if post.post_id not in old_posts else "NEW_ATTACHMENT") if old is None else "NEW_ATTACHMENT" if not old.get("sha256") else (
                "UNCHANGED" if old.get("sha256") and old["sha256"] == attachment.sha256 else "ATTACHMENT_CHANGED")
            role = classify_document_role(attachment.original_filename, post.title,
                                          [a.original_filename for a in post.attachments])
            title_year, title_month = parse_year_month(post.title)
            filename_year, filename_month = parse_year_month(attachment.original_filename)
            result.append({
                "document_id": document_id, "post_id": post.post_id, "attachment_id": attachment.attachment_id,
                "institution_id": institution.institution_id,
                "institution_name": post.institution_name, "filename": attachment.original_filename,
                "document_role": role.role, "declared_extension": attachment.declared_extension or attachment.extension,
                "extension": attachment.extension, "detected_format": None, "sha256": attachment.sha256,
                "change_type": change, "download_status": attachment.status, "file_size": attachment.file_size,
                "local_path": attachment.local_path, "post_url": post.post_url,
                "download_url": attachment.download_url, "published_date": post.published_date,
                "source_title": post.title, "meal_year": post.meal_year, "meal_month": post.meal_month,
                "metadata_year_inferred": bool(post.meal_year and not title_year),
                "period_metadata": {"title_year": title_year, "title_month": title_month,
                                    "filename_year": filename_year, "filename_month": filename_month,
                                    "metadata_year_source": "title" if title_year else "publication_fallback"},
            })
    return result


def seed_ops_catalog(settings, destination, active_manifest):
    """Independent operational catalog; never rewrite the original eight-file catalog."""
    if destination.exists():
        return
    posts = {str(p["post_id"]): p for p in read_jsonl(settings.historical_catalog_path)}
    posts.update({str(p["post_id"]): p for p in read_jsonl(settings.catalog_path)})
    known = {(str(i["post_id"]), str(i["attachment_id"])): i for i in active_manifest}
    for value in posts.values():
        for attachment in value["attachments"]:
            item = known.get((str(value["post_id"]), str(attachment["attachment_id"])))
            if item and item.get("sha256") and item.get("local_path"):
                attachment.update(sha256=item["sha256"], file_size=item.get("file_size"),
                                  local_path=item["local_path"], status="downloaded", error=None)
        Post.from_dict(value).validate()
    atomic_jsonl(destination, list(posts.values()))
