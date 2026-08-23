"""약품 마스터(drug_master) 조회 — Cloud Run 웹 UI 전용.

전달하는 client 의 역할에 따라 조회 범위가 결정된다:
- 로그인 사용자 세션(anon+JWT): RLS로 본인 약국 마스터만
- service_role: 전체 (개발/관리)
Supabase는 한 쿼리에 기본 1000행까지만 주므로 페이지네이션으로 전량을 가져온다.
"""

from datetime import datetime

_PAGE = 1000
_COLS = "name, insurance_code, maker, maker_norm, unit, unit_manual, source"


def register_free_input_drugs(client, pharmacy_id: str, items: list[dict]) -> dict:
    """주문 저장 시, 마스터에 없는 자유입력 약품을 'manual' 행으로 자동 등록.

    자유입력 약품도 사용자가 확인한 신뢰도 높은 이름이므로 마스터에 넣어두면 이후
    OCR 매칭·자동완성에 활용된다. 같은 이름이 이미 있으면 건너뛰고, 입력한
    포장단위는 unit_manual 로 함께 저장한다. 반환 {"added": n, "names": [...]}.
    """
    names, units = [], {}
    for it in items:
        n = (it.get("drug_name") or "").strip()
        if not n or n in names:
            continue
        names.append(n)
        u = (it.get("package_unit") or "").strip()
        if u:
            units[n] = u
    if not names:
        return {"added": 0, "names": []}

    res = (
        client.table("drug_master").select("name")
        .eq("pharmacy_id", pharmacy_id).in_("name", names).execute()
    )
    existing = {r["name"] for r in (res.data or [])}
    imported_at = datetime.now().astimezone().isoformat(timespec="seconds")
    rows = [
        {
            "pharmacy_id": pharmacy_id,
            "name": n,
            "insurance_code": None,
            "maker": "",
            "maker_norm": None,
            "unit": None,
            "unit_manual": units.get(n),
            "source": "manual",
            "imported_at": imported_at,
            "source_file": "자유입력",
        }
        for n in names if n not in existing
    ]
    if rows:
        client.table("drug_master").insert(rows).execute()
    return {"added": len(rows), "names": [r["name"] for r in rows]}


def search_drug_master(client, q: str = "", limit: int = 50, offset: int = 0,
                       unit_filter: str = "") -> tuple[list[dict], int]:
    """약품 DB 조회(읽기 전용) — 약품명·보험코드 검색 + 필터 + 페이지네이션. (rows, 전체 개수).

    필터 의미는 로컬 앱 master_db.list_rows 와 동일:
    filled(규격수집됨) / missing(규격미수집) / nocode(보험코드없음) / manual(자유입력)
    """
    query = client.table("drug_master").select(_COLS, count="exact")
    uf = (unit_filter or "").strip()
    if uf == "filled":
        query = query.not_.is_("unit", "null")
    elif uf == "missing":
        query = query.is_("unit", "null").not_.is_("insurance_code", "null")
    elif uf == "nocode":
        query = query.is_("unit", "null").is_("insurance_code", "null")
    elif uf == "manual":
        query = query.eq("source", "manual")
    if q:
        pat = f"*{q}*"
        query = query.or_(f"name.ilike.{pat},insurance_code.ilike.{pat}")
    res = query.order("name").range(offset, offset + limit - 1).execute()
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
