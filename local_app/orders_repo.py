"""주문장 데이터 접근 계층 (스택 2 로컬 앱).

status='pending' 주문을 품목과 함께 읽어와 크롤링에 넘기고, 크롤링 결과를
Supabase에 write-back 한다. 전달하는 client는 **로그인된 세션**이어야 RLS를 통과해
자기 약국(user)의 주문만 조회된다.

상태 흐름: reviewing(웹) → pending(크롤링 대기) → ordered(담기 완료)
"""

from typing import Any

# position 미설정(None) 품목을 맨 뒤로 보내기 위한 큰 정렬키
_POS_LAST = 1_000_000


def get_pending_orders(client) -> list[dict[str, Any]]:
    """status='pending' 주문을 품목과 함께 오래된 순으로 반환.

    각 주문 dict의 'order_items'는 position(OCR 추출 순서) 오름차순 정렬된다.
    """
    res = (
        client.table("orders")
        .select("id, order_date, order_round, status, image_path, order_items(*)")
        .eq("status", "pending")
        .order("order_date")
        .order("order_round")
        .execute()
    )
    orders = res.data or []
    for order in orders:
        items = order.get("order_items") or []
        items.sort(key=lambda it: it.get("position") if it.get("position") is not None else _POS_LAST)
        order["order_items"] = items
    return orders


def set_item_cart_status(client, item_id: str, status: str) -> None:
    """품목의 크롤링 결과 기록. status ∈ {'none','added','failed'}."""
    if status not in ("none", "added", "failed"):
        raise ValueError(f"잘못된 cart_status: {status!r}")
    client.table("order_items").update({"cart_status": status}).eq("id", item_id).execute()


def mark_order_ordered(client, order_id: str) -> None:
    """주문 전체를 크롤링 완료(ordered) 상태로 전환."""
    client.table("orders").update({"status": "ordered"}).eq("id", order_id).execute()
