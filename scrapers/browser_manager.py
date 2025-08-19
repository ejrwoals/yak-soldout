import os
import sys
import platform
import asyncio
from typing import List, Dict, Any
from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page


class BrowserManager:
    """크로스 플랫폼 브라우저 관리"""
    
    def __init__(self, headless: bool = None):
        # 환경변수 HEADLESS가 설정되어 있으면 우선 적용
        if headless is None:
            env_headless = os.getenv('HEADLESS', 'true').lower()
            self.headless = env_headless not in ('false', '0', 'no')
        else:
            self.headless = headless
        self.playwright = None
        self.browser = None
        self.context = None
        
        # PyInstaller 환경에서 브라우저 경로 설정
        if getattr(sys, 'frozen', False):
            # PyInstaller 임시 디렉토리에서 브라우저 경로 설정
            try:
                base_path = sys._MEIPASS
            except Exception:
                base_path = os.path.dirname(sys.executable)
            
            browsers_dir = os.path.join(base_path, 'ms-playwright')
            os.environ['PLAYWRIGHT_BROWSERS_PATH'] = browsers_dir
    
    def __enter__(self):
        """Context manager 진입"""
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager 종료"""
        self.stop()
    
    def start(self):
        """브라우저 시작"""
        # Windows 환경변수 추가 설정 (전역 설정과 보완)
        if platform.system() == "Windows":
            try:
                os.environ.setdefault('PWTEST_MODE', '0')
                os.environ.setdefault('PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD', '0')
                print("🌐 Windows Playwright 환경변수 설정 완료")
            except Exception as e:
                print(f"⚠️ 환경변수 설정 실패 (무시 가능): {e}")
        
        # Playwright 시작
        try:
            self.playwright = sync_playwright().start()
            print("✅ Playwright 시작 성공")
        except Exception as e:
            print(f"❌ Playwright 시작 실패: {e}")
            raise
        
        # 플랫폼별 브라우저 설정
        browser_args = self._get_browser_args()
        
        # Chromium 사용 (가장 안정적)
        launch_options = {
            'headless': self.headless,
            'args': browser_args
        }
        
        # PyInstaller 환경에서는 브라우저 실행 파일 경로 직접 지정
        if getattr(sys, 'frozen', False):
            try:
                base_path = sys._MEIPASS
                # 가능한 브라우저 경로들 시도
                possible_paths = [
                    os.path.join(base_path, 'ms-playwright', 'chromium-1181', 'chrome-win', 'chrome.exe'),
                    os.path.join(base_path, 'ms-playwright', 'chromium_headless_shell-1181', 'chrome-win', 'headless_shell.exe'),
                ]
                
                for browser_path in possible_paths:
                    if os.path.exists(browser_path):
                        launch_options['executable_path'] = browser_path
                        print(f"✅ 브라우저 실행 파일 발견: {browser_path}")
                        break
                else:
                    print("⚠️ 내장 브라우저를 찾을 수 없습니다. 기본 설정으로 시도합니다.")
            except Exception as e:
                print(f"⚠️ 브라우저 경로 설정 중 오류: {e}")
        
        self.browser = self.playwright.chromium.launch(**launch_options)
        
        # 새 컨텍스트 생성 (쿠키, 세션 분리)
        self.context = self.browser.new_context(
            viewport={'width': 1280, 'height': 720},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
    
    def stop(self):
        """브라우저 정리"""
        if self.context:
            self.context.close()
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()
    
    def new_page(self) -> Page:
        """새 페이지 생성"""
        if not self.context:
            raise RuntimeError("브라우저가 시작되지 않았습니다. start() 메서드를 먼저 호출하세요.")
        
        page = self.context.new_page()
        
        # 기본 타임아웃 설정
        page.set_default_timeout(30000)  # 30초
        page.set_default_navigation_timeout(60000)  # 60초
        
        return page
    
    def _get_browser_args(self) -> List[str]:
        """플랫폼별 브라우저 인수 반환"""
        args = [
            '--no-first-run',
            '--no-default-browser-check',
            '--disable-dev-shm-usage',
            '--disable-extensions',
            '--disable-background-timer-throttling',
            '--disable-backgrounding-occluded-windows',
            '--disable-renderer-backgrounding',
        ]
        
        system = platform.system()
        
        if system == "Linux":
            args.extend([
                '--no-sandbox',
                '--disable-setuid-sandbox',
            ])
        elif system == "Darwin":  # macOS
            args.extend([
                '--no-sandbox',
            ])
        
        return args
    
    @staticmethod
    def install_browsers():
        """필요한 브라우저 설치 (처음 실행 시)"""
        try:
            from playwright._impl._driver import compute_driver_executable
            import subprocess
            import sys
            
            # Playwright 브라우저 설치
            subprocess.run([
                sys.executable, "-m", "playwright", "install", "chromium"
            ], check=True)
            
            print("브라우저 설치가 완료되었습니다.")
            return True
            
        except Exception as e:
            print(f"브라우저 설치 실패: {e}")
            return False