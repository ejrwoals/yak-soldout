#!/usr/bin/env python3
"""자유입력(manual) 마스터 약품 → 정식(excel) 마스터 승격 (소급 연결)

주문서에 마스터에 없는 신약을 자유입력하면, 저장 시 source='manual' 마스터 행으로 자동 등록되어
즉시 OCR 매칭에 활용된다(db.register_free_input_drugs). 이후 엑셀 업데이트로 그 약의 정식 행
(source='excel')이 들어오면, manual 행을 정식 행으로 '승격'(병합)할 수 있다.

승격 = 정식명으로 order_items 갱신 + manual 규격을 정식 행에 병합 + manual 행 삭제
       (실제 적용은 db.promote_manual_drugs).
"""

from typing import Any, Dict, List

import db
from utils import drug_matcher

# 승격 후보로 제시할 최소 유사도 (이 점수 미만이면 후보를 아예 제시하지 않음)
MIN_LINK_SCORE = drug_matcher.LOW_SCORE
# 드롭다운에 후보로 포함할 소프트 플로어 (최상위가 기준 이상이면 그 외 후보는 이 점수 이상만)
DROPDOWN_FLOOR = 55.0


def find_promotion_candidates(min_score: float = MIN_LINK_SCORE) -> List[Dict[str, Any]]:
    """자유입력(manual) 마스터 행을 정식(excel) 행과 매칭해 승격 후보를 만든다.

    후보는 정식(excel) 약품으로만 한정한다(manual끼리 매칭은 승격이 아니므로 제외).
    반환 각 항목: {manual_id, manual_name, item_count, auto, candidates:[{name, core, score, ...}]}
      - auto: 최상위가 확신(>=HIGH_SCORE)이라 기본 선택해도 되는지 여부
    """
    manual_rows = db.list_manual_master_rows()
    if not manual_rows:
        return []
    excel_names = db.excel_master_names()
    if not excel_names:
        return []

    out: List[Dict[str, Any]] = []
    for row in manual_rows:
        name = row["name"]
        cands = drug_matcher.top_candidates(name, 6)
        # 정식(excel) 약품 후보만, 소프트 플로어 이상만 남긴다.
        # (manual 자기 자신의 이름은 excel_names에 없으므로 자연히 제외된다.)
        opts = [c for c in cands
                if c.get("score", 0) >= DROPDOWN_FLOOR and c["name"] in excel_names]
        if not opts or opts[0].get("score", 0) < min_score:
            continue
        out.append({
            "manual_id": row["id"],
            "manual_name": name,
            "item_count": row.get("item_count", 0),
            "auto": opts[0]["score"] >= drug_matcher.HIGH_SCORE,
            "candidates": [{
                "name": c["name"],
                "core": c["core"],
                "score": c["score"],
                "insurance_code": c.get("insurance_code", ""),
                "maker": c.get("maker", ""),
            } for c in opts],
        })
    return out


def apply_promotions(promotions: List[Dict[str, Any]]) -> Dict[str, int]:
    """선택된 승격을 적용한다. 각 promotion = {manual_id, excel_name}.

    반환: {"promoted": 승격한 약품 수, "updated_items": 갱신된 주문 항목 수}.
    """
    return db.promote_manual_drugs(promotions or [])
