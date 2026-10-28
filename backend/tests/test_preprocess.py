from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from app.modules.preprocess import _md_target_name, _safe_target
from tests.conftest import wait_task


def test_safe_target_limits_long_path(tmp_path):
    member = "/".join(
        [
            "国网重庆市电力公司2026年第四次物资公开招",
            "网络特征分析平台-全流量威胁分析",
            "包1_完整招标文件_22729030231448349",
            "国网重庆市电力公司_国网重庆信通公司-信息安全-全流量威胁分析装置设备采购-资本性(H14B-500134830-00002)" * 2,
        ]
    )
    target = _safe_target(tmp_path, member)

    assert str(target).startswith(str(tmp_path.resolve()))
    assert len(str(target).encode("utf-8")) <= 900
    assert all(len(part.encode("utf-8")) <= 255 for part in target.parts)
    assert _safe_target(tmp_path, member + "x") != target


def test_safe_target_rejects_traversal(tmp_path):
    with pytest.raises(RuntimeError):
        _safe_target(tmp_path, "../../etc/passwd")


def test_md_target_name_fits_filesystem_limit():
    long_name = "国网重庆市电力公司_国网重庆信通公司-信息安全-2026年全流量威胁分析装置设备采购-技术规范书.doc"
    rel = Path("国网重庆市电力公司2026年第四次物资公开招") / ("网络特征分析平台-全流量威胁分析" * 2) / (long_name * 3)

    name = _md_target_name(rel)

    assert name.endswith(".md")
    assert len(name.encode("utf-8")) <= 255
    assert _md_target_name(rel.with_name(rel.name + "x")) != name


def test_nested_zip_preprocess(client, auth_headers):
    inner_buffer = io.BytesIO()
    with zipfile.ZipFile(inner_buffer, "w") as inner:
        inner.writestr("公告/招标公告.txt", "项目名称：测试项目\n招标编号：TEST-2026-001\n")
    inner_buffer.seek(0)

    outer_buffer = io.BytesIO()
    with zipfile.ZipFile(outer_buffer, "w") as outer:
        outer.writestr("inner.zip", inner_buffer.getvalue())
        outer.writestr("投标人须知.txt", "投标截止时间：2026年12月31日17:00\n")
    outer_buffer.seek(0)

    response = client.post(
        "/api/preprocess",
        headers=auth_headers,
        files={"file": ("招标文件包.zip", outer_buffer.getvalue(), "application/zip")},
    )
    assert response.status_code == 200, response.text
    task_id = response.json()["id"]

    task = wait_task(client, task_id, auth_headers)
    assert task["status"] == "completed", task.get("error_message")
    assert task["file_count"] >= 2
    manifest = task["manifest"]
    assert manifest["file_count"] == 2
    assert not manifest["warnings"]
