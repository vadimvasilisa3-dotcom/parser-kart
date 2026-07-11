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

prov = client.get("/oauth/providers")
assert prov.status_code == 200, prov.text
pdata = prov.json()
assert pdata["vk"]["configured"] is False
assert "redirect_uri" in pdata["vk"]

setup = client.post(
    "/oauth/setup",
    json={"vk_client_id": "test-id", "vk_client_secret": "test-secret"},
)
assert setup.status_code == 200, setup.text
assert setup.json()["vk"]["configured"] is True

print("OK smoke_test: /health", data)
print("OK smoke_test: /oauth/status", st)
print("OK smoke_test: /oauth/vk/start redirect without keys")
print("OK smoke_test: /oauth/providers + /oauth/setup")
