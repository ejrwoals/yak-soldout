#!/usr/bin/env python3
"""
주문서 ↔ 약품 마스터 소급 연결 (reconcile)

주문서는 마스터에 없는 신약을 자유입력으로 먼저 작성할 수 있다. 이후 마스터를 업데이트하면
그 약이 새로 포함될 수 있는데, 이미 저장된 주문 항목은 자유입력 이름 그대로 남아 있다.

매칭/확인된 주문 항목은 저장 시 '마스터 공식명' 그대로 저장되므로,
마스터에 정확히 일치하지 않는 order_items.drug_name = '고아(orphan)' 약품으로 본다.
마스터 업데이트 후 이 고아들을 새 마스터로 fuzzy 매칭해, 사용자가 확인하면 공식명으로 연결한다.
"""

from typing import Any, Dict, List

import db
from utils import drug_matcher

# 연결 후보로 제시할 최소 유사도 (이 점수 미만이면 고아를 아예 제시하지 않음)
MIN_LINK_SCORE = drug_matcher.LOW_SCORE
# 드롭다운에 후보로 포함할 소프트 플로어 (최상위가 기준 이상이면, 그 외 후보는 이 점수 이상만 보여줌)
DROPDOWN_FLOOR = 55.0


def find_link_candidates(min_score: float = MIN_LINK_SCORE) -> List[Dict[str, Any]]:
    """마스터에 정확히 없는 주문 약품명을 새 마스터로 매칭해 연결 후보를 만든다.

    같은 이름의 주문 항목은 묶어서 1건으로 제시한다(연결 시 일괄 적용).
    각 고아마다 상위 후보 여러 개를 함께 줘서, 프론트 드롭다운에서 사용자가 고를 수 있게 한다.
    반환 각 항목: {orphan_name, item_count, auto, candidates:[{name, core, score, ...}]}
      - auto: 최상위가 확신(>=HIGH_SCORE)이라 기본 선택해도 되는지 여부
    """
    rows = db.query_all(
        """SELECT oi.drug_name AS name, COUNT(*) AS cnt
           FROM order_items oi
           WHERE TRIM(oi.drug_name) != ''
             AND NOT EXISTS (SELECT 1 FROM drug_master dm WHERE dm.name = oi.drug_name)
           GROUP BY oi.drug_name
           ORDER BY oi.drug_name"""
    )

    out: List[Dict[str, Any]] = []
    for r in rows:
        name = r["name"]
        cands = drug_matcher.top_candidates(name, 5)
        # 최상위가 기준 미만이면 쓸만한 제안이 없으므로 이 고아는 제외
        if not cands or cands[0].get("score", 0) < min_score:
            continue
        opts = [c for c in cands if c.get("score", 0) >= DROPDOWN_FLOOR and c["name"] != name]
        if not opts:
            continue
        out.append({
            "orphan_name": name,
            "item_count": r["cnt"],
            "auto": cands[0]["score"] >= drug_matcher.HIGH_SCORE,
            "candidates": [{
                "name": c["name"],
                "core": c["core"],
                "score": c["score"],
                "insurance_code": c.get("insurance_code", ""),
                "maker": c.get("maker", ""),
            } for c in opts],
        })
    return out


def apply_links(links: List[Dict[str, str]]) -> Dict[str, int]:
    """선택된 연결을 적용한다. 각 link = {orphan_name, master_name}.

    해당 고아 이름을 가진 모든 order_items.drug_name 을 마스터 공식명으로 일괄 갱신한다.
    반환: {"linked_names": 연결한 약품 수, "linked_items": 갱신된 주문 항목 수}.
    """
    linked_names = 0
    linked_items = 0
    with db.transaction() as conn:
        for lk in links or []:
            frm = (lk.get("orphan_name") or "").strip()
            to = (lk.get("master_name") or "").strip()
            if not frm or not to or frm == to:
                continue
            cur = conn.execute(
                "UPDATE order_items SET drug_name = ? WHERE drug_name = ?",
                (to, frm),
            )
            if cur.rowcount:
                linked_names += 1
                linked_items += cur.rowcount
    return {"linked_names": linked_names, "linked_items": linked_items}
