"""개발용: 저장 경로(orders/order_items + Storage 업로드) 검증.

service_role 로 devtest 사용자에게 샘플 주문을 저장하고, 다시 읽어 확인한다.
(브라우저 로그인 저장 전, 저장 로직 자체를 de-risk)

실행: uv run python scripts/dev_save.py
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / "cloud_web" / ".env")
sys.path.insert(0, str(ROOT / "cloud_web"))

import orders_repo  # noqa: E402

TEST_EMAIL = "devtest.yaksoldout@gmail.com"
DATE, ROUND = "2026-08-01", 3


def tiny_png() -> bytes:
    from PIL import Image, ImageDraw
    import io
    im = Image.new("RGB", (300, 120), "white")
    ImageDraw.Draw(im).text((10, 50), "dev save test", fill="black")
    buf = io.BytesIO(); im.save(buf, "PNG"); return buf.getvalue()


def main() -> None:
    url = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get("SUPABASE_SERVICE_KEY", "").strip()
    if not url or not key:
        raise SystemExit("cloud_web/.env 에 SUPABASE_URL / SUPABASE_SERVICE_KEY 필요")

    from supabase import create_client
    client = create_client(url, key)

    users = client.auth.admin.list_users()
    user_id = next((u.id for u in users if getattr(u, "email", None) == TEST_EMAIL), None)
    if not user_id:
        raise SystemExit("devtest 계정이 없습니다. scripts/dev_smoke.py 를 먼저 실행하세요.")

    # 재실행 위해 같은 (날짜,차수) 기존 주문 삭제 (order_items는 cascade)
    client.table("orders").delete().eq("user_id", user_id).eq("order_date", DATE).eq("order_round", ROUND).execute()

    items = [
        {"drug_name": "징코로민정", "package_unit": "30정", "quantity": "10"},
        {"drug_name": "아트로벤트흡입액유디비", "package_unit": "", "quantity": "15"},
        {"drug_name": "부스론정5밀리그램", "package_unit": "30정", "quantity": "5"},
    ]
    order_id = orders_repo.save_reviewed_order(
        client, user_id, DATE, ROUND, items, image_bytes=tiny_png(), image_mime="image/png"
    )
    print(f"✅ 저장 성공 order_id={order_id[:8]}…")

    # 검증: 주문 + 품목 + 이미지 경로 다시 읽기
    order = client.table("orders").select("*, order_items(*)").eq("id", order_id).single().execute().data
    print(f"   status={order['status']}  image_path={order['image_path']}")
    print(f"   품목 {len(order['order_items'])}개:")
    for it in sorted(order["order_items"], key=lambda x: x["position"]):
        print(f"     {it['position']}. {it['drug_name']} | {it['package_unit']} | {it['quantity']} | cart={it['cart_status']}")

    # Storage 객체 존재 확인
    folder = order["image_path"].split("/")[0]
    listing = client.storage.from_("order-images").list(folder)
    names = [o["name"] for o in listing]
    fname = order["image_path"].split("/")[-1]
    print(f"   Storage order-images/{folder}/ 에 이미지 존재: {fname in names}")


if __name__ == "__main__":
    main()
