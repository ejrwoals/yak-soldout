#!/usr/bin/env python3
"""자동주문 솔루션 — 스택 2: 로컬 앱 서버 (FastAPI).

PyWebView 창(또는 브라우저)이 이 로컬 서버의 UI를 띄운다. 서버는 관리자의 Supabase
세션을 보관하고, 그 사용자 세션으로 Supabase(RLS)에 접근해 자기 약국 pending 주문을 읽는다.

로그인(Google OAuth)은 Google 정책상 임베디드 웹뷰에서 막히므로 **시스템 브라우저**로 열고,
http://localhost:<PORT>/auth/callback (loopback)로 세션을 받아 서버가 보관한다(RFC 8252).
세션은 refresh token 만 로컬 파일에 저장하고, access token 은 필요 시 갱신한다.
"""

import asyncio
import base64
import json
import os
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

import master_import
import orders_repo

BASE = Path(__file__).parent
load_dotenv(BASE / ".env")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip()
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "").strip()
SESSION_FILE = BASE / ".session.json"   # refresh token 보관 (gitignore)

app = FastAPI(title="자동주문 로컬 앱")

# ===================== 세션 관리 =====================
# access token 은 메모리에 캐시(만료 시 refresh 로 갱신), refresh token 만 디스크 보관.
_sess = {"access": None, "refresh": None, "exp": 0.0}


def _decode_jwt(token: str) -> dict:
    try:
        p = token.split(".")[1]
        p += "=" * (-len(p) % 4)
        return json.loads(base64.urlsafe_b64decode(p))
    except Exception:
        return {}


def _persist_refresh(refresh: str | None) -> None:
    try:
        if refresh:
            SESSION_FILE.write_text(json.dumps({"refresh_token": refresh}))
        elif SESSION_FILE.exists():
            SESSION_FILE.unlink()
    except Exception:
        pass


def _load_refresh() -> str | None:
    try:
        if SESSION_FILE.exists():
            return json.loads(SESSION_FILE.read_text()).get("refresh_token")
    except Exception:
        pass
    return None


def set_tokens(access: str, refresh: str) -> None:
    exp = _decode_jwt(access).get("exp", time.time() + 3600)
    _sess.update(access=access, refresh=refresh, exp=float(exp))
    _persist_refresh(refresh)


def _refresh_tokens(refresh: str) -> tuple[str, str]:
    """refresh token 으로 새 access/refresh 발급 (Supabase 는 refresh 를 회전시킴)."""
    r = httpx.post(
        f"{SUPABASE_URL}/auth/v1/token",
        params={"grant_type": "refresh_token"},
        headers={"apikey": SUPABASE_ANON_KEY, "Content-Type": "application/json"},
        json={"refresh_token": refresh},
        timeout=15,
    )
    r.raise_for_status()
    d = r.json()
    return d["access_token"], d["refresh_token"]


def ensure_access() -> str | None:
    """유효한 access token 반환. 없거나 만료면 refresh 로 갱신. 세션 없으면 None."""
    if not _sess["refresh"]:
        _sess["refresh"] = _load_refresh()
    if _sess["access"] and time.time() < _sess["exp"] - 60:
        return _sess["access"]
    if not _sess["refresh"]:
        return None
    try:
        access, refresh = _refresh_tokens(_sess["refresh"])
        set_tokens(access, refresh)
        return access
    except Exception:
        # refresh 실패(만료/폐기) → 세션 초기화
        clear_session()
        return None


def clear_session() -> None:
    _sess.update(access=None, refresh=None, exp=0.0)
    _persist_refresh(None)


# ===================== Supabase 클라이언트 =====================
_base_client = None


def _client():
    global _base_client
    if _base_client is None:
        from supabase import create_client
        _base_client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
    return _base_client


def authed_client():
    """현재 사용자 세션이 실린 클라이언트. 로그인 안 됐으면 None."""
    access = ensure_access()
    if not access:
        return None
    c = _client()
    c.postgrest.auth(access)  # 이 사용자 토큰으로 RLS 적용
    return c


def _current_email() -> str:
    return _decode_jwt(_sess["access"] or "").get("email", "")


# ===================== API =====================
@app.get("/api/config")
def api_config():
    return {"url": SUPABASE_URL, "anonKey": SUPABASE_ANON_KEY}


@app.get("/api/session")
def api_session():
    return {"logged_in": bool(ensure_access())}


@app.post("/auth/store")
async def auth_store(body: dict):
    access = (body or {}).get("access_token")
    refresh = (body or {}).get("refresh_token")
    if not access or not refresh:
        raise HTTPException(status_code=400, detail="토큰이 누락됐습니다.")
    set_tokens(access, refresh)
    return {"ok": True}


@app.post("/api/logout")
def api_logout():
    clear_session()
    return {"ok": True}


def _membership(c) -> dict | None:
    """현재 사용자의 (첫) 멤버십 {pharmacy_id, role, pharmacy_name}. RLS로 본인 것만."""
    res = c.table("memberships").select("pharmacy_id, role, pharmacies(name)").limit(1).execute()
    if not res.data:
        return None
    m = res.data[0]
    return {
        "pharmacy_id": m["pharmacy_id"],
        "role": m["role"],
        "pharmacy_name": (m.get("pharmacies") or {}).get("name"),
    }


@app.get("/api/me")
def api_me():
    c = authed_client()
    if not c:
        return {"logged_in": False}
    m = _membership(c)
    if not m:
        return {"logged_in": True, "member": False, "email": _current_email()}
    return {"logged_in": True, "member": True, "email": _current_email(), **m}


@app.get("/api/pending-orders")
def api_pending_orders():
    """크롤링 대기 주문 조회 — 로컬 앱은 관리자 전용."""
    c = authed_client()
    if not c:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    m = _membership(c)
    if not m:
        raise HTTPException(status_code=403, detail="약국 소속이 없습니다.")
    if m["role"] != "admin":
        raise HTTPException(status_code=403, detail="이 앱은 관리자만 이용할 수 있습니다.")
    orders = orders_repo.get_pending_orders(c)
    return {"orders": orders, "count": len(orders)}


def _require_admin():
    """(client, membership) 반환. 로그인·소속·admin 아니면 예외."""
    c = authed_client()
    if not c:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    m = _membership(c)
    if not m:
        raise HTTPException(status_code=403, detail="약국 소속이 없습니다.")
    if m["role"] != "admin":
        raise HTTPException(status_code=403, detail="관리자만 이용할 수 있습니다.")
    return c, m


@app.get("/api/drug-master/status")
def dm_status():
    c, m = _require_admin()
    pid = m["pharmacy_id"]
    cnt = c.table("drug_master").select("id", count="exact").eq("pharmacy_id", pid).limit(1).execute()
    meta = (
        c.table("drug_master").select("imported_at, source_file")
        .eq("pharmacy_id", pid).order("imported_at", desc=True).limit(1).execute()
    )
    info = meta.data[0] if meta.data else {}
    return {"count": cnt.count or 0, "imported_at": info.get("imported_at"), "source_file": info.get("source_file")}


@app.post("/api/drug-master/preview")
async def dm_preview(file: UploadFile = File(...), header_row: str = Form("")):
    _require_admin()
    data = await file.read()
    hr = int(header_row) if header_row.strip().isdigit() else None
    try:
        return await asyncio.to_thread(master_import.preview, data, file.filename, hr)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"미리보기 실패: {e}")


@app.post("/api/drug-master/import")
async def dm_import(
    file: UploadFile = File(...),
    name_col: str = Form(...),
    code_col: str = Form(""),
    maker_col: str = Form(""),
    header_row: str = Form("0"),
):
    c, m = _require_admin()
    data = await file.read()
    hr = int(header_row) if header_row.strip().lstrip("-").isdigit() else 0
    try:
        drugs = await asyncio.to_thread(
            master_import.extract_drugs, data, file.filename, name_col,
            code_col or None, maker_col or None, hr,
        )
        result = await asyncio.to_thread(
            master_import.import_to_supabase, c, m["pharmacy_id"], drugs, file.filename
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"임포트 실패: {e}")
    return result


# ===================== 정적/페이지 =====================
@app.get("/", response_class=HTMLResponse)
def index():
    return (BASE / "static" / "index.html").read_text(encoding="utf-8")


@app.get("/auth/start", response_class=HTMLResponse)
def auth_start():
    return (BASE / "static" / "auth_start.html").read_text(encoding="utf-8")


@app.get("/auth/callback", response_class=HTMLResponse)
def auth_callback():
    return (BASE / "static" / "auth_callback.html").read_text(encoding="utf-8")


app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
