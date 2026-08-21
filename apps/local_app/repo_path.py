"""리포지토리 루트를 sys.path 에 올린다 (import 만으로 효과 발생).

로컬 앱은 크롤링을 위해 루트의 공유 패키지 `scrapers`(Playwright 스크래퍼 8종 +
drug_data 데이터 모델)를 그대로 쓴다. 이 패키지는 품절약 서치앱의 로컬 SQLite나 앱
상태를 임포트하지 않아 "자동주문 솔루션은 로컬 DB를 쓰지 않는다"는 전제를 깨지 않는다.

(클라우드 웹 UI(스택 1)와는 여전히 코드를 공유하지 않는다. 그쪽은 Playwright가 없다.)
모노레포 구조: 이 파일은 apps/local_app/ 에 있으므로 루트는 두 단계 위다.
"""

import sys
from pathlib import Path

# 동결(PyInstaller) 시에는 scrapers 가 번들 폴더에 함께 들어가고 그 폴더는 이미
# sys.path 에 있다. 리포 루트라는 개념도 없으므로 아무것도 하지 않는다.
if not getattr(sys, "frozen", False):
    REPO_ROOT = Path(__file__).resolve().parents[2]

    if str(REPO_ROOT) not in sys.path:
        sys.path.append(str(REPO_ROOT))
