# 스택 2 — 로컬 앱 (PyWebView)

약국 밖 PC에서 도는 관리자 전용 데스크톱 앱. Supabase에서 `status='pending'` 주문을 읽고,
**크롤링(도매상 사이트 조작)은 여기서만** 돈다. 도매상이 데이터센터 IP를 막기 때문이다.

```
apps/local_app/
  app.py            # FastAPI 진입점 (세션 · 주문 · 약품 DB · 규격 수집 · 설정)
  main.py           # PyWebView 창 + 서버 기동
  settings.py       # 도매상 계정 — 이 PC 의 .settings.json 에만 보관
  unit_collector.py # 규격(포장단위) 수집 — 기준 도매상 크롤링 → Supabase write-back
  master_db.py      # 약품 DB 뷰어/편집 + 규격 수집용 조회·갱신 (Supabase)
  master_import.py  # 엑셀 → drug_master 병합 임포트
  orders_repo.py    # pending 주문 조회 / cart_status·status write-back
  repo_path.py      # 루트 scrapers·models 를 임포트하기 위한 sys.path 설정
  .env              # SUPABASE_URL / SUPABASE_ANON_KEY (커밋 안 됨)
  .settings.json    # 도매상 아이디·비밀번호 (커밋 안 됨, 클라우드로 안 나감)
```

## 실행

```bash
cp apps/local_app/.env.example apps/local_app/.env      # SUPABASE_* 값 채우기
uv pip install -r apps/local_app/requirements.txt
uv run python -m playwright install chromium  # 크롤링용, 최초 1회
uv run python apps/local_app/main.py               # PyWebView 창
# 브라우저로만 테스트: cd local_app && uv run uvicorn app:app --port 8770
```

리포지토리 루트에 실행 스크립트가 있습니다.

- macOS — `./dev_local_app_mac.sh` : `.venv` 확인 → 포트 8770 좀비 정리 → `main.py` 실행
- Windows — `dev_local_app.bat` : 위에 더해 `.venv`·의존성·Chromium 을 **없을 때만** 자동 설치
  (PowerShell 에서는 `.\dev_local_app.bat`, cmd 에서는 `dev_local_app.bat`, 탐색기 더블클릭도 가능)

## 배포 빌드

리포지토리 루트에서 `.\build_local_app.bat` 하나면 끝난다 (Windows 전용).
준비 단계(venv·의존성·PyInstaller·Chromium)는 없을 때만 하고, 빌드는 매번 새로 한다.

- 산출물 : `apps/local_app/dist/자동주문/자동주문.exe` (+ 배포용 ZIP)
- spec   : `yak_order.spec` — `static/`, 루트 `scrapers/`, Playwright 브라우저를 통째로 번들
- 크기   : 폴더 약 914MB / ZIP 약 396MB (대부분 Chromium)

동결 실행 시 경로는 `runtime_paths.py` 가 갈라준다.

| | 소스 실행 | 동결(exe) |
|---|---|---|
| `RESOURCE_DIR` (static 등) | `apps/local_app/` | 번들 폴더(`_MEIPASS`) |
| `DATA_DIR` (`.env`, `.session.json`, `.settings.json`) | `apps/local_app/` | **exe 가 있는 폴더** |

그래서 배포본은 **exe 옆에 `.env`** 를 두어야 한다. 빌드 시 `apps/local_app/.env` 가 있으면
자동으로 복사하고, 없으면 `.env.example` 을 대신 넣는다.

> 창은 뜨는데 화면이 비어 있으면 exe 옆 `.local_app.log` 를 확인한다. 윈도우 모드로
> 동결하면 `sys.stdout` 이 `None` 이라 서버 스레드가 조용히 죽을 수 있어, `main.py` 가
> 표준 스트림을 이 파일로 돌려놓는다.

Google 로그인은 시스템 브라우저로 열리고(`/auth/start`), loopback 콜백으로 세션을 받아
refresh token 만 `.session.json` 에 보관한다. 로컬 앱은 **관리자(admin) 계정 전용**이다.

## 규격(포장단위) 수집

엑셀에는 규격 컬럼이 없어서, `drug_master` 에서 **보험코드가 있고 규격이 빈 약품**을
기준 도매상(지오영·유팜몰)에 코드로 검색해 결과의 규격을 모아 채운다.

1. **설정 탭** → 기준 도매상·지역·아이디·비밀번호 저장 (이 PC의 `.settings.json`, 평문).
2. **약품 DB 탭 → 규격 수집** → `[규격 수집 시작]`. 진행 상황은 SSE로 실시간 표시되고,
   `[중단]` 을 누르면 현재 항목까지 마무리하고 멈춘다.
3. 같은 보험코드는 한 번만 검색(캐시)하고, 한 코드에 여러 규격이 있으면 `30정, 100정` 처럼 모두 저장한다.
4. 결과는 Supabase `drug_master.unit` 에 기록된다 (사용자가 직접 넣은 `unit_manual` 과 분리).

크롤링은 루트 [../scrapers/](../scrapers/) 를 그대로 재사용한다(품절약 서치앱과 공유하지만
로컬 SQLite는 쓰지 않는다). 브라우저는 기본 headless — `HEADLESS=false` 로 창을 볼 수 있다.

## API

- `GET /api/me` · `GET /api/session` · `POST /api/logout` — 세션/멤버십
- `GET /api/pending-orders` — 크롤링 대기 주문
- `GET|POST /api/drug-master/...` — 약품 DB 상태·미리보기·임포트·조회·규격 직접추가·수정·삭제
- `GET /api/drug-master/unit-stats` — 규격 수집 현황
- `POST /api/drug-master/collect-units` — 수집 실행(응답 = 완료 요약)
- `POST /api/drug-master/collect-units/stop` — 중단 요청
- `GET /api/drug-master/collect-units/stream` — 진행 상황 SSE
- `GET|POST /api/settings/distributor` — 기준 도매상 계정 (비밀번호는 내려보내지 않음)
