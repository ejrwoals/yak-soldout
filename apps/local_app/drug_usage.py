"""월별 약품 사용량 — 임포트/월평균 통계 (Supabase drug_usage / drug_usage_stats).

약국 조제 프로그램의 '월별 약품사용량' 엑셀(청구코드·약품명·제약사 + 1월~12월 컬럼)을
약품 마스터 임포트와 같은 업로드 흐름에서 자동 감지해 함께 저장한다.

- 원본은 (청구코드, 연, 월) 단위로 저장. 같은 연도 파일을 다시 올리면 그 연도만 교체된다.
- 월평균은 저장된 전체 연도를 합쳐 '최근 12개 완전월' 기준으로 재계산한다.
- 파일의 '월평균' 컬럼은 항상 소계÷12 라서 연중 데이터에선 과소평가 → 쓰지 않는다.
- 마지막 달이 부분 데이터(월중 추출)인지는 robust z-score(중앙값·MAD)로 판정한다:
  월 사용량 총합·사용 약품 수 두 지표 중 하나라도 z < -3.5 면 부분 달로 본다.
- 부분 달은 통계 재계산 시 **원본에서 아예 삭제**해 앱 어디에도 노출하지 않는다.
  (같은 연도 파일을 다시 올리면 그 연도가 통째로 교체되므로, 달이 지난 뒤 재업로드하면 복원된다)
- 연중 새로 취급하기 시작한 약은 취급 시작월부터 평균한다 (이전 달은 분모에서 제외).
"""

import re
from datetime import datetime
from statistics import median

from master_import import _read_excel, _read_raw, RAW_PREVIEW_ROWS

MONTH_COLS = [f"{m}월" for m in range(1, 13)]

_Z_CUTOFF = -3.5        # 부분 달 판정 (한쪽 꼬리)
_MIN_REF_MONTHS = 6     # 기준 월이 이보다 적으면 통계 대신 마지막 달을 무조건 제외
_WINDOW = 12            # 월평균 계산 구간 (최근 완전월 수)

_PERIOD_RE = re.compile(r"검색\s*기간\s*[::]?\s*(20\d{2})")
_FILENAME_YEAR_RE = re.compile(r"(20\d{2})")


def _ym(year: int, month: int) -> str:
    return f"{year}-{month:02d}"


def detect(file_bytes: bytes, filename: str, columns: list[str]) -> dict:
    """사용량 데이터 감지 — 1월~12월 컬럼이 모두 있으면 사용량 파일로 본다.

    연도는 파일 상단 '검색기간:YYYY년' 에서 읽고, 없으면 파일명의 연도로 대체한다.
    (제목 행의 연도는 실제 검색기간과 다른 경우가 있어 쓰지 않는다.)
    """
    detected = all(m in columns for m in MONTH_COLS)
    year = None
    if detected:
        try:
            raw_rows = _read_raw(file_bytes, filename, RAW_PREVIEW_ROWS)
            joined = " ".join(c for row in raw_rows for c in row if c)
            m = _PERIOD_RE.search(joined)
            if m:
                year = int(m.group(1))
        except Exception:
            pass
        if year is None:
            m = _FILENAME_YEAR_RE.search(filename or "")
            if m:
                year = int(m.group(1))
    return {"detected": detected, "year": year}


def _to_qty(v) -> float:
    s = str(v or "").strip().replace(",", "")
    if not s or s.lower() == "nan":
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def extract_usage(file_bytes: bytes, filename: str, header_row: int,
                  code_col: str, name_col: str) -> list[dict]:
    """월별 사용량 추출 — [{code, name, month, qty}] (qty=0 인 달은 제외, 청구코드 중복은 첫 행)."""
    df = _read_excel(file_bytes, filename, header_row=max(0, int(header_row)))
    missing = [m for m in MONTH_COLS if m not in df.columns]
    if missing:
        raise ValueError(f"월 컬럼을 찾을 수 없습니다: {', '.join(missing)}")
    if code_col not in df.columns:
        raise ValueError(f"보험코드 컬럼 '{code_col}' 을 찾을 수 없습니다.")

    rows, seen = [], set()
    for _, r in df.iterrows():
        code = str(r.get(code_col, "") or "").strip()
        if not code or code.lower() == "nan" or code in seen:
            continue
        seen.add(code)
        name = str(r.get(name_col, "") or "").strip() if name_col in df.columns else ""
        for i, mcol in enumerate(MONTH_COLS):
            qty = _to_qty(r.get(mcol))
            if qty != 0:
                rows.append({"code": code, "name": name, "month": i + 1, "qty": qty})
    return rows


def save_usage(client, pharmacy_id: str, year: int, rows: list[dict], filename: str) -> dict:
    """그 연도 원본을 전체 교체 저장. 반환: 저장 행 수·데이터가 있는 월 수."""
    imported_at = datetime.now().astimezone().isoformat(timespec="seconds")
    client.table("drug_usage").delete().eq("pharmacy_id", pharmacy_id).eq("year", year).execute()
    payload = [{
        "pharmacy_id": pharmacy_id,
        "insurance_code": r["code"],
        "name": r["name"] or None,
        "year": year,
        "month": r["month"],
        "qty": r["qty"],
        "source_file": filename,
        "imported_at": imported_at,
    } for r in rows]
    for i in range(0, len(payload), 500):
        client.table("drug_usage").insert(payload[i:i + 500]).execute()
    return {
        "rows": len(payload),
        "months": len({r["month"] for r in rows}),
        "drugs": len({r["code"] for r in rows}),
    }


# ===================== 월평균 재계산 =====================

def _robust_z(x: float, ref: list[float]) -> float:
    med = median(ref)
    mad = median(abs(v - med) for v in ref) * 1.4826
    mad = max(mad, abs(med) * 0.01, 1e-9)   # MAD=0 방어 (중앙값의 1% 를 하한으로)
    return (x - med) / mad


def _by_month(rows: list[dict]) -> dict[tuple[int, int], list[float]]:
    """(연, 월) -> [사용량 총합, 사용 약품 수]"""
    out: dict[tuple[int, int], list[float]] = {}
    for r in rows:
        acc = out.setdefault((r["year"], r["month"]), [0.0, 0])
        acc[0] += r["qty"]
        acc[1] += 1
    return out


def find_partial_month(by_month: dict) -> tuple | None:
    """마지막 달이 부분 데이터(월중 추출)인지 판정 — (year, month) 또는 None."""
    months = sorted(by_month)
    if len(months) < 2:
        return None
    last, others = months[-1], months[:-1]
    if len(others) < _MIN_REF_MONTHS:
        return last     # 기준 월 부족 → 보수적으로 마지막 달을 부분 달로 본다
    for idx in (0, 1):
        if _robust_z(by_month[last][idx], [by_month[m][idx] for m in others]) < _Z_CUTOFF:
            return last
    return None


def compute_stats(rows: list[dict]) -> tuple[list[dict], dict]:
    """사용량 원본 → (약품별 통계 행, 요약). rows: [{code, name, year, month, qty}] (qty≠0).

    부분 달은 recompute_stats 가 원본째 삭제한 뒤 넘겨주므로, 여기선 전체를 완전월로 본다.
    순수 계산 함수 (Supabase 접근 없음) — 테스트/검증용으로 분리.
    """
    if not rows:
        return [], {"drugs": 0, "window_months": 0, "months_detail": []}

    by_month = _by_month(rows)
    months = sorted(by_month)
    window = months[-_WINDOW:]
    window_set = set(window)

    # 월별 타일 시각화용 요약 (임포트 시 drug_usage_months 로 저장된다)
    months_detail = [{
        "year": y, "month": m,
        "drugs": int(by_month[(y, m)][1]),
        "total": round(by_month[(y, m)][0], 1),
        "status": "window" if (y, m) in window_set else "stored",
    } for (y, m) in months]

    per_drug: dict[str, dict] = {}   # code -> {name, first, last, total}
    for r in rows:
        ym = (r["year"], r["month"])
        d = per_drug.setdefault(r["code"], {"name": r["name"], "first": ym, "last": ym, "total": 0.0})
        if ym < d["first"]:
            d["first"] = ym
        if ym >= d["last"]:
            d["last"] = ym
            if r["name"]:
                d["name"] = r["name"]    # 최근 이름 우선
        if ym in window_set:
            d["total"] += r["qty"]

    stats = []
    for code, d in per_drug.items():
        denom = sum(1 for m in window if m >= d["first"])
        if denom == 0:
            continue   # 부분 달에만 등장한 약 — 완전월 데이터가 없어 계산 불가
        stats.append({
            "insurance_code": code,
            "name": d["name"] or None,
            "monthly_avg": round(d["total"] / denom, 1),
            "months_used": denom,
            "window_start": _ym(*window[0]),
            "window_end": _ym(*window[-1]),
        })

    summary = {
        "drugs": len(stats),
        "window_months": len(window),
        "window_start": _ym(*window[0]),
        "window_end": _ym(*window[-1]),
        "months_detail": months_detail,
    }
    return stats, summary


def _fetch_usage(client, pharmacy_id: str) -> list[dict]:
    rows, start, page = [], 0, 1000
    while True:
        res = (
            client.table("drug_usage")
            .select("insurance_code, name, year, month, qty")
            .eq("pharmacy_id", pharmacy_id)
            .order("year").order("month").order("insurance_code")
            .range(start, start + page - 1)
            .execute()
        )
        batch = res.data or []
        rows.extend({
            "code": r["insurance_code"], "name": r.get("name") or "",
            "year": r["year"], "month": r["month"], "qty": float(r["qty"] or 0),
        } for r in batch)
        if len(batch) < page:
            break
        start += page
    return rows


def recompute_stats(client, pharmacy_id: str) -> dict:
    """저장된 전체 사용량으로 drug_usage_stats·drug_usage_months 를 전체 재계산(교체).

    부분 달(진행 중인 달)이 감지되면 drug_usage 원본에서 먼저 삭제한다 — 완전한 달만 남긴다.
    """
    rows = _fetch_usage(client, pharmacy_id)
    partial = find_partial_month(_by_month(rows))
    if partial:
        y, mo = partial
        (client.table("drug_usage").delete()
         .eq("pharmacy_id", pharmacy_id).eq("year", y).eq("month", mo).execute())
        rows = [r for r in rows if (r["year"], r["month"]) != partial]
    stats, summary = compute_stats(rows)
    summary["partial_excluded"] = _ym(*partial) if partial else None
    computed_at = datetime.now().astimezone().isoformat(timespec="seconds")
    client.table("drug_usage_stats").delete().eq("pharmacy_id", pharmacy_id).execute()
    payload = [{"pharmacy_id": pharmacy_id, "computed_at": computed_at, **s} for s in stats]
    for i in range(0, len(payload), 500):
        client.table("drug_usage_stats").insert(payload[i:i + 500]).execute()

    client.table("drug_usage_months").delete().eq("pharmacy_id", pharmacy_id).execute()
    month_rows = [{"pharmacy_id": pharmacy_id, **m} for m in summary["months_detail"]]
    for i in range(0, len(month_rows), 500):
        client.table("drug_usage_months").insert(month_rows[i:i + 500]).execute()
    return summary


# ===================== 조회 (표시용) =====================

def usage_status(client, pharmacy_id: str) -> dict | None:
    """상태 카드용 요약 — 통계가 없으면 None.

    계산 구간(최근 12개 완전월)과 별개로 저장된 원본 범위도 함께 알려줘
    '옛날 연도 데이터가 사라졌나?' 하는 오해를 막는다.
    """
    res = (
        client.table("drug_usage_stats")
        .select("window_start, window_end", count="exact")
        .eq("pharmacy_id", pharmacy_id)
        .limit(1)
        .execute()
    )
    if not res.data:
        return None

    mres = (
        client.table("drug_usage_months")
        .select("year, month, drugs, status")
        .eq("pharmacy_id", pharmacy_id)
        .order("year").order("month")
        .execute()
    )
    # 'partial' 은 이 코드 이전에 저장된 옛 요약에만 남아 있을 수 있다 — 표시에서 제외
    months = [m for m in (mres.data or []) if m.get("status") != "partial"]

    def _edge(desc: bool) -> str | None:
        r = (
            client.table("drug_usage")
            .select("year, month")
            .eq("pharmacy_id", pharmacy_id)
            .order("year", desc=desc).order("month", desc=desc)
            .limit(1)
            .execute()
        )
        return _ym(r.data[0]["year"], r.data[0]["month"]) if r.data else None

    return {
        "drugs": res.count or 0,
        "window_start": res.data[0].get("window_start"),
        "window_end": res.data[0].get("window_end"),
        # 월별 요약이 있으면 그걸로 범위 계산, 없으면(0006 이전 데이터) 원본에서 조회
        "data_start": _ym(months[0]["year"], months[0]["month"]) if months else _edge(desc=False),
        "data_end": _ym(months[-1]["year"], months[-1]["month"]) if months else _edge(desc=True),
        "months": months,
    }


def history_by_code(client, pharmacy_id: str, code: str) -> dict:
    """약품 1건의 월별 사용량 이력 + 월평균 — 뷰어 행 클릭 모달용.

    약국 전체 타임라인(drug_usage_months)을 x축으로 쓰고 그 약의 qty 를 채운다.
    저장된 달인데 그 약의 행이 없으면 사용량 0 으로 본다 (qty=0 은 임포트 시 제외되므로).
    """
    qres = (
        client.table("drug_usage")
        .select("year, month, qty")
        .eq("pharmacy_id", pharmacy_id)
        .eq("insurance_code", code)
        .order("year").order("month")
        .execute()
    )
    qty = {(r["year"], r["month"]): float(r["qty"] or 0) for r in (qres.data or [])}

    mres = (
        client.table("drug_usage_months")
        .select("year, month, status")
        .eq("pharmacy_id", pharmacy_id)
        .order("year").order("month")
        .execute()
    )
    # 'partial' 은 이 코드 이전에 저장된 옛 요약에만 남아 있을 수 있다 — 완전한 달만 표시
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
        .eq("pharmacy_id", pharmacy_id)
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


def avg_by_codes(client, codes: list[str]) -> dict[str, float]:
    """보험코드 → 월평균. (RLS 로 자기 약국 행만 조회된다)"""
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


def avg_by_names(client, names: list[str]) -> dict[str, float]:
    """약품명 → 월평균 (drug_master 로 보험코드를 찾아 조인). 주문 검수 화면용."""
    names = [n for n in {str(n).strip() for n in names} if n]
    if not names:
        return {}
    name_code: dict[str, str] = {}
    for i in range(0, len(names), 200):
        res = (
            client.table("drug_master")
            .select("name, insurance_code")
            .in_("name", names[i:i + 200])
            .execute()
        )
        for r in res.data or []:
            if r.get("insurance_code"):
                name_code.setdefault(r["name"], r["insurance_code"])
    avgs = avg_by_codes(client, list(name_code.values()))
    return {n: avgs[c] for n, c in name_code.items() if c in avgs}
