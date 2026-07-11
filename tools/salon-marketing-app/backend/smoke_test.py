"""Smoke: импорт приложения + health + oauth/status."""
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)
resp = client.get("/health")
assert resp.status_code == 200, resp.text
data = resp.json()
assert data.get("status") == "ok"
assert data.get("service") == "salon-marketolog-backend"

status = client.get("/oauth/status?salon_id=test-salon")
assert status.status_code == 200, status.text
st = status.json()
assert st["vk"]["connected"] is False
assert st["yandex"]["connected"] is False

start = client.get("/oauth/vk/start?salon_id=test", follow_redirects=False)
assert start.status_code == 302, start.text
assert "oauth_error=keys_missing" in start.headers.get("location", "")

print("OK smoke_test: /health", data)
print("OK smoke_test: /oauth/status", st)
print("OK smoke_test: /oauth/vk/start redirect without keys")
