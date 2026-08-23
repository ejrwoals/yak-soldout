# 🏥 약품 재고 자동 검색 시스템 (yak-soldout)

> 약국을 위한 도매상 품절 약품 자동 모니터링 시스템

주요 의약품 도매상(지오영, 백제약품, 인천약품, 지오팜, 복산, 유팜몰, HMP몰, 티제이팜)에서 품절된 약품의 재고 상황을 자동으로 모니터링하고 실시간으로 알림을 제공하는 시스템입니다.

FastAPI 기반의 웹 인터페이스와 Playwright를 활용한 안정적인 웹 자동화 기술을 사용하며, 레지스트리 패턴으로 도매상을 손쉽게 추가할 수 있는 확장형 아키텍처를 갖추고 있습니다.

## 🗂️ 저장소 구성 — 두 개의 독립 앱

이 저장소는 이제 **서로 독립적인 두 개의 앱**을 담고 있으며, 둘은 오직 **Supabase**를 통해서만 만납니다.

- **품절약 서치앱** — *이 README의 주 대상.* 도매상 품절 약품을 모니터링하는 로컬 앱입니다. 로컬 SQLite(`data/yak_soldout.db`) + Playwright 기반이며 **로컬 전용**으로 유지됩니다(Supabase를 쓰지 않습니다). 아래 [주요 기능](#-주요-기능) 이하 문서 전체가 이 앱을 설명합니다.
- **자동 주문 솔루션** — 손글씨 주문지를 OCR로 읽어 검수·저장하고, 저장된 주문을 자동으로 도매상 장바구니에 담는 것을 목표로 하는 **신규 앱**입니다. 데이터는 전적으로 **Supabase**(Postgres + Auth + Storage)에 두며, 두 개의 스택으로 나뉩니다.

두 앱은 프로세스·저장소가 분리되어 있고, 공유하는 것은 Supabase 데이터(특히 `drug_master`)뿐입니다. 품절앱의 로컬 SQLite는 건드리지 않습니다. 코드 공유는 딱 하나 — 크롤링이 필요한 **로컬 앱(스택 2)만** 루트의 공유 패키지 `scrapers/`(Playwright 스크래퍼 + drug_data 데이터 모델)를 **읽기 전용으로 재사용**합니다(`apps/local_app/repo_path.py`가 리포지토리 루트를 `sys.path`에 올립니다). 이 두 모듈은 `db.py`(로컬 SQLite)를 임포트하지 않으므로 "자동 주문 솔루션은 로컬 DB를 쓰지 않는다"는 전제는 유지됩니다. 클라우드 웹(스택 1)은 Playwright가 없으므로 여전히 코드를 공유하지 않습니다.

> 전체 설계: [주문-자동화-워크플로우-구현-계획.md](주문-자동화-워크플로우-구현-계획.md)

### 디렉터리 맵 (자동 주문 솔루션)

```
apps/cloud_web/     # 스택 1 — Cloud Run 웹 UI (FastAPI). 업로드→OCR(또는 직접 작성)→매칭→검수→Supabase 저장 + 주문 기록(달력)·약품 DB 조회
apps/local_app/     # 스택 2 — 로컬 PyWebView+FastAPI 관리자 앱. pending 주문 조회·품목별 주문 도매상 지정 + 약품 마스터 엑셀 임포트(월별 약품사용량 자동 감지·월평균 계산 포함)/뷰어 + 규격(포장단위) 수집 크롤링 + 도매상 계정 설정 (장바구니 담기는 예정)
supabase/      # 공유 백엔드 스키마 (migrations/: 0001 스키마+RLS+Storage, 0002 grants, 0003 멀티테넌트 전환, 0004 멤버십 조회 뷰, 0005 월별 약품 사용량, 0006 월별 사용량 요약, 0007 규격 미발견 보류)
scripts/       # 개발·검증·이전 스크립트 (migrate_drug_master.py, dev_smoke.py 등)
deploy.sh      # 스택 1을 Cloud Run에 한 줄로 배포
```

각 폴더에 자체 README가 있습니다 — [apps/cloud_web/README.md](apps/cloud_web/README.md), [apps/cloud_web/DEPLOY.md](apps/cloud_web/DEPLOY.md), [apps/local_app/README.md](apps/local_app/README.md), [supabase/README.md](supabase/README.md).

### 멀티테넌트 모델 (약국 = 테넌트)

자동 주문 솔루션의 데이터 주인은 개인 사용자가 아니라 **약국(pharmacy)**입니다. 약국 1곳이 하나의 테넌트이며, 사용자는 `memberships`로 약국에 소속되고(역할 `admin`|`staff`), 소속을 통해서만 그 약국의 `orders`·`drug_master`·주문 이미지에 접근합니다. 격리는 애플리케이션 코드가 아니라 **Supabase RLS**로 물리적으로 강제됩니다(`supabase/migrations/0003_multitenant.sql`).

- **역할(role)**: `admin`은 약국을 부트스트랩하고 스탭 초대코드를 발행하며(로컬 크롤링·엑셀 마스터 관리도 관리자 몫), `staff`는 초대로 합류해 업로드·OCR·검수·저장을 수행합니다.
- **초대 기반 합류**: 관리자가 발행한 초대코드(`invites` 테이블, 추측 불가능한 랜덤 코드)를 스탭이 Google 로그인 후 `POST /api/accept-invite`로 redeem하면 `memberships` 행이 생겨 합류됩니다. 관리자는 앱 상단의 "스탭 초대" 버튼으로 초대 링크(`/?invite=CODE`)를 만들며, 그 링크로 들어온 사용자는 로그인 직후 자동 합류합니다.
- **membership 기반 RLS**: 모든 정책이 `security definer` 헬퍼 함수 `auth_pharmacy_ids()`(내가 속한 약국 id 집합)와 `auth_is_admin(pharmacy_id)`를 기준으로 동작합니다. `orders`/`order_items`/`drug_master`/`pharmacies`/Storage 객체는 내가 속한 약국 것만 CRUD할 수 있고, `invites`는 그 약국 admin만 관리합니다. 멤버십·초대의 쓰기는 RLS로 막혀 있어, 서버가 JWT를 검증한 뒤 **service_role**로만 수행합니다(`apps/cloud_web/tenant_repo.py`).
- **초기 셋업**: 0003 마이그레이션은 (폐기 가능 전제로) 기존 `user_id` 기반 `orders`/`drug_master` 데이터를 비우고 스키마를 `pharmacy_id` 기준으로 전환합니다. 적용 후 약국(`pharmacies`) 1행과 관리자 멤버십(`memberships`, `role='admin'`)을 만들고, `drug_master`는 로컬 앱의 관리자 엑셀 임포트로 채웁니다.

### 스택 1 — Cloud Run 웹 UI (`apps/cloud_web/`)

약국 스탭이 브라우저에서 주문지를 처리하는 경량 FastAPI 앱입니다. **Playwright를 포함하지 않고**(경량), 스테이트리스이며 `$PORT`에 바인딩해 **Google Cloud Run**에 배포됩니다. 로그인하면 **홈 화면(런처)**이 먼저 뜨고, 세 개의 카드 — **주문지 OCR**(주문지 작성) / **과거 주문 기록**(달력 조회) / **약 목록 조회**(약품 DB 뷰어) — 로 화면을 오갑니다. 데이터 흐름:

1. **Google 로그인 + 약국 소속 확인**(Supabase Auth) — 브라우저의 `supabase-js`가 로그인해 발급한 JWT를 `Authorization: Bearer`로 백엔드에 전달합니다. 로그인 직후 프론트는 `GET /api/me`로 소속(멤버십)을 확인해 **세 상태**(로그인 / 초대코드 합류 / 앱)로 분기합니다 — 소속이 없으면 초대코드 입력 화면이 뜨고, 소속이 있어야 OCR·저장 등 데이터 API를 쓸 수 있습니다(서버 `_require_membership` 게이트, 소속 없으면 403). 백엔드는 그 토큰으로 만든 사용자 스코프 클라이언트에 **membership 기반 RLS**를 적용하며, 멤버십 조회는 짧게 TTL 캐시합니다(`apps/cloud_web/app.py`, `tenant_repo.py`).
2. **입력 방식 — 사진(OCR) / 직접 작성** — 상단 토글로 두 방식 중 고릅니다. *사진으로 읽기*는 업로드한 이미지를 Gemini 멀티모달로 약품명·포장단위·수량을 추출하고(`apps/cloud_web/ocr_service.py`, 구 품절앱 OCR 코드 `legacy_codes/utils/ocr_service.py`를 자체 완결 사본으로 이식), *직접 작성*은 업로드·이미지 없이 빈 검수 테이블을 바로 열어 약품명 자동완성(`/api/drug-search`)으로 손으로 입력합니다(이미지 없이 저장).
3. **약품명 오타 보정** — 그 약국의 `drug_master`(Supabase)로 한글 자모 fuzzy 매칭을 수행해 검수 테이블에 결과를 붙입니다(`apps/cloud_web/drug_matcher.py` + `master_repo.py`, 구 품절앱 OCR 코드 `legacy_codes/utils/drug_matcher.py`에서 이식). 매칭 인덱스는 **약국(`pharmacy_id`)별로** TTL 캐시합니다.
4. **검수·수정 UI** — `static/index.html` + `static/js/order-ocr.js`(구 품절앱 CSS 이식), 타이핑 자동완성(`/api/drug-search`)으로 마스터 후보를 제시합니다.
5. **Supabase 저장** — 검수본을 `orders`/`order_items`(`status='pending'`)로, 원본 이미지를 Supabase Storage(`order-images/<pharmacy_id>/…`)로 저장합니다(`apps/cloud_web/orders_repo.py`). 저장 경로는 JWT를 GoTrue로 검증해 사용자를 얻고 소속 약국을 확인한 뒤, **service_role 키**로 서버가 그 `pharmacy_id` 스코프로 신뢰 기록합니다. 같은 `(pharmacy_id, 날짜, 차수)`가 이미 있으면 409를 반환하고, 프론트가 사용자 동의를 받아 `overwrite=true`로 재요청하면 기존 주문(품목·원본 이미지 포함)을 교체합니다. 저장 시 마스터에 없던 **자유입력 약품은 `drug_master`에 `source='manual'` 행으로 자동 등록**되어(입력한 포장단위는 `unit_manual`로 보관, `master_repo.register_free_input_drugs`) 곧바로 OCR 매칭·자동완성에 활용됩니다(매칭 인덱스 캐시도 즉시 무효화).
6. **주문 기록 조회 (달력)** — 홈의 "과거 주문 기록" 카드로 진입하는 **달력 화면**입니다. 왼쪽 달력에 주문이 있는 날짜가 표시되고, 오른쪽에 그 약국의 저장된 주문이 품목 테이블과 함께 카드 목록으로 펼쳐집니다(`GET /api/orders`, RLS로 소속 약국만). 각 카드는 상태 배지(크롤링 대기 `pending` / 주문완료 `ordered`)와 함께 **원본 주문지 이미지 조회**(`GET /api/orders/{id}/image` — Storage 경로는 노출하지 않고 서버가 소속 확인 후 내려줌)와 **주문 삭제**(`DELETE /api/orders/{id}` — 품목 CASCADE + Storage 이미지 정리)를 지원합니다.
7. **약 목록 조회** — 홈의 "약 목록 조회" 카드로 진입하는 읽기 전용 **약품 DB 뷰어**입니다. 그 약국의 `drug_master`를 약품명 검색 + 페이지네이션으로 조회합니다(`GET /api/drug-master`, `master_repo.search_drug_master`).

주요 엔드포인트: `GET /api/healthz` · `GET /api/config`(브라우저 supabase-js 초기화용 공개 설정) · `GET /api/me`(소속 조회) · `GET /api/orders`(주문 기록) · `GET /api/orders/{id}/image`(원본 주문지 이미지) · `DELETE /api/orders/{id}`(주문 삭제) · `GET /api/drug-master`(약품 DB 뷰어 조회) · `POST /api/accept-invite`(초대코드로 합류) · `POST /api/invites`(관리자 전용 초대코드 발행) · `POST /api/ocr` · `GET /api/drug-search` · `POST /api/save`(`overwrite` 지원 + 자유입력 약품 자동 등록) · `POST /api/preview`(HEIC 등 미리보기용 JPEG 변환).

### 스택 2 — 로컬 관리자 앱 (`apps/local_app/`)

약국 **관리자**가 데스크톱에서 실행하는 **PyWebView + FastAPI** 앱입니다(`apps/local_app/main.py`가 진입점 — `uvicorn`으로 로컬 서버를 포트 `8770`에 띄우고 PyWebView 창으로 그 UI를 엽니다). 로컬 SQLite가 아니라 **anon key + 로그인한 관리자 세션**으로 Supabase에 접속하며(RLS 적용, service 키는 두지 않습니다), 현재 네 가지 기능을 제공합니다: (1) 약국의 `pending` 주문 조회 + 품목별 주문 도매상 지정, (2) 약품 마스터 엑셀 임포트(월별 약품사용량 파일이면 사용량·월평균도 함께 처리) + 뷰어/편집, (3) 기준 도매상 크롤링으로 규격(포장단위) 일괄 수집, (4) 그 크롤링에 쓰는 도매상 계정 설정. UI는 세 개의 탭(크롤링 대기 주문 / 약품 DB / 설정)으로 나뉩니다. 실행: `uv pip install -r apps/local_app/requirements.txt` → `uv run python -m playwright install chromium`(크롤링용, 최초 1회) → `uv run python apps/local_app/main.py`(브라우저 테스트만 하려면 `uv run uvicorn app:app --port 8770`).

- **관리자 전용**: 스탭(`staff`)도 로그인은 되지만 "관리자 전용" 안내 화면만 보게 되며, `/api/pending-orders`·`/api/drug-master/*`·`/api/settings/*`는 서버에서 `role == 'admin'`을 강제합니다(`_require_admin`, 소속 없으면 403).
- **Google OAuth (시스템 브라우저 + loopback)**: Google 정책상 임베디드 웹뷰에서 OAuth가 막히므로, PyWebView JS 브릿지(`Api.start_login`)가 로그인을 **시스템 브라우저**로 엽니다(RFC 8252). 브라우저의 `/auth/start`가 `supabase-js`로 Google 로그인을 시작하고, `http://localhost:8770/auth/callback`(loopback)로 돌아와 `?code=`를 세션으로 교환한 뒤 그 토큰을 로컬 서버 `/auth/store`로 전달합니다. 서버는 **refresh token만** `apps/local_app/.session.json`에 보관하고 access token은 메모리에 캐시하다 만료 시 자동 갱신하며(Supabase가 refresh를 회전), 그 사용자 세션을 실은 클라이언트로 RLS 스코프 읽기를 수행합니다(`apps/local_app/app.py`).
- **pending 주문 조회 + 품목별 도매상 지정**: 웹(스택 1)이 저장한 `status='pending'` 주문을 품목과 함께 오래된 순으로 읽어 창에 표시합니다(`GET /api/pending-orders`, `apps/local_app/orders_repo.py`). 품목은 OCR 추출 순서(`position`)로 정렬됩니다. 각 품목 행에는 **주문 도매상 드롭다운**(`scrapers/registry.py` 기준 전체 도매상, `GET /api/distributors`)이 있어, 주문 카드를 처음 펼칠 때 그 약품의 **가장 최근 주문 이력의 도매상이 기본값으로 자동 선택·저장**되고(`POST /api/order-context` — 약품별 과거 주문 이력 + 마지막 도매상), 바꾸면 즉시 Supabase `order_items.distributor`에 반영됩니다(`POST /api/order-items/distributor`). 행을 클릭하면 오른쪽 패널에 그 약품의 과거 주문 이력(주문일자·차수·도매상·수량)이 표시되어 평소 주문처를 보고 고를 수 있습니다. 각 품목 행과 이력 패널에는 **월평균 사용량**(아래 사용량 임포트로 계산)이 참고 자료로 함께 표시됩니다(`/api/order-context` 응답의 `usage`, 약품명→`drug_master` 보험코드→`drug_usage_stats` 조인). 이것이 웹→Supabase→로컬로 이어지는 주문 파이프라인의 로컬 끝단입니다.
- **약품 마스터 엑셀 임포트(관리자)**: `drug_master`를 채우는 경로입니다. 엑셀 업로드 → 미리보기 모달(머리글 행 자동추정 + 약품명·보험코드·제약사 컬럼 자동 제안, `POST /api/drug-master/preview`) → 임포트(`POST /api/drug-master/import`)로, 그 약국(`pharmacy_id`) 스코프에 **병합 임포트**합니다 — 기존 약품은 규격·정보를 그대로 유지하고 `(약품명, 보험코드)` 조합이 없던 **신규 약품만 추가**하며, 엑셀에 없는 기존 약품도 삭제하지 않습니다. 엑셀 파싱 로직은 레거시 품절앱 OCR 코드(`legacy_codes/utils/drug_master.py`)에서 이식했습니다(`apps/local_app/master_import.py`). 머리글 행 추정은 힌트 단어를 찾으면 확신, 못 찾으면 최다 셀 행 추정으로 동작해 확신 여부(`header_confident`)를 함께 내려보내며, 추정이 불확실하거나 컬럼명이 이상하면 미리보기 모달에서 **파일 원본 상위 행을 직접 클릭해 머리글 행을 선택**할 수 있습니다(선택된 약품명·보험코드 등 컬럼은 미리보기에서 색상으로 강조, 사용량 컬럼은 파란 배경). 임포트가 끝나면 상세 결과 모달로 결과를 안내하고, 브라우저 네이티브 alert/confirm 대신 앱 내 모달을 사용합니다. 등록 현황은 `GET /api/drug-master/status`로 조회합니다. 임포트 시 엑셀의 신규 약품이 기존 **자유입력(`source='manual'`) 약품과 이름이 비슷하면**(한글 자모 분해 + rapidfuzz 유사도 ≥85) 그 행의 임포트를 보류하고 확인 모달("같은 약품인지 확인해주세요")을 띄웁니다 — 같은 약품으로 확인하면 자유입력 행을 **병합·승격**(공식 명칭·보험코드·제약사로 갱신 + `source='excel'`, 등록해둔 규격은 유지)하고, 다른 약품이면 엑셀 행을 신규로 추가합니다(`POST /api/drug-master/resolve-conflict`, `master_import.resolve_conflict`).
- **월별 약품사용량 임포트 + 월평균 계산(관리자)**: 같은 엑셀 업로드 흐름에서 약국 조제 프로그램의 **월별 약품사용량** 파일을 자동 감지합니다(`apps/local_app/drug_usage.py` — `1월`~`12월` 컬럼이 모두 있으면 사용량 파일로 판정, 연도는 파일 상단 "검색기간:YYYY" 또는 파일명에서 추출). 임포트 시 `(청구코드, 연, 월)` 단위 원본을 Supabase `drug_usage`에 저장하고(같은 연도 파일 재업로드 = 그 연도만 교체, `qty=0`인 달은 저장 안 함), 저장된 전체 연도를 합쳐 약품별 월평균을 `drug_usage_stats`로 재계산합니다. 계산 규칙: **최근 12개 완전월** 구간을 잡되, 마지막 달이 월중 추출된 **부분 데이터인지는 robust z-score**(중앙값·MAD 기준, 월 사용량 총합·사용 약품 수 중 하나라도 z < -3.5)로 판정해 제외하고, 연중 새로 취급하기 시작한 약은 **취급 시작월부터** 평균합니다(이전 달은 분모에서 제외). 파일 자체의 "월평균" 컬럼(항상 소계÷12라 연중 데이터에서 과소평가)과 "현재고" 컬럼은 쓰지 않습니다. 연도별 파일(작년·올해)을 각각 올리면 12개 완전월이 온전히 채워집니다. 재계산 시 월별 요약(그 달 사용 약품 수·총량·계산 구간 내 여부)도 `drug_usage_months`에 함께 저장해, 약품 DB 탭 상태 카드의 **월별 타일 시각화**(연도마다 한 행, 저장된 달 초록·빈 달 회색)에 사용합니다 — 원본 `drug_usage`를 매번 집계하지 않기 위한 요약 테이블입니다. 사용량 처리 실패는 약품 임포트 자체를 되돌리지 않고 결과에 에러로만 안내되며, 등록 현황(`GET /api/drug-master/status`)에 사용량 요약(약품 수·완전월 계산 구간·저장된 원본 데이터 범위·월별 타일)이 함께 표시됩니다.
- **약품 마스터 뷰어/편집(관리자)**: 약품 DB 탭에 페이지 단위 마스터 테이블 뷰어가 있습니다(`apps/local_app/master_db.py`). 약품명·보험코드 검색과 상태 필터(규격수집됨 `filled` / 규격미수집 `missing` / 보험코드없음 `nocode` / 자유입력 `manual`) + 페이지네이션으로 조회하고(`GET /api/drug-master/rows`), 각 행에 **월평균 사용량** 컬럼(위 사용량 임포트로 계산, 없으면 —)을 함께 표시하며, 크롤링으로 수집된 규격(`unit`)은 읽기 전용 칩으로만 보여줍니다. 사용자가 직접 입력한 규격은 `unit_manual`에 append-only로 추가하며(`POST /api/drug-master/manual-unit`, 중복 스킵), 자유입력(`source='manual'`) 행에 한해 이름 수정(`POST /api/drug-master/rename`, 중복·빈 이름 불가)·삭제(`POST /api/drug-master/delete`)가 가능합니다. 엑셀 임포트분(`source='excel'`)은 안전상 수정·삭제 대상이 아니며 엑셀 재업로드로 관리합니다.
- **규격(포장단위) 수집(관리자)**: 엑셀에는 규격 컬럼이 없으므로, 그 약국 `drug_master`에서 **보험코드가 있고 `unit`이 빈 행**을 기준 도매상(지오영·유팜몰)에 보험코드로 하나씩 검색해 결과의 규격을 채웁니다(`apps/local_app/unit_collector.py`). 도매상 사이트가 데이터센터 IP를 막기 때문에 **크롤링은 이 PC에서만** 돌고(루트 `scrapers/` 재사용, 기본 headless — `HEADLESS=false`로 창을 볼 수 있음) 결과만 Supabase `drug_master.unit`으로 write-back합니다(사용자가 직접 넣은 `unit_manual`과는 계속 분리). 한 보험코드가 여러 규격을 가질 수 있어 검색 결과의 distinct 규격을 모두 `", "`로 합쳐 저장하고, 같은 코드는 한 번만 검색하도록 캐싱합니다. 도매상에서 규격을 찾지 못한 약품은 `drug_master.unit_notfound_at`에 미발견 시각을 기록해 **미발견 보류** 처리하고 다음 수집의 기본 대상에서 제외합니다(매번 재검색하는 시간 낭비 방지) — 수집 시작 모달의 체크박스를 켜면 보류 약품도 다시 포함되고(`include_notfound`), 이후 규격을 찾으면 보류가 자동 해제됩니다. 대상 조회·저장은 `master_db.rows_missing_unit`/`set_unit`/`mark_unit_notfound`(페이지네이션·약국 스코프)이고, 수집이 오래 걸려 access token이 만료돼도 매번 **갱신된 클라이언트를 받아** 계속 씁니다.
- **규격 수집 실행/진행 표시**: 배치는 앱당 하나만 돕니다(단일 워커 스레드). `POST /api/drug-master/collect-units`로 시작해(계정 미설정이면 400, 이미 진행 중이면 409) 응답으로 완료 요약을 받고, `POST /api/drug-master/collect-units/stop`으로 다음 행 경계에서 중단합니다. 진행 상황은 **SSE**(`GET /api/drug-master/collect-units/stream`, 프론트는 `EventSource`, 유휴 시 keepalive 주석 전송)로 브로드캐스트되어 약품 DB 탭의 진행바·현재 항목에 실시간 표시되고 터미널에도 로그를 남기며(품절앱의 WebSocket 브로드캐스트와 대응되는 구조), 완료 시 상세 결과 모달(수집/미발견/실패 건수)로 안내합니다. 수집 현황(총계/수집됨/수집 대상/미발견 보류)은 `GET /api/drug-master/unit-stats`로 조회합니다. 약품 DB 탭 상단은 **상태(월별 타일) · 약품 DB 갱신 · 규격 수집**의 3열 요약 카드(4:3:3)로 구성되고, 상태 카드에는 갱신(새로고침) 버튼이 있습니다.
- **설정 탭 — 기준 도매상 계정**: 자동 주문 솔루션은 품절앱의 로컬 SQLite(`distributors` 테이블)를 쓰지 않으므로, 크롤링에 필요한 도매상 로그인 정보를 **이 PC의 `apps/local_app/.settings.json`**에 따로 보관합니다(`apps/local_app/settings.py`). 평문 파일이며 `.gitignore` 대상이고, **비밀번호는 Supabase(클라우드)로 올라가지 않습니다**. 설정 탭에서 기준 도매상(텍스트·보험코드 검색을 지원하는 지오영·유팜몰만 선택 가능)과 지역·아이디·비밀번호를 저장하며(`GET|POST /api/settings/distributor`), 조회 응답은 비밀번호 대신 설정 여부(`has_password`)만 내려보내고 저장 시 빈 비밀번호는 기존 값을 유지합니다. 지역 드롭다운 항목은 `scrapers/registry.py`의 `region_options`/`extra_params`에서 그대로 가져옵니다.
- **장바구니 담기는 예정**: 저장된 주문을 도매상 사이트 장바구니에 자동으로 담는 단계는 대상 도매상(바로팜 등)이 확정될 때까지 **의도적으로 보류**되어 있습니다. `orders_repo.py`에는 그 결과를 품목별 `cart_status`(`none`/`added`/`failed`)와 주문 `status='ordered'`로 write-back하는 스캐폴딩(`set_item_cart_status`·`mark_order_ordered`)만 준비되어 있습니다.

### 공유 백엔드 — Supabase (`supabase/`)

두 스택의 유일한 접점입니다. 스키마는 `supabase/migrations/`에 있습니다(`0001_autoorder_schema.sql` = 테이블+RLS+Storage, `0002_grants.sql` = 권한, `0003_multitenant.sql` = 멀티테넌트 전환: `pharmacies`/`memberships`/`invites` 추가 + 데이터 주인을 `user_id`→`pharmacy_id`로 바꾸고 RLS를 membership 기반으로 재작성, `0004_membership_view.sql` = 대시보드 전용 `membership_details` 뷰: 멤버십을 약국명·유저 이메일과 조인해 보기 쉽게 하되 이메일 노출을 막으려 `anon`/`authenticated` 권한은 회수하고 `service_role`에만 부여, `0005_drug_usage.sql` = 월별 약품 사용량 원본 `drug_usage` + 월평균 통계 `drug_usage_stats`, `0006_drug_usage_months.sql` = 월별 사용량 요약 `drug_usage_months`(약품 DB 탭 월별 타일 시각화용), `0007_unit_notfound.sql` = `drug_master.unit_notfound_at` 컬럼(규격 수집 미발견 보류)). 적용은 Supabase 대시보드 SQL Editor 붙여넣기 또는 `supabase db push`.

- **테넌트 테이블**: `pharmacies`(약국=테넌트), `memberships`(`(pharmacy_id, user_id)` 유니크, `role` admin|staff), `invites`(랜덤 `code` PK, `pharmacy_id`, `role`, `expires_at`/`max_uses`/`uses`).
- **데이터 테이블**: `orders`(`(pharmacy_id, order_date, order_round)` 유니크, `status`: `reviewing`→`pending`→`ordered`), `order_items`(`order_id` FK, `cart_status`·`position` 포함), `drug_master`(약국별 약품 마스터, 규격 수집 미발견 보류용 `unit_notfound_at` 포함), `drug_usage`(월별 사용량 원본, `(pharmacy_id, insurance_code, year, month)` 유니크) + `drug_usage_stats`(약품별 월평균, `(pharmacy_id, insurance_code)` 유니크) + `drug_usage_months`(월별 사용량 요약 — 그 달 약품 수·총량·계산 구간 내 여부, `(pharmacy_id, year, month)` 유니크). 모두 `pharmacy_id`를 가지며 **membership 기반 RLS로 약국별 격리**됩니다 — 헬퍼 `auth_pharmacy_ids()`·`auth_is_admin()`(`security definer`)로 소속 약국 데이터에만 접근합니다.
- **Storage**: 비공개 `order-images` 버킷, 경로 규칙 `<pharmacy_id>/<파일명>`으로 그 약국 소속 멤버만 접근합니다.
- **drug_master 이전**: 품절앱의 로컬 SQLite에 있던 약품 마스터를 `scripts/migrate_drug_master.py`로 Supabase `drug_master`에 옮깁니다(멱등 replace 방식).

### 배포

`apps/cloud_web/`은 Docker 이미지로 **Cloud Run**에 배포합니다(`apps/cloud_web/Dockerfile`, 로컬 Docker 없이 Cloud Build가 서버에서 빌드). 루트의 **`./deploy.sh` 한 줄**로 시크릿 동기화(`GEMINI_API_KEY`·`SUPABASE_SERVICE_KEY` → Secret Manager), 빌드·배포, 커스텀 도메인 매핑까지 처리합니다(프로젝트 `gen-lang-client-0011046539`, 리전 `asia-northeast1`, 서비스 `yak-order`, 도메인 `yak-order.chajjaem.dev`). 상세는 [apps/cloud_web/DEPLOY.md](apps/cloud_web/DEPLOY.md).

---

> 아래부터는 **품절약 서치앱**(로컬 SQLite + Playwright) 문서입니다.

## ✨ 주요 기능

- 🔍 **실시간 재고 검색**: 지오영, 백제약품, 인천약품, 지오팜, 복산, 유팜몰, HMP몰, 티제이팜 도매상 자동 로그인 및 재고 확인
- 🔎 **약품 미리보기 검색**: 약품 목록에 약품을 추가할 때 기준 도매상에 실시간으로 질의하여 약품명, 보험코드, 제약사, 규격, 재고를 즉시 조회 (세션 기반 브라우저 재사용으로 로그인 비용 절감)
- 🪟 **도매상 사이트 바로가기**: 재고 카드의 바로가기 아이콘을 클릭하면 headed 브라우저가 해당 도매상을 자동 로그인하고 약품 검색까지 마친 상태로 사용자에게 노출 (지원 도매상 전체)
- 🏠 **홈 화면 (앱 런처)**: 루트(`/`)에 여러 약국 업무 자동화 기능의 진입점을 모은 런처 화면. 현재 "품절 약 서치앱"이 활성화되어 있고, 나머지는 "새 기능 준비 중"(Coming Soon) placeholder 카드로 표시됩니다. (한때 이 앱에 있던 주문지 OCR·주문 기록·약품 DB 기능은 클라우드 **약국 주문 Agent**(자동 주문 솔루션, `apps/cloud_web/`)로 이전되었고, 당시 코드는 `legacy_codes/`에 보관되어 있습니다.) 자동 검색이 진행 중이면 카드에 "검색 중" 배지가 실시간 표시됩니다.
- 📱 **웹 인터페이스**: 실시간 WebSocket 업데이트가 포함된 웹 대시보드(`/checker`)
- 👁️ **결과 표시 제외 기능**: 도매상별로 독립적인 약품 결과 필터링 (검색은 계속 수행)
- 🔔 **스마트 알림**: 품절약 재고 발견시 알림 시스템 (날짜별 제외 관리)
- 📈 **진행 상황 추적**: 약품 검색 진행률 실시간 표시
- 🏗️ **모듈형 설계**: 레지스트리 패턴 기반의 확장 가능한 아키텍처
- 🎨 **도매상별 색상 구분**: 검색 결과 카드를 도매상별 색상으로 시각 구분, 색상 커스터마이징 지원
- ⚙️ **설정 관리**: 웹 UI를 통한 도매상 계정, 약품 목록, 결과 표시 제외 목록 관리
- 🔒 **안전한 스크래핑**: 팝업 자동 처리 및 안전한 요소 클릭 보장

## 🔗 지원 도매상 URL

각 도매상의 사이트 URL은 `scrapers/registry.py`의 `DISTRIBUTOR_REGISTRY`(`site_url` 필드)에서 관리됩니다.

| 도매상 | ID | URL |
|--------|----|-----|
| 지오영 | `geoweb` | https://order.geoweb.kr (지역별 상이, 아래 참고) |
| 백제약품 | `baekje` | https://www.ibjp.co.kr |
| 인천약품 | `incheon` | https://inchunpharm.com |
| 지오팜 | `geopharm` | https://orderpharm.geo-pharm.com |
| 복산 | `boksan` | https://wos.nicepharm.com |
| 유팜몰 | `upharmmall` | https://www.upharmmall.co.kr |
| HMP몰 | `hmpmall` | https://www.hmpmall.co.kr |
| 티제이팜 | `tjpharm` | https://tjp.co.kr |

위 URL은 `site_url` 필드(설정/약품목록 모달의 링크) 기준입니다. 일부 도매상은 지역별로 동작이 갈리는데, 그 방식이 서로 다릅니다.

- **지오영(geoweb)**: 지역마다 접속 도메인 자체가 다릅니다 (`REGION_URLS`, [scrapers/geoweb_scraper.py](scrapers/geoweb_scraper.py)).

  | 지역 | URL |
  |------|-----|
  | 서울·경기·인천 (`seoul`) | https://order.geoweb.kr |
  | 영남 (`yeongnam`) | https://bpm.geoweb.kr |
  | 대전 (`daejeon`) | https://djn.geoweb.kr |

- **지오팜(geopharm)**: URL은 동일하고, 로그인 시 지역코드만 선택합니다 (`daegu`/`daejeon`/`gwangju`/`seoul`).
- **HMP몰(hmpmall)**: URL은 동일하고, 검색 API의 `businessSidoCode` 파라미터로만 지역을 구분합니다 (`41`=경기, `47`=경북).

## 🛠️ 기술 스택

- **Backend**: FastAPI, Python 3.8+
- **Web Scraping**: Playwright (Chromium)
- **Frontend**: HTML5, CSS3, Vanilla JavaScript
- **Real-time Communication**: WebSocket
- **Data Storage**: SQLite (Python 표준 `sqlite3`, WAL 모드) — 약품 목록·결과 표시 제외 목록·도매상 자격증명·검색 세션/결과를 단일 `data/yak_soldout.db`에 통합 저장
- **Data Processing**: pandas, numpy
- **File Handling**: chardet (인코딩 자동 감지)

## 🚀 빠른 시작

**⚠️ 주의사항**: 이 시스템은 교육 및 약국 업무 효율성 향상 목적으로 개발되었습니다. 도매상 이용 약관을 준수하여 사용하시기 바랍니다.

### 1. 환경 설정

```bash
# 저장소 클론
git clone https://github.com/your-username/yak-soldout.git
cd yak-soldout

# 가상환경 생성 (권장)
python -m venv venv
uv venv

# 가상환경 활성화
# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate

# 의존성 설치
uv pip install -r apps/soldout/requirements.txt

# Playwright 브라우저 설치 (처음 실행 시 필수)
python -m playwright install chromium
```

### 2. 설정 파일 준비

`apps/soldout/` 디렉터리에 `config.json` 파일을 생성하세요 (형식은 아래 참고).

> **데이터 저장소(SQLite)**: 도매상 자격증명, 모니터링할 약품 목록, 결과 표시 제외 목록, 검색 세션/결과는 모두 `data/yak_soldout.db` (SQLite, `apps/soldout/data/`)에 저장됩니다. DB 파일과 스키마는 첫 실행 시 자동 생성되므로 직접 만들 필요가 없습니다. `config.json`은 이제 도매상 자격증명이 아닌 `monitoring` 설정만 보관합니다(도매상 자격증명/색상/지역은 DB의 `distributors` 테이블로 이전됨). 과거에 JSON 파일(`geoweb-soldout-list.json`, `exclusion-list.json`, `config.json`의 distributors)을 쓰던 환경이라면 첫 실행 시 해당 JSON이 DB로 자동 시딩(멱등)됩니다.

> **기존 info.txt 사용자**: 기존 `info.txt` 파일이 있으면 첫 실행 시 `config.json`으로 자동 마이그레이션됩니다. 원본은 `info.txt.bak`으로 백업됩니다.

`config.json` 파일 형식:
```json
{
  "distributors": {
    "geoweb": {
      "enabled": true,
      "username": "your_geoweb_username",
      "password": "your_geoweb_password",
      "color": "#0d9488",
      "region": "seoul"
    },
    "baekje": {
      "enabled": false,
      "username": "",
      "password": "",
      "color": "#3b82f6"
    },
    "upharmmall": {
      "enabled": false,
      "username": "",
      "password": "",
      "color": "#059669"
    },
    "hmpmall": {
      "enabled": false,
      "username": "",
      "password": "",
      "color": "#ea580c",
      "region": "41"
    },
    "tjpharm": {
      "enabled": false,
      "username": "",
      "password": "",
      "color": "#0891b2"
    }
  },
  "monitoring": {
    "repeat_interval_minutes": 30,
    "alert_exclusion_days": 7
  }
}
```

> **distributors 시딩**: `config.json`의 `distributors`는 첫 실행 시 DB의 `distributors` 테이블로 시딩되며(테이블이 비어 있을 때만), 이후에는 DB가 정본이 됩니다. 시딩 후 `config.json`에서 `distributors`는 제거되고 `monitoring`만 남습니다. 도매상 자격증명·색상·지역 변경은 웹 UI 설정 모달을 통해 DB에 저장됩니다.

> **color 필드**: 도매상 구분 색상입니다. 웹 UI의 도매상 설정 모달에서 변경할 수 있으며, 생략 시 레지스트리의 `default_color` 값이 사용됩니다.

> **region 필드**: 일부 도매상(지오영, 지오팜, HMP몰)은 지역별로 다른 서버를 사용합니다. 웹 UI의 도매상 설정 모달에서 드롭다운으로 선택할 수 있으며, 생략 시 레지스트리의 `extra_params` 기본값이 사용됩니다. 지오영은 `"seoul"` (서울/경기/인천), `"yeongnam"` (영남), `"daejeon"` (대전) 중 선택하며, 영남/대전 지역은 타센터 재고가 표시되지 않습니다. 지오팜은 `"daegu"`, `"daejeon"`, `"gwangju"`, `"seoul"` 중 선택, HMP몰은 `"41"` (경기) 또는 `"47"` (경북)을 선택합니다.

> **품절 약품 목록 / 결과 표시 제외 목록**: 모니터링할 약품 목록과 결과 표시 제외 목록은 모두 SQLite DB(`data/yak_soldout.db`의 `watch_list`·`exclusion_list` 테이블)에 저장되며 웹 인터페이스를 통해 관리합니다. 별도의 JSON 파일을 만들 필요가 없습니다. (과거 `geoweb-soldout-list.json`·`exclusion-list.json`을 사용하던 환경은 첫 실행 시 DB로 자동 시딩됩니다.)

### 3. 실행 방법

#### 🌐 웹 인터페이스 실행 (권장)

개발 환경에서는 `./dev_soldout_mac.sh` 한 줄로 실행하는 것을 권장합니다. 이 스크립트는 프로젝트 루트의 `.venv` 가상환경 파이썬을 사용하며, `PORT=8002`를 export하고 좀비 프로세스를 정리한 뒤 **`apps/soldout/`에서** `python web_server.py`를 실행합니다. (기본 포트는 **8002**입니다. 8000/8001은 다른 로컬 프로젝트와 충돌하기 때문입니다.)

```bash
# 개발 서버 시작 (권장)
./dev_soldout_mac.sh

# 또는 직접 실행
cd apps/soldout && python web_server.py

# 브라우저에서 접속
# http://localhost:8002

# 포트 변경이 필요한 경우 PORT 환경변수 사용
cd apps/soldout && PORT=3000 python web_server.py
```

> `run_app.py`는 PyInstaller 패키지 빌드용 진입점이며, 개발 시에는 위의 `./dev_soldout_mac.sh` 또는 `python web_server.py`를 사용하세요.

#### 🔍 디버그 모드 (브라우저 화면 보기)

브라우저 창을 보면서 실행하고 싶다면:

```bash
# 웹 인터페이스 디버그 모드 (apps/soldout/ 에서)
HEADLESS=false python web_server.py

# Windows에서는
set HEADLESS=false && python web_server.py

# 환경변수 조합 사용 가능
PORT=3000 HEADLESS=false python web_server.py
```

## 📁 프로젝트 구조

```
yak-soldout/                   # 모노레포 — 앱은 apps/ 아래, 공유 크롤러는 루트 scrapers/
├── dev_local_app_mac.sh       # 약국 주문 Agent 로컬 앱 실행 — macOS (apps/local_app, 포트 8770)
├── dev_local_app.bat          # └ 같은 앱 Windows용 — venv·의존성·Chromium 자동 설치
├── build_local_app.bat        # └ 같은 앱 배포 빌드 (PyInstaller → dist + ZIP, Windows 전용)
├── dev_soldout_mac.sh         # 품절약 서치앱 개발 실행 — macOS (apps/soldout, 포트 8002)
├── build_soldout.bat          # └ 품절약 서치앱 배포 빌드 (PyInstaller → dist + ZIP, Windows 전용)
├── deploy.sh                  # 약국 주문 Agent 웹(apps/cloud_web) Cloud Run 배포
│
├── apps/soldout/              # 품절약 서치앱 (로컬 SQLite)
│   ├── web_server.py          #   FastAPI 웹 서버 (개발 실행: ./dev_soldout_mac.sh)
│   ├── run_app.py             #   PyInstaller 배포 빌드용 진입점
│   ├── db.py                  #   SQLite 데이터 액세스 레이어 (data/yak_soldout.db)
│   ├── config.json            #   monitoring 설정 · build_config.json — 약국별 빌드 설정
│   ├── models/                #   config.py(ConfigManager), build_config.py(약국별 빌드 설정)
│   ├── utils/                 #   search_engine.py(검색 엔진 + PreviewSearchSession),
│   │                          #   open_site_session.py(바로가기 headed 세션), app_state.py,
│   │                          #   file_manager.py(목록 I/O), data_processor.py, notifications.py,
│   │                          #   websocket_manager.py
│   ├── templates/             #   home.html(홈 런처, GET /) · index.html(대시보드, GET /checker)
│   ├── static/                #   css/ · js/ (home.js = 홈, main.js = 대시보드, 모달별 js)
│   └── data/                  #   yak_soldout.db — 약품 목록·제외 목록·도매상·검색 세션/결과 (자동 생성)
├── apps/cloud_web/            # 약국 주문 Agent — 클라우드 웹 (Cloud Run + Supabase)
├── apps/local_app/            # 약국 주문 Agent — 로컬 관리자 앱 (PyWebView)
│
├── scrapers/                  # Playwright 기반 도매상 스크래퍼 — 두 앱이 공유하는 루트 패키지
│   ├── registry.py            # 도매상 레지스트리 — Single Source of Truth
│   ├── drug_data.py           # Drug, AppConfig, DistributorCredentials 데이터 클래스
│   ├── base_scraper.py        # 기본 스크래퍼 공통 기능
│   ├── browser_manager.py     # 브라우저 인스턴스 중앙 관리
│   ├── geoweb_scraper.py      # 지오영 스크래퍼
│   ├── baekje_scraper.py      # 백제약품 스크래퍼 (JWT 인증 + REST API 기반)
│   ├── incheon_scraper.py     # 인천약품 스크래퍼
│   ├── geopharm_scraper.py    # 지오팜 스크래퍼
│   ├── boksan_scraper.py      # 복산 스크래퍼
│   ├── upharmmall_scraper.py  # 유팜몰 스크래퍼
│   ├── hmpmall_scraper.py     # HMP몰 스크래퍼 (JSON API 기반 통합 플랫폼)
│   └── tjpharm_scraper.py     # 티제이팜 스크래퍼 (HTTP API 기반)
│
├── supabase/                  # 자동 주문 솔루션 공유 백엔드 스키마 (migrations/)
├── scripts/                   # 개발·검증·이전 스크립트 (migrate_drug_master.py, dev_smoke.py 등)
├── docs/                      # 기능 계획·설계 문서
│
└── legacy_codes/              # 품절앱에서 이전된 구 OCR/주문 기록/약품 DB 코드 아카이브
                               #   (utils/, templates/, static/, db_ocr_functions.py,
                               #    web_server_ocr_routes.py, analyze_units.py …)
                               #   → 해당 기능은 apps/cloud_web·apps/local_app 로 이전됨
```

## 🏗️ 아키텍처: 도매상 레지스트리

`scrapers/registry.py`의 `DISTRIBUTOR_REGISTRY`가 모든 도매상 메타데이터의 **Single Source of Truth**입니다. 이 딕셔너리 하나에 도매상 ID, 이름, 한국어 키, 스크래퍼 클래스, 기본 색상, 사이트 URL, 지역 옵션 등이 정의되어 있으며, 나머지 시스템(설정 파싱, 검색 엔진, API, 프론트엔드)은 모두 이 레지스트리를 참조해 동적으로 동작합니다. `build_config.json`이 존재하면 `get_visible_registry()` 함수가 빌드 설정에 따라 필터링된 레지스트리를 반환하여, 특정 약국에 불필요한 도매상을 숨길 수 있습니다. 단, 기준 도매상은 `build_config.json`에서 `0`으로 설정해도 항상 표시됩니다.

검색 결과 카드는 도매상별 색상으로 시각적으로 구분됩니다. 각 도매상에 `default_color`가 지정되어 있으며, 사용자가 웹 UI의 도매상 설정 모달에서 색상을 변경하면 `config.json`에 저장되어 기본 색상을 덮어씁니다.

일부 도매상은 지역별로 다른 서버를 사용합니다. `region_options`가 정의된 도매상(지오영, 지오팜, HMP몰)은 설정 모달에 지역 선택 드롭다운이 표시되며, 선택한 지역에 따라 스크래퍼가 해당 지역의 서버에 접속합니다. 기본 지역은 `extra_params`의 `region` 값으로 설정됩니다.

### 홈 화면과 세션 복원

루트 경로 `/`는 앱 런처 역할의 **홈 화면**(`templates/home.html`, `static/js/home.js`, `static/css/home.css`)이며, 품절 약 서치앱 대시보드는 `/checker`(`templates/index.html`)로 분리되어 있습니다. 대시보드 상단 브랜드를 누르면 홈으로 돌아갑니다.

- **keep-alive WebSocket**: 대시보드에서 홈으로 이동하면 대시보드의 WebSocket이 끊깁니다. 서버는 모든 WebSocket이 끊기면 "브라우저가 닫힘"으로 판단해 종료하므로, 홈 화면도 `/ws`로 keep-alive WebSocket을 열어 이를 방지합니다. 홈은 이 연결로 받은 `cycle_start`/`search_stopped` 메시지와 `/api/status`로 카드의 "검색 중" 배지를 갱신합니다.
- **로그 히스토리 버퍼**: `ConnectionManager`는 모든 WebSocket 메시지의 단일 통로인 `broadcast_message`에서 로그성 메시지(로그·사이클·검색 완료·긴급 알림 등)를 텍스트로 정규화해 `log_history` 버퍼(최근 300줄)에 누적합니다. 연결 수와 무관하게 누적되며 `GET /api/logs`로 조회, `POST /api/logs/clear`로 비울 수 있습니다.
- **세션 복원**: 홈 → 대시보드로 다시 진입하면 `main.js`가 `/api/logs`로 진행상황 로그를, `/api/status`의 `current_search`로 직전 완료 사이클의 재고/품절 결과 카드를 복원합니다. 사용자가 대시보드에서 로그를 지우면 서버 버퍼(`/api/logs/clear`)도 함께 비워 재진입 시 되살아나지 않습니다.
- **no-cache 미들웨어**: `web_server.py`는 정적 파일과 페이지(`/`, `/checker`)에 `Cache-Control: no-cache`를 강제하는 HTTP 미들웨어를 둡니다. `StaticFiles`가 `Cache-Control`을 생략해 브라우저가 옛 파일을 휴리스틱 캐싱하는 문제를 막기 위함이며, 변경이 없으면 304로 저렴하게 끝납니다.

반복 검색 모드에서는 한 사이클이 끝나도(`search_completed`) 검색이 계속 진행되므로, 대시보드의 액션 버튼은 명시적으로 중단하기 전까지 "검색 중단" 상태를 유지합니다.

### 기준 도매상 (Primary Distributor)

검색 엔진은 **기준 도매상**을 항상 먼저 검색하여 약품명 텍스트 검색을 수행하고, 그 결과에서 보험코드를 수집합니다. 나머지 도매상은 이 보험코드를 이용해 검색합니다. 기본적으로 지오영이 기준 도매상이며, `build_config.json`의 `primary_distributor` 설정으로 변경할 수 있습니다. 현재 텍스트 검색을 지원하는 도매상은 `geoweb`(지오영)과 `upharmmall`(유팜몰)이며, 이 외의 값이 설정되면 기본값인 `geoweb`으로 동작합니다.

개별 도매상 검색 중 오류가 발생하면 해당 도매상만 건너뛰고 나머지 도매상 검색을 계속 진행합니다.

### 약품 미리보기 검색 (Preview Search)

약품 목록 모달에서 약품을 추가할 때, 사용자가 입력한 키워드를 **기준 도매상**에 실시간으로 질의하여 후보 약품들의 약품명·보험코드·제약사·규격·현재 재고를 제공하는 기능입니다. 정확한 약품명으로 목록에 등록하도록 돕고, 실수로 잘못된 이름을 추가하는 것을 방지합니다.

`utils/search_engine.py`의 `PreviewSearchSession` 클래스가 이 기능을 담당하며, 브라우저/로그인 세션을 프로세스 수명 동안 유지하여 연속 질의에서 로그인 비용을 발생시키지 않습니다. 메인 검색, 미리보기, 바로가기는 각기 독립된 브라우저 세션을 사용하므로 서로 차단하지 않고 동시에 실행할 수 있습니다.

### 도매상 사이트 바로가기 (Open Site)

재고 카드 우측의 바로가기 아이콘을 누르면, 해당 도매상 사이트를 자동 로그인하고 약품 검색까지 마친 상태의 브라우저 창이 사용자에게 노출됩니다. 사용자는 그 창에서 실제 주문/상세 조회 등을 이어서 수행할 수 있습니다.

`utils/open_site_session.py`의 `OpenSiteSession` 클래스가 동시 1개의 headed 브라우저 세션을 관리합니다. 로그인·검색이 끝나기 전에는 창을 작은 크기(또는 Windows의 경우 minimized)로 띄워 사용자의 작업을 방해하지 않고, 준비가 끝나면 CDP `Browser.setWindowBounds`로 1280×800 중앙 위치로 창을 드러냅니다. 사용자가 창을 닫거나 `IDLE_TIMEOUT`(기본 10분)이 경과하면 워치독이 세션을 자동 정리합니다.

바로가기 지원 여부는 `scrapers/registry.py`의 각 도매상 항목의 `supports_open_site` 플래그로 결정됩니다. `True`면 카드에 바로가기 버튼이 표시됩니다. 현재 등록된 8개 도매상(지오영·백제약품·인천약품·지오팜·복산·유팜몰·HMP몰·티제이팜)은 모두 `True`입니다.

각 스크래퍼는 `BaseScraper.open_for_user_interaction(query, original_drug_name)`를 override하여 "검색 실행까지만" 수행하고 결과 파싱은 하지 않습니다. 공통 후처리 `_wait_search_settled(<결과 셀렉터>)`로 DOM 렌더링과 networkidle까지 대기해 UX 일관성을 확보합니다. 도매상별 검색창·결과 셀렉터는 스크래퍼 내부에 정의되어 있으며(예: 지오팜 `#item_name` + iframe 응답, 인천약품 `#tx_insucd`, 복산 `#tx_physic`, 백제 Quasar SPA 검색창 + Enter, 티제이팜 `#search_name_2` + `#table_id_1`), 플랫폼 구조에 맞게 각자 구현됩니다.

프론트엔드는 WebSocket으로 스트리밍되는 재고 카드의 `insurance_code`를 바로가기 쿼리로 사용합니다. 보험코드가 비어 있으면 약품명을 대신 사용합니다.

### 이전된 기능: 주문지 OCR · 주문 기록 · 약품 DB

과거 이 앱에 있던 손글씨 주문지 OCR, 주문 기록(달력 조회), 약품 DB(약품 마스터) 관리, OCR 약품명 오타 보정 기능은 **자동 주문 솔루션**(클라우드 웹 `apps/cloud_web/` + 로컬 관리자 앱 `apps/local_app/`)으로 이전되었습니다. 상세 동작은 문서 앞부분의 "저장소 구성 — 두 개의 독립 앱" 섹션을 참고하세요. 당시 구현 코드(라우트·템플릿·유틸)는 `legacy_codes/`에 아카이브되어 있습니다. 품절앱의 로컬 SQLite에 남아 있던 약품 마스터는 `scripts/migrate_drug_master.py`로 Supabase `drug_master`에 이전할 수 있습니다.

### HMP몰: 통합 플랫폼 스크래퍼

HMP몰(hmpmall.co.kr)은 ~20개 입점 도매상의 재고를 통합 검색하는 플랫폼으로, 기존 도매상 스크래퍼와는 동작 방식이 다릅니다.

- **JSON API 기반**: DOM 파싱 대신 `SearchProductSellerListJson.do` API를 호출하여 안정적으로 데이터를 조회합니다.
- **검색 흐름**: 보험코드 검색 -> HTML에서 `productMasterId` 추출 -> JSON API로 도매상별 재고 조회
- **재고 합산 로직**: 모든 입점 도매상의 `stockQuantity`를 합산하며, 전부 0일 때만 품절로 처리합니다. 검색 결과 카드에 "N/M 업체 재고 합산" 형태로 몇 개 도매상에 재고가 있는지 표시됩니다.
- **지역 필터링**: `businessSidoCode` 파라미터로 지역별 도매상을 필터링합니다 (`41`=경기, `47`=경북).

```python
# scrapers/registry.py
DISTRIBUTOR_REGISTRY = {
    "geoweb": {
        "id": "geoweb",
        "name": "지오영",
        "korean_key": "지오영",       # 한국어 표시명 prefix
        "scraper_class": GeowebScraper,
        "default_enabled": True,
        "default_color": "#0d9488",   # 도매상 구분 색상 (카드 보더, 배경 틴트, 배지에 적용)
        "site_url": "https://order.geoweb.kr",  # 도매상 사이트 URL (설정/약품목록 모달에서 링크로 표시)
        "extra_params": {"region": "seoul"},   # 기본 지역 설정
        "region_options": {                    # 도매상 설정 모달에 드롭다운으로 표시
            "seoul": "서울, 경기, 인천",
            "yeongnam": "영남",
            "daejeon": "대전",
        },
        "supports_open_site": True,            # 재고 카드 바로가기 지원 여부
    },
    # ... 나머지 도매상
}
```

## 🔧 고급 설정

### 검색 간격 및 결과 표시 제외 설정

설정은 `config.json`의 `monitoring` 섹션에서 수정할 수 있습니다:

- `repeat_interval_minutes`: 검색 반복 간격 (분)
- `alert_exclusion_days`: 결과 표시 제외 기간 (일) - 고정하지 않은 항목이 자동 삭제되는 기간

### 약국별 빌드 설정 (build_config.json)

특정 약국에 배포할 때 표시할 도매상을 제한하고 약국 이름을 설정할 수 있습니다. 이 파일은 **선택사항**이며, 파일이 없으면 전체 도매상이 표시됩니다 (개발 환경 호환).

```bash
# 예시 파일을 복사하여 생성
cp apps/soldout/build_config.example.json apps/soldout/build_config.json
```

```json
{
  "pharmacy_name": "가나안약국",
  "primary_distributor": "geoweb",
  "distributors": {
    "geoweb": 1,
    "baekje": 0,
    "incheon": 0,
    "boksan": 0,
    "geopharm": 1,
    "upharmmall": 1,
    "hmpmall": 1,
    "tjpharm": 1
  }
}
```

- **pharmacy_name**: 웹 인터페이스 헤더에 "for XXX약국" 형태로 표시됩니다. 생략하면 표시되지 않습니다.
- **primary_distributor**: 기준 도매상 ID (`"geoweb"` 또는 `"upharmmall"`). 생략하면 기본값 `"geoweb"`이 사용됩니다. 기준 도매상은 `distributors`에서 `0`으로 설정해도 항상 표시됩니다.
- **distributors**: 각 도매상의 표시 여부를 `1`(표시) 또는 `0`(숨김)으로 설정합니다. 누락된 도매상은 기본 표시(1)로 처리됩니다. `0`으로 설정된 도매상은 UI, 설정, 검색에서 완전히 제외됩니다.

PyInstaller로 빌드할 때 `build_config.json`이 번들에 포함되어, 약국별로 맞춤 배포가 가능합니다.

## 📊 데이터 저장 (SQLite)

애플리케이션 데이터는 단일 SQLite 파일 `data/yak_soldout.db`(`apps/soldout/data/`)에 통합 저장됩니다. DB 파일·스키마는 첫 실행 시 자동 생성되며, 데이터 액세스 레이어는 `apps/soldout/db.py`가 담당합니다.

- **동시성**: FastAPI 라우트(asyncio)와 백그라운드 검색 스레드(ThreadPoolExecutor)가 동시에 접근하므로, WAL 저널 모드 + `busy_timeout` + 스레드별 연결(thread-local)로 read/write 충돌을 회피합니다.
- **스키마 버전 관리**: `PRAGMA user_version` 값으로 스키마 버전을 추적하며, 구버전 DB는 시작 시 자동 마이그레이션합니다. (OCR 기능과 함께 쓰이던 `drug_master`/`orders` 테이블 관련 마이그레이션은 기능 이전 후에도 구버전 DB 호환을 위해 남아 있습니다.)
- **JSON → DB 시딩**: 과거 JSON 파일(`geoweb-soldout-list.json`, `exclusion-list.json`, `config.json`의 `distributors`)이 있으면 첫 실행 시 DB로 시딩합니다. 멱등(대상 테이블이 비어 있을 때만 시딩)이라 반복 실행해도 중복되지 않습니다.

### 테이블

- **watch_list**: 모니터링할 품절 약품 목록 (약품명·긴급 알림 여부·추가일시). 웹 UI로 관리.
- **exclusion_list**: 결과 표시 제외 목록 — 도매상별로 독립 관리(`(drug_name, distributor)` 유니크). 웹에서 약품 카드의 눈 모양 아이콘(👁️‍🗨️)으로 추가하며, 백제약품은 규격 정보까지 포함해 정확히 매칭합니다.
- **distributors**: 도매상 자격증명·활성화 여부·색상·지역. 웹 설정 모달로 관리.
- **search_sessions / search_results**: 검색 사이클(시작 시각·소요·상태)과 그 결과(약품별 재고/품절·도매상별 행)를 영속화합니다.

> **config.json**: 이제 도매상 자격증명이 아닌 `monitoring` 설정(`repeat_interval_minutes`, `alert_exclusion_days`)만 보관합니다. 도매상 자격증명·색상·지역은 `distributors` 테이블로 이전되었습니다.

## 🔌 API 엔드포인트

### REST API
- `GET /` - 홈 화면 (앱 런처)
- `GET /checker` - 품절 약 서치앱 대시보드
- `GET /api/status` - 현재 상태 조회
- `POST /api/search/start` - 검색 시작
- `POST /api/search/stop` - 검색 중단
- `GET /api/logs` - 진행상황 로그 히스토리 조회 (페이지 재진입 시 복원용)
- `POST /api/logs/clear` - 진행상황 로그 히스토리 비우기
- `GET /api/distributor-settings` - 도매상 설정 조회
- `PUT /api/distributor-settings` - 도매상 설정 업데이트
- `GET /api/drug-list` - 약품 목록 조회
- `PUT /api/drug-list` - 약품 목록 업데이트
- `GET /api/exclusion-list` - 결과 표시 제외 목록 조회
- `PUT /api/exclusion-list` - 결과 표시 제외 목록 업데이트
- `POST /api/exclusion-add` - 개별 약품을 결과 표시 제외 목록에 추가
- `PUT /api/drug-urgent-toggle` - 약품의 긴급 알림 여부 토글
- `GET /api/system-settings` - 시스템 설정 조회 (검색 반복 간격 등)
- `PUT /api/system-settings` - 시스템 설정 업데이트
- `GET /api/build-info` - 빌드 정보 조회 (약국명, 기준 도매상명 등)
- `POST /api/preview-search` - 약품 미리보기 검색 (기준 도매상에 실시간 질의)
- `POST /api/preview-search/close` - 미리보기 검색 세션 브라우저 종료
- `POST /api/open-distributor-site` - 도매상 사이트 바로가기 (headed 브라우저 자동 로그인+검색)
- `POST /api/open-distributor-site/close` - 바로가기 세션 수동 종료

### WebSocket
- `WS /ws` - 실시간 로그 스트리밍 및 검색 진행 상황 업데이트

## 🔄 개발 가이드

### 새로운 도매상 추가하기

레지스트리 패턴 덕분에 새 도매상 추가 시 수정해야 할 파일이 최소화되어 있습니다.

**1단계**: `DistributorType` enum에 추가 (`scrapers/drug_data.py`)

```python
class DistributorType(Enum):
    # ... 기존 항목 ...
    NEWDIST = "신규도매상명"  # 추가
```

**2단계**: 레지스트리에 항목 추가 (`scrapers/registry.py`)

```python
"newdist": {
    "id": "newdist",
    "name": "신규도매상명",
    "korean_key": "신규도매상",    # 한국어 표시명 prefix
    "scraper_class": NewDistScraper,
    "default_enabled": False,
    "default_color": "#059669",    # 도매상 구분 색상
    "site_url": "https://example.com",  # 도매상 사이트 URL
    "extra_params": {},
    "supports_open_site": False,   # 바로가기 지원 시 True + scraper에 open_for_user_interaction 구현
},
```

**3단계**: 스크래퍼 파일 생성 (`scrapers/newdist_scraper.py`) — `BaseScraper` 상속 후 `login()`, `search_by_insurance_codes()` 등 구현

**4단계**: 도매상 자격증명 입력

레지스트리에 항목이 추가되면 웹 UI 설정 모달에 신규 도매상이 자동으로 나타납니다. 여기서 자격증명을 입력하면 DB의 `distributors` 테이블에 저장됩니다. (초기 시딩이 필요하면 `config.json`의 `distributors`에 항목을 넣어두면 첫 실행 시 DB로 시딩됩니다.)

이 단계만으로 웹 UI, 검색 엔진, 설정 파싱, API 응답이 모두 자동으로 신규 도매상을 지원합니다.

### 프론트엔드 수정하기
- CSS: `apps/soldout/static/css/` 디렉터리의 기능별 파일 수정
- JavaScript: `apps/soldout/static/js/` 디렉터리의 모듈별 파일 수정 (`home.js` = 홈 화면, `main.js` = 대시보드)
- HTML: 홈 화면은 `apps/soldout/templates/home.html`, 대시보드는 `apps/soldout/templates/index.html` 수정

## 🐛 문제 해결

### 브라우저 설치 문제

```bash
# Playwright 브라우저 재설치
python -m playwright install chromium --force

# 시스템 의존성 설치 (Ubuntu/Debian)
sudo python -m playwright install-deps chromium
```
