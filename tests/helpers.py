"""Helpers for API acceptance tests."""
from __future__ import annotations

import time
import uuid


def unique_name(prefix: str) -> str:
    return f"{prefix}-{int(time.time())}-{uuid.uuid4().hex[:6]}"


def body_data(response):
    body = response.json()
    return body.get("data", body) if isinstance(body, dict) else body


def wait_for_build(api, job_id, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        response = api.get(f"/audience-build-jobs/{job_id}/")
        assert response.status_code == 200, response.text
        payload = body_data(response)
        if payload["status"] in {"SUCCEEDED", "FAILED"}:
            return payload
        time.sleep(0.5)
    raise AssertionError(f"Audience build job {job_id} did not finish")
