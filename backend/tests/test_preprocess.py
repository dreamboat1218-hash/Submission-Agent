from __future__ import annotations

import io
import zipfile

from tests.conftest import wait_task


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
