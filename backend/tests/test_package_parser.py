from __future__ import annotations

import io
import zipfile
from pathlib import Path

from docx import Document

from app.modules import package_parser


def _make_docx_bytes(text: str) -> bytes:
    doc = Document()
    for line in text.splitlines():
        doc.add_paragraph(line)
    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


def test_parse_package_archive_groups_tech_specs(tmp_path):
    archive = tmp_path / "包1_完整招标文件_99999999999999.zip"
    tender_text = (
        "项目名称：加密流量解析设备采购项目\n"
        "项目编号：73261A\n"
        "招标编号：ZB-2026-008\n"
        "分标名称：网络流量控制系统\n"
        "分标编号：73261A-2400000-00002\n"
        "包名称：包13加密流量解析设备\n"
        "包号：包13\n"
        "技术规范编码：22729043580804796\n"
    )
    spec_text = "技术规范书：互联网大区终端安全准入管控平台\n技术要求：支持500路视频接入。"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("招标公告.docx", _make_docx_bytes(tender_text))
        zf.writestr("互联网大区终端安全准入管控平台技术规范书.docx", _make_docx_bytes(spec_text))
        zf.writestr("国网重庆信通公司-信息安全-资本性(B005-500134830-00019).docx", _make_docx_bytes("资本性项目"))
        zf.writestr("货物清单.txt", "| 技术规范编码 | 物资名称 |\n|---|---|\n| 22729043580804796 | 加密流量解析设备 |\n")

    result = package_parser.parse_package_archive(archive, tmp_path)
    assert result["package_no"] == "包13"
    assert result["package_name"] == "包13加密流量解析设备"
    assert result["subproject_name"] == "网络流量控制系统"
    assert result["subproject_number"] == "73261A-2400000-00002"
    assert result["tech_spec_code"] == "22729043580804796"
    assert result["tech_spec_codes"][0] == "22729043580804796"
    assert "B005-500134830-00019" in result["tech_spec_codes"]
    assert "99999999999999" not in result["tech_spec_codes"]
    assert result["meta"]["project_number"] == "73261A"
    assert result["项目名称"] == "加密流量解析设备采购项目"
    assert result["项目编号"] == "73261A"
    assert result["分标名称"] == "网络流量控制系统"
    assert result["包号"] == "包13"
    assert any(file["kind"] == "tech_spec" and "技术规范书" in file["name"] for file in result["files"])
    assert "技术规范书" in next(file["content_preview"] for file in result["files"] if file["kind"] == "tech_spec")


def test_find_package_archives(tmp_path):
    (tmp_path / "包1_完整招标文件_12345678.zip").touch()
    (tmp_path / "普通文件.zip").touch()
    archives = package_parser.find_package_archives(tmp_path)
    assert len(archives) == 1
    assert archives[0].name == "包1_完整招标文件_12345678.zip"


def test_find_package_archives_relaxed_and_dedupe(tmp_path):
    (tmp_path / "包1_技术规范书_87654321.zip").touch()
    (tmp_path / "包1_技术规范书_87654321").mkdir()
    (tmp_path / "包2完整招标文件12345678").mkdir()
    (tmp_path / "普通文件.zip").touch()
    archives = package_parser.find_package_archives(tmp_path)
    names = sorted(path.name for path in archives)
    assert names == ["包1_技术规范书_87654321", "包2完整招标文件12345678"]


def test_list_row_linking_and_subproject_grouping():
    table = (
        "| 分标编号 | 分标名称 | 项目名称 | 包号 | 技术规范编码 |\n"
        "|---|---|---|---|---|\n"
        "| 73261A-2400000-00002 | 网络流量控制系统 | 加密流量解析设备采购项目 | 包13 | 22729043580804796 |\n"
    )
    rows = package_parser._parse_list_rows(table)
    assert len(rows) == 1

    package = {"subproject_dir": "网络特征分析平台", "package_no": "包13"}
    row = package_parser._match_list_row(rows, ["网络特征分析平台", "包13", "22729043580804796"])
    assert row is not None
    package_parser._merge_row_fields(package, row)
    assert package["subproject_number"] == "73261A-2400000-00002"
    assert package["subproject_name"] == "网络流量控制系统"
    assert package["project_name"] == "加密流量解析设备采购项目"
    assert package["tech_spec_code"] == "22729043580804796"

    subprojects = package_parser._build_subprojects([package])
    assert subprojects[0]["source_dir"] == "网络特征分析平台"
    assert subprojects[0]["分标编号"] == "73261A-2400000-00002"
    assert len(subprojects[0]["packages"]) == 1


def test_same_subproject_name_kept_separate_by_project():
    package_a = {
        "subproject_dir": "网络特征分析平台",
        "分标名称": "网络特征分析平台",
        "分标编号": "2026W4-1104044-9998",
        "项目名称": "国网重庆信通公司-基础软硬件资源-网络建设-软硬件购置项目",
        "项目编号": "2026W4",
        "package_no": "包1",
        "source_archive": "包1_技术规范书_11111111.zip",
    }
    package_b = {
        "subproject_dir": "网络特征分析平台",
        "分标名称": "网络特征分析平台",
        "分标编号": "2026W4-1104044-9999",
        "项目名称": "国网重庆信通公司-信息安全-终端安全准入建设-软硬件购置项目",
        "项目编号": "2026W4",
        "package_no": "包1",
        "source_archive": "包1_技术规范书_22222222.zip",
    }
    subprojects = package_parser._build_subprojects([package_a, package_b])
    assert len(subprojects) == 2
    assert {item["分标名称"] for item in subprojects} == {"网络特征分析平台"}
    assert {item["项目名称"] for item in subprojects} == {
        package_a["项目名称"],
        package_b["项目名称"],
    }
    assert all(len(item["packages"]) == 1 for item in subprojects)


def test_parse_package_directory_root(tmp_path):
    package_dir = tmp_path / "网络特征分析平台" / "包1_完整招标文件_22729043580804796"
    (package_dir / "货物清单").mkdir(parents=True)
    (package_dir / "招标公告").mkdir()
    (package_dir / "技术规范书").mkdir()
    (package_dir / "货物清单" / "货物清单.txt").write_text(
        "| 分标编号 | 分标名称 | 技术规范编码 |\n|---|---|---|\n| 73261A-2400000-00002 | 网络流量控制系统 | 22729043580804796 |\n",
        encoding="utf-8",
    )
    (package_dir / "招标公告" / "招标公告.txt").write_text("项目编号：73261A\n分标编号：73261A-2400000-00002\n", encoding="utf-8")
    (package_dir / "技术规范书" / "终端安全准入管控平台技术规范书.txt").write_text("技术规范书内容\n", encoding="utf-8")

    assert package_parser.find_package_archives(tmp_path)
    result = package_parser.parse_package_archive(package_dir, tmp_path)
    assert result["subproject_dir"] == "网络特征分析平台"
    assert result["package_no"] == "包1"
    assert result["tech_spec_code"] == "22729043580804796"
    assert result["分标编号"] == "73261A-2400000-00002"
    assert any(file["kind"] == "tech_spec" and "技术规范书" in file["name"] for file in result["files"])


def test_placeholder_filtered_and_row_fields_preferred():
    assert package_parser._is_placeholder("见投标人须知前附表。")
    row = {
        "项目名称": "加密流量解析设备采购项目",
        "项目编号": "73261A",
        "分标名称": "网络流量控制系统",
        "分标编号": "73261A-2400000-00002",
        "包号": "包13",
        "技术规范编码": "22729043580804796",
    }
    fields = package_parser._row_fields(row)
    assert fields["project_name"] == "加密流量解析设备采购项目"
    assert fields["subproject_number"] == "73261A-2400000-00002"

    package = {"subproject_dir": "网络特征分析平台"}
    package_parser._merge_row_fields(package, row)
    assert package["project_name"] == "加密流量解析设备采购项目"
    assert package["tech_spec_code"] == "22729043580804796"


def test_archive_name_number_not_used_as_code(tmp_path):
    package_dir = tmp_path / "包1_技术规范书_22729042998753854"
    package_dir.mkdir()
    (package_dir / "终端安全管控平台技术规范书.txt").write_text("技术规范书内容\n", encoding="utf-8")
    result = package_parser.parse_package_archive(package_dir, tmp_path)
    assert result["tech_spec_code"] == ""
    assert result["tech_spec_codes"] == []


def test_parenthesized_code_extracted_from_spec_filename(tmp_path):
    package_dir = tmp_path / "包1_完整招标文件_12345678"
    package_dir.mkdir()
    (package_dir / "国网重庆信通公司-信息安全-资本性(B005-500134830-00019).docx").write_text("资本性项目\n", encoding="utf-8")
    result = package_parser.parse_package_archive(package_dir, tmp_path)
    assert result["tech_spec_code"] == "B005-500134830-00019"
    assert "22729042998753854" not in result["tech_spec_codes"]
