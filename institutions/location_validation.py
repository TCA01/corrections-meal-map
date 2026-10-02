"""Conservative address/coordinate checks, not an assertion of survey precision."""
from __future__ import annotations

import math
import re
from collections import defaultdict


PROVINCES = {
    "서울": ("서울특별시", "서울시", "서울"), "경기": ("경기도", "경기"),
    "인천": ("인천광역시", "인천시", "인천"), "강원": ("강원특별자치도", "강원도", "강원"),
    "부산": ("부산광역시", "부산시", "부산"), "대구": ("대구광역시", "대구시", "대구"),
    "울산": ("울산광역시", "울산시", "울산"), "경북": ("경상북도", "경북"),
    "경남": ("경상남도", "경남"), "대전": ("대전광역시", "대전시", "대전"),
    "충북": ("충청북도", "충북"), "충남": ("충청남도", "충남"),
    "전북": ("전북특별자치도", "전라북도", "전북"), "전남": ("전라남도", "전남"),
    "광주": ("광주광역시", "광주시", "광주"), "제주": ("제주특별자치도", "제주도", "제주"),
    "세종": ("세종특별자치시", "세종시", "세종"),
}
# Coarse rejection envelopes only, not boundaries, geocodes or substitute points.
REGION_BOUNDS = {
    "서울": (37.40, 37.72, 126.75, 127.20), "경기": (36.85, 38.35, 126.35, 127.95),
    "인천": (37.20, 37.95, 124.55, 126.90), "강원": (37.00, 38.65, 127.05, 129.45),
    "부산": (34.85, 35.45, 128.70, 129.40), "대구": (35.55, 36.40, 128.25, 129.00),
    "울산": (35.20, 35.85, 128.90, 129.65), "경북": (35.55, 37.60, 127.70, 130.95),
    "경남": (34.55, 35.95, 127.55, 129.30), "대전": (36.15, 36.65, 127.15, 127.65),
    "충북": (36.00, 37.25, 127.25, 128.70), "충남": (35.90, 37.15, 125.80, 127.75),
    "전북": (35.25, 36.30, 125.80, 127.95), "전남": (33.90, 35.55, 125.00, 127.95),
    "광주": (35.00, 35.30, 126.60, 127.05), "제주": (33.10, 33.65, 126.10, 127.00),
    "세종": (36.40, 36.80, 127.10, 127.45),
}


def normalized_address(value):
    # A mailing PO box may be in a different city; never geocode that part.
    value = re.sub(r"\([^)]*\)", " ", value)
    value = re.sub(r"\[우편번호[^]]*\]", " ", value)
    value = re.sub(r"(로|대로)\s+(\d+(?:번)?길)", r"\1\2", value)
    value = re.sub(r"^\s*(?:우\s*)?\d{5}\s+|^\s*우\s*\d{5}\s*", "", value)
    match = re.search(r"(?:[가-힣0-9]+(?:대로|로|길))\s*\d+(?:-\d+)?", value)
    return re.sub(r"\s+", " ", value[:match.end()] if match else value).strip()


def province(value):
    first = value.split()[0] if value.split() else ""
    if first == "전남광주통합특별시":
        return "광주" if re.match(r"전남광주통합특별시\s+(?:북구|동구|남구|서구|광산구)", value) else "전남"
    return next((key for key, aliases in PROVINCES.items() if first in aliases), None)


def road_identity(value):
    value = normalized_address(value)
    match = re.search(r"([가-힣0-9]+(?:대로|로|길))\s*(\d+(?:-\d+)?)", value)
    return match.groups() if match else None


def road_matches(expected, returned):
    identity = road_identity(expected)
    if not identity:
        return False
    road, number = identity
    # Accept whitespace-only typography differences, never a different road or number.
    pattern = r"(?<![가-힣0-9])" + r"\s*".join(re.escape(char) for char in road) + r"\s*" + re.escape(number) + r"(?![\d-])"
    return re.search(pattern, normalized_address(returned)) is not None


def coordinate_in_korea(latitude, longitude):
    if not (math.isfinite(latitude) and math.isfinite(longitude)):
        return False
    # Reject foreign/outlying-ocean coordinates; fine coastal checks need address evidence.
    return (34.0 <= latitude <= 38.65 and 125.0 <= longitude <= 129.65) or (
        33.1 <= latitude <= 33.65 and 126.1 <= longitude <= 127.0)


def validate_location(institution, candidate):
    issues = []
    try:
        if isinstance(candidate.get("latitude"), bool) or isinstance(candidate.get("longitude"), bool):
            raise ValueError("boolean coordinate")
        lat, lon = float(candidate["latitude"]), float(candidate["longitude"])
        if not (-90 <= lat <= 90 and -180 <= lon <= 180 and math.isfinite(lat) and math.isfinite(lon)):
            issues.append("INVALID_COORDINATE_RANGE")
        elif not coordinate_in_korea(lat, lon):
            issues.append("OUTSIDE_KOREA_OR_OFFSHORE")
    except (KeyError, ValueError, TypeError):
        lat = lon = None
        issues.append("INVALID_COORDINATE_RANGE")
    original = normalized_address(institution["address"])
    returned = candidate.get("returned_address") or ""
    original_region = province(original)
    result_region = province(normalized_address(returned))
    if not original_region or result_region != original_region:
        issues.append("ADMINISTRATIVE_AREA_MISMATCH")
    if not road_matches(original, returned):
        issues.append("ROAD_ADDRESS_MISMATCH")
    # Compare municipalities in addition to province; wards can be reorganized.
    cities = re.findall(r"(?:^|\s)([가-힣]+(?:시|군))(?=\s)", original)
    cities = [city for city in cities if city not in sum((list(v) for v in PROVINCES.values()), []) and city != "전남광주통합특별시"]
    returned_physical = normalized_address(returned)
    returned_cities = set(re.findall(r"(?:^|\s)([가-힣]+(?:시|군))(?=\s)", returned_physical))
    if any(city not in returned_cities for city in cities):
        issues.append("MUNICIPALITY_MISMATCH")
    districts = set(re.findall(r"(?:^|\s)([가-힣]+구)(?=\s)", original))
    returned_districts = set(re.findall(r"(?:^|\s)([가-힣]+구)(?=\s)", returned_physical))
    if districts and districts != returned_districts:
        issues.append("DISTRICT_MISMATCH")
    if original_region in REGION_BOUNDS and lat is not None and lon is not None:
        lo_lat, hi_lat, lo_lon, hi_lon = REGION_BOUNDS[original_region]
        if not (lo_lat <= lat <= hi_lat and lo_lon <= lon <= hi_lon):
            issues.append("COORDINATE_REGION_MISMATCH")
    if candidate.get("precision") != "institution_marker_or_full_road_address":
        issues.append("INSUFFICIENT_PRECISION")
    if candidate.get("official") and not candidate.get("institution_identity_verified"):
        issues.append("OFFICIAL_INSTITUTION_IDENTITY_MISMATCH")
    return {"status": "PASS" if not issues else "REVIEW", "issues": sorted(set(issues)),
            "official_road_address": original, "returned_road_address": normalized_address(returned),
            "province": original_region,
            "geographic_check": "coarse_country_and_region_envelopes_plus_exact_road_address",
            "land_polygon_verified": False}


def duplicate_coordinates(rows):
    groups = defaultdict(list)
    for row in rows:
        if row.get("latitude") is not None and row.get("longitude") is not None:
            groups[(row["latitude"], row["longitude"])].append(row)
    return [{"latitude": point[0], "longitude": point[1],
             "institution_ids": [r["institution_id"] for r in items],
             "same_official_road_address": len({normalized_address(r["official_address"]) for r in items}) == 1,
             "requires_review": True}
            for point, items in groups.items() if len(items) > 1]
