from __future__ import annotations

import re
from dataclasses import dataclass

from collector.normalizer import normalize_space


@dataclass(frozen=True)
class DocumentRoleResult:
    role: str
    confidence: float
    rule: str


INMATE_RE = re.compile(r"수용자|수용자용|수용\s*식|소년수용|일반수용")
STAFF_RE = re.compile(r"직원|직원용|교도관|의무교도대원")
SUPPLEMENTARY_RE = re.compile(
    r"빵(?:과자)?표|빵\s*공급(?:일정)?표|과자\s*(?:공급)?일정표|"
    r"간식\s*(?:공급)?일정표|별도\s*공급(?:일정)?|부식물"
)
OTHER_RE = re.compile(r"개인정보|업무추진비|접견|민원|보도|채용|자비구매의약품|의약품|구매\s*코드표|코드표")


def classify_document_role(
    filename: str,
    post_title: str = "",
    sibling_filenames: list[str] | tuple[str, ...] = (),
) -> DocumentRoleResult:
    filename_text = normalize_space(filename)
    combined = normalize_space(f"{filename} {post_title}")
    filename_inmate = bool(INMATE_RE.search(filename_text))
    filename_staff = bool(STAFF_RE.search(filename_text))
    if filename_inmate and filename_staff:
        return DocumentRoleResult("mixed", 0.98, "filename_inmate_and_staff")
    if filename_inmate:
        if SUPPLEMENTARY_RE.search(filename_text):
            return DocumentRoleResult("inmate", 0.82, "filename_inmate_with_supplementary_term")
        return DocumentRoleResult("inmate", 0.97, "filename_inmate_keyword")
    if filename_staff:
        return DocumentRoleResult("staff", 0.97, "filename_staff_keyword")
    if SUPPLEMENTARY_RE.search(filename_text):
        return DocumentRoleResult("supplementary", 0.88, "filename_supplementary_keyword")
    if OTHER_RE.search(filename_text):
        return DocumentRoleResult("other", 0.95, "filename_non_meal_admin_keyword")
    # Generic 차림표/식단표 names are common for the main meal document.  A
    # staff-specific sibling is useful ambiguity evidence, but does not prove
    # that this attachment is the inmate version.
    generic_meal_table = bool(re.search(r"(?:차림표|식단표)", filename_text))
    sibling_staff = any(STAFF_RE.search(normalize_space(name)) for name in sibling_filenames if name != filename)
    if generic_meal_table and sibling_staff:
        return DocumentRoleResult("unknown", 0.45, "generic_meal_table_with_staff_sibling")
    title_inmate = bool(INMATE_RE.search(combined))
    title_staff = bool(STAFF_RE.search(combined))
    if title_inmate and title_staff:
        return DocumentRoleResult("unknown", 0.25, "ambiguous_title_context_inmate_and_staff")
    if title_inmate:
        return DocumentRoleResult("unknown", 0.25, "ambiguous_title_context_inmate")
    if title_staff:
        return DocumentRoleResult("unknown", 0.25, "ambiguous_title_context_staff")
    if generic_meal_table:
        return DocumentRoleResult("unknown", 0.15, "generic_meal_table_without_subject")
    return DocumentRoleResult("unknown", 0.0, "no_matching_rule")

