# legacy_codes — 마이그레이션 완료된 레거시 코드 보관소

주문지 OCR·주문 기록·약품 마스터 기능이 **약국 주문 Agent**(apps/cloud_web/ 웹앱 + apps/local_app/
로컬 관리자 앱, Supabase 기반)로 마이그레이션 완료되면서, 레거시 앱(품절약 서치앱)에서
분리해낸 코드들이다. **어디서도 임포트되지 않는 참조용 아카이브**이며, 삭제해도 동작에는
영향이 없다.

## 구성

| 경로 | 내용 |
|---|---|
| `web_server_ocr_routes.py` | web_server.py 에서 잘라낸 OCR/주문/약품마스터 FastAPI 라우트 |
| `templates/` | order_ocr.html, order_history.html, drug_master.html |
| `static/js/`, `static/css/` | 위 페이지들의 프론트 코드 |
| `utils/` | ocr_service, drug_master, drug_matcher, order_reconcile, unit_collector |
| `scripts/`, `analyze_units.py` | 관련 개발용 스크립트 |
| `db_ocr_functions.py` | db.py 에서 분리한 drug_master/orders 데이터 계층 함수 |

## 데이터는 남아 있음

db.py 스키마에서 drug_master/orders/order_items DDL 을 제거했지만, **기존 로컬
SQLite(apps/soldout/data/yak_soldout.db)의 해당 테이블과 과거 주문 데이터는 삭제되지 않고 그대로
남아 있다** (신규 설치에서만 이 테이블들이 안 만들어짐). 필요하면 sqlite3 로 직접 조회.

## 남겨둔 것 (여기 없음)

- **scrapers/** — 도매상 크롤러는 레거시가 아니라 품절약 서치앱과 local_app(규격 수집)이
  공유하는 현역 코드다. 모노레포 개편 후에도 루트에 유지.

새 시스템의 대응 코드: OCR/검수/저장 → `apps/cloud_web/`, 도매상 선택·규격 수집·DB 관리 → `apps/local_app/`.
