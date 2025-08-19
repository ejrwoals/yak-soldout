#!/usr/bin/env python3
"""
약품 재고 검색 프로그램 실행 스크립트
PyInstaller로 패키징할 메인 진입점
"""

import os
import sys
import time
import webbrowser
import threading
import subprocess
from pathlib import Path

def resource_path(relative_path):
    """개발 및 PyInstaller 환경 모두에서 리소스의 절대 경로를 가져옵니다."""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    
    return os.path.join(base_path, relative_path)

def check_and_install_playwright():
    """Playwright 브라우저 환경 설정 (내장된 브라우저 사용)"""
    try:
        # 패키징된 환경에서 브라우저 경로 설정
        if getattr(sys, 'frozen', False):
            # PyInstaller 임시 디렉토리에서 내장된 브라우저 사용
            try:
                base_path = sys._MEIPASS
            except Exception:
                base_path = os.path.dirname(sys.executable)
            
            browsers_dir = os.path.join(base_path, 'ms-playwright')
            os.environ['PLAYWRIGHT_BROWSERS_PATH'] = browsers_dir
            
            print("✅ 내장된 Playwright 브라우저를 사용합니다.")
    except Exception as e:
        print(f"⚠️ Playwright 환경 설정 중 오류: {e}")
        print("프로그램은 계속 실행됩니다...")

def open_browser():
    """브라우저를 열어 애플리케이션 페이지로 이동"""
    time.sleep(2)  # 서버가 시작될 때까지 대기
    webbrowser.open('http://localhost:8000')

def main():
    """메인 실행 함수"""
    print("=" * 60)
    print("약품 재고 자동 검색 프로그램")
    print("=" * 60)
    
    # Playwright 브라우저 설치 확인 (패키징된 환경에서만)
    if getattr(sys, 'frozen', False):
        check_and_install_playwright()
    
    print("서버를 시작하는 중...")
    print("잠시 후 브라우저가 자동으로 열립니다.")
    print("프로그램을 종료하려면 브라우저를 닫거나 Ctrl+C를 누르세요.")
    print("=" * 60)
    
    # 브라우저 자동 열기 스레드 시작
    browser_thread = threading.Thread(target=open_browser)
    browser_thread.daemon = True
    browser_thread.start()
    
    # web_server.py 실행
    web_server_path = resource_path('web_server.py')
    
    # PyInstaller로 패키징된 경우와 개발 환경 구분
    if getattr(sys, 'frozen', False):
        # 패키징된 경우: web_server 모듈을 직접 import하여 실행
        import web_server
        import uvicorn
        
        # 작업 디렉토리를 실행 파일 위치로 변경
        os.chdir(os.path.dirname(sys.executable))
        
        # uvicorn 서버 실행
        uvicorn.run(
            web_server.app,
            host="127.0.0.1",
            port=8000,
            reload=False,
            log_level="info"
        )
    else:
        # 개발 환경: subprocess로 실행
        subprocess.run([sys.executable, web_server_path])

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n프로그램을 종료합니다...")
        sys.exit(0)
    except Exception as e:
        print(f"\n오류 발생: {e}")
        input("Enter 키를 눌러 종료하세요...")
        sys.exit(1)