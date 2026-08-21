"""소스 실행과 PyInstaller 동결 실행을 모두 지원하는 경로 헬퍼.

동결하면 `Path(__file__).parent` 가 번들 폴더(`sys._MEIPASS`)를 가리킨다. 여기는
배포본을 교체하면 통째로 갈아엎히는 자리라 `.env` 나 `.session.json` 처럼 **사용자가
채우고 앱이 써야 하는 파일**을 두면 안 된다. 그래서 두 가지를 구분한다.

- `RESOURCE_DIR` : 번들된 읽기 전용 리소스(static/ 등). 동결 시 `sys._MEIPASS`.
- `DATA_DIR`     : 쓰기 가능한 사용자 파일(.env / .session.json / .settings.json).
                   동결 시 **exe 가 놓인 폴더** — 배포본을 덮어써도 살아남는다.

소스로 실행할 때는 둘 다 `apps/local_app/` 이라 기존 동작과 완전히 같다.
"""

import sys
from pathlib import Path

FROZEN = getattr(sys, "frozen", False)

if FROZEN:
    RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    DATA_DIR = Path(sys.executable).parent
else:
    RESOURCE_DIR = Path(__file__).resolve().parent
    DATA_DIR = RESOURCE_DIR
