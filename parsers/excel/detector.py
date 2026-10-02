from __future__ import annotations

import zipfile
from pathlib import Path


OLE_SIGNATURE = bytes.fromhex("D0CF11E0A1B11AE1")


class UnsupportedExcelFormat(ValueError):
    pass


def detect_excel_format(path: Path) -> str:
    """Detect OOXML or BIFF from content, never from the extension alone."""
    signature = path.read_bytes()[:8]
    if signature.startswith(OLE_SIGNATURE):
        return "xls"
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
        if "xl/workbook.xml" in names and "[Content_Types].xml" in names:
            return "xlsx"
    raise UnsupportedExcelFormat(f"unsupported spreadsheet signature: {path.name}")
