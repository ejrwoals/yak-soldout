# SQLite DB 마이그레이션 계획

## 배경

현재 모든 데이터를 JSON 파일로 관리하고 있음. 아래 한계점을 해결하기 위해 SQLite로 이전.

- 검색 결과를 마지막 1회분(`search_results.json`)만 보관 → 이력 추적 불가
- 품절 시작 시점 추적 불가
- 파일 간 관계(무결성) 없음
- JSON 파일에 락이 없어 동시 쓰기 시 손상 위험 (라우트 + 백그라운드 검색 스레드 동시 접근)

---

## 스키마 설계

> **날짜/시간 포맷 규칙 (전 테이블 공통)**
> 기존 코드는 ISO 포맷 `datetime.now().isoformat()[:19]` → `"2026-06-16T19:46:40"` (`T` 포함)을 사용하고
> 프론트엔드도 이 형식을 기대함. SQLite의 `datetime('now','localtime')`은 공백 구분(`"2026-06-16 19:46:40"`)이라
> 혼용하면 정렬·프론트 파싱이 깨짐.
> → **DEFAULT 절을 쓰지 않고, 앱 코드에서 ISO 문자열을 명시적으로 INSERT**한다. 컬럼 타입은 `TEXT`.

### 1. `drug_master` — 마스터 약품 목록

XLS 파일에서 임포트. 재임포트 시 UPSERT(덮어쓰기+신규추가) 처리.

```sql
CREATE TABLE drug_master (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    name           TEXT NOT NULL,
    insurance_code TEXT NOT NULL UNIQUE,
    maker          TEXT,
    maker_norm     TEXT,
    imported_at    TEXT NOT NULL,
    source_file    TEXT
);
```

- `insurance_code` 기준으로 UPSERT → 재임포트해도 기존 FK 깨지지 않음
- 기존 `data/drug_master.json` 데이터를 초기 시딩
- 참고: `drug_master.json`의 메타데이터(`columns` 매핑, `header_row`, `count`)는 임포트 시점 파싱에만 쓰이고 런타임에는 불필요하므로 테이블에는 옮기지 않음
- OCR 오타 보정용 fuzzy 매칭에서 전체 행을 메모리로 로드해 사용하므로, 앱 시작 시 1회 `SELECT *` 후 캐싱 권장 (호출마다 쿼리 X)

---

### 2. `watch_list` — 모니터링 대상 약품 목록

현재 `geoweb-soldout-list.json` 대체.

```sql
CREATE TABLE watch_list (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    drug_name      TEXT NOT NULL UNIQUE,
    insurance_code TEXT REFERENCES drug_master(insurance_code) ON DELETE SET NULL,
    is_urgent      BOOLEAN NOT NULL DEFAULT 0,
    date_added     TEXT NOT NULL
);
```

- `insurance_code`는 Nullable FK: 마스터에 있으면 연결, 없어도 `drug_name`만으로 모니터링 가능
- 마스터에 없는 약품을 추가할 때 강제로 마스터 등록할 필요 없음
- `drug_name`은 전체 표기(예: `"다이아벡스정500mg (병)100T 대웅"`)를 그대로 보관

---

### 3. `exclusion_list` — 알림 제외 목록

현재 `exclusion-list.json` 대체.

```sql
CREATE TABLE exclusion_list (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    drug_name   TEXT NOT NULL,
    distributor TEXT NOT NULL DEFAULT '',
    date        TEXT NOT NULL,
    is_pinned   BOOLEAN NOT NULL DEFAULT 0,
    UNIQUE(drug_name, distributor)
);
```

- **`distributor` 필수**: 실제 제외 항목은 `drug_name + distributor` 조합으로 중복을 판단하고 저장함
  (`/api/exclusion-add`, `web_server.py`). 같은 약품을 도매상별로 따로 제외할 수 있어야 하므로 복합 유니크로 처리.
- 정렬 규칙(비고정 항목 우선, 날짜 내림차순 후 고정 항목)은 조회 쿼리의 `ORDER BY is_pinned, date DESC`로 구현

---

### 4. `distributors` — 도매상 계정 및 설정

현재 `config.json`의 `distributors` 섹션 대체.

```sql
CREATE TABLE distributors (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    dist_key  TEXT NOT NULL UNIQUE,  -- 'geopharm', 'baekje' 등
    enabled   BOOLEAN NOT NULL DEFAULT 1,
    username  TEXT,
    password  TEXT,
    color     TEXT,
    region    TEXT  -- geopharm의 'daejeon' 등 추가 파라미터
);
```

- 도매상별 정적 메타데이터(이름, site_url 등)는 코드 레지스트리(`models/build_config.py`의 `DISTRIBUTOR_REGISTRY`)에 있으므로, 이 테이블은 **자격증명·활성화·색상·지역**만 보관
- 현재 추가 파라미터는 geopharm의 `region`뿐이라 고정 컬럼으로 충분. 다만 향후 도매상별 파라미터가 늘어날 경우 `extra_params TEXT`(JSON) 단일 컬럼이 더 유연 — 지금은 선택 사항
- `monitoring` 설정(`repeat_interval_minutes`, `alert_exclusion_days`)은 `config.json`에 그대로 유지

---

### 5. `search_sessions` — 검색 사이클 단위 기록

```sql
CREATE TABLE search_sessions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at   TEXT NOT NULL,
    duration_sec REAL,
    status       TEXT NOT NULL DEFAULT 'running'  -- 'running', 'completed', 'error'
);
```

---

### 6. `search_results` — 약품 × 도매상 단위 검색 결과

```sql
CREATE TABLE search_results (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id             INTEGER NOT NULL REFERENCES search_sessions(id) ON DELETE CASCADE,
    drug_name              TEXT NOT NULL,
    insurance_code         TEXT,
    distributor            TEXT NOT NULL,
    main_stock             TEXT,
    incheon_stock          TEXT,
    notes                  TEXT,
    company                TEXT,
    unit                   TEXT,
    status                 TEXT NOT NULL DEFAULT 'soldout',  -- 'found' | 'soldout' | 'error'
    is_excluded_from_alert BOOLEAN NOT NULL DEFAULT 0
);

CREATE INDEX idx_search_results_session ON search_results(session_id);
CREATE INDEX idx_search_results_drug    ON search_results(drug_name);
```

- **`status` 3-state**: 인메모리 검색 상태(`app_state.current_search`)는 결과를 `found_drugs` / `soldout_drugs` / `errors` 3가지로 구분함. 단일 `is_found` 불리언으로는 "품절"과 "검색 실패(에러)"가 합쳐져 품절 추적이 부정확해지므로 `status` 컬럼으로 분리.
- `session_id`로 JOIN하면 특정 회차 결과 조회 가능
- `drug_name` + `status` + `started_at`으로 "언제부터 품절이었나" 추적 가능

---

## 동시성(Concurrency) 전략

이 앱은 **FastAPI(asyncio) 라우트**와 **`ThreadPoolExecutor` 기반 백그라운드 검색 스레드**(`utils/search_engine.py`)가
동시에 동작함. 현재 JSON에는 락이 없어 race 위험이 존재하므로, SQLite 전환 시 아래를 반드시 적용한다.

- **WAL 모드**: `PRAGMA journal_mode=WAL` — 검색 스레드가 쓰는 동안에도 라우트가 읽기 가능
- **busy_timeout**: `PRAGMA busy_timeout=5000` — `database is locked` 회피
- **연결 관리**: `check_same_thread=False`로 열되, 스레드/요청 단위로 연결을 생성하거나 단일 직렬화 락으로 쓰기 보호
- **트랜잭션 단위**: 백그라운드 검색은 결과 1건마다 INSERT하지 말고, **세션(사이클) 단위 트랜잭션**으로 묶어 커밋
- **외래키 강제**: 연결마다 `PRAGMA foreign_keys=ON`

---

## 활용 예시 쿼리

```sql
-- 특정 약품의 품절 시작 시점 추적
SELECT s.started_at, r.distributor, r.main_stock, r.status
FROM search_results r
JOIN search_sessions s ON r.session_id = s.id
WHERE r.drug_name = '다이아벡스정500mg'
ORDER BY s.started_at;

-- 현재 품절 중인 약품 목록 (마지막 세션 기준)
SELECT DISTINCT drug_name, distributor
FROM search_results
WHERE session_id = (SELECT MAX(id) FROM search_sessions)
  AND status = 'soldout';
```

---

## 마이그레이션 순서

1. `db.py` 생성 — DB 연결(WAL/busy_timeout/foreign_keys PRAGMA 적용), 스키마 버전 관리(`PRAGMA user_version`), 테이블 생성, UPSERT 유틸 함수
2. **기존 JSON 백업** (`*.json.bak` 등) 후 DB 초기 시딩 — **멱등 처리**(대상 테이블이 비어 있을 때만 시딩하여 재실행 중복 방지), **단일 트랜잭션**으로 묶고 실패 시 롤백
   - `data/drug_master.json` → `drug_master`
   - `geoweb-soldout-list.json` → `watch_list`
   - `exclusion-list.json` → `exclusion_list` (distributor 포함)
   - `config.json`의 distributors → `distributors`
3. **시딩 검증**: JSON 레코드 수 ↔ DB 레코드 수 대조, 샘플 값 확인
4. `file_manager.py`의 read/write 메서드를 DB 호출로 교체 — **메서드 시그니처·반환 형태(`List[Dict]` 등)는 그대로 유지**하여 `web_server.py` 라우트를 건드리지 않고 blast radius 최소화
5. `app_state.py`의 검색 결과 저장 로직을 `search_sessions` + `search_results`로 교체
6. 기존 `alert_exclusion_days` 만료 항목 자동 삭제 로직(`search_engine.py`)을 DELETE 쿼리로 이전
7. 기존 JSON 파일 보관 후 안정화되면 제거
   - 정리 대상: `data/app_state.json`(호출처 없음, unused), `data/search_results.json`(인메모리로 대체되어 미사용)도 함께 제거

---

## DB 파일 위치 (확정 필요 → 권장안)

엔트리(`run_app.py`)는 PyInstaller 번들로 패키징됨. `app_directory`는 `__file__` 기준이라(`models/config.py`)
프리징 시 **읽기 전용 번들 내부**를 가리킬 수 있음. DB는 반드시 **쓰기 가능한 위치**여야 함.

- 권장: 이미 쓰기 가능한 `data/` 디렉터리 사용 → **`data/yak_soldout.db`**
- 프리징 환경 분기 필요 시 `sys.frozen` / `sys._MEIPASS`로 실행 파일 경로 기준 해석

---

## 미결 사항

- 이력 보관 기간: `search_sessions`가 무한정 쌓이면 용량 이슈 → 일정 기간(예: 30일) 이후 자동 정리 여부 결정 필요
- 비밀번호 평문 저장: `distributors` 테이블에 평문 보관 (현재 `config.json`과 동일 수준). 추후 암호화 여부 별도 검토
- `monitoring` 설정을 `config.json`에 두는 현재 분리 구조 유지 여부 (설정 일부는 DB, 일부는 파일 → 일관성 측면 재검토 여지)
