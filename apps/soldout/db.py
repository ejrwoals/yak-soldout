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
#  v6: order_items.distributor(약품별 주문 도매상 dist_key) 추가. 검수 후 도매상 선택 단계에서 채운다.
#      기존 주문에는 도매상 이력이 없어 NULL로 남는다. _ensure_column 처리(멱등).
#  v7: drug_master.source('excel'|'manual') 추가. 주문서 자유입력 약품을 마스터에 manual 행으로 자동 등록해
#      OCR 매칭·직접검색에 포함시킨다. 엑셀 임포트분과 구분하며, 기존 행은 NULL→'excel'로 간주. _ensure_column 처리.
SCHEMA_VERSION = 7

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
    # (v4~v7 의 drug_master/order_items 컬럼 보강은 OCR 기능과 함께 legacy_codes/ 로 이전됨.
    #  기존 DB 의 해당 테이블·데이터는 건드리지 않고 그대로 남는다.)
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
    watch_path = app_directory / "geoweb-soldout-list.json"
    exclusion_path = app_directory / "exclusion-list.json"
    config_path = app_directory / "config.json"

    seeded = {"watch_list": 0, "exclusion_list": 0, "distributors": 0}

    with transaction() as conn:
        # 1) watch_list (geoweb-soldout-list.json)
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

        # 2) exclusion_list
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

        # 3) distributors (config.json의 distributors 섹션)
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
        for p in (watch_path, exclusion_path, config_path):
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
