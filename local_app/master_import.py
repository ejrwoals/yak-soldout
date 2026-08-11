#!/usr/bin/env python3
"""약품 마스터 엑셀 임포트 — 로컬 앱(관리자) 전용.

기존 utils/drug_master.py 의 엑셀 파싱(머리글 자동추정 + 컬럼 매핑)을 그대로 이식하고,
저장만 로컬 SQLite → Supabase drug_master(약국 스코프)로 바꾼다.
'전체 교체' 방식이되, 크롤링으로 채운 규격(unit/unit_manual)은 (약품명,보험코드) 매칭으로 보존한다.
"""

import io
import re
from datetime import datetime

import pandas as pd

PREVIEW_ROWS = 5
RAW_PREVIEW_ROWS = 10

_HEADER_HINTS = (
    "약품명", "제품명", "품명", "품목명", "청구코드", "약품코드", "보험코드",
    "제약사", "제조사", "업체", "성분", "규격", "단위",
)
_NAME_HINTS = ("약품명", "제품명", "품목명", "품명", "제품")
_CODE_HINTS = ("보험코드", "청구코드", "약품코드", "코드")
_MAKER_HINTS = ("제약사", "제조사", "제조원", "업체", "메이커")

_MAKER_NOISE = re.compile(
    r"㈜|\(\s*주\s*\)|（주）|주식회사|유한회사|제약|약품|파마|팜|홀딩스|코리아|메디칼|메디컬|"
    r"\s+|[().,·]"
)


def normalize_maker(maker: str) -> str:
    if not maker:
        return ""
    return _MAKER_NOISE.sub("", maker).strip()


def _engine_for(filename: str) -> str:
    return "xlrd" if (filename or "").lower().endswith(".xls") else "openpyxl"


def _clean(v) -> str:
    s = str(v).strip()
    return "" if s.lower() == "nan" else s


def _read_excel(file_bytes: bytes, filename: str, header_row: int = 0) -> pd.DataFrame:
    try:
        df = pd.read_excel(
            io.BytesIO(file_bytes), sheet_name=0, dtype=str,
            engine=_engine_for(filename), header=header_row,
        )
    except Exception as e:
        raise ValueError(f"엑셀을 읽을 수 없습니다: {e}") from e
    df.columns = [str(c).strip() for c in df.columns]
    return df


def _read_raw(file_bytes: bytes, filename: str, nrows: int) -> list[list[str]]:
    raw = pd.read_excel(
        io.BytesIO(file_bytes), sheet_name=0, dtype=str,
        engine=_engine_for(filename), header=None, nrows=nrows,
    )
    return [[_clean(v) for v in raw.iloc[i].tolist()] for i in range(len(raw))]


def _guess_header_row(raw_rows: list[list[str]]) -> int:
    best_idx, best_nonempty = 0, -1
    for i, cells in enumerate(raw_rows):
        joined = " ".join(c for c in cells if c)
        if any(h in joined for h in _HEADER_HINTS):
            return i
        nonempty = sum(1 for c in cells if c)
        if nonempty > best_nonempty:
            best_idx, best_nonempty = i, nonempty
    return best_idx


def _guess_col(columns: list[str], hints: tuple) -> str | None:
    for h in hints:
        for c in columns:
            if h in c:
                return c
    return None


def preview(file_bytes: bytes, filename: str, header_row: int | None = None) -> dict:
    """엑셀 미리보기 — 머리글 행 자동추정 + 컬럼/샘플 + 이름/코드/제약사 컬럼 자동 제안."""
    raw_rows = _read_raw(file_bytes, filename, RAW_PREVIEW_ROWS)
    if not raw_rows:
        raise ValueError("엑셀에서 데이터를 찾을 수 없습니다.")
    suggested = _guess_header_row(raw_rows)
    used = suggested if header_row is None else max(0, int(header_row))
    used = min(used, len(raw_rows) - 1)

    df = _read_excel(file_bytes, filename, header_row=used)
    columns = list(df.columns)
    sample = df.head(PREVIEW_ROWS).fillna("")
    sample_rows = [{col: _clean(row[col]) for col in columns} for _, row in sample.iterrows()]
    return {
        "suggested_header_row": suggested,
        "used_header_row": used,
        "columns": columns,
        "sample_rows": sample_rows,
        "total_rows": int(len(df)),
        "suggested_cols": {
            "name": _guess_col(columns, _NAME_HINTS),
            "code": _guess_col(columns, _CODE_HINTS),
            "maker": _guess_col(columns, _MAKER_HINTS),
        },
    }


def extract_drugs(file_bytes: bytes, filename: str, name_col: str,
                  code_col: str | None, maker_col: str | None, header_row: int) -> list[dict]:
    """선택한 컬럼 매핑으로 약품 리스트 추출. (약품명+보험코드) 중복 제거."""
    df = _read_excel(file_bytes, filename, header_row=max(0, int(header_row)))
    if name_col not in df.columns:
        raise ValueError(f"약품명 컬럼 '{name_col}' 을 찾을 수 없습니다.")
    for label, col in (("보험코드", code_col), ("제약사", maker_col)):
        if col and col not in df.columns:
            raise ValueError(f"{label} 컬럼 '{col}' 을 찾을 수 없습니다.")

    drugs, seen = [], set()
    for _, row in df.iterrows():
        name = str(row.get(name_col, "") or "").strip()
        if not name or name.lower() == "nan":
            continue
        code = str(row.get(code_col, "") or "").strip() if code_col else ""
        maker = str(row.get(maker_col, "") or "").strip() if maker_col else ""
        key = (name, code)
        if key in seen:
            continue
        seen.add(key)
        drugs.append({
            "name": name,
            "insurance_code": code or None,
            "maker": maker or None,
            "maker_norm": normalize_maker(maker) or None,
        })
    if not drugs:
        raise ValueError("선택한 컬럼에서 유효한 약품명을 찾지 못했습니다.")
    return drugs


def _fetch_existing_keys(client, pharmacy_id: str) -> set:
    """기존 약품의 (name, insurance_code) 키 집합 (페이지네이션)."""
    keys, start, page = set(), 0, 1000
    while True:
        res = (
            client.table("drug_master")
            .select("name, insurance_code")
            .eq("pharmacy_id", pharmacy_id)
            .range(start, start + page - 1)
            .execute()
        )
        batch = res.data or []
        for r in batch:
            keys.add((r["name"], r.get("insurance_code") or ""))
        if len(batch) < page:
            break
        start += page
    return keys


def import_to_supabase(client, pharmacy_id: str, drugs: list[dict], filename: str) -> dict:
    """병합 임포트 — 기존 약품은 그대로 유지(규격·정보 보존), 목록에 없던 신규 약품만 추가.

    엑셀엔 없는 기존 약품도 삭제하지 않는다. (약품명, 보험코드) 조합이 이미 있으면 건너뛴다.
    """
    imported_at = datetime.now().astimezone().isoformat(timespec="seconds")
    existing = _fetch_existing_keys(client, pharmacy_id)

    new_rows = []
    for d in drugs:
        if (d["name"], d.get("insurance_code") or "") in existing:
            continue  # 기존 약품 — 그대로 둔다(규격·정보 보존)
        new_rows.append({
            "pharmacy_id": pharmacy_id,
            "name": d["name"],
            "insurance_code": d.get("insurance_code"),
            "maker": d.get("maker"),
            "maker_norm": d.get("maker_norm"),
            "unit": None,
            "unit_manual": None,
            "source": "excel",
            "imported_at": imported_at,
            "source_file": filename,
        })

    for i in range(0, len(new_rows), 500):
        client.table("drug_master").insert(new_rows[i:i + 500]).execute()

    total = (
        client.table("drug_master").select("id", count="exact")
        .eq("pharmacy_id", pharmacy_id).limit(1).execute()
    )
    return {"inserted": len(new_rows), "count": total.count or 0, "source_file": filename}
