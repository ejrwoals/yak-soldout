"""drug_master 데이터 이전: 로컬 SQLite → Supabase.

품절앱의 로컬 DB(data/yak_soldout.db)에 있는 약품 마스터를 자동주문 솔루션의
Supabase drug_master 로 옮긴다. 재실행 안전(멱등): 대상 사용자의 기존 drug_master 를
모두 지우고 전량 재삽입("replace" 방식, 로컬 replace_drug_master 와 동일 개념).

로컬 DB는 읽기 전용으로만 연다(품절앱 데이터 불변).
service_role 키로 실행하므로 RLS를 우회한다(개발/관리 도구).

전제: apps/cloud_web/.env 에 SUPABASE_URL, SUPABASE_SERVICE_KEY.
실행:
  uv run python scripts/migrate_drug_master.py                 # devtest 계정으로
  uv run python scripts/migrate_drug_master.py --email you@gmail.com
  uv run python scripts/migrate_drug_master.py --user-id <uuid>
"""

import argparse
import os
import sqlite3
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / "apps" / "cloud_web" / ".env")

DB_PATH = ROOT / "apps" / "soldout" / "data" / "yak_soldout.db"
DEFAULT_EMAIL = "devtest.yaksoldout@gmail.com"
CHUNK = 500

COLUMNS = ["name", "insurance_code", "maker", "maker_norm", "unit", "unit_manual", "source", "imported_at", "source_file"]


def read_local_rows() -> list[dict]:
    if not DB_PATH.exists():
        raise SystemExit(f"로컬 DB를 찾을 수 없습니다: {DB_PATH}")
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(f"SELECT {', '.join(COLUMNS)} FROM drug_master ORDER BY id").fetchall()
    conn.close()
    out = []
    for r in rows:
        d = {c: r[c] for c in COLUMNS}
        d["source"] = d.get("source") or "excel"
        # imported_at 이 비어 있으면 null (timestamptz)
        if not (d.get("imported_at") or "").strip():
            d["imported_at"] = None
        out.append(d)
    return out


def resolve_user_id(client, email: str | None, user_id: str | None) -> str:
    if user_id:
        return user_id
    users = client.auth.admin.list_users()
    for u in users:
        if getattr(u, "email", None) == email:
            return u.id
    raise SystemExit(
        f"'{email}' 계정을 찾을 수 없습니다. --user-id 로 직접 지정하거나 "
        "먼저 그 계정으로 로그인/생성하세요."
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--email", default=DEFAULT_EMAIL, help="대상 사용자 이메일 (기본: devtest)")
    ap.add_argument("--user-id", default=None, help="대상 사용자 UUID (이메일 대신 직접 지정)")
    args = ap.parse_args()

    url = os.environ.get("SUPABASE_URL", "").strip()
    service_key = os.environ.get("SUPABASE_SERVICE_KEY", "").strip()
    if not url or not service_key:
        raise SystemExit("apps/cloud_web/.env 에 SUPABASE_URL / SUPABASE_SERVICE_KEY 가 필요합니다.")

    from supabase import create_client

    client = create_client(url, service_key)
    user_id = resolve_user_id(client, args.email, args.user_id)

    rows = read_local_rows()
    print(f"로컬 drug_master {len(rows)}건 읽음 → user_id={user_id[:8]}… 로 이전")

    # 기존 것 비우기 (replace)
    client.table("drug_master").delete().eq("user_id", user_id).execute()

    inserted = 0
    for i in range(0, len(rows), CHUNK):
        chunk = [{**r, "user_id": user_id} for r in rows[i : i + CHUNK]]
        client.table("drug_master").insert(chunk).execute()
        inserted += len(chunk)
        print(f"  ...{inserted}/{len(rows)}")

    total = client.table("drug_master").select("id", count="exact").eq("user_id", user_id).execute()
    print(f"✅ 완료. Supabase drug_master (해당 사용자) 총 {total.count}건")


if __name__ == "__main__":
    main()
