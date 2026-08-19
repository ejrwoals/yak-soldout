# 스택 1 — Cloud Run 웹 UI

약국 사람이 주문지 사진을 올려 OCR → 검토·수정 → (B단계부터) Supabase 저장하는 웹 앱.
Playwright 없음(경량), 스테이트리스, `$PORT` 바인딩 — Cloud Run 배포를 전제로 개발.

```
cloud_web/
  app.py             # FastAPI 진입점 (업로드/OCR/미리보기)
  ocr_service.py     # Gemini OCR (자체 완결 사본)
  static/index.html  # 업로드 + 검토·수정 UI
  requirements.txt
  .env               # SUPABASE_*, GEMINI_* (커밋 안 됨)
```

## 로컬 실행

의존성은 개발 중 루트 `.venv` 에 설치되어 있다(`uv pip install -r cloud_web/requirements.txt`).

```bash
# 프로젝트 루트에서
.venv/bin/python cloud_web/app.py       # 기본 http://localhost:8080
# 포트 바꾸려면: PORT=8090 .venv/bin/python cloud_web/app.py
```

브라우저에서 `http://localhost:8080` 접속 → 주문지 사진 업로드 → **OCR 하기** →
검토 테이블에서 약품명·포장단위·수량 확인/수정.

- OCR에는 `cloud_web/.env` 의 `GEMINI_API_KEY` 필요 (개발용으로 루트 `.env` 값 복사해 둠).
- `GET /api/healthz` 로 상태 확인: `{"ok":true,"ocr_configured":true}`.
  (최상위 `/healthz` 는 Google Front End가 가로채므로 `/api/` 아래에 둠)

## 기능 흐름 (구현 완료)

1. **Google 로그인** (Supabase Auth) — 로그인해야 앱 진입. 브라우저 supabase-js가 JWT 발급.
2. **업로드 → OCR** — 사진(HEIC 포함) 업로드 → `/api/ocr` (Gemini). Bearer JWT 필요.
3. **오타 교정(매칭)** — 그 약국의 `drug_master`로 fuzzy 매칭(일치/후보/미등록 배지),
   약품명 타이핑 시 `/api/drug-search` 자동완성.
4. **저장** — 검토본을 `orders`/`order_items`(status=pending)로 저장, 원본 이미지는
   Supabase Storage(`order-images/<user_id>/…`)로 업로드(`/api/save`).
   서버가 토큰을 GoTrue로 검증한 뒤 service_role 키로 기록한다.

저장된 pending 주문은 로컬 앱(스택 2)이 읽어 크롤링(장바구니 담기)할 대상이 된다.

## API

- `GET /api/config` — 브라우저 supabase-js 초기화용(URL·anon key)
- `GET /api/healthz` — 상태 확인
- `POST /api/ocr` — 이미지 → OCR + 매칭 (Bearer)
- `POST /api/preview` — HEIC 등 미리보기용 JPEG 변환
- `GET /api/drug-search?q=` — 약품명 자동완성 (Bearer)
- `POST /api/save` — 검토본 저장 (Bearer)
