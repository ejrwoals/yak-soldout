"""약품 DB 뷰어/편집 — Supabase drug_master (약국 스코프). 로컬 앱 관리자용.

전달 client 는 관리자 사용자 세션(RLS로 자기 약국만). 기존 db.py 의 뷰어/편집 의미를 그대로 이식:
- 필터: filled(규격수집됨) / missing(규격미수집) / nocode(보험코드없음) / manual(자유입력)
- 직접추가 규격: unit_manual 에 append-only (중복 스킵)
- 수정/삭제: 자유입력(source='manual') 행만 가능
- 규격수집(unit_collector)이 쓰는 조회/갱신도 여기에 둔다 (unit_stats / rows_missing_unit / set_unit)
"""

import re

_COLS = "id, name, insurance_code, maker, unit, unit_manual, source"

# 규격 값 안의 천 단위 콤마 ('1,000정') — 콤마는 다중 규격 구분자라 값에 남으면 쪼개진다
_THOUSANDS_COMMA = re.compile(r"(?<=\d),(?=\d{3}(?!\d))")


def clean_unit(u: str) -> str:
    """규격 문자열 정규화 — 천 단위 콤마 제거 ('1,000정(병)' → '1000정(병)')."""
    return _THOUSANDS_COMMA.sub("", (u or "").strip())


def _split_units(s: str) -> list[str]:
    out, seen = [], set()
    for u in clean_unit(s).split(","):
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
    unit = clean_unit(unit)
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


# ===================== 규격(포장단위) 수집용 =====================
# 엑셀에는 규격 컬럼이 없어, unit 이 빈 행을 기준 도매상에 보험코드로 검색해 채운다.
# 보험코드가 없으면 검색할 수 없으므로 수집 대상에서 제외한다(레거시 db.py 와 동일한 기준).

def unit_stats(client, pharmacy_id: str) -> dict:
    """규격 수집 현황 — total / filled(수집됨) / missing_with_code(수집 대상) / notfound_held(미발견 보류)."""
    def counter():
        """이 약국 행을 세는 쿼리 빌더 (뒤에 필터를 더 붙일 수 있다)."""
        return (
            client.table("drug_master")
            .select("id", count="exact")
            .eq("pharmacy_id", pharmacy_id)
            .limit(1)
        )

    def count(query) -> int:
        return query.execute().count or 0

    def missing():
        return counter().is_("unit", "null").not_.is_("insurance_code", "null").neq("insurance_code", "")

    return {
        "total": count(counter()),
        "filled": count(counter().not_.is_("unit", "null")),
        "missing_with_code": count(missing().is_("unit_notfound_at", "null")),
        "notfound_held": count(missing().not_.is_("unit_notfound_at", "null")),
    }


def rows_missing_unit(client, pharmacy_id: str, include_notfound: bool = False) -> list[dict]:
    """규격 수집 대상 행(id, name, insurance_code) 전체. 페이지네이션으로 모두 가져온다.

    미발견 보류(unit_notfound_at 기록됨) 행은 기본 제외 — include_notfound=True 면 포함.
    """
    rows, start, page = [], 0, 1000
    while True:
        query = (
            client.table("drug_master")
            .select("id, name, insurance_code")
            .eq("pharmacy_id", pharmacy_id)
            .is_("unit", "null")
            .not_.is_("insurance_code", "null")
            .neq("insurance_code", "")
        )
        if not include_notfound:
            query = query.is_("unit_notfound_at", "null")
        res = query.order("name").range(start, start + page - 1).execute()
        batch = res.data or []
        rows.extend(batch)
        if len(batch) < page:
            break
        start += page
    return rows


def set_unit(client, row_id: str, unit: str) -> None:
    """수집한 규격 저장 (미발견 보류도 해제). 빈 값은 NULL 로 둬서 다음 수집 대상으로 남긴다."""
    client.table("drug_master").update({
        "unit": (unit or "").strip() or None,
        "unit_notfound_at": None,
    }).eq("id", row_id).execute()


def mark_unit_notfound(client, row_id: str) -> None:
    """기준 도매상에서 규격 미발견 — 기본 수집 대상에서 보류 처리."""
    from datetime import datetime
    ts = datetime.now().astimezone().isoformat(timespec="seconds")
    client.table("drug_master").update({"unit_notfound_at": ts}).eq("id", row_id).execute()
