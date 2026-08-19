"""멀티테넌트(약국) 멤버십·초대 처리 — Cloud Run 웹 UI 전용.

전달 client 는 service_role 이어야 한다(멤버십/초대 쓰기는 RLS로는 막혀 있으므로,
서버가 토큰을 검증한 뒤 신뢰된 주체로 수행). 권한 검사는 이 계층/엔드포인트에서 명시적으로 한다.
"""

import secrets
from datetime import datetime, timezone


class InviteError(RuntimeError):
    """초대코드가 유효하지 않음(없음/만료/한도초과 등)."""


def get_membership(client, user_id: str) -> dict | None:
    """사용자의 (첫) 멤버십 반환: {pharmacy_id, role, pharmacy_name}. 없으면 None."""
    res = (
        client.table("memberships")
        .select("pharmacy_id, role, pharmacies(name)")
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    if not res.data:
        return None
    m = res.data[0]
    return {
        "pharmacy_id": m["pharmacy_id"],
        "role": m["role"],
        "pharmacy_name": (m.get("pharmacies") or {}).get("name"),
    }


def create_invite(client, pharmacy_id: str, created_by: str, role: str = "staff",
                  max_uses: int | None = None) -> str:
    """초대코드 발행 후 code 반환. (호출 전에 created_by 가 pharmacy admin 인지 확인할 것)"""
    if role not in ("staff", "admin"):
        raise ValueError("role 은 staff|admin")
    code = secrets.token_urlsafe(9)  # 추측 불가능한 랜덤 (~12자)
    client.table("invites").insert({
        "code": code,
        "pharmacy_id": pharmacy_id,
        "created_by": created_by,
        "role": role,
        "max_uses": max_uses,
    }).execute()
    return code


def accept_invite(client, user_id: str, code: str) -> dict:
    """초대코드로 멤버십 생성. 반환 {pharmacy_id, role}. 유효하지 않으면 InviteError."""
    code = (code or "").strip()
    if not code:
        raise InviteError("초대코드를 입력하세요.")

    res = client.table("invites").select("*").eq("code", code).limit(1).execute()
    if not res.data:
        raise InviteError("존재하지 않는 초대코드입니다.")
    inv = res.data[0]

    # 만료 검사
    exp = inv.get("expires_at")
    if exp:
        try:
            if datetime.fromisoformat(exp) < datetime.now(timezone.utc):
                raise InviteError("만료된 초대코드입니다.")
        except InviteError:
            raise
        except Exception:
            pass  # 파싱 실패 시 만료 검사 생략

    # 사용 한도 검사
    if inv.get("max_uses") is not None and inv.get("uses", 0) >= inv["max_uses"]:
        raise InviteError("사용 한도를 초과한 초대코드입니다.")

    pharmacy_id = inv["pharmacy_id"]

    # 이미 멤버면 그대로 반환 (재사용 안전)
    existing = (
        client.table("memberships")
        .select("role")
        .eq("user_id", user_id)
        .eq("pharmacy_id", pharmacy_id)
        .limit(1)
        .execute()
    )
    if existing.data:
        return {"pharmacy_id": pharmacy_id, "role": existing.data[0]["role"]}

    client.table("memberships").insert({
        "pharmacy_id": pharmacy_id,
        "user_id": user_id,
        "role": inv["role"],
    }).execute()
    client.table("invites").update({"uses": inv.get("uses", 0) + 1}).eq("code", code).execute()

    return {"pharmacy_id": pharmacy_id, "role": inv["role"]}
