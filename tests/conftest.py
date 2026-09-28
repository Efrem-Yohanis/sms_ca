"""Shared fixtures for the Dockerized API acceptance tests."""
from __future__ import annotations

import os
import requests
import pytest

BASE = os.getenv("API_BASE", "http://localhost:8000/api/v1")


@pytest.fixture(scope="session")
def api():
    class API:
        base = BASE

        def request(self, method, path, **kwargs):
            return requests.request(method, f"{self.base}{path}", timeout=30, **kwargs)

        def get(self, path, **kwargs):
            return self.request("GET", path, **kwargs)

        def post(self, path, **kwargs):
            return self.request("POST", path, **kwargs)

        def put(self, path, **kwargs):
            return self.request("PUT", path, **kwargs)

        def patch(self, path, **kwargs):
            return self.request("PATCH", path, **kwargs)

        def delete(self, path, **kwargs):
            return self.request("DELETE", path, **kwargs)

    return API()


@pytest.fixture(scope="session")
def ensure_language(api):
    response = api.get("/languages/")
    items = response.json() if response.ok and isinstance(response.json(), list) else response.json().get("results", [])
    for item in items:
        if item.get("code") == "en":
            return item["id"]
    response = api.post("/languages/", json={"code": "en", "name": "English", "is_active": True})
    assert response.status_code in (200, 201), response.text
    return response.json().get("id")


@pytest.fixture(scope="session")
def ensure_sender_id(api):
    response = api.get("/sender-ids/")
    body = response.json() if response.ok else {}
    items = body if isinstance(body, list) else body.get("results", [])
    for item in items:
        if item.get("sender_id") == "mpes_info":
            return item["id"]
    response = api.post("/sender-ids/", json={
        "sender_id": "mpes_info",
        "name": "M-PESA Info",
        "is_active": True,
        "is_default": False,
    })
    assert response.status_code in (200, 201), response.text
    return response.json().get("id")
