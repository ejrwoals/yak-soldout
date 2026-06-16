# SQLite DB 마이그레이션 계획

## 배경

현재 모든 데이터를 JSON 파일로 관리하고 있음. 아래 한계점을 해결하기 위해 SQLite로 이전.

- 검색 결과를 마지막 1회분(`search_results.json`)만 보관 → 이력 추적 불가
- 품절 시작 시점 추적 불가
- 파일 간 관계(무결성) 없음

---

## 스키마 설계

### 1. `drug_master` — 마스터 약품 목록

XLS 파일에서 임포트. 재임포트 시 UPSERT(덮어쓰기+신규추가) 처리.

```sql
CREATE TABLE drug_master (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    name           TEXT NOT NULL,
    insurance_code TEXT NOT NULL UNIQUE,
    maker          TEXT,
    maker_norm     TEXT,
    imported_at    DATETIME NOT NULL,
    source_file    TEXT
);
```

- `insurance_code` 기준으로 UPSERT → 재임포트해도 기존 FK 깨지지 않음
- 기존 `data/drug_master.json` 데이터를 초기 시딩

---

### 2. `watch_list` — 모니터링 대상 약품 목록

현재 `geoweb-soldout-list.json` 대체.

```sql
CREATE TABLE watch_list (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    drug_name      TEXT NOT NULL UNIQUE,
    insurance_code TEXT REFERENCES drug_master(insurance_code) ON DELETE SET NULL,
    is_urgent      BOOLEAN NOT NULL DEFAULT 0,
    date_added     DATETIME NOT NULL DEFAULT (datetime('now', 'localtime'))
);
```

- `insurance_code`는 Nullable FK: 마스터에 있으면 연결, 없어도 `drug_name`만으로 모니터링 가능
- 마스터에 없는 약품을 추가할 때 강제로 마스터 등록할 필요 없음

---

### 3. `exclusion_list` — 알림 제외 목록

현재 `exclusion-list.json` 대체.

```sql
CREATE TABLE exclusion_list (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    drug_name  TEXT NOT NULL,
    date       DATETIME NOT NULL DEFAULT (datetime('now', 'localtime')),
    is_pinned  BOOLEAN NOT NULL DEFAULT 0
);
```

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
    region    TEXT  -- geopharm의 'daegu' 등 추가 파라미터
);
```

- `monitoring` 설정(`repeat_interval_minutes`, `alert_exclusion_days`)은 `config.json`에 그대로 유지

---

### 5. `search_sessions` — 검색 사이클 단위 기록

```sql
CREATE TABLE search_sessions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at   DATETIME NOT NULL DEFAULT (datetime('now', 'localtime')),
    duration_sec REAL,
    status       TEXT NOT NULL DEFAULT 'running'  -- 'running', 'completed', 'error'
);
```

---

### 6. `search_results` — 약품 × 도매상 단위 검색 결과

```sql
CREATE TABLE search_results (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id            INTEGER NOT NULL REFERENCES search_sessions(id) ON DELETE CASCADE,
    drug_name             TEXT NOT NULL,
    insurance_code        TEXT,
    distributor           TEXT NOT NULL,
    main_stock            TEXT,
    incheon_stock         TEXT,
    notes                 TEXT,
    company               TEXT,
    unit                  TEXT,
    is_found              BOOLEAN NOT NULL DEFAULT 0,
    is_excluded_from_alert BOOLEAN NOT NULL DEFAULT 0
);

CREATE INDEX idx_search_results_session ON search_results(session_id);
CREATE INDEX idx_search_results_drug    ON search_results(drug_name);
```

- `session_id`로 JOIN하면 특정 회차 결과 조회 가능
- `drug_name` + `is_found` + `started_at`으로 "언제부터 품절이었나" 추적 가능

---

## 활용 예시 쿼리

```sql
-- 특정 약품의 품절 시작 시점 추적
SELECT s.started_at, r.distributor, r.main_stock
FROM search_results r
JOIN search_sessions s ON r.session_id = s.id
WHERE r.drug_name = '다이아벡스정500mg'
ORDER BY s.started_at;

-- 현재 품절 중인 약품 목록 (마지막 세션 기준)
SELECT DISTINCT drug_name, distributor
FROM search_results
WHERE session_id = (SELECT MAX(id) FROM search_sessions)
  AND is_found = 0;
```

---

## 마이그레이션 순서

1. `db.py` 생성 — DB 연결, 테이블 생성, UPSERT 유틸 함수
2. 기존 JSON → DB 초기 시딩
   - `drug_master.json` → `drug_master`
   - `geoweb-soldout-list.json` → `watch_list`
   - `exclusion-list.json` → `exclusion_list`
   - `config.json`의 distributors → `distributors`
3. `file_manager.py`의 read/write 메서드를 DB 호출로 교체
4. `app_state.py`의 검색 결과 저장 로직을 `search_sessions` + `search_results`로 교체
5. 기존 JSON 파일 보관 후 안정화되면 제거

---

## 미결 사항

- DB 파일 위치: `app_directory / yak_soldout.db`로 통일 예정
- 이력 보관 기간: `search_sessions`가 무한정 쌓이면 용량 이슈 → 일정 기간(예: 30일) 이후 자동 정리 여부 결정 필요
- 비밀번호 평문 저장: `distributors` 테이블에 평문 보관 (현재 `config.json`과 동일 수준). 추후 암호화 여부 별도 검토
