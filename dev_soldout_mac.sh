#!/usr/bin/env bash
# 품절약 서치앱 dev 환경 실행 스크립트 (모노레포: apps/soldout/)
# 사용법: ./dev_soldout_mac.sh

set -e

cd "$(dirname "$0")"
ROOT="$(pwd)"

VENV_PYTHON="$ROOT/.venv/bin/python"
# 8000/8001은 다른 로컬 프로젝트가 사용하므로 8002 사용.
# export 해야 web_server.py 가 이 값을 읽는다 (안 하면 좀비 정리만 8002, 서버는 기본값으로 떠 불일치).
export PORT=8002

# 1) .venv 확인
if [ ! -x "$VENV_PYTHON" ]; then
    echo "❌ $VENV_PYTHON 을 찾을 수 없습니다."
    echo "   먼저 'uv venv' 로 가상환경을 만들고 의존성을 설치하세요."
    exit 1
fi

# 2) 해당 포트를 점유 중인 좀비 프로세스 정리 (say-boyak의 8000은 건드리지 않음)
ZOMBIES=$(lsof -ti tcp:"$PORT" -sTCP:LISTEN 2>/dev/null || true)
if [ -n "$ZOMBIES" ]; then
    echo "⚠️  포트 $PORT 점유 프로세스 정리: $ZOMBIES"
    echo "$ZOMBIES" | xargs kill -9 2>/dev/null || true
    sleep 1
fi

# 3) 서버 실행 (앱 디렉토리에서 실행 — config.json/data/ 는 apps/soldout/ 기준)
cd apps/soldout
exec "$VENV_PYTHON" web_server.py
