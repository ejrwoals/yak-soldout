#!/usr/bin/env bash
# yak-soldout dev 환경 실행 스크립트
# 사용법: ./dev.sh

set -e

cd "$(dirname "$0")"

VENV_PYTHON=".venv/bin/python"
PORT=8000

# 1) .venv 확인
if [ ! -x "$VENV_PYTHON" ]; then
    echo "❌ $VENV_PYTHON 을 찾을 수 없습니다."
    echo "   먼저 'uv venv' 로 가상환경을 만들고 의존성을 설치하세요."
    exit 1
fi

# 2) 포트 8000을 점유 중인 좀비 프로세스 정리
ZOMBIES=$(lsof -ti tcp:"$PORT" -sTCP:LISTEN 2>/dev/null || true)
if [ -n "$ZOMBIES" ]; then
    echo "⚠️  포트 $PORT 점유 프로세스 정리: $ZOMBIES"
    echo "$ZOMBIES" | xargs kill -9 2>/dev/null || true
    sleep 1
fi

# 3) 서버 실행 (exec로 교체하여 Ctrl+C 시그널을 직접 받도록)
exec "$VENV_PYTHON" web_server.py
