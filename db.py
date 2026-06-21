"""
SQLite 데이터 액세스 레이어

기존 JSON 파일(geoweb-soldout-list.json, exclusion-list.json, config.json의
distributors, data/drug_master.json)을 SQLite로 통합 관리한다.

설계 원칙
- 날짜/시간은 ISO 포맷 문자열(`"2026-06-16T19:46:40"`, T 포함)을 앱 코드에서 명시적으로 INSERT.
  → SQLite DEFAULT(`datetime('now')`)는 공백 구분이라 프론트 파싱/정렬이 깨지므로 사용하지 않는다.
- 동시성: FastAPI 라우트(asyncio)와 백그라운드 검색 스레드(ThreadPoolExecutor)가 동시에 접근하므로
  WAL + busy_timeout + 스레드별 연결로 read/write 충돌을 회피한다.
"""

import sys
import json
import shutil
import sqlite3
import threading
from pathlib import Path
from contextlib import contextmanager
from typing import Any, Dict, List, Optional, Sequence

# 스키마 버전 — 향후 마이그레이션 시 증가
#  v1: 최초 스키마
#  v2: drug_master.insurance_code 를 nullable·비유니크로 완화(코드 컬럼 미매핑/규격별 코드중복 허용),
#      watch_list 의 미사용 FK 제거
#  v3: 주문지 OCR 저장용 orders/order_items 추가 (신규 테이블이라 IF NOT EXISTS로 생성, 별도 마이그레이션 불필요)
#  v4: drug_master.unit(포장단위/규격) 추가. 엑셀엔 규격 컬럼이 없어 기준 도매상 스크래핑으로 채운다.
#      기존 DB는 _ensure_column 으로 ALTER TABLE ADD COLUMN 처리(멱등).
#  v5: drug_master.unit_manual(사용자가 뷰어에서 직접 추가한 규격) 추가. 수집 unit과 출처를 분리하고
#      수집분은 삭제 불가(읽기전용), 직접추가분은 append-only로 운영한다. _ensure_column 처리.
SCHEMA_VERSION = 5

# 날짜/시간 ISO 포맷 (전 테이블 공통, T 포함, 초 단위)
ISO_LEN = 19


def _db_path() -> Path:
    """쓰기 가능한 DB 파일 경로. 프리징(PyInstaller) 환경에서도 data/는 쓰기 가능 위치."""
    if getattr(sys, "frozen", False):
        # PyInstaller 번들: 실행 파일 옆을 기준으로 data/ 사용
        base = Path(sys.executable).resolve().parent
    else:
        base = Path(__file__).resolve().parent
    data_dir = base / "data"
    data_dir.mkdir(exist_ok=True)
    return data_dir / "yak_soldout.db"


# ----------------------------------------------------------------------------
# 연결 관리 (스레드별 연결)
# ----------------------------------------------------------------------------
_local = threading.local()


def get_conn() -> sqlite3.Connection:
    """현재 스레드 전용 연결을 반환(없으면 생성). WAL/busy_timeout/foreign_keys 적용.

    ThreadPoolExecutor 워커 스레드가 종료되면 해당 스레드의 thread-local 연결도
    GC되어 자동 정리되므로 별도 close 관리가 필요 없다.
    """
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = sqlite3.connect(str(_db_path()), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA foreign_keys=ON")
        _local.conn = conn
    return conn


@contextmanager
def transaction():
    """쓰기 트랜잭션 컨텍스트. 정상 종료 시 commit, 예외 시 rollback."""
    conn = get_conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def query_all(sql: str, params: Sequence[Any] = ()) -> List[sqlite3.Row]:
    return get_conn().execute(sql, params).fetchall()


def query_one(sql: str, params: Sequence[Any] = ()) -> Optional[sqlite3.Row]:
    return get_conn().execute(sql, params).fetchone()


def execute(sql: str, params: Sequence[Any] = ()) -> sqlite3.Cursor:
    """단일 쓰기 실행 + 커밋. 마지막 row id 등은 반환 커서에서 확인."""
    with transaction() as conn:
        return conn.execute(sql, params)


# ----------------------------------------------------------------------------
# 스키마
# ----------------------------------------------------------------------------
_SCHEMA = """
CREATE TABLE IF NOT EXISTS drug_master (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    name           TEXT NOT NULL,
    insurance_code TEXT,
    maker          TEXT,
    maker_norm     TEXT,
    unit           TEXT,
    unit_manual    TEXT,
    imported_at    TEXT NOT NULL,
    source_file    TEXT
);

CREATE INDEX IF NOT EXISTS idx_drug_master_code ON drug_master(insurance_code);

CREATE TABLE IF NOT EXISTS watch_list (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    drug_name      TEXT NOT NULL UNIQUE,
    insurance_code TEXT,
    is_urgent      INTEGER NOT NULL DEFAULT 0,
    date_added     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS exclusion_list (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    drug_name   TEXT NOT NULL,
    distributor TEXT NOT NULL DEFAULT '',
    date        TEXT NOT NULL,
    is_pinned   INTEGER NOT NULL DEFAULT 0,
    UNIQUE(drug_name, distributor)
);

CREATE TABLE IF NOT EXISTS distributors (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    dist_key  TEXT NOT NULL UNIQUE,
    enabled   INTEGER NOT NULL DEFAULT 1,
    username  TEXT,
    password  TEXT,
    color     TEXT,
    region    TEXT
);

CREATE TABLE IF NOT EXISTS search_sessions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at   TEXT NOT NULL,
    duration_sec REAL,
    status       TEXT NOT NULL DEFAULT 'running'
);

CREATE TABLE IF NOT EXISTS search_results (
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
    status                 TEXT NOT NULL DEFAULT 'soldout',
    is_excluded_from_alert INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_search_results_session ON search_results(session_id);
CREATE INDEX IF NOT EXISTS idx_search_results_drug    ON search_results(drug_name);

CREATE TABLE IF NOT EXISTS orders (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    order_date  TEXT NOT NULL,                 -- 주문일자 YYYY-MM-DD
    order_round INTEGER NOT NULL,              -- 주문차수 1~3
    image_path  TEXT,                          -- 원본 주문지 이미지 파일명(data/order_images 기준)
    created_at  TEXT NOT NULL,                 -- 저장 시각(ISO)
    UNIQUE(order_date, order_round)            -- (날짜,차수) = 한 주문
);

CREATE TABLE IF NOT EXISTS order_items (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id     INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    drug_name    TEXT NOT NULL,                -- 검수 후 확정 약품명
    package_unit TEXT,                         -- 포장단위
    quantity     TEXT,                         -- 주문 수량(OCR 안정성 위해 문자열)
    position     INTEGER NOT NULL DEFAULT 0    -- 검수표 표시 순서
);

CREATE INDEX IF NOT EXISTS idx_order_items_order ON order_items(order_id);
"""


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, decl: str) -> None:
    """테이블에 컬럼이 없으면 ALTER TABLE ADD COLUMN 으로 추가(멱등).

    SQLite는 컬럼 추가는 ALTER로 지원하므로(제약 변경과 달리) 데이터 보존하며 안전하게 보강한다.
    """
    cols = [r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")


def init_schema() -> None:
    """테이블/인덱스 생성, 필요 시 마이그레이션, 스키마 버전 기록."""
    conn = get_conn()
    current = get_schema_version()

    # 기존 DB(v1)를 v2로 마이그레이션 (테이블 재구성, 데이터 보존)
    if 0 < current < 2:
        _migrate_to_v2(conn)

    # 누락 테이블/인덱스 보강 (신규 설치는 여기서 최신 스키마 생성)
    conn.executescript(_SCHEMA)
    # v4/v5: 기존 drug_master 테이블에 unit/unit_manual 컬럼 보강 (신규 설치는 이미 있으므로 no-op)
    _ensure_column(conn, "drug_master", "unit", "TEXT")
    _ensure_column(conn, "drug_master", "unit_manual", "TEXT")
    conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
    conn.commit()


def _migrate_to_v2(conn: sqlite3.Connection) -> None:
    """v1 → v2: drug_master.insurance_code 제약 완화 + watch_list FK 제거.

    SQLite는 ALTER로 제약을 못 바꾸므로 새 테이블을 만들어 데이터를 옮기고 교체한다.
    FK가 걸린 테이블을 재구성하므로 작업 동안 foreign_keys를 잠시 끈다.
    """
    conn.execute("PRAGMA foreign_keys=OFF")
    conn.executescript(
        """
        BEGIN;
        -- drug_master: insurance_code NOT NULL UNIQUE → nullable, 비유니크
        CREATE TABLE drug_master_v2 (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            name           TEXT NOT NULL,
            insurance_code TEXT,
            maker          TEXT,
            maker_norm     TEXT,
            imported_at    TEXT NOT NULL,
            source_file    TEXT
        );
        INSERT INTO drug_master_v2 (id, name, insurance_code, maker, maker_norm, imported_at, source_file)
            SELECT id, name, insurance_code, maker, maker_norm, imported_at, source_file FROM drug_master;
        DROP TABLE drug_master;
        ALTER TABLE drug_master_v2 RENAME TO drug_master;

        -- watch_list: drug_master 참조 FK 제거 (insurance_code는 평범한 nullable 컬럼)
        CREATE TABLE watch_list_v2 (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            drug_name      TEXT NOT NULL UNIQUE,
            insurance_code TEXT,
            is_urgent      INTEGER NOT NULL DEFAULT 0,
            date_added     TEXT NOT NULL
        );
        INSERT INTO watch_list_v2 (id, drug_name, insurance_code, is_urgent, date_added)
            SELECT id, drug_name, insurance_code, is_urgent, date_added FROM watch_list;
        DROP TABLE watch_list;
        ALTER TABLE watch_list_v2 RENAME TO watch_list;
        COMMIT;
        """
    )
    conn.execute("PRAGMA foreign_keys=ON")


def get_schema_version() -> int:
    row = query_one("PRAGMA user_version")
    return row[0] if row else 0


# ----------------------------------------------------------------------------
# drug_master 쓰기 유틸
# ----------------------------------------------------------------------------
def insert_drug_master(conn: sqlite3.Connection, drug: Dict[str, Any],
                       imported_at: str, source_file: str) -> None:
    """drug_master 행 1건 INSERT. insurance_code는 비어 있으면 NULL로 저장."""
    code = (drug.get("insurance_code") or "").strip()
    if code.lower() == "nan":  # pandas가 빈 셀을 'nan' 문자열로 주는 경우 정규화
        code = ""
    conn.execute(
        """INSERT INTO drug_master (name, insurance_code, maker, maker_norm, imported_at, source_file)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            drug.get("name", ""),
            code or None,
            drug.get("maker", ""),
            drug.get("maker_norm", "") or None,
            imported_at,
            source_file,
        ),
    )


def replace_drug_master(drugs: List[Dict[str, Any]], source_file: str, imported_at: str) -> int:
    """약품 마스터 전체 교체 (재임포트). 단일 트랜잭션으로 DELETE 후 INSERT.

    엑셀에는 포장단위(unit)가 없고 스크래핑으로 수집하므로, 재임포트로 기존에 모아둔
    unit이 사라지지 않도록 (약품명, 보험코드) 기준으로 보존해 복원한다.

    반환: 저장된 행 수.
    """
    with transaction() as conn:
        # 기존 규격 스냅샷 (name, code) → (수집 unit, 직접추가 unit_manual)
        prev_units: Dict[tuple, tuple] = {}
        for r in conn.execute(
            """SELECT name, insurance_code, unit, unit_manual FROM drug_master
               WHERE (unit IS NOT NULL AND unit != '')
                  OR (unit_manual IS NOT NULL AND unit_manual != '')"""
        ).fetchall():
            prev_units[(r["name"], r["insurance_code"] or "")] = (r["unit"], r["unit_manual"])

        conn.execute("DELETE FROM drug_master")
        for drug in drugs:
            insert_drug_master(conn, drug, imported_at, source_file)

        # 보존된 규격 복원 (동일 약품명+보험코드 행에만)
        for (name, code), (unit, unit_manual) in prev_units.items():
            conn.execute(
                """UPDATE drug_master SET unit = ?, unit_manual = ?
                   WHERE name = ? AND IFNULL(insurance_code, '') = ?""",
                (unit, unit_manual, name, code),
            )
        return conn.execute("SELECT COUNT(*) FROM drug_master").fetchone()[0]


def upsert_drug_master(drugs: List[Dict[str, Any]], source_file: str, imported_at: str) -> Dict[str, int]:
    """약품 마스터 병합(upsert). (약품명, 보험코드) 기준으로 있으면 갱신, 없으면 추가.

    전체 교체(replace)와 달리 새 파일에 없는 기존 약품은 삭제하지 않고 그대로 둔다.
    기존 행을 지우지 않으므로 수집/직접추가한 규격(unit, unit_manual)은 자연히 유지된다.
    (제약사 표기만 새 파일 값으로 갱신; 규격 컬럼은 건드리지 않는다.)

    반환: {"inserted": 신규, "updated": 갱신, "total": 전체 행 수}.
    """
    inserted = updated = 0
    with transaction() as conn:
        for drug in drugs:
            name = drug.get("name", "")
            code = (drug.get("insurance_code") or "").strip()
            if code.lower() == "nan":
                code = ""
            maker = drug.get("maker", "")
            maker_norm = drug.get("maker_norm", "") or None

            # (약품명 + 보험코드) 일치 행을 갱신; 없으면 INSERT.
            # 빈 보험코드는 NULL로 저장되므로 IFNULL로 비교를 맞춘다.
            cur = conn.execute(
                """UPDATE drug_master SET maker = ?, maker_norm = ?, imported_at = ?, source_file = ?
                   WHERE name = ? AND IFNULL(insurance_code, '') = ?""",
                (maker, maker_norm, imported_at, source_file, name, code),
            )
            if cur.rowcount and cur.rowcount > 0:
                updated += 1
            else:
                insert_drug_master(conn, drug, imported_at, source_file)
                inserted += 1

        total = conn.execute("SELECT COUNT(*) FROM drug_master").fetchone()[0]
    return {"inserted": inserted, "updated": updated, "total": total}


def load_drug_master() -> List[Dict[str, Any]]:
    """drug_master 전체를 매칭용 dict 리스트로 반환."""
    rows = query_all(
        "SELECT name, insurance_code, maker, maker_norm, unit, unit_manual FROM drug_master ORDER BY id"
    )
    return [
        {
            "name": r["name"],
            "insurance_code": r["insurance_code"] or "",
            "maker": r["maker"] or "",
            "maker_norm": r["maker_norm"] or "",
            "unit": r["unit"] or "",
            "unit_manual": r["unit_manual"] or "",
        }
        for r in rows
    ]


def drug_master_meta() -> Dict[str, Any]:
    """등록 현황 요약 (count/source_file/imported_at). 비어 있으면 count=0."""
    row = query_one("SELECT COUNT(*) AS c, MAX(imported_at) AS m FROM drug_master")
    count = row["c"] if row else 0
    if not count:
        return {"count": 0, "source_file": "", "imported_at": ""}
    latest = query_one(
        "SELECT source_file, imported_at FROM drug_master ORDER BY imported_at DESC, id DESC LIMIT 1"
    )
    return {
        "count": count,
        "source_file": (latest["source_file"] if latest else "") or "",
        "imported_at": (latest["imported_at"] if latest else "") or "",
    }


def drug_master_cache_key() -> tuple:
    """매처 캐시 무효화 신호. 임포트(전체교체)마다 MAX(id)/count/imported_at이 바뀜."""
    # unit/unit_manual 은 UPDATE 로만 바뀌어 count/id/imported_at 이 안 변하므로,
    # 규격 텍스트 총길이를 시그니처에 포함해 규격 수집·직접추가 시에도 매처 캐시가 갱신되게 한다.
    row = query_one(
        """SELECT COUNT(*) AS c, COALESCE(MAX(imported_at),'') AS m, COALESCE(MAX(id),0) AS x,
                  COALESCE(SUM(LENGTH(COALESCE(unit,'')) + LENGTH(COALESCE(unit_manual,''))), 0) AS u
           FROM drug_master"""
    )
    return (row["c"], row["m"], row["x"], row["u"]) if row else (0, "", 0, 0)


# ----------------------------------------------------------------------------
# drug_master 포장단위(unit) 수집
# ----------------------------------------------------------------------------
def drug_master_rows_missing_unit() -> List[Dict[str, Any]]:
    """포장단위(unit)가 비어 있고 보험코드가 있는 행만 반환 (스크래핑 수집 대상).

    보험코드가 없으면 코드로 검색할 수 없으므로 제외한다.
    """
    rows = query_all(
        """SELECT id, name, insurance_code FROM drug_master
           WHERE insurance_code IS NOT NULL AND TRIM(insurance_code) != ''
             AND (unit IS NULL OR TRIM(unit) = '')
           ORDER BY id"""
    )
    return [
        {"id": r["id"], "name": r["name"], "insurance_code": r["insurance_code"]}
        for r in rows
    ]


def update_drug_master_unit(row_id: int, unit: str) -> None:
    """drug_master 한 행의 포장단위(unit) 갱신. 빈 값은 NULL로 저장."""
    execute("UPDATE drug_master SET unit = ? WHERE id = ?", ((unit or "").strip() or None, row_id))


def drug_master_unit_stats() -> Dict[str, int]:
    """포장단위 수집 현황 요약.

    - total: 전체 행 수
    - filled: unit이 채워진 행 수
    - missing_with_code: unit이 비었지만 보험코드가 있어 수집 가능한 행 수
    """
    row = query_one(
        """SELECT
             COUNT(*) AS total,
             SUM(CASE WHEN unit IS NOT NULL AND TRIM(unit) != '' THEN 1 ELSE 0 END) AS filled,
             SUM(CASE WHEN (unit IS NULL OR TRIM(unit) = '')
                       AND insurance_code IS NOT NULL AND TRIM(insurance_code) != ''
                      THEN 1 ELSE 0 END) AS missing_with_code
           FROM drug_master"""
    )
    return {
        "total": (row["total"] if row else 0) or 0,
        "filled": (row["filled"] if row else 0) or 0,
        "missing_with_code": (row["missing_with_code"] if row else 0) or 0,
    }


# ----------------------------------------------------------------------------
# drug_master 테이블 뷰어 / 사용자 직접 규격 추가
# ----------------------------------------------------------------------------
def _split_units(s: str) -> List[str]:
    """", "로 합쳐 저장한 규격 문자열을 토큰 리스트로 분해(공백 정리·빈값 제거)."""
    return [u.strip() for u in (s or "").split(",") if u.strip()]


def list_drug_master_rows(offset: int = 0, limit: int = 50, q: str = "") -> Dict[str, Any]:
    """마스터 테이블을 페이지 단위로 조회(뷰어용). q는 약품명/보험코드 부분일치 검색.

    반환: {"total": 전체(검색 적용) 행 수, "rows": [...]}.
    """
    where, params = "", []
    if q.strip():
        where = "WHERE name LIKE ? OR insurance_code LIKE ?"
        like = f"%{q.strip()}%"
        params = [like, like]

    total = query_one(f"SELECT COUNT(*) AS c FROM drug_master {where}", params)["c"]
    rows = query_all(
        f"""SELECT id, name, insurance_code, maker, unit, unit_manual
            FROM drug_master {where} ORDER BY id LIMIT ? OFFSET ?""",
        params + [int(limit), int(offset)],
    )
    return {
        "total": total,
        "rows": [
            {
                "id": r["id"],
                "name": r["name"],
                "insurance_code": r["insurance_code"] or "",
                "maker": r["maker"] or "",
                "unit": r["unit"] or "",
                "unit_manual": r["unit_manual"] or "",
            }
            for r in rows
        ],
    }


def add_drug_master_manual_unit(row_id: int, unit: str) -> Optional[Dict[str, Any]]:
    """사용자가 직접 입력한 규격 1건을 unit_manual에 append(append-only, 삭제 없음).

    이미 수집(unit)되었거나 이미 직접추가(unit_manual)된 규격이면 중복 추가하지 않는다.
    반환: 행이 없으면 None. 있으면 {"added": bool, "unit_manual": 갱신된 문자열}.
    """
    unit = (unit or "").strip()
    row = query_one("SELECT unit, unit_manual FROM drug_master WHERE id = ?", (row_id,))
    if row is None:
        return None
    manual = _split_units(row["unit_manual"])
    if not unit:
        return {"added": False, "unit_manual": ", ".join(manual)}

    existing = set(_split_units(row["unit"])) | set(manual)
    if unit in existing:
        return {"added": False, "unit_manual": ", ".join(manual)}

    manual.append(unit)
    new_manual = ", ".join(manual)
    execute("UPDATE drug_master SET unit_manual = ? WHERE id = ?", (new_manual, row_id))
    return {"added": True, "unit_manual": new_manual}


def count_orphan_order_drugs() -> int:
    """주문서에만 있고 마스터에는 정확히 일치하는 이름이 없는 약품(자유입력 고아) 수.

    이름 기준 distinct. 마스터 소급 연결(order_reconcile) 대상 규모를 가늠하는 데 쓴다.
    """
    row = query_one(
        """SELECT COUNT(DISTINCT oi.drug_name) AS c
           FROM order_items oi
           WHERE TRIM(oi.drug_name) != ''
             AND NOT EXISTS (SELECT 1 FROM drug_master dm WHERE dm.name = oi.drug_name)"""
    )
    return (row["c"] if row else 0) or 0


def list_orphan_order_drugs() -> List[Dict[str, Any]]:
    """주문서 자유입력 약품(마스터 미일치) 목록.

    이름별로 주문 항목 수와 마지막 주문일자(MAX(order_date))를 함께, 최근 주문 순으로 반환한다.
    """
    rows = query_all(
        """SELECT oi.drug_name AS name, COUNT(*) AS cnt, MAX(o.order_date) AS last_date
           FROM order_items oi
           JOIN orders o ON o.id = oi.order_id
           WHERE TRIM(oi.drug_name) != ''
             AND NOT EXISTS (SELECT 1 FROM drug_master dm WHERE dm.name = oi.drug_name)
           GROUP BY oi.drug_name
           ORDER BY last_date DESC, oi.drug_name"""
    )
    return [
        {"name": r["name"], "item_count": r["cnt"], "last_order_date": r["last_date"] or ""}
        for r in rows
    ]


# ----------------------------------------------------------------------------
# 초기 시딩 (JSON → DB)
# ----------------------------------------------------------------------------
def _load_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"⚠️ 시딩용 JSON 읽기 실패({path.name}): {e}")
        return None


def _backup_once(path: Path) -> None:
    """원본 JSON을 *.json.bak로 1회 백업(이미 있으면 건너뜀)."""
    if path.exists():
        bak = path.with_suffix(path.suffix + ".bak")
        if not bak.exists():
            shutil.copy2(path, bak)


def _table_count(conn: sqlite3.Connection, table: str) -> int:
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def seed_from_json(app_directory: Path) -> Dict[str, int]:
    """기존 JSON 데이터를 DB로 초기 시딩. 멱등(테이블이 비어 있을 때만 시딩).

    전체를 단일 트랜잭션으로 묶어 실패 시 롤백한다.
    반환: 테이블별로 이번 호출에서 새로 시딩한 레코드 수.
    """
    app_directory = Path(app_directory)
    drug_master_path = app_directory / "data" / "drug_master.json"
    watch_path = app_directory / "geoweb-soldout-list.json"
    exclusion_path = app_directory / "exclusion-list.json"
    config_path = app_directory / "config.json"

    seeded = {"drug_master": 0, "watch_list": 0, "exclusion_list": 0, "distributors": 0}

    with transaction() as conn:
        # 1) drug_master
        if _table_count(conn, "drug_master") == 0:
            master = _load_json(drug_master_path)
            if master and master.get("drugs"):
                imported_at = master.get("imported_at", "")
                source_file = master.get("source_filename", "")
                for drug in master["drugs"]:
                    insert_drug_master(conn, drug, imported_at, source_file)
                    seeded["drug_master"] += 1

        # 2) watch_list (geoweb-soldout-list.json)
        if _table_count(conn, "watch_list") == 0:
            watch = _load_json(watch_path)
            if isinstance(watch, list):
                for item in watch:
                    if not isinstance(item, dict):
                        continue
                    name = (item.get("drugName") or "").strip()
                    if not name:
                        continue
                    conn.execute(
                        """INSERT OR IGNORE INTO watch_list
                           (drug_name, insurance_code, is_urgent, date_added)
                           VALUES (?, ?, ?, ?)""",
                        (
                            name,
                            None,
                            1 if item.get("isUrgent") else 0,
                            item.get("dateAdded", ""),
                        ),
                    )
                    seeded["watch_list"] += 1

        # 3) exclusion_list
        if _table_count(conn, "exclusion_list") == 0:
            exclusions = _load_json(exclusion_path)
            if isinstance(exclusions, list):
                for item in exclusions:
                    if not isinstance(item, dict):
                        continue
                    name = (item.get("drugName") or "").strip()
                    if not name:
                        continue
                    conn.execute(
                        """INSERT OR IGNORE INTO exclusion_list
                           (drug_name, distributor, date, is_pinned)
                           VALUES (?, ?, ?, ?)""",
                        (
                            name,
                            item.get("distributor", "") or "",
                            item.get("date", ""),
                            1 if item.get("isPinned") else 0,
                        ),
                    )
                    seeded["exclusion_list"] += 1

        # 4) distributors (config.json의 distributors 섹션)
        if _table_count(conn, "distributors") == 0:
            config = _load_json(config_path)
            if isinstance(config, dict):
                for dist_key, d in (config.get("distributors") or {}).items():
                    if not isinstance(d, dict):
                        continue
                    conn.execute(
                        """INSERT OR IGNORE INTO distributors
                           (dist_key, enabled, username, password, color, region)
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        (
                            dist_key,
                            1 if d.get("enabled", True) else 0,
                            d.get("username", ""),
                            d.get("password", ""),
                            d.get("color"),
                            d.get("region"),
                        ),
                    )
                    seeded["distributors"] += 1

    # 시딩에 성공했으면 원본 JSON 백업 (트랜잭션 커밋 이후)
    if any(seeded.values()):
        for p in (drug_master_path, watch_path, exclusion_path, config_path):
            _backup_once(p)

    return seeded


def init_db(app_directory: Path) -> Dict[str, int]:
    """앱 시작 시 1회 호출: 스키마 생성 + 멱등 시딩."""
    init_schema()
    return seed_from_json(app_directory)


# ----------------------------------------------------------------------------
# 검색 사이클 기록 (search_sessions / search_results)
# ----------------------------------------------------------------------------
def start_search_session(started_at: str) -> int:
    """검색 사이클 시작 행을 만들고 session_id 반환."""
    cur = execute(
        "INSERT INTO search_sessions (started_at, status) VALUES (?, 'running')",
        (started_at,),
    )
    return cur.lastrowid


def _result_row(session_id: int, drug: Dict[str, Any], status: str) -> tuple:
    return (
        session_id,
        drug.get("name", ""),
        drug.get("insurance_code") or None,
        drug.get("distributor", "") or "",
        drug.get("main_stock"),
        drug.get("incheon_stock"),
        (drug.get("notes") or None),
        drug.get("company"),
        drug.get("unit"),
        status,
        1 if drug.get("is_excluded_from_alert") else 0,
    )


def save_search_results(session_id: int,
                        found_drugs: List[Dict[str, Any]],
                        soldout_drugs: List[Dict[str, Any]],
                        errors: List[str],
                        duration_sec: float,
                        status: str = "completed") -> None:
    """사이클 결과(found/soldout/errors)를 한 트랜잭션으로 INSERT하고 세션을 마감.

    개별 INSERT 대신 사이클 단위 트랜잭션으로 묶어 동시성 부담을 줄인다.
    """
    rows: List[tuple] = []
    for d in found_drugs or []:
        rows.append(_result_row(session_id, d, "found"))
    for d in soldout_drugs or []:
        rows.append(_result_row(session_id, d, "soldout"))
    for err in errors or []:
        name, sep, rest = str(err).partition(":")
        rows.append((
            session_id,
            (name.strip() or str(err)),
            None,
            "",
            None,
            None,
            (rest.strip() or None) if sep else None,
            None,
            None,
            "error",
            0,
        ))

    with transaction() as conn:
        if rows:
            conn.executemany(
                """INSERT INTO search_results
                   (session_id, drug_name, insurance_code, distributor, main_stock,
                    incheon_stock, notes, company, unit, status, is_excluded_from_alert)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                rows,
            )
        conn.execute(
            "UPDATE search_sessions SET duration_sec = ?, status = ? WHERE id = ?",
            (duration_sec, status, session_id),
        )


def fail_search_session(session_id: int, duration_sec: float = None) -> None:
    """사이클 실행이 실패했을 때 세션 상태를 'error'로 마감."""
    execute(
        "UPDATE search_sessions SET status = 'error', duration_sec = ? WHERE id = ?",
        (duration_sec, session_id),
    )


# ----------------------------------------------------------------------------
# 주문지 OCR 저장 (orders / order_items)
# ----------------------------------------------------------------------------
def order_image_dir() -> Path:
    """원본 주문지 이미지를 보관할 디렉터리(없으면 생성). DB와 같은 data/ 아래에 둔다."""
    d = _db_path().parent / "order_images"
    d.mkdir(exist_ok=True)
    return d


def order_exists(order_date: str, order_round: int) -> bool:
    """같은 (날짜, 차수) 주문이 이미 저장돼 있는지 여부."""
    row = query_one(
        "SELECT 1 FROM orders WHERE order_date = ? AND order_round = ?",
        (order_date, order_round),
    )
    return row is not None


def save_order(order_date: str, order_round: int, items: List[Dict[str, Any]],
               image_path: Optional[str], created_at: str) -> int:
    """검수 완료된 주문 1건을 저장하고 order_id 반환.

    같은 (날짜, 차수) 주문이 이미 있으면 기존 주문을 삭제하고 새로 저장한다(덮어쓰기).
    order_items 는 orders FK의 ON DELETE CASCADE로 함께 정리되므로 별도 삭제가 필요 없다.
    호출 전에 덮어쓰기 동의는 라우트(409 → 사용자 확인)에서 받는다.
    """
    with transaction() as conn:
        existing = conn.execute(
            "SELECT id FROM orders WHERE order_date = ? AND order_round = ?",
            (order_date, order_round),
        ).fetchone()
        if existing:
            conn.execute("DELETE FROM orders WHERE id = ?", (existing["id"],))
        cur = conn.execute(
            "INSERT INTO orders (order_date, order_round, image_path, created_at) VALUES (?, ?, ?, ?)",
            (order_date, order_round, image_path, created_at),
        )
        order_id = cur.lastrowid
        rows = [
            (order_id, it.get("drug_name", ""), it.get("package_unit", "") or None,
             it.get("quantity", "") or None, i)
            for i, it in enumerate(items)
        ]
        if rows:
            conn.executemany(
                """INSERT INTO order_items (order_id, drug_name, package_unit, quantity, position)
                   VALUES (?, ?, ?, ?, ?)""",
                rows,
            )
        return order_id


def list_orders() -> List[Dict[str, Any]]:
    """저장된 모든 주문 요약을 최신순으로 반환 (달력 표시용).

    각 주문의 품목 수(item_count)와 이미지 보유 여부(has_image)를 함께 준다.
    """
    rows = query_all(
        """SELECT o.id, o.order_date, o.order_round, o.image_path, o.created_at,
                  COUNT(oi.id) AS item_count
           FROM orders o
           LEFT JOIN order_items oi ON oi.order_id = o.id
           GROUP BY o.id
           ORDER BY o.order_date DESC, o.order_round ASC"""
    )
    return [
        {
            "id": r["id"],
            "order_date": r["order_date"],
            "order_round": r["order_round"],
            "item_count": r["item_count"],
            "has_image": bool(r["image_path"]),
            "created_at": r["created_at"],
        }
        for r in rows
    ]


def get_order(order_id: int) -> Optional[Dict[str, Any]]:
    """주문 1건의 상세(메타 + 품목 목록). 없으면 None."""
    o = query_one(
        "SELECT id, order_date, order_round, image_path, created_at FROM orders WHERE id = ?",
        (order_id,),
    )
    if o is None:
        return None
    items = query_all(
        """SELECT drug_name, package_unit, quantity
           FROM order_items WHERE order_id = ? ORDER BY position""",
        (order_id,),
    )
    return {
        "id": o["id"],
        "order_date": o["order_date"],
        "order_round": o["order_round"],
        "image_path": o["image_path"],
        "created_at": o["created_at"],
        "items": [
            {
                "drug_name": it["drug_name"],
                "package_unit": it["package_unit"] or "",
                "quantity": it["quantity"] or "",
            }
            for it in items
        ],
    }


def delete_order(order_id: int) -> Optional[str]:
    """주문 1건 삭제(품목은 FK CASCADE).

    반환:
      - 주문이 없으면 None (호출 측 404 처리)
      - 삭제 성공 시 image_path 문자열. 이미지가 없던 주문이면 빈 문자열("").
    호출 측은 반환된 파일명으로 원본 이미지 파일도 함께 정리한다.
    """
    row = query_one("SELECT image_path FROM orders WHERE id = ?", (order_id,))
    if row is None:
        return None
    execute("DELETE FROM orders WHERE id = ?", (order_id,))
    return row["image_path"] or ""


def delete_expired_exclusions(exclusion_days: int, now_iso: str) -> int:
    """비고정(is_pinned=0) & date가 exclusion_days보다 오래된 제외 항목 삭제.

    날짜 비교는 ISO 문자열 앞 10자리(YYYY-MM-DD)의 julianday 차이로 수행한다.
    반환: 삭제된 행 수.
    """
    cur = execute(
        """DELETE FROM exclusion_list
           WHERE is_pinned = 0
             AND date != ''
             AND julianday(?) - julianday(substr(date, 1, 10)) > ?""",
        (now_iso[:10], exclusion_days),
    )
    return cur.rowcount
