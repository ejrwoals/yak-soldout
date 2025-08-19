# PyInstaller 빌드 및 배포 가이드 (Playwright 브라우저 내장 버전)

## 개요
이 가이드는 Python 웹 애플리케이션을 PyInstaller를 사용하여 **Playwright 브라우저가 내장된** 독립 실행형 .exe 파일로 빌드하고 배포하는 전체 과정을 다룹니다.

### 다빈도 명령어
```powershell
# 이전 빌드 파일 정리 (권한 문제 해결)
Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue

# 원-폴더 모드로 빌드 (권장) - 브라우저 포함으로 시간이 오래 걸림
pyinstaller yak_soldout.spec

# dist 폴더로 이동
cd dist

# ZIP 파일 생성
Compress-Archive -Path "약품재고검색" -DestinationPath "품절약똑똑이for이안약국.zip" -Force
```

## 특징
- ✅ **완전 독립 실행**: Python 설치 불필요
- ✅ **브라우저 내장**: 인터넷 연결 없이도 바로 실행 가능
- ✅ **원클릭 솔루션**: 별도 설치 과정 없음
- ⚠️ **파일 크기**: 약 200-300MB (브라우저 포함)

## 전제 조건
- Python 3.11+ 설치
- 프로젝트가 가상환경에서 개발됨 (`.venv` 폴더 존재)
- 모든 종속성이 `requirements.txt`에 정의됨
- **Playwright 브라우저가 설치되어 있어야 함**

## 1단계: 환경 준비

### 가상환경 활성화
```powershell
# PowerShell에서
.\.venv\Scripts\Activate.ps1

# 또는 Command Prompt에서
.venv\Scripts\activate
```

### PyInstaller 및 Playwright 브라우저 설치
```bash
# uv를 사용하는 경우
uv pip install pyinstaller

# 또는 일반 pip 사용
pip install pyinstaller

# Playwright 브라우저 설치 (중요!)
playwright install chromium
```

**중요**: 브라우저 설치 후 설치된 브라우저 경로를 확인하세요:
```bash
# 브라우저 설치 경로 확인
python -c "from playwright.sync_api import sync_playwright; p = sync_playwright().start(); print('Browser path:', p.chromium.executable_path); p.stop()"

# 예상 출력: Browser path: C:\Users\[사용자명]\AppData\Local\ms-playwright\chromium-1181\chrome-win\chrome.exe
```

## 2단계: 코드 수정 (PyInstaller 호환성)

### 2-1. web_server.py 수정
```python
# 파일 상단에 resource_path 함수 추가
def resource_path(relative_path):
    """개발 및 PyInstaller 환경 모두에서 리소스의 절대 경로를 가져옵니다."""
    try:
        # PyInstaller는 임시 폴더를 만들고 _MEIPASS에 경로를 저장합니다
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    
    return os.path.join(base_path, relative_path)

# 정적 파일 경로 설정 수정
if getattr(sys, 'frozen', False):
    # 번들된 경우
    static_folder = resource_path('static')
    template_folder = resource_path('templates')
    app.mount("/static", StaticFiles(directory=static_folder), name="static")
    templates = Jinja2Templates(directory=template_folder)
else:
    # 개발 환경인 경우
    app.mount("/static", StaticFiles(directory="static"), name="static")
    templates = Jinja2Templates(directory="templates")
```

### 2-2. run_app.py 생성 (메인 진입점)
```python
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
import glob
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
            log_level="info",
            access_log=False,
            log_config=None
        )
    else:
        # 개발 환경: subprocess로 실행
        web_server_path = resource_path('web_server.py')
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
```

### 2-3. browser_manager.py 수정
```python
# BrowserManager 클래스 __init__ 메소드에 추가
def __init__(self, headless: bool = None):
    # ... 기존 코드 ...
    
    # PyInstaller 환경에서 브라우저 경로 설정
    if getattr(sys, 'frozen', False):
        # PyInstaller 임시 디렉토리에서 브라우저 경로 설정
        try:
            base_path = sys._MEIPASS
        except Exception:
            base_path = os.path.dirname(sys.executable)
        
        browsers_dir = os.path.join(base_path, 'ms-playwright')
        os.environ['PLAYWRIGHT_BROWSERS_PATH'] = browsers_dir

# start 메소드의 Chromium 실행 부분 수정
def start(self):
    # ... 기존 코드 ...
    
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
```

## 3단계: PyInstaller Spec 파일 생성

### yak_soldout.spec 파일 생성
```python
# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

# Analysis 객체 - 필요한 모든 파일과 데이터를 정의
a = Analysis(
    ['run_app.py'],  # 메인 진입점
    pathex=[],
    binaries=[],
    datas=[
        ('templates', 'templates'),
        ('static', 'static'),
        ('data', 'data'),
        ('geoweb-soldout-list.json', '.'),
        ('exclusion-list.json', '.'),
        ('info.txt', '.'),
        ('web_server.py', '.'),  # web_server.py 포함
        ('models', 'models'),     # models 폴더 포함
        ('utils', 'utils'),       # utils 폴더 포함
        ('scrapers', 'scrapers'), # scrapers 폴더 포함
        # Playwright 브라우저 포함 (전체 ms-playwright 폴더)
        (r'C:\Users\[사용자명]\AppData\Local\ms-playwright', 'ms-playwright'),
    ],
    hiddenimports=[
        'uvicorn.logging',
        'uvicorn.loops',
        'uvicorn.loops.auto',
        'uvicorn.protocols',
        'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan',
        'uvicorn.lifespan.on',
        'websockets',
        'websockets.legacy',
        'websockets.legacy.server',
        'jinja2',
        'plyer',
        'plyer.platforms.win.notification',
        'playwright',
        'playwright.sync_api',
        'playwright.async_api',
        'pandas',
        'numpy',
        'openpyxl',
        'xlrd',
        'chardet',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# EXE 객체 - 실행 파일 속성 정의
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='약품재고검색',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,  # 콘솔 창 표시 (서버 로그 확인용), 실제 배포시에는 False로 변경
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon='app.ico',  # 아이콘 파일이 있으면 주석 해제
)

# COLLECT - 원-폴더 모드용 (안정성을 위해 권장)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='약품재고검색',
)
```

## 4단계: 빌드 실행

### 빌드 명령어
```powershell
# 이전 빌드 파일 정리 (권한 문제 해결)
Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue

# 원-폴더 모드로 빌드 (권장) - 브라우저 포함으로 시간이 오래 걸림
pyinstaller yak_soldout.spec

# 또는 원-파일 모드로 빌드 (선택사항)
# pyinstaller --onefile yak_soldout.spec
```

### 빌드 시 주의사항
- **빌드 시간**: Playwright 브라우저(약 200MB) 포함으로 5-10분 소요
- **권한 문제**: 기존 실행 파일이 실행 중이면 종료 후 빌드
- **확인 메시지**: dist 폴더 삭제 확인 시 `y` 입력

### 빌드 확인
```powershell
# 생성된 파일 확인
ls dist

# 테스트 실행
.\dist\약품재고검색\약품재고검색.exe
```

## 5단계: 배포 준비

### ZIP 파일 생성
```powershell
# dist 폴더로 이동
cd dist

# ZIP 파일 생성
Compress-Archive -Path "약품재고검색" -DestinationPath "품절약똑똑이for이안약국.zip" -Force

# 또는 7zip 사용 (설치된 경우)
# 7z a "약품재고검색_v1.0.zip" "약품재고검색\"
```

## 6단계: 사용자 배포 가이드

### 사용자에게 제공할 설명서

```markdown
# 약품재고검색 프로그램 설치 및 사용법 (브라우저 내장 버전)

## 시스템 요구사항
- Windows 10/11 (64비트)
- **인터넷 연결 불필요** (브라우저 내장)

## 설치 방법
1. `약품재고검색_v1.0.zip` 파일을 다운로드합니다
2. 압축을 원하는 위치에 해제합니다
3. 압축 해제된 `약품재고검색` 폴더를 확인합니다

## 실행 방법
1. `약품재고검색` 폴더를 엽니다
2. `약품재고검색.exe` 파일을 더블클릭합니다
3. **"내장된 Playwright 브라우저를 사용합니다"** 메시지 확인
4. 브라우저가 자동으로 열리고 프로그램이 바로 시작됩니다

## 종료 방법
- 브라우저를 닫거나
- 콘솔 창에서 Ctrl+C를 누릅니다

## 특징
- ✅ **즉시 실행**: 별도 브라우저 설치 불필요
- ✅ **오프라인 작동**: 인터넷 연결 없이도 사용 가능
- ✅ **완전 독립**: Python 설치 불필요

## 주의사항
- 실행 파일을 다른 위치로 옮기지 마세요 (폴더 째로 이동은 가능)
- 안티바이러스에서 차단되면 예외 목록에 추가하세요
- 파일 크기가 약 200-300MB입니다 (브라우저 포함)
```

## 문제 해결

### 일반적인 문제

#### 1. 안티바이러스 오탐
```powershell
# Windows Defender 예외 추가
# Windows 설정 > 업데이트 및 보안 > Windows 보안 > 바이러스 및 위협 방지
# > 바이러스 및 위협 방지 설정 > 예외 추가
```

#### 2. 브라우저 내장 경로 문제
브라우저가 내장되어 있음에도 실행되지 않는 경우:
```powershell
# 실제 설치된 브라우저 폴더 확인
dir "C:\Users\[사용자명]\AppData\Local\ms-playwright" -Recurse -Name | findstr ".exe"

# spec 파일에서 정확한 경로로 수정 필요
```

#### 3. 빌드 권한 오류
빌드 시 "액세스가 거부되었습니다" 오류가 발생하는 경우:
```powershell
# 실행 중인 프로세스 모두 종료
# 작업 관리자에서 약품재고검색.exe 프로세스 확인

# 강제 삭제 후 빌드
Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue
pyinstaller yak_soldout.spec
```

#### 4. 빌드 오류 디버깅
```powershell
# 상세 로그와 함께 빌드
pyinstaller --log-level=DEBUG yak_soldout.spec

# 경고 파일 확인
type build\yak_soldout\warn-yak_soldout.txt
```

## 고급 옵션

### 아이콘 추가
```python
# yak_soldout.spec에서 수정
exe = EXE(
    # ... 기존 설정 ...
    icon='app.ico',  # 주석 해제하고 ico 파일 경로 지정
)
```

### 콘솔 창 숨기기 (GUI 모드)
```python
# yak_soldout.spec에서 수정
exe = EXE(
    # ... 기존 설정 ...
    console=False,  # True를 False로 변경
)
```

### 원-파일 모드로 배포
```powershell
# 원-파일 모드 빌드
pyinstaller --onefile yak_soldout.spec

# 결과: dist\약품재고검색.exe (단일 파일)
```

## 버전 관리

### requirements.txt 업데이트
```bash
# 현재 환경의 패키지 목록 저장
pip freeze > requirements.txt
```

### 빌드 스크립트 자동화
```powershell
# build.ps1 스크립트 생성
@"
# 빌드 자동화 스크립트
Write-Host "약품재고검색 프로그램 빌드 시작..." -ForegroundColor Green

# 가상환경 활성화
.\.venv\Scripts\Activate.ps1

# 이전 빌드 정리
Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue

# 빌드 실행
pyinstaller yak_soldout.spec

if ($LASTEXITCODE -eq 0) {
    Write-Host "빌드 성공!" -ForegroundColor Green
    
    # ZIP 파일 생성
    cd dist
    $version = Get-Date -Format "yyyy-MM-dd"
    Compress-Archive -Path "약품재고검색" -DestinationPath "약품재고검색_$version.zip" -Force
    
    Write-Host "배포 파일 생성 완료: 약품재고검색_$version.zip" -ForegroundColor Yellow
} else {
    Write-Host "빌드 실패!" -ForegroundColor Red
}
"@ | Out-File -FilePath build.ps1 -Encoding UTF8
```