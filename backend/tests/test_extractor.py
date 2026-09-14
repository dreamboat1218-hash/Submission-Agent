from __future__ import annotations

from pathlib import Path

from app.modules import fallback_extractor

SAMPLE = Path(__file__).parent / "sample_tender.md"


def test_fallback_extractor_covers_26_fields():
    content = SAMPLE.read_text(encoding="utf-8")
    result = fallback_extractor.extract_file(content, "招标公告.md")

    assert result["project_name"]["primary_value"] == "智慧交通建设项目"
    assert result["bid_number"]["primary_value"] == "ZB-2026-008"
    assert result["budget"]["primary_value"] == 5680000.0
    assert "综合评分法" in result["evaluation_criteria"]["primary_value"]
    assert isinstance(result["qualifications"]["primary_value"], list)
    assert len(result["qualifications"]["primary_value"]) >= 2
    assert result["bid_deadline"]["primary_value"].startswith("2026-09-30")
    assert result["bid_opening_time"]["primary_value"].startswith("2026-10-08")
    assert result["bid_security_amount"]["primary_value"] == 80000.0

    bid_format = result["bid_format"]["primary_value"]
    assert bid_format["chapter"] == "第六章 投标文件格式"
    assert "商务文件" in bid_format["sections"]
    assert "技术文件" in bid_format["sections"]
    assert "价格文件" in bid_format["sections"]
    assert "投标函" in bid_format["templates"]
    assert "电子签章" in bid_format["requirements"]
    assert "商务偏差表" in bid_format["commercial_raw"]
    assert "技术偏差表" in bid_format["technical_raw"]

    for field in fallback_extractor.FIELD_LABELS:
        assert field in result, f"missing field {field}"
        assert result[field]["evidence"]["source_file"] == "招标公告.md"


def test_merge_and_summary():
    a = fallback_extractor.extract_file(SAMPLE.read_text(encoding="utf-8"), "a.md")
    b = fallback_extractor.extract_file("项目名称：另一个项目\n联系人：王工\n", "b.md")
    merged = fallback_extractor.merge([a, b])
    assert merged["project_name"]["primary_value"] == "智慧交通建设项目"
    assert merged["contact_person"]["primary_value"] in {"张工", "王工"}
    summary = fallback_extractor.summarize(merged)
    assert summary["high"] > 0
