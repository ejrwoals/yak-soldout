#!/usr/bin/env python3
"""
약품명 fuzzy 매칭 (2단계: OCR 오타 보정)

OCR 로 읽은 약품명을 등록된 약품 마스터(DB drug_master 테이블)와 비교해
오타를 잡아낸다. 한글은 단순 글자 단위 편집거리로는 부정확하므로 자모(초/중/종성)로
분해한 뒤 유사도를 계산한다.

마스터 약품명은 매우 길고 상세하므로(예: "가나칸정50밀리그램(이토프리드염산염)_(50mg/1정)")
손글씨의 짧은 약품명과 직접 비교가 어렵다. 그래서 숫자/괄호 앞까지의 '핵심 이름'을
뽑아 그것끼리 비교한다.

자동 교정은 하지 않는다(Human-in-the-loop). 매칭 결과만 검수 화면에 후보로 제시한다.
"""

import re

from rapidfuzz import fuzz, process

from utils import drug_master

# 유사도 임계값 (자모 기반 0~100)
HIGH_SCORE = 90   # 이 이상이면 마스터에 있는 약으로 확신 (일치 배지)
LOW_SCORE = 70    # 이 이상~HIGH 미만이면 후보 제시 (확인 필요)
MAX_CANDIDATES = 5
# 브랜드는 같지만 용량(규격) 숫자가 다르면 점수를 이 값으로 제한 → '일치'가 아닌 '확인 필요'로
STRENGTH_MISMATCH_CAP = 78

# 제형 접미 — 매칭 전 핵심 이름 끝에서 떼어낸다 (손글씨는 보통 제형을 생략).
# 길이가 긴 것부터 시도해 한 번만 제거. (예: '리포텍스서방정' → '리포텍스', '호이펜주' → '호이펜')
_FORM_SUFFIXES = sorted([
    "서방정", "서방캡슐", "장용정", "이연정", "점안액", "점비액", "현탁액", "건조시럽",
    "시럽", "주사액", "주사", "캡슐", "캅셀", "정제", "좌제", "과립", "분말", "패치",
    "연고", "크림", "로션", "겔", "산", "액", "환", "정", "주",
], key=len, reverse=True)


def _strip_form(s: str) -> str:
    """핵심 이름 끝의 제형 접미를 한 번 제거."""
    for suf in _FORM_SUFFIXES:
        if len(s) > len(suf) and s.endswith(suf):
            return s[: -len(suf)]
    return s

# 한글 자모 테이블
_CHO = list("ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ")
_JUNG = list("ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ")
_JONG = ["", "ㄱ", "ㄲ", "ㄳ", "ㄴ", "ㄵ", "ㄶ", "ㄷ", "ㄹ", "ㄺ", "ㄻ", "ㄼ", "ㄽ",
         "ㄾ", "ㄿ", "ㅀ", "ㅁ", "ㅂ", "ㅄ", "ㅅ", "ㅆ", "ㅇ", "ㅈ", "ㅊ", "ㅋ", "ㅌ", "ㅍ", "ㅎ"]

# 핵심 이름(브랜드) 추출: 숫자 / '(' / '_' / '/' 등 부가정보가 시작되기 전까지
_CORE_CUT = re.compile(r"[0-9(_/\[].*$")
# 손글씨 약품명 앞의 제약사 접두 (예: "일성)호이펜", "부광)이맥...")
_MAKER_PREFIX = re.compile(r"^[가-힣A-Za-z]{1,6}\)")
# 용량(규격) 숫자: 첫 번째 숫자 토큰 (예: '300', '600', '100/1000', '5/50')
_STRENGTH_RE = re.compile(r"\d+(?:[./]\d+)*")
# 표시용 이름: 첫 '(' 또는 '_' 앞까지 (예: '리포덱스정300밀리그램(리팜피신)_(0.3g/1정)' → '리포덱스정300밀리그램')
_DISPLAY_CUT = re.compile(r"[(_].*$")


def _brand_score(q: str, cand: str) -> float:
    """브랜드(자모열) 유사도. 짧은 질의가 긴 마스터명의 접두인 경우를 부분일치로 보정한다.

    - 완전 동일 → 100 (예: '아모잘탄'은 '아모잘탄플러스'보다 '아모잘탄'에 우선)
    - 한쪽이 다른 쪽의 접두 → 부분일치 점수(최대 96, 완전일치보다는 낮게)
      ('아트로벤트' ↔ '아트로벤트흡입액유디비' 같은 케이스)
    - 그 외 → 일반 ratio (오타 대응)
    """
    if q == cand:
        return 100.0
    if cand.startswith(q) or q.startswith(cand):
        return min(fuzz.partial_ratio(q, cand), 96.0)
    return fuzz.ratio(q, cand)


def _strength(s: str) -> str:
    """이름에서 첫 용량 숫자 토큰을 뽑는다. 없으면 ''."""
    m = _STRENGTH_RE.search(s)
    return m.group(0) if m else ""


def _display(name: str) -> str:
    """후보 목록에 보여줄 짧은 이름 (용량까지 포함, 성분/포장 괄호 제거)."""
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
    """마스터 약품명에서 핵심 이름 추출. 예) '가드메트정100/1000밀리그램_(1정)' → '가드메트정'."""
    return _CORE_CUT.sub("", name.strip()).strip()


def _query_core(name: str) -> str:
    """OCR 약품명 정규화 — 제약사 접두 제거 + 핵심 이름 추출.
    예) '일성)호이펜' → '호이펜',  '리포텍스 600mg' → '리포텍스'."""
    s = _MAKER_PREFIX.sub("", name.strip())
    return _CORE_CUT.sub("", s).strip()


# (key, entries, jamo_list, units) 캐시 — 마스터(DB)가 바뀌면 재구축
_cache = {"key": None, "entries": None, "jamo": None, "units": None}


def _unit_tokens(s: str) -> list[str]:
    """", "로 합쳐 저장한 규격 문자열을 토큰 리스트로 분해."""
    return [u.strip() for u in (s or "").split(",") if u.strip()]


def _known_units(core: str) -> list[str]:
    """해당 약품(표시 핵심명 기준)의 알려진 규격 집합. 개수 오름차순으로 정렬해 반환.

    같은 표시명을 가진 여러 마스터 행의 수집 규격(unit)+직접추가 규격(unit_manual)을 합친 것.
    """
    units = (_cache.get("units") or {}).get(core)
    if not units:
        return []

    def _count_key(u: str):
        m = re.match(r"\s*(\d+(?:\.\d+)?)", u)
        return (0, float(m.group(1))) if m else (1, u)

    return sorted(units, key=_count_key)


def _get_index():
    """마스터를 (entries, 자모열 리스트)로 인덱싱. DB 변경 시 갱신."""
    key = drug_master.cache_key()
    if not key[0]:  # count == 0 → 마스터 미등록
        return None, None
    if _cache["key"] == key and _cache["entries"] is not None:
        return _cache["entries"], _cache["jamo"]

    data = drug_master.load_master()
    if not data:
        return None, None

    entries, jamo = [], []
    units: dict[str, set] = {}   # 표시 핵심명(core) → 규격 토큰 집합
    for d in data.get("drugs", []):
        name = d.get("name", "")
        core = _master_core(name)
        if not core:
            continue
        disp = _display(name)            # 후보 표시용 (용량 포함) = 규격 집계 키
        entries.append({
            "name": name,
            "core": disp,
            "strength": _strength(name),     # 용량 숫자 (매칭 비교용)
            "insurance_code": d.get("insurance_code", ""),
            "maker": d.get("maker", ""),
        })
        # 매칭(브랜드 유사도)은 숫자·제형 뗀 형태로
        jamo.append(decompose(_strip_form(core)))
        # 같은 표시명의 수집·직접추가 규격을 합쳐 둔다 (규격 자동보정용)
        toks = _unit_tokens(d.get("unit", "")) + _unit_tokens(d.get("unit_manual", ""))
        if toks:
            units.setdefault(disp, set()).update(toks)

    _cache.update(key=key, entries=entries, jamo=jamo, units=units)
    return entries, jamo


def _ranked_candidates(ocr_name: str) -> list[dict]:
    """OCR 약품명에 대한 상위 후보 리스트(점수 내림차순, 표시명 기준 중복 제거).

    상태 판정 없이 순수 순위만 반환한다. match_one / top_candidates 가 공유한다.
    """
    entries, jamo = _get_index()
    if not entries:
        return []

    q = decompose(_strip_form(_query_core(ocr_name)))
    if not q:
        return []
    q_strength = _strength(_MAKER_PREFIX.sub("", ocr_name))

    # 전체 항목을 접두-보정 점수로 평가 (긴 마스터명의 접두를 놓치지 않도록 사전 필터 없이),
    # 이어서 용량 일치 여부로 보정해 재정렬한다.
    scored = []
    for idx, cand_jamo in enumerate(jamo):
        final = _brand_score(q, cand_jamo)
        e = entries[idx]
        # 양쪽 다 용량이 있고 다르면 '일치'로 보지 않도록 점수 제한
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
            "known_units": _known_units(e["core"]),
        })
        if len(candidates) >= MAX_CANDIDATES:
            break
    return candidates


def top_candidates(ocr_name: str, limit: int = MAX_CANDIDATES) -> list[dict]:
    """OCR 약품명의 상위 후보 N개 (상태 판정 없이). 소급 연결 드롭다운 등에 사용."""
    return _ranked_candidates(ocr_name)[:limit]


def match_one(ocr_name: str) -> dict:
    """OCR 약품명 하나에 대한 매칭 결과.

    반환: {
      status: 'matched' | 'candidate' | 'none' | 'skip',
      best:   {name, core, score, insurance_code, maker} | None,
      candidates: [ {name, core, score, ...}, ... ]   # status=='candidate' 일 때만 채움
    }
    'skip' = 마스터 미등록.
    """
    entries, _ = _get_index()
    if not entries:
        return {"status": "skip", "best": None, "candidates": []}

    candidates = _ranked_candidates(ocr_name)
    if not candidates:
        return {"status": "none", "best": None, "candidates": []}

    best = candidates[0]
    if best["score"] >= HIGH_SCORE:
        return {"status": "matched", "best": best, "candidates": []}
    if best["score"] >= LOW_SCORE:
        return {"status": "candidate", "best": best, "candidates": candidates}
    return {"status": "none", "best": best, "candidates": []}


def _pub(e: dict, score: float) -> dict:
    return {
        "name": e["name"],
        "core": e["core"],
        "score": round(score, 1),
        "insurance_code": e["insurance_code"],
        "maker": e["maker"],
        "known_units": _known_units(e["core"]),
    }


def search(query: str, limit: int = 20) -> list[dict]:
    """약품 마스터 직접 검색 — 후보 드롭다운에 원하는 약이 없을 때 사용.

    이름 부분일치(우선) + 자모 fuzzy(보충)로 상위 결과를 반환한다.
    """
    entries, jamo = _get_index()
    if not entries:
        return []
    q = query.strip()
    if not q:
        return []

    ql = q.lower().replace(" ", "")
    seen = set()
    contains = []
    for i, e in enumerate(entries):
        if ql in e["name"].lower().replace(" ", ""):
            contains.append(i)
            seen.add(i)
    # 부분일치는 이름이 짧을수록(더 정확할수록) 위로
    contains.sort(key=lambda i: len(entries[i]["name"]))
    results = [_pub(entries[i], 100.0) for i in contains[:limit]]

    # 부족하면 자모 fuzzy 로 보충 (오타 입력 대응)
    if len(results) < limit:
        qj = decompose(_strip_form(_query_core(q)))
        if qj:
            for _, score, idx in process.extract(qj, jamo, scorer=fuzz.ratio, limit=limit * 3):
                if idx in seen or score < 55:
                    continue
                seen.add(idx)
                results.append(_pub(entries[idx], score))
                if len(results) >= limit:
                    break
    return results[:limit]


def attach_matches(items: list[dict]) -> list[dict]:
    """OCR 추출 결과 각 항목에 match 정보를 덧붙인다."""
    for it in items:
        it["match"] = match_one(it.get("drug_name", ""))
    return items
