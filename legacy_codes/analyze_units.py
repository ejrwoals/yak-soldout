#!/usr/bin/env python3
"""drug_master.unit 규격 빈도 분석 → JSON 출력.

각 행의 unit은 "100T, 30T"처럼 여러 규격이 ", "로 합쳐져 있을 수 있다.
규격 토큰별로 "그 규격을 가진 약품(행) 수"를 세어 빈도 오름차순으로 정렬해 저장한다.
"""

import json
from collections import Counter

import db

UNIT_SEP = ", "
OUTPUT = "unit_frequency.json"


def main():
    db.get_conn()
    rows = db.query_all(
        "SELECT unit FROM drug_master WHERE unit IS NOT NULL AND TRIM(unit) != ''"
    )

    counter = Counter()
    rows_with_unit = 0
    for r in rows:
        raw = (r["unit"] or "").strip()
        if not raw:
            continue
        rows_with_unit += 1
        # 한 행 내 중복 규격은 한 번만 (그 약품이 해당 규격을 '가진다'를 1로 셈)
        units = {u.strip() for u in raw.split(UNIT_SEP) if u.strip()}
        for u in units:
            counter[u] += 1

    # 빈도 오름차순 (동률이면 규격명 가나다/알파벳 순)
    ordered = sorted(counter.items(), key=lambda kv: (kv[1], kv[0]))

    result = {
        "total_rows_with_unit": rows_with_unit,
        "distinct_units": len(counter),
        "frequency": {unit: count for unit, count in ordered},
    }

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"✅ {OUTPUT} 생성 — unit 보유 행 {rows_with_unit}개, 서로 다른 규격 {len(counter)}종")
    print("\n빈도 오름차순 (하위 10종):")
    for unit, count in ordered[:10]:
        print(f"  {unit}: {count}개")
    print("\n빈도 상위 10종:")
    for unit, count in ordered[-10:]:
        print(f"  {unit}: {count}개")


if __name__ == "__main__":
    main()
