from __future__ import annotations

import json
import os
import re
from collections import Counter, defaultdict
from pathlib import Path

from collector.models import Post
from institutions.master import InstitutionMaster


FILE_TYPES = ("xlsx", "xls", "pdf", "hwp", "hwpx", "csv", "unknown")
ROLES = ("inmate", "staff", "mixed", "supplementary", "other", "unknown")


def build_audit_summary(posts: list[Post], master: InstitutionMaster) -> dict[str, object]:
    attachments = [item for post in posts for item in post.attachments]
    institutions = Counter(post.institution_id or "unresolved" for post in posts)
    unresolved = Counter(post.institution_name for post in posts if not post.institution_id)
    file_types = Counter(item.extension for item in attachments)
    roles = Counter(item.document_role or "unknown" for item in attachments)
    parser_attachments = [item for item in attachments if (item.document_role or "unknown") in {"inmate", "mixed"}]
    parser_file_types = Counter(item.extension for item in parser_attachments)
    years = Counter(str(post.meal_year or (post.published_date or "unknown")[:4]) for post in posts)
    months = Counter(
        f"{post.meal_year or 'unknown'}-{post.meal_month:02d}" if post.meal_month else "unknown"
        for post in posts
    )
    institution_file_types: dict[str, Counter[str]] = defaultdict(Counter)
    file_type_year: dict[str, Counter[str]] = defaultdict(Counter)
    for post in posts:
        institution = post.institution_id or f"unresolved:{post.institution_name}"
        year = str(post.meal_year or (post.published_date or "unknown")[:4])
        for item in post.attachments:
            institution_file_types[institution][item.extension] += 1
            file_type_year[item.extension][year] += 1
    return {
        "total_meal_posts": len(posts),
        "total_attachments": len(attachments),
        "institutions": dict(sorted(institutions.items())),
        "resolved_institution_count": len({post.institution_id for post in posts if post.institution_id}),
        "master_institution_count": len(master.institutions),
        "unresolved_institutions": dict(sorted(unresolved.items())),
        "file_types": {key: file_types[key] for key in FILE_TYPES},
        "inmate_mixed_file_types": {key: parser_file_types[key] for key in FILE_TYPES},
        "document_roles": {key: roles[key] for key in ROLES},
        "year_distribution": dict(sorted(years.items())),
        "month_distribution": dict(sorted(months.items())),
        "institution_file_types": {
            key: dict(sorted(value.items())) for key, value in sorted(institution_file_types.items())
        },
        "file_type_year": {key: dict(sorted(value.items())) for key, value in sorted(file_type_year.items())},
    }


def build_corpus_comparison(baseline: dict[str, object], current: dict[str, object]) -> dict[str, object]:
    baseline_total = int(baseline["total_attachments"])
    current_total = int(current["total_attachments"])
    baseline_types = dict(baseline["file_types"])
    current_types = dict(current["file_types"])
    return {
        "baseline_search_pages": baseline.get("search_pages"),
        "baseline_attachments": baseline_total,
        "completed_attachments": current_total,
        "file_types": {
            key: {
                "baseline_count": int(baseline_types.get(key, 0)),
                "baseline_percent": round(int(baseline_types.get(key, 0)) / baseline_total * 100, 2),
                "completed_count": int(current_types.get(key, 0)),
                "completed_percent": round(int(current_types.get(key, 0)) / current_total * 100, 2),
                "percentage_point_change": round(
                    int(current_types.get(key, 0)) / current_total * 100
                    - int(baseline_types.get(key, 0)) / baseline_total * 100,
                    2,
                ),
            }
            for key in FILE_TYPES
        },
    }


def build_parser_priority(summary: dict[str, object]) -> dict[str, object]:
    counts = dict(summary["inmate_mixed_file_types"])
    total = sum(int(value) for value in counts.values())
    formats = [
        {
            "extension": extension,
            "count": int(counts.get(extension, 0)),
            "percent": round(int(counts.get(extension, 0)) / total * 100, 2) if total else 0.0,
        }
        for extension in FILE_TYPES
    ]
    formats.sort(key=lambda item: (-int(item["count"]), str(item["extension"])))
    return {"inmate_mixed_attachments": total, "priority_by_coverage": formats}


def unresolved_report(posts: list[Post]) -> list[dict[str, object]]:
    grouped: dict[str, list[str]] = defaultdict(list)
    for post in posts:
        if not post.institution_id:
            grouped[post.institution_name].append(post.post_id)
    return [
        {"source_institution": source, "count": len(ids), "post_ids": sorted(ids)}
        for source, ids in sorted(grouped.items())
    ]


def unknown_role_report(posts: list[Post]) -> list[dict[str, str]]:
    return [
        {
            "post_id": post.post_id,
            "attachment_id": item.attachment_id,
            "filename": item.original_filename,
            "post_title": post.title,
            "rule": item.role_rule or "not_classified",
        }
        for post in posts
        for item in post.attachments
        if (item.document_role or "unknown") == "unknown"
    ]


def select_representative_samples(posts: list[Post], limit: int = 24) -> list[dict[str, object]]:
    return _select_diverse_samples(posts, limit=limit, allowed_roles=None)


def select_parser_samples(posts: list[Post], limit: int = 40) -> list[dict[str, object]]:
    """Select a compact, diverse corpus for inmate meal parser development."""
    return _select_diverse_samples(
        posts,
        limit=limit,
        allowed_roles={"inmate", "mixed"},
        allowed_extensions={"xlsx", "xls", "pdf", "hwp", "hwpx"},
    )


def select_classification_samples(posts: list[Post], limit: int = 24) -> list[dict[str, object]]:
    """Select role edge cases separately from parser-development documents."""
    edge_roles = {"staff", "supplementary", "other", "unknown"}
    samples = _select_diverse_samples(posts, limit=limit, allowed_roles=edge_roles)
    selected = {(item["post_id"], item["attachment_id"]) for item in samples}
    complex_posts = [
        post for post in posts
        if len({item.document_role or "unknown" for item in post.attachments}) > 1
    ]
    for post in sorted(complex_posts, key=lambda value: value.published_date or "", reverse=True):
        for item in post.attachments:
            key = (post.post_id, item.attachment_id)
            if key in selected or len(samples) >= limit:
                continue
            samples.append(_sample_record(post, item, "multi-role post coverage"))
            selected.add(key)
            break
    return samples


def _select_diverse_samples(
    posts: list[Post],
    *,
    limit: int,
    allowed_roles: set[str] | None,
    allowed_extensions: set[str] | None = None,
) -> list[dict[str, object]]:
    candidates = [
        (post, item)
        for post in sorted(posts, key=lambda value: value.published_date or "", reverse=True)
        for item in post.attachments
        if allowed_roles is None or (item.document_role or "unknown") in allowed_roles
        if allowed_extensions is None or item.extension in allowed_extensions
    ]
    selected: list[dict[str, object]] = []
    selected_keys: set[tuple[str, str]] = set()
    covered_extensions: set[str] = set()
    covered_institutions: set[str] = set()
    covered_years: set[int | None] = set()
    covered_patterns: set[str] = set()

    def add(post: Post, item: object, reason: str) -> None:
        attachment = item
        key = (post.post_id, attachment.attachment_id)
        if key in selected_keys or len(selected) >= limit:
            return
        selected_keys.add(key)
        pattern = filename_pattern(attachment.original_filename)
        selected.append(_sample_record(post, attachment, reason))
        covered_extensions.add(attachment.extension)
        if post.institution_id:
            covered_institutions.add(post.institution_id)
        covered_years.add(post.meal_year)
        covered_patterns.add(pattern)

    # Cover each format with both its oldest and newest candidate when possible.
    for extension in FILE_TYPES:
        extension_candidates = [(post, item) for post, item in candidates if item.extension == extension]
        if not extension_candidates:
            continue
        newest = extension_candidates[0]
        oldest = extension_candidates[-1]
        add(*newest, f"newest available {extension} sample")
        if oldest != newest:
            add(*oldest, f"oldest available {extension} sample")
    # Years come before institutions so a compact manifest does not spend its
    # whole budget on the many current institutions and miss older layouts.
    for post, item in candidates:
        if post.meal_year not in covered_years:
            add(post, item, f"year coverage: {post.meal_year}")
    for post, item in candidates:
        if post.institution_id and post.institution_id not in covered_institutions:
            add(post, item, f"institution coverage: {post.institution_id}")
    for post, item in candidates:
        pattern = filename_pattern(item.original_filename)
        if pattern not in covered_patterns:
            add(post, item, f"filename pattern coverage: {pattern}")
    return selected


def _sample_record(post: Post, attachment: object, reason: str) -> dict[str, object]:
    item = attachment
    return {
        "institution_id": post.institution_id,
        "post_id": post.post_id,
        "attachment_id": item.attachment_id,
        "filename": item.original_filename,
        "extension": item.extension,
        "published_date": post.published_date,
        "meal_year": post.meal_year,
        "meal_month": post.meal_month,
        "document_role": item.document_role or "unknown",
        "download_url": item.download_url,
        "selection_reason": reason,
        "download_status": "pending",
        "sha256": None,
        "local_path": None,
        "file_size": None,
    }


def preserve_download_metadata(
    samples: list[dict[str, object]],
    previous: list[dict[str, object]],
) -> list[dict[str, object]]:
    by_key = {(str(item.get("post_id")), str(item.get("attachment_id"))): item for item in previous}
    for sample in samples:
        old = by_key.get((str(sample["post_id"]), str(sample["attachment_id"])))
        if not old:
            continue
        for field in ("download_status", "sha256", "local_path", "file_size", "mime_type", "duplicate_of"):
            if old.get(field) is not None:
                sample[field] = old[field]
    return samples


def filename_pattern(filename: str) -> str:
    value = re.sub(r"\d+", "#", filename.lower())
    value = re.sub(r"[\s_.()-]+", " ", value).strip()
    return value[:80]


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix(path.suffix + ".pending")
    try:
        pending.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(pending, path)
    finally:
        pending.unlink(missing_ok=True)
