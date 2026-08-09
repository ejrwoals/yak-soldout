#!/usr/bin/env python3
"""자동주문 솔루션 — 스택 1: Cloud Run 웹 UI (FastAPI).

역할: 약국 사람이 Google 로그인 → 사진 업로드 → OCR(Gemini) + 오타 교정(drug_master 매칭)
      → 검토·수정 → (다음) Supabase 저장.

Cloud Run 제약 준수: 스테이트리스(로컬 디스크 영속 X), $PORT 바인딩, Playwright 미포함.
인증: 브라우저가 supabase-js로 Google 로그인 → JWT를 Authorization: Bearer 로 전달.
      백엔드는 그 토큰으로 사용자 스코프 Supabase 클라이언트를 만들어 RLS를 적용한다.
"""

import asyncio
import base64
import io
import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

import drug_matcher
import master_repo
import ocr_service
import orders_repo

BASE = Path(__file__).parent
load_dotenv(BASE / ".env")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip()
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "").strip()

# HEIC(아이폰) 미리보기 변환을 위해 PIL에 HEIF 오프너 등록
try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    pass

app = FastAPI(title="자동주문 웹 UI")

_ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}
_EXT_TO_MIME = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
    ".webp": "image/webp", ".heic": "image/heic", ".heif": "image/heif",
}
_MAX_BYTES = 15 * 1024 * 1024  # 15MB


def _user_client(authorization: str | None):
    """Authorization: Bearer <jwt> 로 사용자 스코프 Supabase 클라이언트 생성 (RLS 적용)."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    token = authorization.split(" ", 1)[1].strip()
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        raise HTTPException(status_code=500, detail="SUPABASE_URL/ANON_KEY 가 설정되지 않았습니다.")
    from supabase import create_client

    client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
    client.postgrest.auth(token)  # 이 사용자 토큰으로 이후 쿼리 실행 → RLS (읽기용)
    return client


def _bearer(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    return authorization.split(" ", 1)[1].strip()


def _verify_user_id(authorization: str | None) -> str:
    """JWT를 GoTrue로 검증하고 user id 반환 (서명·만료 검증)."""
    token = _bearer(authorization)
    from supabase import create_client

    c = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
    try:
        return c.auth.get_user(token).user.id
    except Exception:
        raise HTTPException(status_code=401, detail="유효하지 않은 로그인입니다. 다시 로그인해주세요.")


def _service_client():
    """서버 전용 service_role 클라이언트 (신뢰된 쓰기: Storage 업로드/저장)."""
    key = os.environ.get("SUPABASE_SERVICE_KEY", "").strip()
    if not SUPABASE_URL or not key:
        raise HTTPException(status_code=500, detail="SUPABASE_SERVICE_KEY 가 설정되지 않았습니다.")
    from supabase import create_client

    return create_client(SUPABASE_URL, key)


def _token_sub(authorization: str | None) -> str:
    """JWT의 sub(user id) 로컬 디코드 — 캐시 키/스코프용. 조회는 RLS(사용자 토큰)로 이미 제한됨."""
    token = _bearer(authorization)
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload))["sub"]
    except Exception:
        raise HTTPException(status_code=401, detail="유효하지 않은 로그인 토큰입니다.")


# 사용자별 drug_master 매칭 인덱스 캐시 (자동완성이 매 요청마다 전량 재조회하지 않도록)
_index_cache: dict[str, tuple[float, dict]] = {}
_INDEX_TTL = 120  # 초. drug_master 변경이 반영되도록 짧게 유지.


def _get_user_index(client, user_id: str) -> dict:
    now = time.monotonic()
    hit = _index_cache.get(user_id)
    if hit and now - hit[0] < _INDEX_TTL:
        return hit[1]
    drugs = master_repo.fetch_drug_master(client)
    index = drug_matcher.build_index(drugs)
    _index_cache[user_id] = (now, index)
    return index


def _resolve_mime(image: UploadFile) -> str:
    mime = (image.content_type or "").lower()
    if mime not in _ALLOWED_MIME:
        ext = os.path.splitext(image.filename or "")[1].lower()
        mime = _EXT_TO_MIME.get(ext, mime)
    return mime


async def _read_validated(image: UploadFile) -> bytes:
    data = await image.read()
    if not data:
        raise HTTPException(status_code=400, detail="빈 파일입니다.")
    if len(data) > _MAX_BYTES:
        raise HTTPException(status_code=413, detail="이미지가 너무 큽니다 (최대 15MB).")
    return data


@app.get("/api/healthz")
async def healthz():
    # 참고: 최상위 /healthz 는 Google Front End가 가로채므로 /api/ 아래에 둔다.
    return {"ok": True, "ocr_configured": ocr_service.is_configured()}


@app.get("/api/config")
async def api_config():
    """브라우저 supabase-js 초기화용 공개 설정 (anon key는 공개돼도 안전, RLS로 보호)."""
    return {"url": SUPABASE_URL, "anonKey": SUPABASE_ANON_KEY}


@app.get("/", response_class=HTMLResponse)
async def index():
    return (BASE / "static" / "index.html").read_text(encoding="utf-8")


@app.post("/api/ocr")
async def api_ocr(image: UploadFile = File(...), authorization: str = Header(None)):
    """주문지 이미지 → Gemini OCR → drug_master 매칭 → [{drug_name, package_unit, quantity, match}]."""
    if not ocr_service.is_configured():
        raise HTTPException(status_code=503, detail="GEMINI_API_KEY 가 설정되지 않았습니다.")

    client = _user_client(authorization)  # 로그인 필수 (401 if 없음)
    user_id = _token_sub(authorization)

    mime = _resolve_mime(image)
    if mime not in _ALLOWED_MIME:
        raise HTTPException(status_code=400, detail=f"지원하지 않는 이미지 형식입니다: {mime or '알 수 없음'}")

    data = await _read_validated(image)
    try:
        items = await asyncio.to_thread(ocr_service.extract_order_items, data, mime)
    except ocr_service.OcrConfigError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OCR 처리 실패: {e}")

    # 오타 교정: 그 약국의 drug_master 로 매칭 (실패해도 OCR 결과는 반환)
    try:
        index = await asyncio.to_thread(_get_user_index, client, user_id)
        items = drug_matcher.attach_matches(index, items)
    except Exception:
        for it in items:
            it["match"] = {"status": "skip", "best": None, "candidates": []}

    return {"items": items, "count": len(items)}


@app.get("/api/drug-search")
async def api_drug_search(q: str = "", authorization: str = Header(None)):
    """약품 마스터 자동완성 검색 — 사용자가 약품명을 타이핑할 때 후보를 준다."""
    client = _user_client(authorization)
    user_id = _token_sub(authorization)
    q = (q or "").strip()
    if not q:
        return {"results": []}
    index = await asyncio.to_thread(_get_user_index, client, user_id)
    results = await asyncio.to_thread(drug_matcher.search, index, q, 12)
    return {"results": results}


@app.post("/api/save")
async def api_save(
    payload: str = Form(...),
    image: UploadFile = File(None),
    authorization: str = Header(None),
):
    """검토 완료된 주문 저장: 이미지 → Storage, orders/order_items(status=pending).

    토큰을 GoTrue로 검증해 user_id를 얻고, 저장(Storage+DB)은 서버의 service 키로 수행한다
    (Storage RLS를 사용자 토큰으로 태우는 대신 신뢰된 서버가 user_id 스코프로 기록)."""
    user_id = _verify_user_id(authorization)
    client = _service_client()

    try:
        body = json.loads(payload)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="payload JSON 파싱 실패")

    order_date = (body.get("order_date") or "").strip()
    if not order_date:
        raise HTTPException(status_code=400, detail="주문 일자를 선택하세요.")
    try:
        order_round = int(body.get("order_round"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="주문 차수가 올바르지 않습니다.")
    if order_round not in (1, 2, 3):
        raise HTTPException(status_code=400, detail="주문 차수는 1~3 이어야 합니다.")

    items = body.get("items") or []
    if not any((it.get("drug_name") or "").strip() for it in items):
        raise HTTPException(status_code=400, detail="저장할 품목이 없습니다.")

    image_bytes, image_mime = None, None
    if image is not None:
        image_mime = _resolve_mime(image)
        if image_mime not in _ALLOWED_MIME:
            raise HTTPException(status_code=400, detail=f"지원하지 않는 이미지 형식: {image_mime or '알 수 없음'}")
        image_bytes = await _read_validated(image)

    try:
        order_id = await asyncio.to_thread(
            orders_repo.save_reviewed_order,
            client, user_id, order_date, order_round, items, image_bytes, image_mime,
        )
    except orders_repo.DuplicateOrderError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"저장 실패: {e}")

    return {"saved": True, "order_id": order_id}


def _to_preview_jpeg(data: bytes, max_side: int = 1600) -> bytes:
    """업로드 이미지를 브라우저 미리보기용 JPEG로 변환 (HEIC 대응 + EXIF 회전 보정 + 축소)."""
    from PIL import Image, ImageOps

    im = Image.open(io.BytesIO(data))
    im = ImageOps.exif_transpose(im)
    im = im.convert("RGB")
    if max(im.size) > max_side:
        im.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=82)
    return buf.getvalue()


@app.post("/api/preview")
async def api_preview(image: UploadFile = File(...)):
    """HEIC 등 브라우저가 못 그리는 이미지를 미리보기용 JPEG로 변환해 반환."""
    data = await _read_validated(image)
    try:
        jpeg = await asyncio.to_thread(_to_preview_jpeg, data)
    except Exception as e:
        raise HTTPException(status_code=415, detail=f"미리보기 변환 실패: {e}")
    return Response(content=jpeg, media_type="image/jpeg")


app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
