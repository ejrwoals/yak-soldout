"""원본 매처(utils/drug_matcher) vs 신규 매처(cloud_web/drug_matcher) 출력 비교.

목적: 신규 매처가 원본과 '완벽하게 동일'한지 증명.
- A) 원본(로컬 SQLite, id순)  vs  신규(동일 로컬 데이터, 동일 id순)
     → 로직이 그대로 복제됐다면 100% 일치해야 함.
- B) 원본(id순)  vs  신규(Supabase, 이름순)
     → 차이가 있다면 '데이터 순서'(동점 후보 tie-break) 때문인지 확인.

로컬 DB는 읽기 전용 의도. 실행: uv run python scripts/compare_matcher.py
"""

import random
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))              # import db, utils.*
load_dotenv(ROOT / "cloud_web" / ".env")

import db  # noqa: E402
from utils import drug_matcher as orig  # noqa: E402

sys.path.insert(0, str(ROOT / "cloud_web"))
import drug_matcher as new  # noqa: E402  (cloud_web/drug_matcher.py)
import master_repo  # noqa: E402
import os  # noqa: E402

PHOTO = ["벡사움 20", "낙센에스 500/50", "묽시토 4", "징코민", "일성)호이펜", "아트로벤트",
         "네오신진연고", "시네츄라", "부스론 5", "진크텍", "루키오 10", "라시토핀",
         "이가레스 40", "한미오메가", "피타큐젯 40", "코수젯 10/10"]


def sig(m: dict) -> tuple:
    """비교용 시그니처: (status, best이름, best점수, [(후보이름, 점수)...])."""
    b = m.get("best")
    best = (b["name"], b["score"]) if b else None
    cands = [(c["name"], c["score"]) for c in m.get("candidates", [])]
    return (m["status"], best, cands)


def main() -> None:
    local_drugs = db.load_drug_master()  # id 순
    print(f"로컬 drug_master: {len(local_drugs)}건")

    # 신규 매처용 인덱스 두 벌
    idx_local = new.build_index(local_drugs)  # 동일 데이터·동일 순서

    # 테스트 이름: 사진 16개 + 마스터 표시명 랜덤 60개(정확일치 검증)
    random.seed(42)
    master_names = [d["name"] for d in local_drugs]
    sample_cores = random.sample(master_names, 60)
    names = PHOTO + sample_cores

    # A) 원본 vs 신규(로컬 동일순서)
    mismatchA = []
    for nm in names:
        if sig(orig.match_one(nm)) != sig(new.match_one(idx_local, nm)):
            mismatchA.append(nm)

    print(f"\n[A] 원본 vs 신규(동일 데이터·순서): {len(names)}개 중 불일치 {len(mismatchA)}개")
    for nm in mismatchA[:10]:
        print("   ✗", nm)
        print("      원본:", sig(orig.match_one(nm)))
        print("      신규:", sig(new.match_one(idx_local, nm)))

    # B) 순서 영향: Supabase(이름순) 인덱스와 비교 (service_role)
    url = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get("SUPABASE_SERVICE_KEY", "").strip()
    if url and key:
        from supabase import create_client
        sb_drugs = master_repo.fetch_drug_master(create_client(url, key))
        idx_sb = new.build_index(sb_drugs)
        mismatchB = [nm for nm in names if sig(orig.match_one(nm)) != sig(new.match_one(idx_sb, nm))]
        print(f"\n[B] 원본 vs 신규(Supabase 이름순): {len(names)}개 중 불일치 {len(mismatchB)}개  (순서 영향)")
        for nm in mismatchB[:10]:
            print("   ✗", nm)
            print("      원본:", sig(orig.match_one(nm)))
            print("      신규(SB):", sig(new.match_one(idx_sb, nm)))
    else:
        print("\n[B] 스킵 (SUPABASE_SERVICE_KEY 없음)")

    print("\n결론:", "A 완전일치 → 로직 동일 ✅" if not mismatchA else "A 불일치 있음 → 로직 차이 ⚠️")


if __name__ == "__main__":
    main()
