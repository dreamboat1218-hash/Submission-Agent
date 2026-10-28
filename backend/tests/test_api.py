from __future__ import annotations

from pathlib import Path

from tests.conftest import wait_task

SAMPLE = Path(__file__).parent / "sample_tender.md"


def test_login_and_me(client):
    response = client.post("/api/auth/login", json={"username": "demo", "password": "demo123"})
    assert response.status_code == 200
    token = response.json()["token"]
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["username"] == "demo"


def test_kb_crud_and_search(client, auth_headers):
    response = client.post(
        "/api/kb/documents",
        headers=auth_headers,
        json={"title": "测试项目案例", "content": "2025年完成某市智慧园区平台建设，合同金额800万元。", "doc_type": "项目案例"},
    )
    assert response.status_code == 200, response.text
    doc_id = response.json()["id"]
    search = client.get("/api/kb/search", headers=auth_headers, params={"q": "智慧园区"})
    assert search.status_code == 200
    assert any(item["id"] == doc_id for item in search.json()["results"])
    deleted = client.delete(f"/api/kb/documents/{doc_id}", headers=auth_headers)
    assert deleted.status_code == 200


def test_full_pipeline_from_upload_to_download(client, auth_headers):
    content = SAMPLE.read_bytes()
    response = client.post(
        "/api/preprocess",
        headers=auth_headers,
        files={"file": ("招标公告.md", content, "text/markdown")},
        params={"auto_run": "true"},
    )
    assert response.status_code == 200, response.text
    task_id = response.json()["id"]

    task = wait_task(client, task_id, auth_headers, timeout=60)
    assert task["status"] == "completed", task.get("error_message")
    assert task["file_count"] == 1
    assert task["industry"] in {"交通", "IT"}
    data = task["extracted_data"]
    assert data["project_name"]["primary_value"] == "智慧交通建设项目"
    assert data["budget"]["primary_value"] == 5680000.0
    assert len([k for k in data if k != "_meta"]) >= 20

    assert Path(task["bid_file_path"]).exists()
    assert task["check_result"]["status"] in {"PASS", "WARN", "FAIL"}

    download = client.get(f"/api/download/{task_id}", headers=auth_headers)
    assert download.status_code == 200
    assert len(download.content) > 1000


def test_health_live_skips_external_probes(client):
    response = client.get("/api/health/live")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
