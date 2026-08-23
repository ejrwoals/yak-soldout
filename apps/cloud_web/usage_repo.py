"""월별 사용량 조회 (읽기 전용) — 웹 약품 DB 뷰어용.

local_app/drug_usage.py 의 조회 의미를 그대로 따른다:
- 부분 달(진행 중인 달)은 임포트 시점에 원본에서 걸러지며, 그 이전에 저장된
  옛 요약의 'partial' 행은 여기서도 표시에서 제외한다.
- 조회는 사용자 세션(RLS)으로 실행되므로 자기 약국 행만 내려온다.
"""


def _ym(year: int, month: int) -> str:
    return f"{year}-{month:02d}"


def avg_by_codes(client, codes: list[str]) -> dict[str, float]:
    """보험코드 → 월평균 (drug_usage_stats). 뷰어 목록의 월평균 컬럼용."""
    codes = [c for c in {str(c).strip() for c in codes} if c]
    out: dict[str, float] = {}
    for i in range(0, len(codes), 200):
        res = (
            client.table("drug_usage_stats")
            .select("insurance_code, monthly_avg")
            .in_("insurance_code", codes[i:i + 200])
            .execute()
        )
        for r in res.data or []:
            out[r["insurance_code"]] = float(r["monthly_avg"] or 0)
    return out


def history_by_code(client, code: str) -> dict:
    """약품 1건의 월별 사용량 이력 + 월평균 — 뷰어 행 클릭 모달용.

    약국 전체 타임라인(drug_usage_months)을 x축으로 쓰고 그 약의 qty 를 채운다.
    저장된 달인데 그 약의 행이 없으면 사용량 0 으로 본다 (qty=0 은 임포트 시 제외되므로).
    """
    qres = (
        client.table("drug_usage")
        .select("year, month, qty")
        .eq("insurance_code", code)
        .order("year").order("month")
        .execute()
    )
    qty = {(r["year"], r["month"]): float(r["qty"] or 0) for r in (qres.data or [])}

    mres = (
        client.table("drug_usage_months")
        .select("year, month, status")
        .order("year").order("month")
        .execute()
    )
    # 'partial' 은 부분 달 삭제 도입 이전에 저장된 옛 요약에만 남아 있을 수 있다 — 완전한 달만 표시
    months = [m for m in (mres.data or []) if m.get("status") != "partial"]
    if not months:   # 월별 요약이 없는 옛 데이터 — 그 약의 원본 행만으로 축을 구성
        months = [{"year": y, "month": m} for (y, m) in sorted(qty)]
    if qty:
        # 취급 시작월 이전은 잘라낸다 (월평균도 시작월부터 계산하므로 0 구간을 그리면 오해)
        first = min(qty)
        months = [m for m in months if (m["year"], m["month"]) >= first]
    else:
        months = []   # 사용 기록이 전혀 없는 약 — 빈 차트 대신 안내 문구

    sres = (
        client.table("drug_usage_stats")
        .select("monthly_avg, months_used, window_start, window_end")
        .eq("insurance_code", code)
        .limit(1)
        .execute()
    )
    return {
        "months": [{
            "ym": _ym(m["year"], m["month"]),
            "qty": qty.get((m["year"], m["month"]), 0.0),
        } for m in months],
        "stats": sres.data[0] if sres.data else None,
    }
