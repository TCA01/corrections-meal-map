from __future__ import annotations

from dataclasses import replace
import hashlib
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import pytest

from config.settings import Settings
from parsers.excel.meal_normalizer import split_menu_text, split_menu_tokens
from parsers.excel.menu_artifacts import classify_menu_token
from parsers.excel.models import CellData, SheetGrid, WorkbookGrid
from parsers.excel.pipeline import ExcelMealParser
from parsers.excel.workbook_reader import read_workbook
from production.gate import production_route
from production.io import atomic_json, atomic_jsonl, read_jsonl
from production.menu_lint import require_clean_public_menus, scan_public_menus
from production.pipeline import ProductionExcelPipeline
from production.validation import read_json
from production.web_bridge import WebDataBridge, tree_digest

ROOT = Path(__file__).resolve().parents[1]
CASES = read_json(ROOT / "tests/fixtures/menu_quality/real_cases.json")


def real_sample(document_id: str) -> dict:
    # Fixed immutable source manifest, unaffected by new run routing changes.
    manifest = read_json(ROOT / "tests/fixtures/menu_quality/manifest.json")
    return next(i for i in manifest if i["document_id"] == document_id)


def test_real_formula_cache_resolution_and_raw_provenance():
    sample = real_sample("65664-66430")
    grid = read_workbook(ROOT / sample["local_path"], "xlsx")
    cell = next(c for s in grid.sheets for c in s.cells if c.coordinate == "D4" and c.is_formula)
    assert cell.text == "소고기무국" and cell.display_value == "소고기무국"
    assert cell.raw_value == cell.formula == "=[1]차림표!C35"
    assert cell.formula_cache_status == "resolved"
    result = ExcelMealParser(ROOT).parse_sample(sample)
    assert any(i["name"] == "소고기무국" for r in result["records"] for i in r["menu_items"])
    assert any(f["formula"] == cell.formula for r in result["records"] for f in r["source"].get("formula_cells", []))


@pytest.mark.parametrize("cached_error", [None, "#REF!", "#VALUE!", "#DIV/0!", "#N/A", "#BUSY!"])
def test_formula_missing_or_error_cache_not_recovered(tmp_path, cached_error):
    sample = real_sample("65664-66430")
    path = tmp_path / "unresolved.xlsx"
    ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    replaced = False
    with ZipFile(ROOT / sample["local_path"]) as source, ZipFile(path, "w") as target:
        for item in source.infolist():
            content = source.read(item.filename)
            if item.filename.startswith("xl/worksheets/") and item.filename.endswith(".xml"):
                xml = ET.fromstring(content)
                for cell in xml.findall(".//s:c", ns):
                    if cell.get("r") == "D4" and cell.find("s:f", ns) is not None:
                        value = cell.find("s:v", ns)
                        if value is not None:
                            cell.remove(value)
                        if cached_error is not None:
                            cell.set("t", "e")
                            ET.SubElement(cell, f"{{{ns['s']}}}v").text = cached_error
                        content = ET.tostring(xml)
                        replaced = True
            target.writestr(item, content)
    assert replaced
    grid = read_workbook(path, "xlsx")
    cell = next(c for s in grid.sheets for c in s.cells if c.coordinate == "D4" and c.is_formula)
    assert cell.formula_cache_status == "unresolved"
    assert cell.text == (cached_error or cell.formula)


@pytest.mark.parametrize("token,category", [
    ("#REF!", "excel_error"), ("#DIV/0!", "excel_error"), ("=[1]차림표!C35", "formula_literal"),
    ("소 계", "subtotal"), ("합계", "subtotal"), ("총계", "subtotal"),
    ("330원", "price"), ("414.3원", "price"), ("0.0", "placeholder"), ("-", "placeholder"),
    ("부식물 단가", "cost_metadata"), ("예정인원", "cost_metadata"),
    ("1. 부식비 범위내 물량으로 조절", "instruction_note"),
    ("2. 가격 변동시 물량조절 및 대체 할수 있음", "instruction_note"),
    ("3. 동일 식군내 상호 대체", "instruction_note"),
    ("물량공급이 어려울 시 동일 식군내 대체가능.", "instruction_note"),
    ("1인1일 평균", "cost_metadata"), ("월중급식", "cost_metadata"),
    ("1일 총급식비 : 5", "cost_metadata"),
])
def test_definite_artifact_classifier(token, category):
    assert classify_menu_token(token) == category
    assert split_menu_text(token) == []


@pytest.mark.parametrize("food", CASES["legitimate_foods"])
def test_legitimate_food_false_positives_protected(food):
    assert classify_menu_token(food) is None
    assert [item.name for item in split_menu_text(food)] == [food]


def synthetic_parse(monkeypatch, text: str, *, formula=False):
    cells = [CellData("A1", 1, 1, "2026년 1월 식단표", "2026년 1월 식단표")]
    cells += [CellData(f"{column}1", 1, i, label, label) for column, i, label in
              (("B", 2, "아침"), ("C", 3, "점심"), ("D", 4, "저녁"))]
    for day in range(1, 32):
        row = day + 1
        cells.append(CellData(f"A{row}", row, 1, day, str(day)))
        for column, i in (("B", 2), ("C", 3), ("D", 4)):
            value = text if day == 1 and i == 2 else "쌀밥\n계란찜"
            cell = CellData(f"{column}{row}", row, i, value, value)
            if day == 1 and i == 2 and formula:
                cell.is_formula = True
                cell.formula = value
                cell.formula_cache_status = "unresolved"
            cells.append(cell)
    grid = WorkbookGrid("synthetic", "xlsx", "xlsx", False, [SheetGrid("S", 1, 32, 1, 4, cells=cells)])
    monkeypatch.setattr("parsers.excel.pipeline.read_workbook", lambda *args: grid)
    return ExcelMealParser(ROOT).parse_sample({"post_id": "1", "attachment_id": "1", "institution_id": "I1",
                                              "filename": "2026년 1월 식단.xlsx", "extension": "xlsx",
                                              "meal_year": 2026, "meal_month": 1, "local_path": "unused"})


def test_safe_filter_preserves_normal_food_and_audit(monkeypatch):
    result = synthetic_parse(monkeypatch, "쌀밥\n계란찜\n※ 1식 급양비 단가 4\n330원")
    assert result["status"] == "PASS" and result["menu_quality_valid"]
    assert result["excluded_artifacts"] == 2
    assert [i["name"] for i in result["records"][0]["menu_items"]] == ["쌀밥", "계란찜"]
    assert result["menu_artifacts"][0]["source_cell"] == "B2"
    assert "330원" in result["records"][0]["source"]["raw_text"]
    assert production_route(result, institution_id="I1") == "ready"


@pytest.mark.parametrize("text", ["소 계", "#REF!", "밥\n#REF!", "밥\n330원\n국", "0.0"])
def test_unsafe_contamination_is_review_and_recalculates_coverage(monkeypatch, text):
    result = synthetic_parse(monkeypatch, text)
    assert not result["menu_quality_valid"]
    assert result["coverage"]["missing_meals"] == [{"meal_date": "2026-01-01", "meal_type": "breakfast"}]
    assert production_route(result, institution_id="I1") == "review"
    assert all(not classify_menu_token(i["name"]) for r in result["records"] for i in r["menu_items"])


def test_unresolved_formula_quarantine(monkeypatch):
    result = synthetic_parse(monkeypatch, "=[1]차림표!C35", formula=True)
    assert result["unresolved_formula_values"] == 1
    assert any(i["code"] == "UNRESOLVED_FORMULA_VALUE" for i in result["document_issues"])
    assert production_route(result, institution_id="I1") == "review"


def test_new_production_gate_requires_quality_certificate(monkeypatch):
    result = synthetic_parse(monkeypatch, "밥\n국")
    result.pop("menu_quality_valid")
    assert production_route(result, institution_id="I1") == "review"


@pytest.mark.parametrize("case", CASES["cases"], ids=lambda c: c["document_id"])
def test_actual_corpus_regression(case):
    result = ExcelMealParser(ROOT).parse_sample(real_sample(case["document_id"]))
    assert production_route(result, institution_id=result["institution_id"]) == case["expected_route"]
    assert all(not classify_menu_token(i["name"]) for r in result["records"] for i in r["menu_items"])
    if case["expected_route"] == "review" and case['document_id'] != '72303-74034':
        assert not result["menu_quality_valid"] and result["coverage"]["missing_meals"]
    if case["document_id"] == "72303-74034":
        assert any(i['code']=='STAFF_TABLE_SELECTED' for i in result['document_issues'])
        # Original cell is a complete "4,330원" cost note. It must not be
        # broken at the thousands comma into a spurious standalone 330원.
        # Footer lies outside the structurally bounded meal block in 3B.3.
        assert all('4,330' not in r['source']['raw_text'] for r in result['records'])


def test_production_lint_rejects_artifact_in_public_item(tmp_path):
    atomic_json(tmp_path / "manifest.json", {})
    atomic_json(tmp_path / "menus/I1/2026/01.json", {"institution_id": "I1", "days": {
        "2026-01-01": {"breakfast": {"menu_items": [{"name": "#REF!", "raw_text": "#REF!"}],
                                      "source_document_ids": ["1-1"]}}}})
    assert scan_public_menus(tmp_path)["artifact_counts"]["excel_error"] == 1
    with pytest.raises(ValueError, match="lint failed"):
        require_clean_public_menus(tmp_path)


def test_old_immutable_run_matches_pre_quality_hash():
    if not (ROOT / "data/production/reports/menu_quality_before.json").exists():
        pytest.skip("Local archival integrity check; historical runs intentionally excluded from GitHub")
    baseline = read_json(ROOT / "data/production/reports/menu_quality_before.json")
    assert tree_digest(ROOT / "data/production" / baseline["run_path"]) == baseline["immutable_run_sha256"]


def test_new_run_bundle_stats_reconcile_without_touching_old_run(tmp_path):
    cfg = replace(Settings(), production_root=tmp_path / "production",
                  production_manifest_path=tmp_path / "production/manifest.jsonl",
                  production_parse_checkpoint_path=tmp_path / "production/checkpoint.json")
    items = [real_sample(c["document_id"]) for c in CASES["cases"]]
    atomic_jsonl(cfg.production_manifest_path, items)
    report = ProductionExcelPipeline(cfg).run(new_run=True)
    assert report["documents"]["ready"] == 2 and report["documents"]["review"] == 2
    result = WebDataBridge(cfg).build()
    assert result["total_meal_records"] == report["records"]["production_ready"]
    assert result["institution_month_files"] == report["web_data"]["institution_month_files"]
    assert result["menu_lint"]["artifact_occurrences"] == 0


@pytest.mark.parametrize("error", ["#DIV/0!", "#N/A", "#REF!", "#VALUE!", "#NAME?", "#NUM!", "#NULL!"])
def test_excel_error_inside_multiline_menu_is_not_split_or_published(error):
    assert split_menu_tokens(f"밥\n{error}") == ["밥", error]
    assert [item.name for item in split_menu_text(f"밥\n{error}")] == ["밥"]


def test_publication_lint_failure_preserves_previous_pointer(tmp_path, monkeypatch):
    result = synthetic_parse(monkeypatch, "밥\n국")
    cfg = replace(Settings(), project_root=tmp_path, institutions_path=tmp_path / "institutions.json",
                  production_root=tmp_path / "production", production_manifest_path=tmp_path / "manifest.jsonl",
                  production_parse_checkpoint_path=tmp_path / "checkpoint.json")
    atomic_json(cfg.institutions_path, [{"institution_id": "I1", "canonical_name": "기관", "short_name": "기관",
                                        "institution_type": "prison", "aliases": [], "address": "",
                                        "source_url": "https://example.test", "active": True,
                                        "postal_code": None, "phone": None, "latitude": None, "longitude": None}])
    raw = b"mocked parser input"
    (tmp_path / "raw.xlsx").write_bytes(raw)
    atomic_jsonl(cfg.production_manifest_path, [{"document_id": "1-1", "post_id": "1", "attachment_id": "1",
        "institution_id": "I1", "filename": "meal.xlsx", "extension": "xlsx", "meal_year": 2026, "meal_month": 1,
        "post_url": "https://example.test/post/1", "download_url": "https://example.test/download/1",
        "published_date": "2025-12-20", "local_path": "raw.xlsx", "download_status": "reused",
        "sha256": hashlib.sha256(raw).hexdigest(), "file_size": len(raw)}])
    atomic_json(cfg.production_root / "current.json", {"dataset_version": "previous", "run_path": "runs/previous"})
    before = (cfg.production_root / "current.json").read_bytes()
    pipeline = ProductionExcelPipeline(cfg)
    monkeypatch.setattr(pipeline.parser, "parse_sample", lambda item: result)
    write_public = pipeline._write_web_data
    def corrupt_public(root, parsed, version):
        stats = write_public(root, parsed, version)
        path = next((root / "menus").rglob("*.json"))
        value = read_json(path)
        value["days"]["2026-01-01"]["breakfast"]["menu_items"][0] = {"name": "#REF!", "raw_text": "#REF!"}
        atomic_json(path, value)
        return stats
    monkeypatch.setattr(pipeline, "_write_web_data", corrupt_public)
    # Independently prove semantic lint blocks publication even if structural
    # validation alone would accept the tree.
    monkeypatch.setattr("production.pipeline.validate_dataset", lambda *args: {"status": "PASS"})
    with pytest.raises(ValueError, match="lint failed"):
        pipeline.run(new_run=True)
    assert (cfg.production_root / "current.json").read_bytes() == before
    assert not (cfg.production_root / "runs").exists()
