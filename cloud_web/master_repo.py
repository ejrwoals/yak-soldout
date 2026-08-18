"""약품 마스터(drug_master) 조회 — Cloud Run 웹 UI 전용.

전달하는 client 의 역할에 따라 조회 범위가 결정된다:
- 로그인 사용자 세션(anon+JWT): RLS로 본인 약국 마스터만
- service_role: 전체 (개발/관리)
Supabase는 한 쿼리에 기본 1000행까지만 주므로 페이지네이션으로 전량을 가져온다.
"""

_PAGE = 1000
_COLS = "name, insurance_code, maker, maker_norm, unit, unit_manual"


def search_drug_master(client, q: str = "", limit: int = 50, offset: int = 0) -> tuple[list[dict], int]:
    """약품 DB 조회(읽기 전용) — 이름 부분일치 검색 + 페이지네이션. (rows, 전체 개수) 반환."""
    query = client.table("drug_master").select(_COLS, count="exact").order("name")
    if q:
        query = query.ilike("name", f"%{q}%")
    res = query.range(offset, offset + limit - 1).execute()
    return (res.data or []), (res.count or 0)


def fetch_drug_master(client) -> list[dict]:
    """drug_master 전체 행을 매칭용 dict 리스트로 반환(페이지네이션)."""
    rows: list[dict] = []
    start = 0
    while True:
        res = (
            client.table("drug_master")
            .select(_COLS)
            .order("name")
            .range(start, start + _PAGE - 1)
            .execute()
        )
        batch = res.data or []
        rows.extend(batch)
        if len(batch) < _PAGE:
            break
        start += _PAGE
    return rows
