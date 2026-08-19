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


def get_order_context(client, drug_names: list[str], exclude_order_id: str | None = None) -> dict:
    """도매상 선택 단계용 — 약품명별 과거 주문 이력(최신순)과 마지막 도매상.

    exclude_order_id 를 주면 그 주문(지금 검수 중인 주문)의 품목은 이력에서 제외한다.
    반환: {약품명: {"last_distributor": str|None,
                    "history": [{order_date, order_round, distributor, quantity, package_unit}, ...]}}
    """
    names = [str(n).strip() for n in drug_names if str(n or "").strip()]
    out: dict[str, dict] = {}
    if not names:
        return out
    res = (
        client.table("order_items")
        .select("drug_name, package_unit, quantity, distributor, orders!inner(id, order_date, order_round)")
        .in_("drug_name", names)
        .execute()
    )
    rows = res.data or []
    rows.sort(
        key=lambda r: ((r.get("orders") or {}).get("order_date") or "",
                       (r.get("orders") or {}).get("order_round") or 0),
        reverse=True,
    )
    for r in rows:
        o = r.get("orders") or {}
        if exclude_order_id and o.get("id") == exclude_order_id:
            continue
        h = out.setdefault(r["drug_name"], {"last_distributor": None, "history": []})
        h["history"].append({
            "order_date": o.get("order_date") or "",
            "order_round": o.get("order_round") or 0,
            "distributor": r.get("distributor") or "",
            "quantity": r.get("quantity") or "",
            "package_unit": r.get("package_unit") or "",
        })
    for h in out.values():
        h["last_distributor"] = next((x["distributor"] for x in h["history"] if x["distributor"]), None)
    return out


def set_item_distributor(client, item_id: str, distributor: str | None) -> None:
    """품목의 주문 도매상(dist_key) 지정. 빈 값이면 미지정(NULL)."""
    client.table("order_items").update({"distributor": distributor or None}).eq("id", item_id).execute()


def set_item_cart_status(client, item_id: str, status: str) -> None:
    """품목의 크롤링 결과 기록. status ∈ {'none','added','failed'}."""
    if status not in ("none", "added", "failed"):
        raise ValueError(f"잘못된 cart_status: {status!r}")
    client.table("order_items").update({"cart_status": status}).eq("id", item_id).execute()


def mark_order_ordered(client, order_id: str) -> None:
    """주문 전체를 크롤링 완료(ordered) 상태로 전환."""
    client.table("orders").update({"status": "ordered"}).eq("id", order_id).execute()
