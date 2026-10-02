from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict


def build_template_families(records: list[dict[str, object]]) -> dict[str, list[dict[str, object]]]:
    groups: dict[str, dict[str, list[dict[str, object]]]] = defaultdict(lambda: defaultdict(list))
    fingerprints: dict[tuple[str, str], dict[str, object]] = {}
    for record in records:
        if record.get("survey_status") != "ok":
            continue
        extension = str(record.get("extension", "unknown"))
        features = template_features(record)
        canonical = json.dumps(features, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]
        groups[extension][digest].append(record)
        fingerprints[(extension, digest)] = features
    result: dict[str, list[dict[str, object]]] = {}
    for extension, extension_groups in sorted(groups.items()):
        families = []
        for index, (digest, items) in enumerate(
            sorted(extension_groups.items(), key=lambda pair: (-len(pair[1]), pair[0])), 1
        ):
            families.append({
                "family_id": f"{extension.upper()}-{index:02d}-{digest}",
                "sample_count": len(items),
                "institutions": sorted({str(item.get("institution_id")) for item in items}),
                "files": sorted(str(item.get("filename")) for item in items),
                "fingerprint": fingerprints[(extension, digest)],
            })
        result[extension] = families
    return result


def template_features(record: dict[str, object]) -> dict[str, object]:
    extension = str(record.get("extension"))
    if extension in {"xlsx", "xls"}:
        sheets = list(record.get("sheets", []))
        return {
            "sheet_count": record.get("sheet_count"),
            "sheet_names": [normalize_name(str(sheet.get("name", ""))) for sheet in sheets],
            "used_shapes": [used_shape(sheet) for sheet in sheets],
            "merged_counts": [sheet.get("merged_cell_ranges") for sheet in sheets],
            "meal_keywords": [keyword_presence(sheet.get("meal_keyword_counts", {})) for sheet in sheets],
        }
    if extension == "pdf":
        pages = list(record.get("pages", []))
        blocks = sum(int(page.get("text_block_count", 0)) for page in pages)
        text = int(record.get("text_character_count", 0))
        images = int(record.get("image_count", 0))
        first = pages[0] if pages else {}
        return {
            "page_count": record.get("page_count"),
            "page_size": [first.get("width_points"), first.get("height_points")],
            "text_block_bucket": bucket(blocks, (20, 60, 120, 240)),
            "text_character_bucket": bucket(text, (100, 500, 1000, 2500, 5000)),
            "image_bucket": bucket(images, (0, 2, 6, 12)),
            "possible_image_only": record.get("possible_image_only"),
        }
    if extension == "hwpx":
        return {
            "section_count": record.get("section_count"),
            "table_count": record.get("table_count"),
            "nested_table_count": record.get("nested_table_count"),
            "row_count": record.get("row_count"),
            "cell_count": record.get("cell_count"),
            "max_detected_columns": record.get("max_detected_columns"),
            "meal_keywords": keyword_presence(record.get("meal_keyword_counts", {})),
        }
    if extension == "hwp":
        return {
            "is_ole_cfb": record.get("is_ole_cfb"),
            "ole_stream_count": record.get("ole_stream_count"),
        }
    return {"extension": extension}


def normalize_name(value: str) -> str:
    return re.sub(r"\d+", "#", re.sub(r"\s+", "", value.lower()))


def used_shape(sheet: dict[str, object]) -> list[object]:
    used = dict(sheet.get("nonempty_used_range", {}))
    if not used.get("min_row"):
        return [0, 0]
    return [
        int(used["max_row"]) - int(used["min_row"]) + 1,
        int(used["max_column"]) - int(used["min_column"]) + 1,
    ]


def keyword_presence(value: object) -> list[str]:
    mapping = dict(value) if isinstance(value, dict) else {}
    return sorted(key for key, count in mapping.items() if count)


def bucket(value: int, thresholds: tuple[int, ...]) -> str:
    for threshold in thresholds:
        if value <= threshold:
            return f"<= {threshold}"
    return f"> {thresholds[-1]}"
