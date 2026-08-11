# 🏥 약품 재고 자동 검색 시스템 (yak-soldout)

> 약국을 위한 도매상 품절 약품 자동 모니터링 시스템

주요 의약품 도매상(지오영, 백제약품, 인천약품, 지오팜, 복산, 유팜몰, HMP몰, 티제이팜)에서 품절된 약품의 재고 상황을 자동으로 모니터링하고 실시간으로 알림을 제공하는 시스템입니다.

FastAPI 기반의 웹 인터페이스와 Playwright를 활용한 안정적인 웹 자동화 기술을 사용하며, 레지스트리 패턴으로 도매상을 손쉽게 추가할 수 있는 확장형 아키텍처를 갖추고 있습니다.

## 🗂️ 저장소 구성 — 두 개의 독립 앱

이 저장소는 이제 **서로 독립적인 두 개의 앱**을 담고 있으며, 둘은 오직 **Supabase**를 통해서만 만납니다.

- **품절약 서치앱** — *이 README의 주 대상.* 도매상 품절 약품을 모니터링하는 로컬 앱입니다. 로컬 SQLite(`data/yak_soldout.db`) + Playwright 기반이며 **로컬 전용**으로 유지됩니다(Supabase를 쓰지 않습니다). 아래 [주요 기능](#-주요-기능) 이하 문서 전체가 이 앱을 설명합니다.
- **자동 주문 솔루션** — 손글씨 주문지를 OCR로 읽어 검수·저장하고, 저장된 주문을 자동으로 도매상 장바구니에 담는 것을 목표로 하는 **신규 앱**입니다. 데이터는 전적으로 **Supabase**(Postgres + Auth + Storage)에 두며, 두 개의 스택으로 나뉩니다.

두 앱은 코드·프로세스·저장소가 분리되어 있고, 공유하는 것은 Supabase 데이터(특히 `drug_master`)뿐입니다. 품절앱의 로컬 SQLite는 건드리지 않습니다.

> 전체 설계: [주문-자동화-워크플로우-구현-계획.md](주문-자동화-워크플로우-구현-계획.md)

### 디렉터리 맵 (자동 주문 솔루션)

```
cloud_web/     # 스택 1 — Cloud Run 웹 UI (FastAPI). 업로드→OCR(또는 직접 작성)→매칭→검수→Supabase 저장 + 주문 기록 조회
local_app/     # 스택 2 — 로컬 PyWebView+FastAPI 관리자 앱. pending 주문 조회 + 약품 마스터 엑셀 임포트/뷰어 (크롤링·규격수집은 예정)
supabase/      # 공유 백엔드 스키마 (migrations/: 0001 스키마+RLS+Storage, 0002 grants, 0003 멀티테넌트 전환, 0004 멤버십 조회 뷰)
scripts/       # 개발·검증·이전 스크립트 (migrate_drug_master.py, dev_smoke.py 등)
deploy.sh      # 스택 1을 Cloud Run에 한 줄로 배포
```

각 폴더에 자체 README가 있습니다 — [cloud_web/README.md](cloud_web/README.md), [cloud_web/DEPLOY.md](cloud_web/DEPLOY.md), [supabase/README.md](supabase/README.md).

### 멀티테넌트 모델 (약국 = 테넌트)

자동 주문 솔루션의 데이터 주인은 개인 사용자가 아니라 **약국(pharmacy)**입니다. 약국 1곳이 하나의 테넌트이며, 사용자는 `memberships`로 약국에 소속되고(역할 `admin`|`staff`), 소속을 통해서만 그 약국의 `orders`·`drug_master`·주문 이미지에 접근합니다. 격리는 애플리케이션 코드가 아니라 **Supabase RLS**로 물리적으로 강제됩니다(`supabase/migrations/0003_multitenant.sql`).

- **역할(role)**: `admin`은 약국을 부트스트랩하고 직원 초대코드를 발행하며(로컬 크롤링·엑셀 마스터 관리도 관리자 몫), `staff`는 초대로 합류해 업로드·OCR·검수·저장을 수행합니다.
- **초대 기반 합류**: 관리자가 발행한 초대코드(`invites` 테이블, 추측 불가능한 랜덤 코드)를 직원이 Google 로그인 후 `POST /api/accept-invite`로 redeem하면 `memberships` 행이 생겨 합류됩니다. 관리자는 앱 상단의 "직원 초대" 버튼으로 초대 링크(`/?invite=CODE`)를 만들며, 그 링크로 들어온 사용자는 로그인 직후 자동 합류합니다.
- **membership 기반 RLS**: 모든 정책이 `security definer` 헬퍼 함수 `auth_pharmacy_ids()`(내가 속한 약국 id 집합)와 `auth_is_admin(pharmacy_id)`를 기준으로 동작합니다. `orders`/`order_items`/`drug_master`/`pharmacies`/Storage 객체는 내가 속한 약국 것만 CRUD할 수 있고, `invites`는 그 약국 admin만 관리합니다. 멤버십·초대의 쓰기는 RLS로 막혀 있어, 서버가 JWT를 검증한 뒤 **service_role**로만 수행합니다(`cloud_web/tenant_repo.py`).
- **초기 셋업**: 0003 마이그레이션은 (폐기 가능 전제로) 기존 `user_id` 기반 `orders`/`drug_master` 데이터를 비우고 스키마를 `pharmacy_id` 기준으로 전환합니다. 적용 후 약국(`pharmacies`) 1행과 관리자 멤버십(`memberships`, `role='admin'`)을 만들고, `drug_master`는 로컬 앱의 관리자 엑셀 임포트로 채웁니다.

### 스택 1 — Cloud Run 웹 UI (`cloud_web/`)

약국 직원이 브라우저에서 주문지를 처리하는 경량 FastAPI 앱입니다. **Playwright를 포함하지 않고**(경량), 스테이트리스이며 `$PORT`에 바인딩해 **Google Cloud Run**에 배포됩니다. 데이터 흐름:

1. **Google 로그인 + 약국 소속 확인**(Supabase Auth) — 브라우저의 `supabase-js`가 로그인해 발급한 JWT를 `Authorization: Bearer`로 백엔드에 전달합니다. 로그인 직후 프론트는 `GET /api/me`로 소속(멤버십)을 확인해 **세 상태**(로그인 / 초대코드 합류 / 앱)로 분기합니다 — 소속이 없으면 초대코드 입력 화면이 뜨고, 소속이 있어야 OCR·저장 등 데이터 API를 쓸 수 있습니다(서버 `_require_membership` 게이트, 소속 없으면 403). 백엔드는 그 토큰으로 만든 사용자 스코프 클라이언트에 **membership 기반 RLS**를 적용하며, 멤버십 조회는 짧게 TTL 캐시합니다(`cloud_web/app.py`, `tenant_repo.py`).
2. **입력 방식 — 사진(OCR) / 직접 작성** — 상단 토글로 두 방식 중 고릅니다. *사진으로 읽기*는 업로드한 이미지를 Gemini 멀티모달로 약품명·포장단위·수량을 추출하고(`cloud_web/ocr_service.py`, 품절앱 `utils/ocr_service.py`를 자체 완결 사본으로 이식), *직접 작성*은 업로드·이미지 없이 빈 검수 테이블을 바로 열어 약품명 자동완성(`/api/drug-search`)으로 손으로 입력합니다(이미지 없이 저장).
3. **약품명 오타 보정** — 그 약국의 `drug_master`(Supabase)로 한글 자모 fuzzy 매칭을 수행해 검수 테이블에 결과를 붙입니다(`cloud_web/drug_matcher.py` + `master_repo.py`, 품절앱 `utils/drug_matcher.py`에서 이식). 매칭 인덱스는 **약국(`pharmacy_id`)별로** TTL 캐시합니다.
4. **검수·수정 UI** — `static/index.html` + `static/js/order-ocr.js`(품절앱 CSS 재사용), 타이핑 자동완성(`/api/drug-search`)으로 마스터 후보를 제시합니다.
5. **Supabase 저장** — 검수본을 `orders`/`order_items`(`status='pending'`)로, 원본 이미지를 Supabase Storage(`order-images/<pharmacy_id>/…`)로 저장합니다(`cloud_web/orders_repo.py`). 저장 경로는 JWT를 GoTrue로 검증해 사용자를 얻고 소속 약국을 확인한 뒤, **service_role 키**로 서버가 그 `pharmacy_id` 스코프로 신뢰 기록합니다. 같은 `(pharmacy_id, 날짜, 차수)`가 이미 있으면 409를 반환합니다.
6. **주문 기록 조회** — 상단 바의 "주문 기록" 토글로 주문 작성 화면과 **주문 기록** 목록을 오갑니다. 목록은 그 약국의 저장된 주문을 품목과 함께 최신순으로 보여주며(`GET /api/orders`, RLS로 소속 약국만), 각 주문은 접기/펼치기로 품목 테이블을 열고 상태 배지(크롤링 대기 `pending` / 주문완료 `ordered`)를 표시합니다.

주요 엔드포인트: `GET /api/healthz` · `GET /api/config`(브라우저 supabase-js 초기화용 공개 설정) · `GET /api/me`(소속 조회) · `GET /api/orders`(주문 기록) · `POST /api/accept-invite`(초대코드로 합류) · `POST /api/invites`(관리자 전용 초대코드 발행) · `POST /api/ocr` · `GET /api/drug-search` · `POST /api/save` · `POST /api/preview`(HEIC 등 미리보기용 JPEG 변환).

### 스택 2 — 로컬 관리자 앱 (`local_app/`)

약국 **관리자**가 데스크톱에서 실행하는 **PyWebView + FastAPI** 앱입니다(`local_app/main.py`가 진입점 — `uvicorn`으로 로컬 서버를 포트 `8770`에 띄우고 PyWebView 창으로 그 UI를 엽니다). 로컬 SQLite가 아니라 **anon key + 로그인한 관리자 세션**으로 Supabase에 접속하며(RLS 적용, service 키는 두지 않습니다), 현재 두 가지 기능을 제공합니다: (1) 약국의 `pending` 주문 조회, (2) 약품 마스터 엑셀 임포트 + 뷰어/편집. 실행: `uv run python local_app/main.py`(브라우저 테스트만 하려면 `uv run uvicorn app:app --port 8770`).

- **관리자 전용**: 직원(`staff`)도 로그인은 되지만 "관리자 전용" 안내 화면만 보게 되며, `/api/pending-orders`와 `/api/drug-master/*`는 서버에서 `role == 'admin'`을 강제합니다(`_require_admin`, 소속 없으면 403).
- **Google OAuth (시스템 브라우저 + loopback)**: Google 정책상 임베디드 웹뷰에서 OAuth가 막히므로, PyWebView JS 브릿지(`Api.start_login`)가 로그인을 **시스템 브라우저**로 엽니다(RFC 8252). 브라우저의 `/auth/start`가 `supabase-js`로 Google 로그인을 시작하고, `http://localhost:8770/auth/callback`(loopback)로 돌아와 `?code=`를 세션으로 교환한 뒤 그 토큰을 로컬 서버 `/auth/store`로 전달합니다. 서버는 **refresh token만** `local_app/.session.json`에 보관하고 access token은 메모리에 캐시하다 만료 시 자동 갱신하며(Supabase가 refresh를 회전), 그 사용자 세션을 실은 클라이언트로 RLS 스코프 읽기를 수행합니다(`local_app/app.py`).
- **pending 주문 조회**: 웹(스택 1)이 저장한 `status='pending'` 주문을 품목과 함께 오래된 순으로 읽어 창에 표시합니다(`GET /api/pending-orders`, `local_app/orders_repo.py`). 품목은 OCR 추출 순서(`position`)로 정렬됩니다. 이것이 웹→Supabase→로컬로 이어지는 주문 파이프라인의 로컬 끝단입니다.
- **약품 마스터 엑셀 임포트(관리자)**: `drug_master`를 채우는 경로입니다. 엑셀 업로드 → 미리보기(머리글 행 자동추정 + 약품명·보험코드·제약사 컬럼 자동 제안, `POST /api/drug-master/preview`) → 임포트(`POST /api/drug-master/import`)로, 그 약국(`pharmacy_id`) 스코프의 마스터를 **전체 교체**합니다. 단 크롤링으로 채운 규격(`unit`/`unit_manual`)은 `(약품명, 보험코드)` 매칭으로 보존합니다. 엑셀 파싱 로직은 품절앱 `utils/drug_master.py`에서 이식했습니다(`local_app/master_import.py`). 등록 현황은 `GET /api/drug-master/status`로 조회합니다.
- **약품 마스터 뷰어/편집(관리자)**: 약품 DB 탭에 페이지 단위 마스터 테이블 뷰어가 있습니다(`local_app/master_db.py`). 약품명·보험코드 검색과 상태 필터(규격수집됨 `filled` / 규격미수집 `missing` / 보험코드없음 `nocode` / 자유입력 `manual`) + 페이지네이션으로 조회하고(`GET /api/drug-master/rows`), 크롤링으로 수집된 규격(`unit`)은 읽기 전용 칩으로만 보여줍니다. 사용자가 직접 입력한 규격은 `unit_manual`에 append-only로 추가하며(`POST /api/drug-master/manual-unit`, 중복 스킵), 자유입력(`source='manual'`) 행에 한해 이름 수정(`POST /api/drug-master/rename`, 중복·빈 이름 불가)·삭제(`POST /api/drug-master/delete`)가 가능합니다. 엑셀 임포트분(`source='excel'`)은 안전상 수정·삭제 대상이 아니며 엑셀 재업로드로 관리합니다.
- **크롤링·규격수집은 예정**: 도매상 사이트 자동 로그인·장바구니 담기와 보험코드 기반 규격 일괄 수집(규격수집)은 대상 도매상(바로팜 등)이 확정될 때까지 **의도적으로 보류**되어 있습니다. 그래서 위 뷰어의 `unit`은 읽기 전용이고, 직접추가(`unit_manual`)만 가능합니다. `orders_repo.py`에는 크롤링 결과를 품목별 `cart_status`(`none`/`added`/`failed`)와 주문 `status='ordered'`로 write-back하는 스캐폴딩(`set_item_cart_status`·`mark_order_ordered`)만 준비되어 있습니다.

### 공유 백엔드 — Supabase (`supabase/`)

두 스택의 유일한 접점입니다. 스키마는 `supabase/migrations/`에 있습니다(`0001_autoorder_schema.sql` = 테이블+RLS+Storage, `0002_grants.sql` = 권한, `0003_multitenant.sql` = 멀티테넌트 전환: `pharmacies`/`memberships`/`invites` 추가 + 데이터 주인을 `user_id`→`pharmacy_id`로 바꾸고 RLS를 membership 기반으로 재작성, `0004_membership_view.sql` = 대시보드 전용 `membership_details` 뷰: 멤버십을 약국명·유저 이메일과 조인해 보기 쉽게 하되 이메일 노출을 막으려 `anon`/`authenticated` 권한은 회수하고 `service_role`에만 부여). 적용은 Supabase 대시보드 SQL Editor 붙여넣기 또는 `supabase db push`.

- **테넌트 테이블**: `pharmacies`(약국=테넌트), `memberships`(`(pharmacy_id, user_id)` 유니크, `role` admin|staff), `invites`(랜덤 `code` PK, `pharmacy_id`, `role`, `expires_at`/`max_uses`/`uses`).
- **데이터 테이블**: `orders`(`(pharmacy_id, order_date, order_round)` 유니크, `status`: `reviewing`→`pending`→`ordered`), `order_items`(`order_id` FK, `cart_status`·`position` 포함), `drug_master`(약국별 약품 마스터). 모두 `pharmacy_id`를 가지며 **membership 기반 RLS로 약국별 격리**됩니다 — 헬퍼 `auth_pharmacy_ids()`·`auth_is_admin()`(`security definer`)로 소속 약국 데이터에만 접근합니다.
- **Storage**: 비공개 `order-images` 버킷, 경로 규칙 `<pharmacy_id>/<파일명>`으로 그 약국 소속 멤버만 접근합니다.
- **drug_master 이전**: 품절앱의 로컬 SQLite에 있던 약품 마스터를 `scripts/migrate_drug_master.py`로 Supabase `drug_master`에 옮깁니다(멱등 replace 방식).

### 배포

`cloud_web/`은 Docker 이미지로 **Cloud Run**에 배포합니다(`cloud_web/Dockerfile`, 로컬 Docker 없이 Cloud Build가 서버에서 빌드). 루트의 **`./deploy.sh` 한 줄**로 시크릿 동기화(`GEMINI_API_KEY`·`SUPABASE_SERVICE_KEY` → Secret Manager), 빌드·배포, 커스텀 도메인 매핑까지 처리합니다(프로젝트 `gen-lang-client-0011046539`, 리전 `asia-northeast1`, 서비스 `yak-order`, 도메인 `yak-order.chajjaem.dev`). 상세는 [cloud_web/DEPLOY.md](cloud_web/DEPLOY.md).

---

> 아래부터는 **품절약 서치앱**(로컬 SQLite + Playwright) 문서입니다.

## ✨ 주요 기능

- 🔍 **실시간 재고 검색**: 지오영, 백제약품, 인천약품, 지오팜, 복산, 유팜몰, HMP몰, 티제이팜 도매상 자동 로그인 및 재고 확인
- 🔎 **약품 미리보기 검색**: 약품 목록에 약품을 추가할 때 기준 도매상에 실시간으로 질의하여 약품명, 보험코드, 제약사, 규격, 재고를 즉시 조회 (세션 기반 브라우저 재사용으로 로그인 비용 절감)
- 🪟 **도매상 사이트 바로가기**: 재고 카드의 바로가기 아이콘을 클릭하면 headed 브라우저가 해당 도매상을 자동 로그인하고 약품 검색까지 마친 상태로 사용자에게 노출 (지원 도매상 전체)
- 🏠 **홈 화면 (앱 런처)**: 루트(`/`)에 여러 약국 업무 자동화 기능의 진입점을 모은 런처 화면. 현재 "품절 약 서치앱", "주문지 OCR"이 활성화되어 있고, 나머지는 "새 기능 준비 중"(Coming Soon) placeholder 카드로 표시됩니다. (주문 기록은 별도 최상위 카드가 아니라 주문지 OCR의 하위 화면입니다 — 아래 참고.) 자동 검색이 진행 중이면 카드에 "검색 중" 배지가 실시간 표시됩니다.
- ✍️ **손글씨 주문지 OCR**: 손으로 작성한 약국 주문지를 사진으로 올리면 멀티모달 LLM(Google Gemini)이 약품명·포장단위·수량을 구조화 추출(`/order-ocr`). `AxB` 표기를 포장단위×주문수량으로, 함량/규격은 약품명에 포함하는 약국 도메인 프롬프트를 사용합니다. 한 줄도 빠뜨리지 않도록 흐린 글씨·동그라미 주석이 있는 줄까지 모두 추출하며, 결과는 사용자가 직접 확인·수정하는 검수 테이블(Human-in-the-loop)로 제공됩니다. 검수(검수→다음) 후 약품별로 주문할 **도매상을 선택**하는 단계를 거쳐, (주문일자, 차수) 단위로 로컬 SQLite에 원본 이미지와 함께 저장합니다.
- 🏪 **주문 도매상 선택**: 검수를 마치고 "다음"을 누르면 약품별 도매상 선택 화면으로 넘어갑니다. 각 행의 드롭다운은 그 약품을 마지막으로 주문했던 도매상(없으면 기준 도매상)을 기본값으로 두고, 행을 클릭하면 왼쪽 패널에 그 약품의 과거 주문 이력(주문일자·차수·도매상·수량)이 표시되어 평소 어디서 주문했는지 보고 고를 수 있습니다. 선택한 도매상은 품목별로 함께 저장됩니다.
- 📅 **주문 기록 (달력 조회)**: 저장된 주문지 내역을 달력 UI로 조회·관리하는 화면(`/orders`). 주문지 OCR 페이지(`/order-ocr`)의 상단 바에 있는 "주문 기록" 버튼(시계 아이콘)을 통해서만 진입하는 OCR 기능의 하위 화면이며, 뒤로가기 버튼은 홈이 아니라 주문지 작성 화면(`/order-ocr`)으로 돌아갑니다. 주문이 있는 날짜는 표시되며, 날짜를 클릭하면 그날의 차수별 주문이 품목 테이블(약품명·포장단위·수량·도매상)·원본 이미지 썸네일·삭제 버튼이 달린 카드로 펼쳐집니다.
- 🔤 **OCR 약품명 오타 보정**: 약품 마스터가 등록돼 있으면, OCR로 읽은 약품명을 한글 자모(초/중/종성) 기반 fuzzy 매칭으로 마스터와 대조해 검수 테이블 각 행에 결과 배지를 표시합니다 — "약품명 일치"(공식 전체명 자동 적용, 원본으로 되돌리기 가능), "확인 필요"(후보 드롭다운에서 선택), "미등록". 용량(600mg≠300mg)·접두(짧은 손글씨명↔긴 공식명) 인식, 제형 접미·제약사 접두 제거를 반영하며, 후보에 없으면 행별 "직접 검색" 박스로 마스터 DB를 직접 조회할 수 있습니다.
- 📏 **OCR 규격(포장단위) 자동 보정**: 약품명이 마스터와 매칭되면, 그 약품이 마스터에 보유한 알려진 규격 집합(수집 규격 + 직접추가 규격)으로 검수 테이블의 규격칸을 (개수 기준으로) 검증·자동보정합니다. 빈칸이거나 유효 규격이 하나뿐이면 자동으로 채우고, 개수만 맞고 표기가 다르면 정식 표기로 교정하며(같은 개수의 다른 포장 선택은 보존), 유효하지 않은 개수면 오인식 의심으로 경고 색상을 표시합니다. 알려진 규격은 클릭 가능한 칩으로도 노출됩니다.
- 🆕 **자유입력 약품 자동 등록**: 주문을 저장할 때 마스터에 없던 자유입력 약품은 마스터에 `source='manual'` 행으로 자동 등록되어(입력한 포장단위는 `unit_manual`로 보관) 곧바로 OCR 약품명 매칭·직접 검색에 활용됩니다. 마스터 DB 뷰어는 이런 행을 "자유입력" 배지/필터로 구분하고, 이름 수정(주문 항목까지 연동)·삭제를 지원합니다.
- 🔗 **자유입력 약품 정식 승격(소급 연결)**: 엑셀 마스터를 갱신한 뒤, 자유입력(manual) 약품 중 공식(excel) 약품과 fuzzy 매칭되는 것을 약품 DB 관리 화면의 확인 모달에서 정식 약품으로 승격(병합)할 수 있습니다. 승격하면 그 약품의 주문 항목이 공식명으로 갱신되고, 자유입력 규격이 공식 행으로 이관된 뒤 manual 행은 삭제됩니다.
- 💊 **약품 DB 관리**: 약국이 취급하는 전체 약품 목록을 엑셀로 업로드해 로컬에 등록(`/drug-master`). (UI에는 "약품 DB"로 표기되며, 내부 코드·테이블명은 `drug_master`를 그대로 사용합니다.) 머리글 행 자동 추정 + 컬럼 매핑(약품명 필수, 보험코드·제약사 선택)을 거쳐 SQLite DB(`drug_master` 테이블)에 병합(upsert) 저장하며, 위의 OCR 약품명 오타 보정의 기준 데이터로 사용됩니다. 엑셀엔 없는 포장단위(규격)는 기준 도매상에 보험코드로 검색해 일괄 수집하고, 페이지형 마스터 DB 뷰어에서 검색·확인하거나 직접 규격을 추가할 수 있습니다. 행은 출처(엑셀 임포트 / 자유입력 자동등록)로 구분되며, 자유입력 행은 이름 수정·삭제가 가능합니다.
- 📱 **웹 인터페이스**: 실시간 WebSocket 업데이트가 포함된 웹 대시보드(`/checker`)
- 👁️ **결과 표시 제외 기능**: 도매상별로 독립적인 약품 결과 필터링 (검색은 계속 수행)
- 🔔 **스마트 알림**: 품절약 재고 발견시 알림 시스템 (날짜별 제외 관리)
- 📈 **진행 상황 추적**: 약품 검색 진행률 실시간 표시
- 🏗️ **모듈형 설계**: 확장 가능한 아키텍처와 포괄적인 테스트 커버리지
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
- **OCR / LLM**: Google Gemini (멀티모달, `google-genai` SDK), 키는 `.env`에서 로드(`python-dotenv`)
- **Data Storage**: SQLite (Python 표준 `sqlite3`, WAL 모드) — 약품 목록·결과 표시 제외 목록·도매상 자격증명·약품 마스터·검색 세션/결과·주문 기록을 단일 `data/yak_soldout.db`에 통합 저장 (주문지 원본 이미지는 `data/order_images/`에 별도 보관)
- **Fuzzy Matching**: rapidfuzz (한글 자모 분해 기반 약품명 오타 보정)
- **Data Processing**: pandas, numpy, openpyxl/xlrd (엑셀 파싱)
- **Testing**: pytest (단위 테스트 & 통합 테스트)
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
pip install -r requirements.txt
uv pip install -r requirements.txt

# Playwright 브라우저 설치 (처음 실행 시 필수)
python -m playwright install chromium
```

### 2. 설정 파일 준비

프로젝트 루트 디렉터리에 다음 파일을 생성하세요:

```bash
# 로그인 정보 설정 (config.example.json을 참고하여 생성)
cp config.example.json config.json
# config.json 파일을 열어 실제 도매상 계정 정보 입력
```

> **데이터 저장소(SQLite)**: 도매상 자격증명, 모니터링할 약품 목록, 결과 표시 제외 목록, 약품 마스터, 검색 세션/결과는 모두 `data/yak_soldout.db` (SQLite)에 저장됩니다. DB 파일과 스키마는 첫 실행 시 자동 생성되므로 직접 만들 필요가 없습니다. `config.json`은 이제 도매상 자격증명이 아닌 `monitoring` 설정만 보관합니다(도매상 자격증명/색상/지역은 DB의 `distributors` 테이블로 이전됨). 과거에 JSON 파일(`geoweb-soldout-list.json`, `exclusion-list.json`, `data/drug_master.json`, `config.json`의 distributors)을 쓰던 환경이라면 첫 실행 시 해당 JSON이 DB로 자동 시딩(멱등)됩니다.

> **기존 info.txt 사용자**: 기존 `info.txt` 파일이 있으면 첫 실행 시 `config.json`으로 자동 마이그레이션됩니다. 원본은 `info.txt.bak`으로 백업됩니다.

> **손글씨 주문지 OCR 사용 시(`.env`)**: OCR 기능은 Google Gemini API 키가 필요합니다. `.env.example`을 `.env`로 복사한 뒤 [Google AI Studio](https://aistudio.google.com/apikey)에서 발급한 키를 `GEMINI_API_KEY`에 입력하세요. (선택: `GEMINI_MODEL`, 기본값 `gemini-2.5-flash`) 키가 없으면 OCR 기능만 비활성화되고 나머지 기능은 정상 동작합니다.
>
> ```bash
> cp .env.example .env   # .env 를 열어 GEMINI_API_KEY 입력
> ```

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

개발 환경에서는 `./dev.sh` 한 줄로 실행하는 것을 권장합니다. 이 스크립트는 프로젝트 루트의 `.venv` 가상환경 파이썬을 사용하며, `PORT=8002`를 export한 뒤 해당 포트를 점유 중인 좀비 프로세스를 정리하고 `python web_server.py`를 실행합니다. (기본 포트는 **8002**입니다. 8000/8001은 다른 로컬 프로젝트와 충돌하기 때문입니다.)

```bash
# 개발 서버 시작 (권장)
./dev.sh

# 또는 직접 실행
python web_server.py

# 브라우저에서 접속
# http://localhost:8002

# 포트 변경이 필요한 경우 PORT 환경변수 사용
PORT=3000 python web_server.py
```

> `run_app.py`는 PyInstaller 패키지 빌드용 진입점이며, 개발 시에는 위의 `./dev.sh` 또는 `python web_server.py`를 사용하세요.

#### 🔍 디버그 모드 (브라우저 화면 보기)

브라우저 창을 보면서 실행하고 싶다면:

```bash
# 웹 인터페이스 디버그 모드
HEADLESS=false python web_server.py

# Windows에서는
set HEADLESS=false && python web_server.py

# 환경변수 조합 사용 가능
PORT=3000 HEADLESS=false python web_server.py
```

## 📁 프로젝트 구조

```
yak-soldout/
├── web_server.py              # FastAPI 웹 서버 (개발 실행: ./dev.sh 또는 python web_server.py)
├── dev.sh                     # 개발 실행 스크립트 (.venv 사용 + 포트 정리 + 서버 실행)
├── run_app.py                 # PyInstaller 배포 빌드용 진입점
├── config.json                # monitoring 설정 (직접 생성, distributors는 첫 실행 시 DB로 시딩)
├── build_config.json          # 약국별 빌드 설정 (선택사항, PyInstaller 배포 시 사용)
├── db.py                      # SQLite 데이터 액세스 레이어 (스키마/마이그레이션/JSON 시딩)
├── analyze_units.py           # drug_master.unit 규격 빈도 분석 스크립트 → unit_frequency.json 출력
│
├── scrapers/                  # Playwright 기반 도매상 스크래퍼
│   ├── registry.py            # 도매상 레지스트리 — Single Source of Truth
│   ├── base_scraper.py        # 기본 스크래퍼 공통 기능
│   ├── browser_manager.py     # 브라우저 인스턴스 중앙 관리
│   ├── geoweb_scraper.py      # 지오영 스크래퍼
│   ├── baekje_scraper.py      # 백제약품 스크래퍼 (JWT 인증 + REST API 기반)
│   ├── incheon_scraper.py     # 인천약품 스크래퍼
│   ├── geopharm_scraper.py    # 지오팜 스크래퍼
│   ├── boksan_scraper.py      # 복산 스크래퍼
│   ├── upharmmall_scraper.py  # 유팜몰 스크래퍼
│   ├── hmpmall_scraper.py     # HMP몰 스크래퍼 (JSON API 기반 통합 플랫폼)
│   └── tjpharm_scraper.py    # 티제이팜 스크래퍼 (HTTP API 기반)
│
├── models/                    # 데이터 구조 및 설정
│   ├── drug_data.py           # Drug, AppConfig, DistributorCredentials 데이터 클래스
│   ├── config.py              # ConfigManager — config.json 기반 설정 관리 (자동 마이그레이션 포함)
│   └── build_config.py        # 빌드 설정 관리 — build_config.json 기반 약국별 커스터마이징 및 기준 도매상 설정
│
├── utils/                     # 유틸리티
│   ├── search_engine.py       # 검색 실행 엔진 (registry 루프 기반) + PreviewSearchSession
│   ├── open_site_session.py   # 바로가기 headed 브라우저 세션 관리 (OpenSiteSession)
│   ├── ocr_service.py         # 손글씨 주문지 OCR — Gemini 호출 및 약품명·포장단위·수량 추출
│   ├── drug_master.py         # 약품 마스터 — 엑셀 업로드(upsert)/머리글 추정/컬럼 매핑/제약사 정규화
│   ├── unit_collector.py      # 포장단위(규격) 일괄 수집 배치 — 기준 도매상에 보험코드 검색 + WebSocket 진행상황
│   ├── drug_matcher.py        # OCR 약품명 오타 보정 — 한글 자모 fuzzy 매칭(rapidfuzz) + 마스터 직접 검색 + 약품별 규격 인덱스
│   ├── order_reconcile.py     # 자유입력(manual) 마스터 약품을 정식(excel) 약품으로 fuzzy 매칭·승격(병합)
│   ├── file_manager.py        # 약품 목록 / 결과 표시 제외 목록 I/O (DB 위임)
│   ├── data_processor.py      # 데이터 처리 및 분류
│   └── notifications.py       # 크로스 플랫폼 알림
│
├── templates/
│   ├── home.html              # 홈 화면(앱 런처) HTML 템플릿 (GET /)
│   ├── index.html             # 품절 약 서치앱 대시보드 HTML 템플릿 (GET /checker)
│   ├── order_ocr.html         # 손글씨 주문지 OCR 업로드·검수·저장 화면 (GET /order-ocr)
│   ├── order_history.html     # 주문 기록 달력 조회 화면 (GET /orders)
│   └── drug_master.html       # 약품 DB 관리 화면 (GET /drug-master, UI 표기 "약품 DB")
│
├── static/
│   ├── css/                   # 기능별 CSS 파일 (home.css = 홈, order-ocr.css, order-history.css, drug-master.css 등)
│   └── js/                    # 모듈별 JavaScript 파일 (home.js = 홈, main.js = 대시보드, order-ocr.js, order-history.js, drug-master.js)
│
├── data/                      # 로컬 데이터 (자동 생성)
│   ├── yak_soldout.db         # SQLite DB — 약품 목록·제외 목록·도매상·약품 마스터·검색 세션/결과·주문 기록
│   └── order_images/          # 저장된 주문지의 원본 이미지 파일
│
├── .env                       # OCR용 Gemini API 키 (직접 생성, .env.example 참고, git 미커밋)
├── docs/                      # 기능 계획·설계 문서 (예: 손글씨-주문지-OCR-기능-계획.md)
│
├── tests/                     # 테스트 (단위 + 통합)
│   ├── unit/
│   └── integration/
│
└── legacy_codes/              # 구 Selenium/Streamlit 구현 (참고용)
    └── g50.py
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
- **no-cache 미들웨어**: `web_server.py`는 정적 파일과 페이지(`/`, `/checker`, `/order-ocr`, `/drug-master`, `/orders`)에 `Cache-Control: no-cache`를 강제하는 HTTP 미들웨어를 둡니다. `StaticFiles`가 `Cache-Control`을 생략해 브라우저가 옛 파일을 휴리스틱 캐싱하는 문제를 막기 위함이며, 변경이 없으면 304로 저렴하게 끝납니다.

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

### 손글씨 주문지 OCR (Order OCR)

손으로 작성한 약국 주문지를 사진으로 올리면 약품명·포장단위·주문수량을 구조화 추출하는 기능입니다(`/order-ocr`, `utils/ocr_service.py`).

- **멀티모달 LLM**: `google-genai` SDK로 Google Gemini(`gemini-2.5-flash`, `GEMINI_MODEL`로 변경 가능)를 호출합니다. 응답은 `response_schema`로 `[{drug_name, package_unit, quantity}]` 배열을 강제하고 `temperature=0`으로 안정성을 높입니다.
- **도메인 프롬프트**: 약국 주문지의 표기 규칙을 학습시킵니다 — 줄 오른쪽의 `AxB`는 'A정짜리 통을 B개 주문'으로 해석해 `package_unit`(예: `30정`)과 `quantity`(예: `2`)로 분리하고, 약품명 뒤 함량/규격(예: `600mg`)은 약품명에 포함하며, 머리글·날짜·메모 등 주문 품목이 아닌 줄은 제외합니다.
- **누락 방지(recall-first)**: 한 줄도 빠뜨리지 않도록 왼쪽 열을 위에서 아래로, 그다음 오른쪽 열을 전부 추출합니다. 글씨가 흐리거나 동그라미 등 주석이 있어도 모두 포함합니다.
- **Human-in-the-loop 검수**: 추출이 끝나면 화면이 업로드 카드를 감추고 **좌우 2단 검수 레이아웃**으로 전환됩니다 — 왼쪽은 원본 사진을 sticky로 고정한 패널, 오른쪽은 편집 가능한 검수 테이블입니다. 왼쪽 사진은 원본과 대조하며 확인할 수 있도록 확대(휠/버튼, 커서·핀치 중심 고정)·이동(드래그/태블릿 터치)·원래대로(더블클릭/버튼) 및 '다른 이미지 올리기'(재업로드) 조작을 지원하고, 읽어온 품목 수는 검수 헤더로 옮겨 대조 중에도 보이게 했습니다. 화면이 좁으면(≤900px) 자동으로 위아래 세로 배치로 바뀝니다.
- **도매상 선택 단계**: 검수 테이블에서 "다음"을 누르면 약품별 **도매상 선택** 화면으로 전환됩니다. 프론트가 약품명 목록을 `POST /api/order-ocr/order-context`로 보내면 서버는 표시 대상 도매상 목록(드롭다운 옵션, 기준 도매상이 맨 앞)·기준 도매상·약품별 과거 주문 이력과 마지막 주문 도매상(`db.get_order_context`)을 돌려줍니다. 각 행의 도매상 드롭다운 기본값은 *그 약품을 마지막으로 주문했던 도매상*이며, 이력이 없으면 기준 도매상이 선택됩니다. 행을 클릭하면 왼쪽 패널에 그 약품의 과거 주문 이력(주문일자·차수·도매상·수량)이 표시되어 평소 주문처를 보고 고를 수 있습니다.
- **저장(로컬 SQLite)**: 도매상 선택까지 끝나면 "저장" 버튼으로 `POST /api/order-ocr/save`를 호출해 (주문일자, 차수) 단위로 주문을 저장합니다. 약품명이 빈 행은 제외한 품목(`drug_name`·`package_unit`·`quantity`·`distributor`)이 `orders`/`order_items` 테이블에, 업로드한 원본 이미지는 `data/order_images/`에 `'(날짜_차수)'` 이름으로 함께 저장됩니다. 같은 (날짜, 차수) 주문이 이미 있으면 서버가 HTTP 409를 반환하고, 프론트가 사용자에게 덮어쓰기 동의를 받아 `overwrite=true`로 재요청하면 기존 주문을 교체합니다. (현재는 로컬 저장 전용입니다. 키 유출 방지를 위해 OCR 호출 자체는 배포 단계에서 서버 측(Supabase Edge Function 등)으로 이전할 예정입니다 — `docs/손글씨-주문지-OCR-기능-계획.md`.)
- **키 미설정 처리**: SDK는 지연 임포트하며, `GEMINI_API_KEY`가 없으면 `/api/order-ocr/extract`가 503을 반환할 뿐 앱의 나머지 기능은 정상 동작합니다. 업로드는 JPEG/PNG/WebP/HEIC/HEIF, 최대 15MB로 제한됩니다.

### 주문 기록 (Order History)

저장된 주문지 내역을 달력 UI로 조회·관리하는 화면입니다(`/orders`, `templates/order_history.html`, `static/js/order-history.js`, `static/css/order-history.css`).

- **진입 경로**: 홈 화면의 최상위 카드가 아니라 **주문지 OCR의 하위 화면**입니다. 주문지 OCR 페이지(`/order-ocr`) 상단 바의 "주문 기록" 버튼(시계 아이콘)으로만 진입하며, 화면 상단의 뒤로가기 버튼은 홈이 아니라 주문지 작성 화면(`/order-ocr`)으로 돌아갑니다.
- **달력 조회**: `GET /api/orders`로 저장된 주문 요약을 받아 주문이 있는 날짜를 달력에 표시합니다. 날짜를 클릭하면 그날의 차수(1~3차)별 주문이 카드로 펼쳐집니다.
- **상세 카드**: 각 카드는 `GET /api/orders/{id}`로 받은 품목 테이블(약품명·포장단위·수량·도매상)과 원본 주문지 이미지 썸네일(`GET /api/orders/{id}/image`), 삭제 버튼을 표시합니다.
- **삭제**: `DELETE /api/orders/{id}`는 주문과 품목(FK CASCADE)을 지우고 `data/order_images/`의 원본 이미지 파일도 함께 정리합니다.

### OCR 약품명 오타 보정 (Drug Matcher)

OCR로 읽은 약품명을 등록된 약품 마스터와 대조해 오타를 잡아내는 기능입니다(`utils/drug_matcher.py`, 의존성 `rapidfuzz`). 마스터가 등록돼 있을 때만 동작하며, 자동 교정 없이 검수 화면에 후보를 제시하는 Human-in-the-loop 방식입니다.

- **한글 자모 매칭**: 한글은 글자 단위 편집거리로는 부정확하므로 음절을 초/중/종성 자모로 분해한 뒤 유사도를 계산합니다. 마스터명은 길고 상세하므로(예: `가나칸정50밀리그램(이토프리드염산염)_(50mg/1정)`) 숫자·괄호 앞의 '핵심 이름'만 뽑아 비교하고, 제형 접미(`서방정`·`주`·`캡슐` 등)와 손글씨 약품명 앞의 제약사 접두(`일성)호이펜`→`호이펜`)는 떼어냅니다. 짧은 손글씨명이 긴 공식명의 접두인 경우는 부분일치로 보정합니다.
- **용량 인식**: 브랜드는 같아도 용량(규격) 숫자가 다르면(600mg≠300mg) 점수를 제한해 '일치'가 아닌 '확인 필요'로 처리합니다.
- **검수 화면 표시**: `/api/order-ocr/extract`가 각 항목에 매칭 결과(`match`)를 덧붙이며, 검수 테이블 각 행이 상태 배지를 보여줍니다 — `matched`(유사도 ≥90, "✓ 약품명 일치" 배지로 공식 전체명을 자동 적용하고 드롭다운으로 원본 복원 가능), `candidate`(70~90, 후보 드롭다운 제시), `none`(미등록), `skip`(마스터 미등록 → 표시 없음). 사용자가 드롭다운이나 "직접 검색"으로 약품을 직접 고르면 해당 행 배지가 "✓ 사용자 확인"으로 바뀌어 어디까지 검토·확정했는지 한눈에 보입니다.
- **직접 검색**: 후보에 원하는 약이 없으면 행별 "직접 검색" 박스로 `GET /api/drug-master/search`를 호출해 마스터 DB를 이름 부분일치(우선) + 자모 fuzzy(보충)로 직접 조회·선택합니다. 매처는 `drug_master`만 인덱싱하므로, 자유입력 약품도 주문 저장 시 manual 행으로 자동 등록되어 곧바로 검색·매칭 대상에 포함됩니다.
- **규격(포장단위) 자동 보정**: 매처는 같은 표시 핵심명을 가진 마스터 행들의 수집 규격(`unit`) + 직접추가 규격(`unit_manual`)을 합친 약품별 `known_units` 인덱스를 만들어 매칭/검색 결과에 함께 실어 보냅니다. 프론트엔드(`static/js/order-ocr.js`)는 규격을 (개수, 제형)으로 정규화해, 약품이 확정되면 규격칸을 검증·자동보정하고(자동 채움/정식 표기 교정/오인식 경고), 알려진 규격을 클릭 가능한 칩으로 노출하며, 같은 개수라도 포장이 다른 사용자 선택(예: `100정(PTP)` vs `100정(병)`)은 정확히 일치할 때만 강조하고 덮어쓰지 않습니다.
- **인덱스 캐시**: 약품 마스터(DB `drug_master` 테이블)를 기준으로 자모 인덱스와 규격 인덱스를 캐싱하고, 마스터가 재임포트되면(DB의 등록 수·시각 기반 캐시 키 변경) 자동 재구축합니다. 캐시 키에는 규격 텍스트 총길이 시그니처가 포함돼, 규격 수집·직접추가로 `unit`/`unit_manual`만 바뀌어도 캐시가 갱신됩니다.

### 약품 DB 관리 (Drug Master)

약국이 취급하는 전체 약품 목록을 엑셀로 등록하는 기능입니다(`/drug-master`, `utils/drug_master.py`). 위의 OCR 약품명 오타 보정(`drug_matcher`)의 기준 데이터로 사용됩니다. (사용자에게는 "약품 DB"로 표기하지만, 내부 코드·DB 테이블·함수명은 일관성을 위해 `drug_master`를 그대로 유지합니다.)

- **머리글 행 자동 추정**: 실제 약국 엑셀 export는 제목·조회일시 등이 머리글 위에 깔리는 경우가 많습니다. `_guess_header_row`가 `약품명`·`보험코드`·`제약사` 등 키워드가 든 행(또는 비어있지 않은 칸이 가장 많은 행)을 머리글로 추정하며, `/api/drug-master/preview`로 원본 상단 행과 함께 반환합니다. 사용자는 모달에서 머리글 행을 직접 바꿀 수 있습니다.
- **컬럼 매핑**: 컬럼명이 약국마다 다르므로, 사용자가 약품명(필수)·보험코드(선택)·제약사(선택) 컬럼을 직접 지정해 `/api/drug-master/import`로 등록합니다. 빈 행은 건너뛰고 (약품명, 보험코드) 조합으로 중복을 제거합니다.
- **제약사 정규화**: `normalize_maker`가 `대웅제약(주)`→`대웅`, `(주)보령`→`보령`처럼 법인/접미 토큰을 제거한 정규화 형태(`maker_norm`)를 함께 저장해, 표기 편차에도 매칭이 가능하게 합니다.
- **병합(upsert) 저장**: 엑셀 업로드는 전체 교체가 아니라 병합입니다(`db.upsert_drug_master`). (약품명, 보험코드) 기준으로 일치하면 제약사 표기 등을 갱신하고 없으면 새로 추가하며, 새 파일에 없는 기존 약품은 삭제하지 않고 보존합니다. 따라서 아래에서 수집·직접추가한 규격(`unit`/`unit_manual`)과 기존 행 ID가 그대로 유지됩니다. 등록 현황(개수·출처 파일·포장단위 수집 현황)은 `/api/drug-master`로 조회합니다. (엑셀 업로드 UI는 현황 카드 안에 "엑셀 파일 올려서 갱신" 액션으로 통합되어 있습니다.)
- **포장단위(규격) 수집**: 엑셀에는 규격 컬럼이 없으므로, `drug_master`의 `unit`이 비어 있고 보험코드가 있는 행을 기준 도매상(유팜몰/지오영)에 보험코드로 하나씩 검색해 규격을 채웁니다(`utils/unit_collector.py`). 같은 보험코드가 여러 규격을 가질 수 있어 검색 결과의 distinct 규격을 모두 모아 `", "`로 합쳐 저장하고, 같은 코드는 한 번만 검색하도록 캐싱합니다. `POST /api/drug-master/collect-units`로 백그라운드 배치를 시작하면 진행 상황을 WebSocket으로 브로드캐스트하고 터미널에도 로그를 남기며, `POST /api/drug-master/collect-units/stop`으로 다음 행 경계에서 중단합니다. (지오영 결과의 규격은 `td.standard`에서 추출합니다.)
- **마스터 DB 뷰어 / 직접 규격 추가**: 화면 우측에 페이지 단위 마스터 테이블 뷰어가 있습니다(`GET /api/drug-master/rows`, 약품명·보험코드 검색 + 상태 필터 지원). 수집한 규격(`unit`)은 읽기 전용으로 보여주고, 사용자가 직접 입력한 규격은 별도의 `unit_manual` 컬럼에 append-only로 보관합니다(`POST /api/drug-master/manual-unit`, 중복·기존 규격은 추가하지 않으며 삭제는 되지 않음). 수집분과 직접추가분을 출처별로 분리해 관리합니다.
- **자유입력 행 표시·편집**: 주문 저장 시 자동 등록된 자유입력 약품(`source='manual'`)은 뷰어에서 "자유입력" 배지로 구분되며, 전용 필터로 모아 볼 수 있습니다. 이런 행만 이름을 수정(`PUT /api/drug-master/rows/{id}`, 같은 이름의 `order_items.drug_name`도 함께 갱신)하거나 삭제(`DELETE /api/drug-master/rows/{id}`)할 수 있습니다. 엑셀 임포트분(`source='excel'`)은 안전상 수정·삭제 대상에서 제외되며 엑셀 재업로드로 관리합니다.
- **규격 빈도 분석 스크립트**: 독립 실행 스크립트 `analyze_units.py`는 마스터 전체의 `unit` 토큰별 보유 약품 수를 세어 `unit_frequency.json`으로 출력합니다.

### 자유입력 약품 정식 승격 (Order Reconcile / Promotion)

주문서는 마스터에 없는 신약을 자유입력으로 먼저 작성할 수 있습니다. 이런 약품은 주문 저장 시 마스터에 `source='manual'` 행으로 자동 등록되어(`db.register_free_input_drugs`) 즉시 OCR 매칭·직접 검색에 활용됩니다. 이후 엑셀 업데이트로 같은 약의 공식(`source='excel'`) 행이 들어오면, 자유입력 행을 공식 행으로 **승격(병합)**하는 기능입니다(`utils/order_reconcile.py`).

- **승격 후보 탐지**: 자유입력(manual) 마스터 행 각각을 매처의 `drug_matcher.top_candidates`로 매칭하되, 후보는 **공식(excel) 약품으로만 한정**합니다(`db.excel_master_names`). 소프트 플로어(`DROPDOWN_FLOOR`) 이상 후보만 남기고, 최상위 점수가 기준 미만이거나 후보가 없으면 그 행은 제외합니다.
- **확인 모달(다중 후보 드롭다운)**: 엑셀 업로드(마스터 갱신) 직후 약품 DB 관리 화면이 `GET /api/drug-master/promotion-candidates`로 후보를 받아 확인 모달을 띄웁니다. manual 행마다 `<select>` 드롭다운으로 여러 공식명 후보(`공식명 (점수%)`)를 제시하며 기본값은 "승격 안 함"입니다. 최상위 후보가 고확신(≥`HIGH_SCORE`)인 경우에만 자동 선택하고, 그 외에는 오매칭을 막기 위해 비워 둡니다. 사용자가 고른 항목만 `POST /api/drug-master/promote`로 적용됩니다.
- **승격(병합) 처리**: 승격 시 ① 자유입력 행의 규격(`unit_manual`)을 공식 행에 중복 없이 합치고, ② 그 자유입력 이름으로 저장된 모든 `order_items.drug_name`을 공식명으로 갱신한 뒤, ③ 자유입력 행을 삭제합니다(`db.promote_manual_drugs`).
- **멱등성**: 승격된 약품은 manual 행이 사라지므로 다시 후보로 제시되지 않습니다.

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
cp build_config.example.json build_config.json
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

애플리케이션 데이터는 단일 SQLite 파일 `data/yak_soldout.db`에 통합 저장됩니다. DB 파일·스키마는 첫 실행 시 자동 생성되며, 데이터 액세스 레이어는 `db.py`가 담당합니다.

- **동시성**: FastAPI 라우트(asyncio)와 백그라운드 검색 스레드(ThreadPoolExecutor)가 동시에 접근하므로, WAL 저널 모드 + `busy_timeout` + 스레드별 연결(thread-local)로 read/write 충돌을 회피합니다.
- **스키마 버전 관리**: `PRAGMA user_version` 값으로 스키마 버전을 추적하며, 구버전 DB는 시작 시 자동 마이그레이션합니다.
- **JSON → DB 시딩**: 과거 JSON 파일(`geoweb-soldout-list.json`, `exclusion-list.json`, `data/drug_master.json`, `config.json`의 `distributors`)이 있으면 첫 실행 시 DB로 시딩합니다. 멱등(대상 테이블이 비어 있을 때만 시딩)이라 반복 실행해도 중복되지 않습니다.

### 테이블

- **drug_master**: 약품 마스터 (약품명·보험코드·제약사·정규화 제약사명·포장단위·출처). 엑셀 업로드는 (약품명, 보험코드) 기준 병합(upsert)으로 반영해 기존 행을 보존합니다. 포장단위는 엑셀에 없어 두 컬럼으로 나뉩니다 — `unit`(기준 도매상에서 일괄 수집한 규격, 읽기 전용)과 `unit_manual`(뷰어에서 사용자가 직접 추가한 규격, append-only). 한 행에 여러 규격은 `", "`로 합쳐 저장합니다. `source` 컬럼은 행 출처를 구분합니다 — `'excel'`(엑셀 임포트분, 기존 행은 마이그레이션 시 `'excel'`로 채움)과 `'manual'`(주문 저장 시 자유입력 약품을 자동 등록한 행). manual 행만 뷰어에서 이름 수정·삭제와 정식 승격 대상이 됩니다.
- **watch_list**: 모니터링할 품절 약품 목록 (약품명·긴급 알림 여부·추가일시). 웹 UI로 관리.
- **exclusion_list**: 결과 표시 제외 목록 — 도매상별로 독립 관리(`(drug_name, distributor)` 유니크). 웹에서 약품 카드의 눈 모양 아이콘(👁️‍🗨️)으로 추가하며, 백제약품은 규격 정보까지 포함해 정확히 매칭합니다.
- **distributors**: 도매상 자격증명·활성화 여부·색상·지역. 웹 설정 모달로 관리.
- **search_sessions / search_results**: 검색 사이클(시작 시각·소요·상태)과 그 결과(약품별 재고/품절·도매상별 행)를 영속화합니다.
- **orders / order_items**: 주문지 OCR 검수 완료분. `orders`는 주문 1건(주문일자·차수·원본 이미지 파일명·저장 시각, `(order_date, order_round)` 유니크)이고 `order_items`는 그 품목(약품명·포장단위·수량·도매상 dist_key·표시 순서, `order_id` FK + ON DELETE CASCADE)입니다. `distributor`는 저장 직전 도매상 선택 단계에서 채워지며, 이력이 없던 기존 주문에는 NULL로 남습니다. 원본 이미지 파일은 `data/order_images/`에 별도 보관합니다.

> **config.json**: 이제 도매상 자격증명이 아닌 `monitoring` 설정(`repeat_interval_minutes`, `alert_exclusion_days`)만 보관합니다. 도매상 자격증명·색상·지역은 `distributors` 테이블로 이전되었습니다.

## 🔌 API 엔드포인트

### REST API
- `GET /` - 홈 화면 (앱 런처)
- `GET /checker` - 품절 약 서치앱 대시보드
- `GET /order-ocr` - 손글씨 주문지 OCR 업로드·검수·저장 화면
- `POST /api/order-ocr/extract` - 주문지 이미지 → Gemini OCR → 약품명·포장단위·수량 추출 (마스터 등록 시 항목별 오타 보정 매칭 결과 포함)
- `POST /api/order-ocr/order-context` - 도매상 선택 단계용 컨텍스트 (표시 도매상 목록 + 기준 도매상 + 약품별 과거 주문 이력/마지막 주문 도매상)
- `POST /api/order-ocr/save` - 검수 완료된 주문을 로컬 SQLite에 저장(품목별 도매상 포함, 원본 이미지 동봉, `(날짜,차수)` 중복 시 409 → `overwrite=true`로 덮어쓰기)
- `GET /orders` - 주문 기록 달력 조회 화면
- `GET /api/orders` - 저장된 주문 요약 목록 (달력 표시용)
- `GET /api/orders/{id}` - 주문 1건 상세 (메타 + 품목 목록)
- `GET /api/orders/{id}/image` - 주문에 저장된 원본 주문지 이미지 파일
- `DELETE /api/orders/{id}` - 주문 1건 삭제 (품목 CASCADE + 원본 이미지 파일 정리)
- `GET /drug-master` - 약품 DB 관리 화면 (UI 표기 "약품 DB")
- `GET /api/drug-master` - 약품 마스터 등록 현황 조회 (포장단위 수집 현황 포함)
- `GET /api/drug-master/search` - 약품 마스터 직접 검색 (OCR 검수 화면의 "직접 검색"용, `q` 파라미터)
- `GET /api/drug-master/rows` - 마스터 DB 뷰어용 페이지 조회 (`offset`/`limit`/`q`/상태 필터 파라미터)
- `PUT /api/drug-master/rows/{id}` - 자유입력(manual) 마스터 행 이름 수정 (같은 이름의 주문 항목도 함께 갱신)
- `DELETE /api/drug-master/rows/{id}` - 자유입력(manual) 마스터 행 삭제 (엑셀 임포트분은 불가)
- `POST /api/drug-master/preview` - 업로드 엑셀 미리보기 (머리글 행 추정 + 컬럼·샘플 반환)
- `POST /api/drug-master/import` - 선택한 컬럼 매핑으로 약품 마스터 등록(병합/upsert)
- `POST /api/drug-master/collect-units` - 빈 포장단위(규격) 일괄 수집 시작 (기준 도매상에 보험코드 검색, 진행상황 WebSocket 스트리밍)
- `POST /api/drug-master/collect-units/stop` - 진행 중인 포장단위 수집 중단 요청
- `POST /api/drug-master/manual-unit` - 뷰어에서 사용자가 직접 규격 추가 (append-only)
- `GET /api/drug-master/promotion-candidates` - 엑셀 갱신 후 자유입력(manual) 약품의 정식(excel) 승격 후보 조회
- `POST /api/drug-master/promote` - 선택한 자유입력 약품을 정식 약품으로 승격(병합)
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
- `GET /api/build-info` - 빌드 정보 조회 (약국명, 기준 도매상명 등)
- `POST /api/preview-search` - 약품 미리보기 검색 (기준 도매상에 실시간 질의)
- `POST /api/preview-search/close` - 미리보기 검색 세션 브라우저 종료
- `POST /api/open-distributor-site` - 도매상 사이트 바로가기 (headed 브라우저 자동 로그인+검색)
- `POST /api/open-distributor-site/close` - 바로가기 세션 수동 종료

### WebSocket
- `WS /ws` - 실시간 로그 스트리밍 및 검색 진행 상황 업데이트

## 🧪 테스트

```bash
# 전체 테스트 실행
python -m pytest

# 특정 모듈 테스트
python -m pytest tests/unit/
python -m pytest tests/integration/

# 커버리지 포함 테스트
python -m pytest --cov=.
```

## 🔄 개발 가이드

### 새로운 도매상 추가하기

레지스트리 패턴 덕분에 새 도매상 추가 시 수정해야 할 파일이 최소화되어 있습니다.

**1단계**: `DistributorType` enum에 추가 (`models/drug_data.py`)

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
- CSS: `static/css/` 디렉터리의 기능별 파일 수정
- JavaScript: `static/js/` 디렉터리의 모듈별 파일 수정 (`home.js` = 홈 화면, `main.js` = 대시보드)
- HTML: 홈 화면은 `templates/home.html`, 대시보드는 `templates/index.html` 수정

## 🐛 문제 해결

### 브라우저 설치 문제

```bash
# Playwright 브라우저 재설치
python -m playwright install chromium --force

# 시스템 의존성 설치 (Ubuntu/Debian)
sudo python -m playwright install-deps chromium
```
