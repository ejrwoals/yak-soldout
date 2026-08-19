"""개발용 원클릭 스모크 테스트 (service_role 키 사용).

로컬 앱 데이터 계층(local_app/orders_repo)이 Supabase에서 pending 주문을 읽어오는지
한 번에 확인한다. service_role 키로:
  ① 확인된 테스트 계정 생성(멱등, 메일 발송 없음) → ② 샘플 주문 시드(멱등) → ③ 조회·출력.
사람 개입(대시보드 클릭/시드 SQL/UID 복사)이 전혀 없다.

실행:  uv run python scripts/dev_smoke.py

전제: apps/cloud_web/.env 에 SUPABASE_URL, SUPABASE_SERVICE_KEY 가 채워져 있어야 함.
      (cp apps/cloud_web/.env.example apps/cloud_web/.env 후 service_role 키 붙여넣기)

주의: service_role 키는 RLS를 우회한다 → 이 스크립트는 개발 도구이며, 배포 앱(local_app)에는
      service 키를 넣지 않는다. 이 테스트는 '데이터 계층 동작' 확인용(연결·쿼리·시드·조회).
정리: 테스트 계정 = devtest.yaksoldout@gmail.com. Supabase Authentication → Users 에서
      삭제하면 관련 주문도 FK cascade로 함께 삭제된다.
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / "apps" / "cloud_web" / ".env")
sys.path.insert(0, str(ROOT / "local_app"))

from orders_repo import get_pending_orders  # noqa: E402

TEST_EMAIL = "devtest.yaksoldout@gmail.com"
TEST_PASSWORD = "devtest-password-1234"


def ensure_test_user(client) -> str:
    """확인된 테스트 계정을 만들거나(이미 있으면 찾아서) user id 반환. 메일 발송 없음."""
    try:
        res = client.auth.admin.create_user(
            {"email": TEST_EMAIL, "password": TEST_PASSWORD, "email_confirm": True}
        )
        return res.user.id
    except Exception:
        # 이미 존재 → 목록에서 이메일로 찾는다
        users = client.auth.admin.list_users()
        for u in users:
            if getattr(u, "email", None) == TEST_EMAIL:
                return u.id
        raise


def ensure_seed(client, user_id: str) -> None:
    """해당 사용자에게 pending 주문이 없으면 샘플 1건(품목 3개)을 심는다(멱등)."""
    existing = (
        client.table("orders")
        .select("id")
        .eq("user_id", user_id)
        .eq("status", "pending")
        .execute()
    )
    if existing.data:
        return
    order = (
        client.table("orders")
        .insert({"user_id": user_id, "order_date": "2026-08-01", "order_round": 1, "status": "pending"})
        .execute()
    ).data[0]
    client.table("order_items").insert(
        [
            {"order_id": order["id"], "drug_name": "레복사신 500mg", "package_unit": "30정", "quantity": "2", "position": 1},
            {"order_id": order["id"], "drug_name": "리포덱스 600mg", "package_unit": "100정", "quantity": "3", "position": 2},
            {"order_id": order["id"], "drug_name": "아트로벤트", "package_unit": "", "quantity": "15", "position": 3},
        ]
    ).execute()


def main() -> None:
    url = os.environ.get("SUPABASE_URL", "").strip()
    service_key = os.environ.get("SUPABASE_SERVICE_KEY", "").strip()
    if not url or not service_key:
        raise SystemExit(
            "apps/cloud_web/.env 에 SUPABASE_URL / SUPABASE_SERVICE_KEY 가 필요합니다.\n"
            "  cp apps/cloud_web/.env.example apps/cloud_web/.env  후 Project Settings → API 의 "
            "service_role key 를 SUPABASE_SERVICE_KEY 에 붙여넣으세요."
        )

    from supabase import create_client

    client = create_client(url, service_key)

    user_id = ensure_test_user(client)
    ensure_seed(client, user_id)
    orders = [o for o in get_pending_orders(client) if o.get("order_items")]

    print(f"✅ pending 주문 {len(orders)}건 (service_role 조회)")
    for o in orders:
        print(f"- {o['order_date']} {o['order_round']}차 · {len(o['order_items'])}품목")
        for it in o["order_items"]:
            print(
                f"    · {it['drug_name']} | 포장 {it.get('package_unit')!r} "
                f"| 수량 {it.get('quantity')!r} | cart={it.get('cart_status')}"
            )


if __name__ == "__main__":
    main()
