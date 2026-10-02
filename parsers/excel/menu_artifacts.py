"""Conservative, anchored rules for definite non-food spreadsheet artifacts."""
from __future__ import annotations

import re
import unicodedata

EXCEL_ERRORS = {"#REF!", "#VALUE!", "#DIV/0!", "#N/A", "#NAME?", "#NUM!", "#NULL!",
                "#SPILL!", "#CALC!", "#GETTING_DATA", "#CONNECT!", "#BLOCKED!", "#FIELD!",
                "#BUSY!", "#UNKNOWN!", "#PYTHON!", "#DATA!"}
CATEGORIES = ("formula_literal", "excel_error", "subtotal", "price", "cost_metadata",
              "instruction_note", "placeholder", "other")
ISSUE_CODES = {"formula_literal": "UNRESOLVED_FORMULA_VALUE", "excel_error": "EXCEL_ERROR_VALUE",
               "subtotal": "NON_MENU_SUBTOTAL", "price": "NON_MENU_PRICE",
               "cost_metadata": "NON_MENU_COST_METADATA", "instruction_note": "NON_MENU_INSTRUCTION",
               "placeholder": "NON_MENU_PLACEHOLDER"}


def classify_menu_token(value: str) -> str | None:
    text = unicodedata.normalize("NFKC", str(value)).strip()
    compact = re.sub(r"\s+", "", text)
    if text.startswith("="):
        return "formula_literal"
    if compact.upper() in EXCEL_ERRORS:
        return "excel_error"
    if compact in {"소계", "합계", "총계"}:
        return "subtotal"
    if re.fullmatch(r"[\d,]+(?:\.\d+)?원", compact):
        return "price"
    if re.fullmatch(r"(?:0+(?:\.0+)?|-)", compact):
        return "placeholder"
    # Exact labels, or the complete observed cost-note prefix plus its numeric
    # value. Never match food names by the substrings 계 / 원 / 주식.
    if compact in {"부식물단가", "예정인원", "일일급식예정금액", "1일1인당평균부식지급액",
                   "1인1일평균", "월중급식", "1인1일급식비"}:
        return "cost_metadata"
    if re.fullmatch(r"[※*]?1식(?:급양비|매식비)단가[\d,.]*원?", compact):
        return "cost_metadata"
    if (re.fullmatch(r"[※*]?(?:\d+[.)])?(?:1인당1식단가는|1인1일부식단가|1일평균단가:|1일총급식비:)[\d,.]*원?", compact)
            or compact in {"1인1일부식비급여예정액", "(주식,부식,연료비등포함)"}
            or re.fullmatch(r"[\d,.]+원\((?:주부식연료비포함|주,부식,연료비등포함)\)", compact)):
        return "cost_metadata"
    if re.fullmatch(r"[※*]?(?:\d+[.)])?(?:가격변동시물량으로조절(?:급식)?|가격변동시물량조절및대체할수있음|부식비범위내물량으로조절(?:할수있음)?|예정단가초과시물량으로조절함|물량공급이어려울시동일식군내대체가능|동일식군내상호대체(?:할수있음)?)[.]?", compact):
        return "instruction_note"
    return None
