#!/usr/bin/env python3
"""로컬 앱 진입점 — FastAPI 서버를 백그라운드로 띄우고 PyWebView 창을 연다.

로그인(Google OAuth)은 임베디드 웹뷰에서 막히므로 Api.start_login 이 **시스템 브라우저**를
연다(webbrowser.open). 창 UI 는 window.pywebview.api.start_login 으로 이를 호출한다.

실행:  uv run python apps/local_app/main.py
(브라우저에서만 테스트하려면:  uv run uvicorn app:app --port 8770  후 localhost:8770)
"""

import threading
import time
import webbrowser

import uvicorn

from app import app

PORT = 8770


class Api:
    """PyWebView JS ↔ Python 브릿지."""

    def start_login(self):
        webbrowser.open(f"http://localhost:{PORT}/auth/start")
        return True


def _run_server():
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")


def main():
    threading.Thread(target=_run_server, daemon=True).start()
    time.sleep(1.0)
    import webview  # 지연 임포트 — 브라우저 테스트 시 pywebview 불필요

    webview.create_window(
        "자동주문 (로컬)", f"http://localhost:{PORT}/",
        js_api=Api(), width=1120, height=820,
    )
    webview.start()


if __name__ == "__main__":
    main()
