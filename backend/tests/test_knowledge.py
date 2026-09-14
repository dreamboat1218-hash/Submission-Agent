from __future__ import annotations

from app.modules.knowledge import classify_document


def test_classify_attachment_chapter():
    doc_type, chapter = classify_document("ISO9001质量管理体系认证", "我司持有ISO9001质量管理体系认证证书和营业执照。")
    assert doc_type == "企业资质"
    assert chapter == "商务文件"

    doc_type, chapter = classify_document("技术方案", "本技术方案采用微服务架构，包含系统设计、设备配置与性能指标。")
    assert doc_type in {"项目案例", "企业资质"}
    assert chapter == "技术文件"


def test_kb_upload_endpoint(client, auth_headers):
    content = "营业执照编号：9144XXXXXXXXXX\n经营范围：信息系统集成服务、软件开发。".encode("utf-8")
    response = client.post(
        "/api/kb/upload",
        headers=auth_headers,
        files={"file": ("营业执照.txt", content, "text/plain")},
        data={"doc_type": "auto", "title": "企业营业执照"},
    )
    assert response.status_code == 200, response.text
    doc = response.json()
    assert doc["doc_type"] == "企业资质"
    assert doc["metadata"]["chapter"] == "商务文件"
    assert doc["metadata"]["original_name"] == "营业执照.txt"
    assert "9144" in doc["content"]


def test_custom_kb_type_lifecycle(client, auth_headers):
    created = client.post(
        "/api/kb/types",
        headers=auth_headers,
        json={"name": "技术资料", "chapter": "技术文件", "description": "自定义技术资料"},
    )
    assert created.status_code == 200, created.text
    kb_type = created.json()

    listed = client.get("/api/kb/types", headers=auth_headers)
    assert listed.status_code == 200
    assert any(item["name"] == "技术资料" for item in listed.json())
    builtin = next(item for item in listed.json() if item["name"] == "企业资质")
    protected = client.delete(f"/api/kb/types/{builtin['id']}", headers=auth_headers)
    assert protected.status_code == 400

    uploaded = client.post(
        "/api/kb/upload",
        headers=auth_headers,
        files={"file": ("架构设计.pdf", b"%PDF-1.4 test", "application/pdf")},
        data={"doc_type": "技术资料", "title": "系统架构设计"},
    )
    assert uploaded.status_code == 200, uploaded.text
    assert uploaded.json()["doc_type"] == "技术资料"
    assert uploaded.json()["metadata"]["chapter"] == "技术文件"

    deleted = client.delete(f"/api/kb/types/{kb_type['id']}", headers=auth_headers)
    assert deleted.status_code == 200
