from __future__ import annotations

import json

from app.database import get_session_factory
from app.models import Task
from app.modules.reference_resolver import (
    _build_qualification_groups,
    _build_qualifications_payload,
    _collect_warranty_summary,
    _extract_contact_person,
    _extract_bid_location,
    _parse_special_qualification_table,
    _performance_summary,
)


def test_extract_bid_location_only_location() -> None:
    text = (
        "| 5.1 | 开标时间和地点 | 开标地点：招标人招投标交易平台信息系统 "
        "本项目开标过程全程在招标人招投标交易平台信息系统在线进行 参加开标的方法：见招标公告 |"
    )
    assert _extract_bid_location(text) == "招标人招投标交易平台信息系统"


def test_parse_special_qualification_table() -> None:
    text = (
        "附件2：专用资格要求\n"
        "| 分标名称 | 厂商类型 | 业绩要求 | 生产许可证或检测合格证(入网许可证) | 产品型式试验报告或检测报告或鉴定报告 | 3C认证证书 | 生产设备 | 试验设备 | 备注 |\n"
        "|---|---|---|---|---|---|---|---|---|\n"
        "| 流量编排装置 | 制造商 | 2023年1月1日至2025年12月31日，具有信息安全产品累计销售业绩不少于100万元。 | / | 提供国家认可的第三方检测机构出具的有效的检测报告。 | / | / | / | / |\n"
    )
    rows = _parse_special_qualification_table(text)
    assert len(rows) == 1
    assert rows[0]["分标名称"] == "流量编排装置"
    assert "信息安全产品累计销售业绩" in _performance_summary(rows)[0]


def test_parse_special_qualification_table_chongqing_header() -> None:
    text = (
        "| 分标名称 | 包号 | 投标人类别 | 业绩要求 | 试验报告 | 关键参数 | 生产设备 | 试验设备 | 认证证书 | 许可证（生产许可证、入网许可证或CCC等） | 其他资质要求 |\n"
        "|---|---|---|---|---|---|---|---|---|---|---|\n"
        "| 网络特征分析平台 | 包1 | B接受制造商或代理商 | 有同类产品销售业绩 | / | / | / | / | / | / | / |\n"
    )
    rows = _parse_special_qualification_table(text)
    assert len(rows) == 1
    assert rows[0]["投标人类别"] == "B接受制造商或代理商"
    assert rows[0]["包号"] == "包1"
    assert "有同类产品销售业绩" in _performance_summary(rows)[0]


def test_collect_warranty_summary_from_package_contract(client, tmp_path) -> None:
    factory = get_session_factory()
    with factory() as db:
        task = Task(user_id="test", status="completed", original_file_name="tender.zip", work_dir=str(tmp_path))
        db.add(task)
        db.commit()
        db.refresh(task)
        task_id = task.id

    try:
        (tmp_path / "packages.json").write_text(
            json.dumps(
                {
                    "packages": [
                        {
                            "source_archive": "包01_完整招标文件_123456789.zip",
                            "subproject_dir": "流量编排装置",
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        contract_dir = tmp_path / "packages_md" / "包01_完整招标文件_123456789"
        contract_dir.mkdir(parents=True)
        (contract_dir / "合同专用条款.md").write_text(
            "8.1（修改为）合同货物的质量保证期为从合同货物通过验收后36个月。",
            encoding="utf-8",
        )
        assert _collect_warranty_summary(task_id) == "36个月（从合同货物通过验收后起算，以合同专用条款为准）"
    finally:
        with factory() as db:
            task = db.get(Task, task_id)
            if task is not None:
                db.delete(task)
                db.commit()


def test_build_qualification_groups() -> None:
    rows = [
        {
            "分标名称": "流量编排装置",
            "包号": "包1",
            "投标人类别": "制造商",
            "许可证": "/",
            "检测报告": "提供国家认可的第三方检测机构出具的有效的检测报告。",
            "认证证书": "/",
            "生产设备": "/",
            "试验设备": "/",
            "其他资质要求": "/",
        }
    ]
    text = (
        "3.投标人资格要求\n"
        "3.1 本次招标要求投标人须为中华人民共和国境内依法注册的法人或其他组织。\n"
        "3.2 本次招标不接受联合体投标。\n"
        "3.3 是否接受代理商投标见3.6专用资格要求。\n"
        "3.5 投标人及其投标产品须满足如下通用资格要求：\n"
        "（1）投标产品制造商必须具有生产投标产品所需的生产场地、生产设备、生产人员、产品及元器件检测能力。\n"
        "4.招标文件的获取\n"
    )
    payload = _build_qualifications_payload(rows, text)
    assert payload["product_table"]["rows"][0][0] == "流量编排装置"
    assert "有效的检测报告" in payload["product_table"]["rows"][0][3]
    assert any("3.1" in item for item in payload["bidder"])
    assert any("生产场地" in item for item in payload["enterprise"])
    groups = _build_qualification_groups(rows, text)
    assert groups[0].startswith("产品资质：")
    assert groups[1].startswith("企业资质：")
    assert groups[2].startswith("投标人资格要求：")


def test_extract_contact_person() -> None:
    shandong = "联系电话：\n业务咨询\n联系电话：贺经理（0531-83160765）、陈经理（0531-83160708）"
    assert _extract_contact_person(shandong) == "贺经理、陈经理"
    chongqing = "招标代理机构：国网重庆招标有限公司\n项目负责人：巫工\n地址：重庆市"
    assert _extract_contact_person(chongqing) == "巫工"
