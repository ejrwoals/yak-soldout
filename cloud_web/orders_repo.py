"""검토 완료된 주문 저장 — Cloud Run 웹 UI 전용.

이미지를 Supabase Storage(order-images/<user_id>/…)에 올리고, orders/order_items 를
status='pending' 으로 저장한다. (날짜, 차수)가 이미 있으면 DuplicateOrderError.
전달 client 는 로그인 사용자 세션이어야 RLS/Storage 정책을 통과한다.
"""

import uuid

_MIME_EXT = {
    "image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp",
    "image/heic": ".heic", "image/heif": ".heif",
}


class DuplicateOrderError(RuntimeError):
    """같은 (user_id, order_date, order_round) 주문이 이미 존재."""


def _upload_image(client, user_id: str, order_date: str, order_round: int,
                  image_bytes: bytes, mime: str) -> str:
    ext = _MIME_EXT.get(mime, ".jpg")
    # Storage 키는 ASCII만 허용 → 한글 없이 구성 (r{차수})
    path = f"{user_id}/{order_date}_r{order_round}_{uuid.uuid4().hex[:8]}{ext}"
    client.storage.from_("order-images").upload(
        path, image_bytes, {"content-type": mime, "upsert": "false"}
    )
    return path


def save_reviewed_order(client, user_id: str, order_date: str, order_round: int,
                        items: list[dict], image_bytes: bytes | None = None,
                        image_mime: str | None = None) -> str:
    """주문 저장 후 order_id 반환. 중복이면 DuplicateOrderError."""
    # 중복 선검사 (친절한 메시지용). 경합 시 unique 제약이 최종 방어.
    dup = (
        client.table("orders")
        .select("id")
        .eq("user_id", user_id)
        .eq("order_date", order_date)
        .eq("order_round", order_round)
        .execute()
    )
    if dup.data:
        raise DuplicateOrderError(f"{order_date} {order_round}차 주문이 이미 저장돼 있습니다.")

    image_path = None
    if image_bytes:
        image_path = _upload_image(client, user_id, order_date, order_round, image_bytes, image_mime or "image/jpeg")

    order = (
        client.table("orders")
        .insert({
            "user_id": user_id,
            "order_date": order_date,
            "order_round": order_round,
            "status": "pending",
            "image_path": image_path,
        })
        .execute()
    ).data[0]
    order_id = order["id"]

    rows = []
    for pos, it in enumerate(items, start=1):
        name = (it.get("drug_name") or "").strip()
        if not name:
            continue  # 빈 약품명 행은 저장하지 않음
        rows.append({
            "order_id": order_id,
            "drug_name": name,
            "package_unit": (it.get("package_unit") or "").strip() or None,
            "quantity": (it.get("quantity") or "").strip() or None,
            "position": pos,
        })
    if rows:
        client.table("order_items").insert(rows).execute()

    return order_id
