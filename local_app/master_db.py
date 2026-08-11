"""약품 DB 뷰어/편집 — Supabase drug_master (약국 스코프). 로컬 앱 관리자용.

전달 client 는 관리자 사용자 세션(RLS로 자기 약국만). 기존 db.py 의 뷰어/편집 의미를 그대로 이식:
- 필터: filled(규격수집됨) / missing(규격미수집) / nocode(보험코드없음) / manual(자유입력)
- 직접추가 규격: unit_manual 에 append-only (중복 스킵)
- 수정/삭제: 자유입력(source='manual') 행만 가능
"""

_COLS = "id, name, insurance_code, maker, unit, unit_manual, source"


def _split_units(s: str) -> list[str]:
    out, seen = [], set()
    for u in (s or "").split(","):
        u = u.strip()
        if u and u not in seen:
            seen.add(u)
            out.append(u)
    return out


def list_rows(client, offset: int, limit: int, q: str = "", unit_filter: str = "") -> dict:
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

    q = (q or "").strip()
    if q:
        pat = f"*{q}*"
        query = query.or_(f"name.ilike.{pat},insurance_code.ilike.{pat}")

    res = query.order("name").range(offset, offset + limit - 1).execute()
    rows = [{
        "id": r["id"],
        "name": r["name"],
        "insurance_code": r.get("insurance_code") or "",
        "maker": r.get("maker") or "",
        "unit": r.get("unit") or "",
        "unit_manual": r.get("unit_manual") or "",
        "source": r.get("source") or "excel",
    } for r in (res.data or [])]
    return {"total": res.count or 0, "rows": rows}


def add_manual_unit(client, row_id: str, unit: str) -> dict | None:
    """직접 입력 규격 1건을 unit_manual 에 append(중복 스킵). 없는 행이면 None."""
    unit = (unit or "").strip()
    r = client.table("drug_master").select("unit, unit_manual").eq("id", row_id).limit(1).execute()
    if not r.data:
        return None
    row = r.data[0]
    manual = _split_units(row.get("unit_manual"))
    if not unit:
        return {"added": False, "unit_manual": ", ".join(manual)}
    if unit in (set(_split_units(row.get("unit"))) | set(manual)):
        return {"added": False, "unit_manual": ", ".join(manual)}
    manual.append(unit)
    nm = ", ".join(manual)
    client.table("drug_master").update({"unit_manual": nm}).eq("id", row_id).execute()
    return {"added": True, "unit_manual": nm}


def rename_row(client, row_id: str, new_name: str) -> dict | None:
    """자유입력 행 약품명 수정. 대상없음/자유입력아님/빈이름/중복이면 None."""
    new_name = (new_name or "").strip()
    if not new_name:
        return None
    r = client.table("drug_master").select("name, source").eq("id", row_id).limit(1).execute()
    if not r.data:
        return None
    row = r.data[0]
    if (row.get("source") or "excel") != "manual":
        return None
    if new_name == row["name"]:
        return {"renamed": False}
    dup = client.table("drug_master").select("id").eq("name", new_name).neq("id", row_id).limit(1).execute()
    if dup.data:
        return None
    client.table("drug_master").update({"name": new_name}).eq("id", row_id).execute()
    return {"renamed": True}


def delete_row(client, row_id: str) -> bool:
    """자유입력 행 삭제. 엑셀 임포트분은 삭제 불가(엑셀 재업로드로 관리)."""
    r = client.table("drug_master").select("source").eq("id", row_id).limit(1).execute()
    if not r.data:
        return False
    if (r.data[0].get("source") or "excel") != "manual":
        return False
    client.table("drug_master").delete().eq("id", row_id).execute()
    return True
