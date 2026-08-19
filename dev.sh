#!/usr/bin/env bash
# 약국 주문 Agent — 로컬 관리자 앱 실행 스크립트 (apps/local_app/)
# FastAPI 서버(포트 8770)를 띄우고 PyWebView 데스크톱 창을 연다.
# 사용법: ./dev.sh

set -e

cd "$(dirname "$0")"
ROOT="$(pwd)"

VENV_PYTHON="$ROOT/.venv/bin/python"
PORT=8770   # apps/local_app/main.py 의 고정 포트 (loopback OAuth 콜백 주소와 맞물려 있음)

# 1) .venv 확인
if [ ! -x "$VENV_PYTHON" ]; then
    echo "❌ $VENV_PYTHON 을 찾을 수 없습니다."
    echo "   먼저 'uv venv' 로 가상환경을 만들고 의존성을 설치하세요:"
    echo "   uv pip install -r apps/local_app/requirements.txt"
    exit 1
fi

# 2) 해당 포트를 점유 중인 좀비 프로세스 정리
ZOMBIES=$(lsof -ti tcp:"$PORT" -sTCP:LISTEN 2>/dev/null || true)
if [ -n "$ZOMBIES" ]; then
    echo "⚠️  포트 $PORT 점유 프로세스 정리: $ZOMBIES"
    echo "$ZOMBIES" | xargs kill -9 2>/dev/null || true
    sleep 1
fi

# 3) 로컬 앱 실행 (PyWebView 창 + 로컬 서버)
exec "$VENV_PYTHON" apps/local_app/main.py
