#!/usr/bin/env python3
"""약품명 fuzzy 매칭 (OCR 오타 보정) — Cloud Run 웹 UI 전용.

기존 utils/drug_matcher.py 와 동일한 스코어링 로직을, 데이터 소스를 로컬 SQLite가 아니라
'주입받은 약품 목록(Supabase drug_master)'으로 바꾼 이식본. 마스터 인덱스를 한 번 만들어
(build_index) 여러 매칭에 재사용한다.

자동 교정은 하지 않는다(Human-in-the-loop). 매칭 결과만 후보로 제시한다.
"""

import re

from rapidfuzz import fuzz, process

# 유사도 임계값 (자모 기반 0~100)
HIGH_SCORE = 90
LOW_SCORE = 70
MAX_CANDIDATES = 5
STRENGTH_MISMATCH_CAP = 78

_FORM_SUFFIXES = sorted([
    "서방정", "서방캡슐", "장용정", "이연정", "점안액", "점비액", "현탁액", "건조시럽",
    "시럽", "주사액", "주사", "캡슐", "캅셀", "정제", "좌제", "과립", "분말", "패치",
    "연고", "크림", "로션", "겔", "산", "액", "환", "정", "주",
], key=len, reverse=True)


def _strip_form(s: str) -> str:
    for suf in _FORM_SUFFIXES:
        if len(s) > len(suf) and s.endswith(suf):
            return s[: -len(suf)]
    return s


_CHO = list("ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ")
_JUNG = list("ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ")
_JONG = ["", "ㄱ", "ㄲ", "ㄳ", "ㄴ", "ㄵ", "ㄶ", "ㄷ", "ㄹ", "ㄺ", "ㄻ", "ㄼ", "ㄽ",
         "ㄾ", "ㄿ", "ㅀ", "ㅁ", "ㅂ", "ㅄ", "ㅅ", "ㅆ", "ㅇ", "ㅈ", "ㅊ", "ㅋ", "ㅌ", "ㅍ", "ㅎ"]

_CORE_CUT = re.compile(r"[0-9(_/\[].*$")
_MAKER_PREFIX = re.compile(r"^[가-힣A-Za-z]{1,6}\)")
_STRENGTH_RE = re.compile(r"\d+(?:[./]\d+)*")
_DISPLAY_CUT = re.compile(r"[(_].*$")


def _brand_score(q: str, cand: str) -> float:
    if q == cand:
        return 100.0
    if cand.startswith(q) or q.startswith(cand):
        return min(fuzz.partial_ratio(q, cand), 96.0)
    return fuzz.ratio(q, cand)


def _strength(s: str) -> str:
    m = _STRENGTH_RE.search(s)
    return m.group(0) if m else ""


def _display(name: str) -> str:
    return _DISPLAY_CUT.sub("", name.strip()).strip()


def decompose(text: str) -> str:
    """한글 음절을 초/중/종성 자모열로 분해. 비한글은 그대로 둔다."""
    out = []
    for ch in text:
        code = ord(ch)
        if 0xAC00 <= code <= 0xD7A3:
            i = code - 0xAC00
            out.append(_CHO[i // 588])
            out.append(_JUNG[(i % 588) // 28])
            jong = _JONG[i % 28]
            if jong:
                out.append(jong)
        elif not ch.isspace():
            out.append(ch.lower())
    return "".join(out)


def _master_core(name: str) -> str:
    return _CORE_CUT.sub("", name.strip()).strip()


def _query_core(name: str) -> str:
    s = _MAKER_PREFIX.sub("", name.strip())
    return _CORE_CUT.sub("", s).strip()


def _unit_tokens(s: str) -> list[str]:
    return [u.strip() for u in (s or "").split(",") if u.strip()]


def build_index(drugs: list[dict]) -> dict:
    """Supabase drug_master 행 리스트 → 매칭 인덱스 {entries, jamo, units}.

    drugs: [{name, insurance_code, maker, unit, unit_manual}, ...]
    """
    entries, jamo = [], []
    units: dict[str, set] = {}
    for d in drugs:
        name = d.get("name", "") or ""
        core = _master_core(name)
        if not core:
            continue
        disp = _display(name)
        entries.append({
            "name": name,
            "core": disp,
            "strength": _strength(name),
            "insurance_code": d.get("insurance_code", "") or "",
            "maker": d.get("maker", "") or "",
        })
        jamo.append(decompose(_strip_form(core)))
        toks = _unit_tokens(d.get("unit", "")) + _unit_tokens(d.get("unit_manual", ""))
        if toks:
            units.setdefault(disp, set()).update(toks)
    return {"entries": entries, "jamo": jamo, "units": units}


def _known_units(index: dict, core: str) -> list[str]:
    units = (index.get("units") or {}).get(core)
    if not units:
        return []

    def _count_key(u: str):
        m = re.match(r"\s*(\d+(?:\.\d+)?)", u)
        return (0, float(m.group(1))) if m else (1, u)

    return sorted(units, key=_count_key)


def _ranked_candidates(index: dict, ocr_name: str) -> list[dict]:
    entries, jamo = index["entries"], index["jamo"]
    if not entries:
        return []

    q = decompose(_strip_form(_query_core(ocr_name)))
    if not q:
        return []
    q_strength = _strength(_MAKER_PREFIX.sub("", ocr_name))

    scored = []
    for idx, cand_jamo in enumerate(jamo):
        final = _brand_score(q, cand_jamo)
        e = entries[idx]
        if q_strength and e["strength"] and q_strength != e["strength"]:
            final = min(final, STRENGTH_MISMATCH_CAP)
        scored.append((final, e))
    scored.sort(key=lambda x: x[0], reverse=True)

    seen = set()
    candidates = []
    for final, e in scored:
        if e["core"] in seen:
            continue
        seen.add(e["core"])
        candidates.append({
            "name": e["name"],
            "core": e["core"],
            "score": round(final, 1),
            "insurance_code": e["insurance_code"],
            "maker": e["maker"],
            "known_units": _known_units(index, e["core"]),
        })
        if len(candidates) >= MAX_CANDIDATES:
            break
    return candidates


def top_candidates(index: dict, ocr_name: str, limit: int = MAX_CANDIDATES) -> list[dict]:
    return _ranked_candidates(index, ocr_name)[:limit]


def match_one(index: dict, ocr_name: str) -> dict:
    """OCR 약품명 하나에 대한 매칭 결과.

    status: 'matched'(확신) | 'candidate'(확인 필요) | 'none'(못 찾음) | 'skip'(마스터 미등록)
    """
    entries = index["entries"]
    if not entries:
        return {"status": "skip", "best": None, "candidates": []}

    candidates = _ranked_candidates(index, ocr_name)
    if not candidates:
        return {"status": "none", "best": None, "candidates": []}

    best = candidates[0]
    if best["score"] >= HIGH_SCORE:
        return {"status": "matched", "best": best, "candidates": []}
    if best["score"] >= LOW_SCORE:
        return {"status": "candidate", "best": best, "candidates": candidates}
    return {"status": "none", "best": best, "candidates": []}


def attach_matches(index: dict, items: list[dict]) -> list[dict]:
    """OCR 추출 결과 각 항목에 match 정보를 덧붙인다."""
    for it in items:
        it["match"] = match_one(index, it.get("drug_name", ""))
    return items


def _pub(index: dict, e: dict, score: float) -> dict:
    return {
        "name": e["name"],
        "core": e["core"],
        "score": round(score, 1),
        "insurance_code": e["insurance_code"],
        "maker": e["maker"],
        "known_units": _known_units(index, e["core"]),
    }


def search(index: dict, query: str, limit: int = 20) -> list[dict]:
    """약품 마스터 직접 검색 (자동완성용).

    이름 부분일치(우선) + 자모 fuzzy(보충)로 상위 결과를 반환한다. 원본 utils/drug_matcher.search 와 동일.
    """
    entries, jamo = index["entries"], index["jamo"]
    if not entries:
        return []
    q = (query or "").strip()
    if not q:
        return []

    ql = q.lower().replace(" ", "")
    seen = set()
    contains = []
    for i, e in enumerate(entries):
        if ql in e["name"].lower().replace(" ", ""):
            contains.append(i)
            seen.add(i)
    contains.sort(key=lambda i: len(entries[i]["name"]))
    results = [_pub(index, entries[i], 100.0) for i in contains[:limit]]

    if len(results) < limit:
        qj = decompose(_strip_form(_query_core(q)))
        if qj:
            for _, score, idx in process.extract(qj, jamo, scorer=fuzz.ratio, limit=limit * 3):
                if idx in seen or score < 55:
                    continue
                seen.add(idx)
                results.append(_pub(index, entries[idx], score))
                if len(results) >= limit:
                    break
    return results[:limit]
