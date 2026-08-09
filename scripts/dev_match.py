"""개발용: 오타 교정(drug_matcher)이 Supabase drug_master 로 동작하는지 확인.

service_role 키로 drug_master 를 전량 조회 → 매칭 인덱스 구축 → 실제 주문지에서 나온
OCR 약품명 샘플들에 대해 매칭 상태를 출력한다. (login 연동 전, 로직 검증용)

실행: uv run python scripts/dev_match.py
전제: cloud_web/.env 에 SUPABASE_URL, SUPABASE_SERVICE_KEY + drug_master 이전 완료.
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / "cloud_web" / ".env")
sys.path.insert(0, str(ROOT / "cloud_web"))

from master_repo import fetch_drug_master  # noqa: E402
import drug_matcher  # noqa: E402

# 실제 주문지 사진에서 OCR로 읽힌 이름들(일부는 오독 포함).
SAMPLES = ["벡사움 20", "낙센에스 500/50", "묽시토 4", "징코민", "아트로벤트",
           "부스론 5", "네오신진연고", "라시토핀", "이가레스 40"]


def main() -> None:
    url = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get("SUPABASE_SERVICE_KEY", "").strip()
    if not url or not key:
        raise SystemExit("cloud_web/.env 에 SUPABASE_URL / SUPABASE_SERVICE_KEY 필요")

    from supabase import create_client

    client = create_client(url, key)
    drugs = fetch_drug_master(client)
    print(f"drug_master {len(drugs)}건 로드 → 인덱스 구축")
    index = drug_matcher.build_index(drugs)

    icon = {"matched": "✓ 일치", "candidate": "? 후보", "none": "✗ 없음", "skip": "- 미등록"}
    for name in SAMPLES:
        m = drug_matcher.match_one(index, name)
        best = m.get("best")
        line = f"[{icon[m['status']]}] {name!r:24}"
        if best:
            line += f" → {best['core']}  ({best['score']}점)"
        print(line)
        if m["status"] == "candidate":
            for c in m["candidates"][1:3]:
                print(f"           · 다른 후보: {c['core']} ({c['score']})")


if __name__ == "__main__":
    main()
