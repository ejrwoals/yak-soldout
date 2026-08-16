"""리포지토리 루트를 sys.path 에 올린다 (import 만으로 효과 발생).

로컬 앱은 크롤링을 위해 루트의 `scrapers`(Playwright 스크래퍼 8종)와 `models.drug_data`
를 그대로 쓴다. 두 모듈은 로컬 SQLite(`db.py`)나 품절약 서치앱 상태를 임포트하지 않아
"자동주문 솔루션은 로컬 DB를 쓰지 않는다"는 전제를 깨지 않는다 — 읽기 전용 재사용이다.

(클라우드 웹 UI(스택 1)와는 여전히 코드를 공유하지 않는다. 그쪽은 Playwright가 없다.)
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

if str(REPO_ROOT) not in sys.path:
    sys.path.append(str(REPO_ROOT))
