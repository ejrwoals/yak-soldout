#!/usr/bin/env python3
"""
약품 마스터 관리 (2단계: 오타 보정 기반 데이터)

약국이 취급하는 전체 약품 목록을 엑셀로 업로드받아 로컬에 저장한다.
업로드한 엑셀의 컬럼명은 사용자마다 다를 수 있으므로, 어떤 컬럼이 약품명인지
사용자가 직접 선택(매핑)하게 한 뒤 등록한다.

저장소는 SQLite의 `drug_master` 테이블(db.py). 업로드한 엑셀을 파싱해 전체 교체(재임포트)한다.
이후 OCR 결과의 약품명을 이 마스터와 fuzzy 매칭하여 오타를 보정한다.
"""

import io
import re
from datetime import datetime
from typing import Optional

import pandas as pd

import db

# 미리보기로 보여줄 샘플 행 수
PREVIEW_ROWS = 5
# 머리글 행 선택을 위해 가공 없이 보여줄 상단 원본 행 수
RAW_PREVIEW_ROWS = 10

# 머리글(헤더) 행 자동 추정에 쓰는 키워드 — 이 단어가 든 행을 머리글로 본다
_HEADER_HINTS = (
    "약품명", "제품명", "품명", "품목명", "청구코드", "약품코드", "보험코드",
    "제약사", "제조사", "업체", "성분", "규격", "단위",
)

# 제약사 표기에서 떼어낼 법인/접미 토큰들 ('대웅제약(주)', '(주)보령' → '대웅', '보령')
_MAKER_NOISE = re.compile(
    r"㈜|\(\s*주\s*\)|（주）|주식회사|유한회사|제약|약품|파마|팜|홀딩스|코리아|메디칼|메디컬|"
    r"\s+|[().,·]"
)


def normalize_maker(maker: str) -> str:
    """제약사 표기 정규화 — 표기 불일치를 흡수해 매칭에 쓰기 위한 형태.

    예) '대웅제약(주)' → '대웅',  '(주)보령' → '보령',  '한미약품' → '한미'
    완벽하진 않지만(매칭 보조 신호로만 사용) 표기 편차를 크게 줄여준다.
    """
    if not maker:
        return ""
    return _MAKER_NOISE.sub("", maker).strip()


def _engine_for(filename: str) -> str:
    """BytesIO 는 확장자를 모르므로 파일명으로 엔진을 정한다."""
    return "xlrd" if (filename or "").lower().endswith(".xls") else "openpyxl"


def _clean(v) -> str:
    s = str(v).strip()
    return "" if s.lower() == "nan" else s


def _read_excel(file_bytes: bytes, filename: str, header_row: int = 0) -> pd.DataFrame:
    """엑셀 바이트 → DataFrame(모든 값 문자열). header_row(0-based)를 머리글로 사용한다."""
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
    """머리글 없이 상단 원본 행을 그대로 읽어 2차원 리스트로 반환 (머리글 행 선택용)."""
    raw = pd.read_excel(
        io.BytesIO(file_bytes), sheet_name=0, dtype=str,
        engine=_engine_for(filename), header=None, nrows=nrows,
    )
    return [[_clean(v) for v in raw.iloc[i].tolist()] for i in range(len(raw))]


def _guess_header_row(raw_rows: list[list[str]]) -> int:
    """상단 원본 행들에서 머리글로 가장 그럴듯한 행 인덱스를 추정한다.

    1순위: 키워드(_HEADER_HINTS)가 들어있는 첫 행.
    2순위: 비어있지 않은 칸이 가장 많은 행.
    """
    best_idx, best_nonempty = 0, -1
    for i, cells in enumerate(raw_rows):
        joined = " ".join(c for c in cells if c)
        if any(h in joined for h in _HEADER_HINTS):
            return i
        nonempty = sum(1 for c in cells if c)
        if nonempty > best_nonempty:
            best_idx, best_nonempty = i, nonempty
    return best_idx


def preview(file_bytes: bytes, filename: str, header_row: Optional[int] = None) -> dict:
    """업로드한 엑셀의 미리보기. 머리글 행을 자동 추정(또는 지정)해 컬럼·샘플을 반환한다.

    반환:
        raw_rows: 상단 원본 행(머리글 행 선택용)
        used_header_row / suggested_header_row: 사용/추천 머리글 행 인덱스
        columns / sample_rows / total_rows: 선택한 머리글 기준 파싱 결과
    """
    raw_rows = _read_raw(file_bytes, filename, RAW_PREVIEW_ROWS)
    if not raw_rows:
        raise ValueError("엑셀에서 데이터를 찾을 수 없습니다.")

    suggested = _guess_header_row(raw_rows)
    used = suggested if header_row is None else max(0, int(header_row))
    used = min(used, len(raw_rows) - 1)

    df = _read_excel(file_bytes, filename, header_row=used)
    columns = list(df.columns)
    sample = df.head(PREVIEW_ROWS).fillna("")
    sample_rows = [
        {col: _clean(row[col]) for col in columns}
        for _, row in sample.iterrows()
    ]
    return {
        "raw_rows": raw_rows,
        "suggested_header_row": suggested,
        "used_header_row": used,
        "columns": columns,
        "sample_rows": sample_rows,
        "total_rows": int(len(df)),
    }


def import_master(
    file_bytes: bytes,
    filename: str,
    name_col: str,
    code_col: Optional[str] = None,
    maker_col: Optional[str] = None,
    header_row: int = 0,
) -> dict:
    """선택한 컬럼 매핑으로 약품 마스터를 등록(덮어쓰기)한다.

    Args:
        name_col: 약품명에 해당하는 컬럼 (필수)
        code_col: 보험코드 컬럼 (선택)
        maker_col: 제약사 컬럼 (선택)
        header_row: 머리글 행 인덱스(0-based) — 이 행을 컬럼명으로 사용
    """
    df = _read_excel(file_bytes, filename, header_row=max(0, int(header_row)))
    if name_col not in df.columns:
        raise ValueError(f"약품명 컬럼 '{name_col}' 을 찾을 수 없습니다.")
    code_col = code_col or None
    maker_col = maker_col or None
    for label, col in (("보험코드", code_col), ("제약사", maker_col)):
        if col and col not in df.columns:
            raise ValueError(f"{label} 컬럼 '{col}' 을 찾을 수 없습니다.")

    drugs = []
    seen = set()
    for _, row in df.iterrows():
        name = str(row.get(name_col, "") or "").strip()
        if not name or name.lower() == "nan":
            continue
        code = str(row.get(code_col, "") or "").strip() if code_col else ""
        maker = str(row.get(maker_col, "") or "").strip() if maker_col else ""
        # 약품명 + 보험코드 조합으로 중복 제거 (동명이약은 코드로 구분)
        key = (name, code)
        if key in seen:
            continue
        seen.add(key)
        drug = {"name": name, "insurance_code": code, "maker": maker}
        if maker:
            # 제약사 표기가 제각각('대웅제약(주)', '(주)보령')이라 매칭용 정규화 형태도 함께 저장
            drug["maker_norm"] = normalize_maker(maker)
        drugs.append(drug)

    if not drugs:
        raise ValueError("선택한 컬럼에서 유효한 약품명을 찾지 못했습니다.")

    # 약품 마스터 전체 교체 (DB drug_master 테이블)
    imported_at = datetime.now().isoformat(timespec="seconds")
    stored = db.replace_drug_master(drugs, filename, imported_at)

    return {"count": stored, "source_filename": filename}


def load_master() -> Optional[dict]:
    """저장된 약품 마스터 전체를 반환(매칭용). 비어 있으면 None.

    반환 형태는 기존 JSON 구조와 호환: {drugs, count, source_filename, imported_at}.
    """
    drugs = db.load_drug_master()
    if not drugs:
        return None
    meta = db.drug_master_meta()
    return {
        "drugs": drugs,
        "count": meta["count"],
        "source_filename": meta["source_file"],
        "imported_at": meta["imported_at"],
    }


def cache_key() -> tuple:
    """매처 캐시 무효화용 신호 (임포트마다 변함)."""
    return db.drug_master_cache_key()


def status() -> dict:
    """마스터 등록 현황 요약 (목록 본문 제외)."""
    meta = db.drug_master_meta()
    if not meta["count"]:
        return {"registered": False, "count": 0}
    return {
        "registered": True,
        "count": meta["count"],
        "source_filename": meta["source_file"],
        "imported_at": meta["imported_at"],
        "columns": {},
    }
