from __future__ import annotations

import os
import tempfile

_tmp_root = tempfile.mkdtemp(prefix="bid_agent_test_")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp_root}/test.db"
os.environ["DATA_DIR"] = f"{_tmp_root}/data"
os.environ["TEMP_DIR"] = f"{_tmp_root}/tmp"
os.environ["GENERATED_DIR"] = f"{_tmp_root}/generated"
os.environ["KNOWLEDGE_BASE_PATH"] = f"{_tmp_root}/kb"
os.environ["CHROMA_PERSIST_DIR"] = f"{_tmp_root}/chroma"
os.environ["REDIS_URL"] = "redis://127.0.0.1:6399/0"
os.environ["BID_SYSTEM_ENV"] = "development"
os.environ["TENDER_EXTRACT_URL"] = "http://127.0.0.1:6398"
os.environ["LLM_PROVIDER"] = "none"
os.environ["BIAOSHU_SKILL_PATH"] = ""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="session")
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="session")
def auth_headers(client: TestClient) -> dict[str, str]:
    response = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert response.status_code == 200, response.text
    token = response.json()["token"]
    return {"Authorization": f"Bearer {token}"}


def wait_task(client: TestClient, task_id: str, auth_headers: dict[str, str], timeout: float = 30.0) -> dict:
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(f"/api/tasks/{task_id}", headers=auth_headers)
        assert response.status_code == 200, response.text
        task = response.json()
        if task["status"] in {"completed", "failed"}:
            return task
        time.sleep(0.25)
    raise AssertionError(f"task {task_id} did not finish within {timeout}s")
