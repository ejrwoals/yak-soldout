@echo off
setlocal enabledelayedexpansion
REM ------------------------------------------------------------------
REM Windows launcher for apps/local_app (Korean messages below :main).
REM
REM Why the self re-launch: cmd.exe parses a .bat using the CONSOLE code
REM page. This file is UTF-8, but a Korean Windows console starts at 949,
REM and running "chcp 65001" in the middle of the file desyncs the parser
REM (it keeps reading by byte offset) -- Korean lines then get split and
REM their fragments are executed as commands. So: set the code page while
REM only ASCII lines have been parsed, then hand the file to a child cmd
REM that parses all of it under one correct code page.
REM Everything above :main must stay ASCII-only.
REM ------------------------------------------------------------------
if "%~1"=="__child__" goto :main

set "_OLDCP="
for /f "tokens=2 delims=:" %%C in ('chcp 2^>nul') do set "_OLDCP=%%C"
chcp 65001 >nul
cmd /d /c ""%~f0" __child__"
set "_RC=%ERRORLEVEL%"
if defined _OLDCP chcp !_OLDCP! >nul 2>&1
exit /b !_RC!

:main
REM 약국 주문 Agent — 로컬 관리자 앱 실행 스크립트 (apps/local_app/) — Windows용
REM 가상환경/의존성/Playwright 브라우저를 필요할 때만 자동 설치한 뒤,
REM FastAPI 서버(포트 8770)를 띄우고 PyWebView 데스크톱 창을 연다.
REM 사용법: 탐색기에서 더블클릭, 또는 터미널에서
REM          PowerShell:  .\dev_local_app.bat   (PowerShell은 현재 폴더 명령에 .\ 가 필요)
REM          cmd.exe   :  dev_local_app.bat

cd /d "%~dp0"
set "ROOT=%CD%"
set "VENV_PYTHON=%ROOT%\.venv\Scripts\python.exe"
set "REQ=%ROOT%\apps\local_app\requirements.txt"
set "STAMP=%ROOT%\.venv\.deps.sha256"
REM apps/local_app/main.py 의 고정 포트 (loopback OAuth 콜백 주소와 맞물려 있음)
set "PORT=8770"
set "FRESH="

if not exist "%REQ%" (
    echo [오류] %REQ% 를 찾을 수 없습니다. 리포지토리 루트에서 실행하세요.
    goto :fail
)

REM ============================================================
REM 1) 가상환경(.venv) — 없을 때만 생성
REM ============================================================
if exist "%VENV_PYTHON%" goto :venv_ready

echo [1/4] 가상환경(.venv)을 만드는 중...
set "FRESH=1"
where uv >nul 2>&1 && goto :venv_uv

REM uv 가 없으면 표준 venv 모듈로 대체
set "PYCMD="
py -3 --version >nul 2>&1 && set "PYCMD=py -3"
if defined PYCMD goto :venv_stdlib
python --version >nul 2>&1 && set "PYCMD=python"
if defined PYCMD goto :venv_stdlib
echo [오류] uv 도 Python 도 찾을 수 없습니다.
echo        https://www.python.org/downloads/ 에서 Python 3.10+ 을 먼저 설치하세요.
goto :fail

:venv_stdlib
%PYCMD% -m venv "%ROOT%\.venv" || goto :fail_venv
goto :venv_verify

:venv_uv
uv venv "%ROOT%\.venv" || goto :fail_venv

:venv_verify
if not exist "%VENV_PYTHON%" goto :fail_venv

:venv_ready

REM ============================================================
REM 2) 의존성 — requirements.txt 가 바뀌었거나 처음일 때만 설치
REM ============================================================
set "REQ_HASH="
for /f "skip=1 tokens=*" %%H in ('certutil -hashfile "%REQ%" SHA256 2^>nul') do if not defined REQ_HASH set "REQ_HASH=%%H"
set "REQ_HASH=!REQ_HASH: =!"
set "OLD_HASH="
if exist "%STAMP%" set /p OLD_HASH=<"%STAMP%"

if defined FRESH goto :deps_install
if not defined REQ_HASH goto :deps_install
if /i "!REQ_HASH!"=="!OLD_HASH!" goto :deps_ready

:deps_install
echo [2/4] 의존성을 설치하는 중... (requirements.txt 기준, 처음이면 몇 분 걸립니다)
where uv >nul 2>&1 && goto :deps_uv
"%VENV_PYTHON%" -m pip install -r "%REQ%" || goto :fail_deps
goto :deps_stamp

:deps_uv
uv pip install --python "%VENV_PYTHON%" -r "%REQ%" || goto :fail_deps

:deps_stamp
if defined REQ_HASH >"%STAMP%" echo !REQ_HASH!

:deps_ready

REM ============================================================
REM 3) Playwright Chromium — 없을 때만 설치 (크롤링에 필요)
REM ============================================================
dir /b "%LOCALAPPDATA%\ms-playwright\chromium-*" >nul 2>&1
if not errorlevel 1 goto :playwright_ready
echo [3/4] Playwright Chromium 을 내려받는 중... (최초 1회, 약 150MB)
"%VENV_PYTHON%" -m playwright install chromium || goto :fail_playwright

:playwright_ready

REM ============================================================
REM 4) 포트를 점유 중인 좀비 프로세스 정리
REM ============================================================
for /f "tokens=5" %%P in ('netstat -ano -p TCP ^| findstr /R /C:":%PORT% " ^| findstr "LISTENING"') do (
    if not "%%P"=="0" (
        echo [주의] 포트 %PORT% 점유 프로세스 정리: %%P
        taskkill /F /PID %%P >nul 2>&1
        set "KILLED=1"
    )
)
if defined KILLED timeout /t 1 /nobreak >nul

REM ============================================================
REM 5) 로컬 앱 실행 (PyWebView 창 + 로컬 서버)
REM ============================================================
if not exist "%ROOT%\apps\local_app\.env" (
    echo [안내] apps\local_app\.env 가 없습니다. Supabase 로그인/조회가 동작하지 않습니다.
    echo        apps\local_app\.env.example 를 .env 로 복사한 뒤 키를 채워주세요.
    echo.
)
echo [4/4] 앱을 실행합니다... (창이 뜰 때까지 잠시 기다려 주세요)
"%VENV_PYTHON%" "%ROOT%\apps\local_app\main.py"
set "EXITCODE=%ERRORLEVEL%"
if not "%EXITCODE%"=="0" (
    echo.
    echo [오류] 앱이 코드 %EXITCODE% 로 종료되었습니다.
    pause
)
exit /b %EXITCODE%

:fail_venv
echo [오류] 가상환경 생성에 실패했습니다.
goto :fail

:fail_deps
echo [오류] 의존성 설치에 실패했습니다. 네트워크 연결을 확인하고 다시 실행하세요.
goto :fail

:fail_playwright
echo [오류] Playwright Chromium 설치에 실패했습니다. 네트워크 연결을 확인하고 다시 실행하세요.
goto :fail

:fail
echo.
pause
exit /b 1
