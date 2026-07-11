"""Smoke: импорт приложения + GET /health."""
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)
resp = client.get("/health")
assert resp.status_code == 200, resp.text
data = resp.json()
assert data.get("status") == "ok"
assert data.get("service") == "salon-marketolog-backend"
print("OK smoke_test: /health", data)
