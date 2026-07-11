"""Салон-Маркетолог v2 — OAuth бэкенд (VK / Яндекс)."""
from __future__ import annotations

import os
import secrets
import sqlite3
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field

load_dotenv()

APP_DIR = Path(__file__).resolve().parent
ENV_PATH = APP_DIR / ".env"
TOKENS_PATH = Path(os.getenv("TOKENS_DB_PATH", str(APP_DIR / "tokens.sqlite3")))
REDIRECT_BASE = os.getenv("OAUTH_REDIRECT_BASE", "http://127.0.0.1:8000").rstrip("/")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://127.0.0.1:8777").rstrip("/")

PROVIDERS = ("vk", "yandex")

app = FastAPI(title="Salon-Marketolog OAuth Backend", version="2.0.0")

_origins = [FRONTEND_URL, "http://127.0.0.1:8777", "http://localhost:8777"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(dict.fromkeys(_origins)),
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(TOKENS_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """CREATE TABLE IF NOT EXISTS tokens (
            salon_id TEXT NOT NULL,
            provider TEXT NOT NULL,
            access_token TEXT NOT NULL,
            refresh_token TEXT,
            expires_at REAL,
            PRIMARY KEY (salon_id, provider)
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS oauth_states (
            state TEXT PRIMARY KEY,
            salon_id TEXT NOT NULL,
            provider TEXT NOT NULL,
            created_at REAL NOT NULL
        )"""
    )
    conn.commit()
    return conn


def _provider_config(provider: str) -> dict[str, str]:
    if provider == "vk":
        cid, secret = os.getenv("VK_CLIENT_ID", ""), os.getenv("VK_CLIENT_SECRET", "")
        return {
            "client_id": cid,
            "client_secret": secret,
            "authorize_url": "https://oauth.vk.com/authorize",
            "token_url": "https://oauth.vk.com/access_token",
            "scope": "ads,offline",
        }
    if provider == "yandex":
        cid, secret = os.getenv("YANDEX_CLIENT_ID", ""), os.getenv("YANDEX_CLIENT_SECRET", "")
        return {
            "client_id": cid,
            "client_secret": secret,
            "authorize_url": "https://oauth.yandex.ru/authorize",
            "token_url": "https://oauth.yandex.ru/token",
            "scope": "direct:api",
        }
    raise HTTPException(400, detail={"error": "unknown_provider", "provider": provider})


def _require_configured(provider: str) -> dict[str, str]:
    cfg = _provider_config(provider)
    if not cfg["client_id"] or not cfg["client_secret"]:
        raise HTTPException(
            503,
            detail={"error": "provider_not_configured", "provider": provider},
        )
    return cfg


def _provider_configured(provider: str) -> bool:
    cfg = _provider_config(provider)
    return bool(cfg["client_id"] and cfg["client_secret"])


def _local_only(request: Request) -> None:
    host = request.client.host if request.client else ""
    if host not in ("127.0.0.1", "::1", "localhost", "testclient"):
        raise HTTPException(403, detail={"error": "local_only"})


def _write_env(updates: dict[str, str]) -> None:
    if not ENV_PATH.exists():
        example = APP_DIR / ".env.example"
        if example.exists():
            ENV_PATH.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
        else:
            ENV_PATH.write_text("", encoding="utf-8")
    lines = ENV_PATH.read_text(encoding="utf-8").splitlines()
    done: set[str] = set()
    out: list[str] = []
    for line in lines:
        if "=" in line and not line.strip().startswith("#"):
            key = line.split("=", 1)[0].strip()
            if key in updates:
                out.append(f"{key}={updates[key]}")
                done.add(key)
                continue
        out.append(line)
    for key, val in updates.items():
        if key not in done:
            out.append(f"{key}={val}")
    ENV_PATH.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")
    for key, val in updates.items():
        os.environ[key] = val


class SetupBody(BaseModel):
    vk_client_id: str | None = Field(None, max_length=200)
    vk_client_secret: str | None = Field(None, max_length=500)
    yandex_client_id: str | None = Field(None, max_length=200)
    yandex_client_secret: str | None = Field(None, max_length=500)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "salon-marketolog-backend"}


@app.get("/oauth/providers")
def oauth_providers() -> dict[str, dict[str, bool | str]]:
    return {
        "vk": {
            "configured": _provider_configured("vk"),
            "redirect_uri": f"{REDIRECT_BASE}/oauth/vk/callback",
        },
        "yandex": {
            "configured": _provider_configured("yandex"),
            "redirect_uri": f"{REDIRECT_BASE}/oauth/yandex/callback",
        },
    }


@app.post("/oauth/setup")
def oauth_setup(body: SetupBody, request: Request) -> dict[str, dict[str, bool]]:
    _local_only(request)
    updates: dict[str, str] = {}
    if body.vk_client_id is not None:
        updates["VK_CLIENT_ID"] = body.vk_client_id.strip()
    if body.vk_client_secret is not None:
        updates["VK_CLIENT_SECRET"] = body.vk_client_secret.strip()
    if body.yandex_client_id is not None:
        updates["YANDEX_CLIENT_ID"] = body.yandex_client_id.strip()
    if body.yandex_client_secret is not None:
        updates["YANDEX_CLIENT_SECRET"] = body.yandex_client_secret.strip()
    if not updates:
        raise HTTPException(400, detail={"error": "empty_setup"})
    _write_env(updates)
    return {
        "vk": {"configured": _provider_configured("vk")},
        "yandex": {"configured": _provider_configured("yandex")},
    }


@app.get("/oauth/{provider}/start")
def oauth_start(provider: str, salon_id: str = Query(..., min_length=1)) -> RedirectResponse:
    if provider not in PROVIDERS:
        raise HTTPException(400, detail={"error": "unknown_provider", "provider": provider})
    try:
        cfg = _require_configured(provider)
    except HTTPException:
        return RedirectResponse(
            f"{FRONTEND_URL}?oauth_error=keys_missing_{provider}", status_code=302
        )
    state = secrets.token_urlsafe(32)
    conn = _db()
    conn.execute(
        "INSERT INTO oauth_states (state, salon_id, provider, created_at) VALUES (?, ?, ?, ?)",
        (state, salon_id, provider, time.time()),
    )
    conn.commit()
    conn.close()
    redirect_uri = f"{REDIRECT_BASE}/oauth/{provider}/callback"
    params = {
        "client_id": cfg["client_id"],
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "state": state,
        "scope": cfg["scope"],
    }
    if provider == "yandex":
        params["force_confirm"] = "yes"
    url = f"{cfg['authorize_url']}?{urlencode(params)}"
    return RedirectResponse(url, status_code=302)


@app.get("/oauth/{provider}/callback")
async def oauth_callback(
    provider: str,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    if provider not in PROVIDERS:
        return RedirectResponse(f"{FRONTEND_URL}?oauth_error={provider}", status_code=302)
    if error or not code or not state:
        return RedirectResponse(f"{FRONTEND_URL}?oauth_error={provider}", status_code=302)

    conn = _db()
    row = conn.execute(
        "SELECT salon_id, provider FROM oauth_states WHERE state = ?", (state,)
    ).fetchone()
    if not row or row["provider"] != provider:
        conn.close()
        return RedirectResponse(f"{FRONTEND_URL}?oauth_error={provider}", status_code=302)

    salon_id = row["salon_id"]
    conn.execute("DELETE FROM oauth_states WHERE state = ?", (state,))
    conn.commit()

    try:
        cfg = _require_configured(provider)
    except HTTPException:
        conn.close()
        return RedirectResponse(f"{FRONTEND_URL}?oauth_error={provider}", status_code=302)

    redirect_uri = f"{REDIRECT_BASE}/oauth/{provider}/callback"
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": cfg["client_id"],
        "client_secret": cfg["client_secret"],
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(cfg["token_url"], data=data)
    if resp.status_code >= 400:
        conn.close()
        return RedirectResponse(f"{FRONTEND_URL}?oauth_error={provider}", status_code=302)

    payload: dict[str, Any] = resp.json()
    access = payload.get("access_token")
    if not access:
        conn.close()
        return RedirectResponse(f"{FRONTEND_URL}?oauth_error={provider}", status_code=302)

    refresh = payload.get("refresh_token")
    expires_in = payload.get("expires_in")
    expires_at = time.time() + float(expires_in) if expires_in else None

    conn.execute(
        """INSERT INTO tokens (salon_id, provider, access_token, refresh_token, expires_at)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(salon_id, provider) DO UPDATE SET
             access_token=excluded.access_token,
             refresh_token=excluded.refresh_token,
             expires_at=excluded.expires_at""",
        (salon_id, provider, access, refresh, expires_at),
    )
    conn.commit()
    conn.close()
    return RedirectResponse(f"{FRONTEND_URL}?connected={provider}", status_code=302)


@app.get("/oauth/status")
def oauth_status(salon_id: str = Query(..., min_length=1)) -> dict[str, dict[str, bool]]:
    conn = _db()
    rows = conn.execute(
        "SELECT provider FROM tokens WHERE salon_id = ?", (salon_id,)
    ).fetchall()
    conn.close()
    connected = {r["provider"] for r in rows}
    return {
        "vk": {"connected": "vk" in connected},
        "yandex": {"connected": "yandex" in connected},
    }


@app.post("/oauth/{provider}/disconnect")
def oauth_disconnect(provider: str, salon_id: str = Query(..., min_length=1)) -> dict[str, bool]:
    if provider not in PROVIDERS:
        raise HTTPException(400, detail={"error": "unknown_provider", "provider": provider})
    conn = _db()
    conn.execute(
        "DELETE FROM tokens WHERE salon_id = ? AND provider = ?", (salon_id, provider)
    )
    conn.commit()
    conn.close()
    return {"ok": True}
