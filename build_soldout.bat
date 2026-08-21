@echo off
setlocal enabledelayedexpansion
REM ------------------------------------------------------------------
REM Windows build script for apps/soldout (PyInstaller -> dist + zip).
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
REM 품절약 서치앱(apps/soldout) 배포 빌드 스크립트 — Windows 전용
REM 준비 단계(venv·의존성·Chromium·spec·build_config)는 없을 때만 수행하고,
REM 빌드 자체는 매번 깨끗이 다시 수행한다. 반복 실행해도 안전하다.
REM 사용법: PowerShell  .\build_soldout.bat   /  cmd  build_soldout.bat   /  탐색기 더블클릭

cd /d "%~dp0"
set "ROOT=%CD%"
set "APP=%ROOT%\apps\soldout"
set "VENV_PYTHON=%ROOT%\.venv\Scripts\python.exe"
set "REQ=%APP%\requirements.txt"
set "STAMP=%ROOT%\.venv\.deps_soldout.sha256"
REM spec 의 COLLECT name — 산출물 폴더/실행파일 이름
set "OUTNAME=약품재고검색"
set "FRESH="

if not exist "%APP%\web_server.py" (
    echo [오류] %APP% 를 찾을 수 없습니다. 리포지토리 루트에서 실행하세요.
    goto :fail
)

REM ============================================================
REM 1) 가상환경(.venv) — 없을 때만 생성
REM ============================================================
if exist "%VENV_PYTHON%" goto :venv_ready

echo [1/7] 가상환경(.venv)을 만드는 중...
set "FRESH=1"
where uv >nul 2>&1 && goto :venv_uv

set "PYCMD="
py -3 --version >nul 2>&1 && set "PYCMD=py -3"
if defined PYCMD goto :venv_stdlib
python --version >nul 2>&1 && set "PYCMD=python"
if defined PYCMD goto :venv_stdlib
echo [오류] uv 도 Python 도 찾을 수 없습니다.
echo        https://www.python.org/downloads/ 에서 Python 3.11+ 을 먼저 설치하세요.
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
REM    (pyinstaller 도 여기에 포함되어 있다)
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
echo [2/7] 의존성을 설치하는 중... (apps\soldout\requirements.txt)
where uv >nul 2>&1 && goto :deps_uv
"%VENV_PYTHON%" -m pip install -r "%REQ%" || goto :fail_deps
goto :deps_stamp

:deps_uv
uv pip install --python "%VENV_PYTHON%" -r "%REQ%" || goto :fail_deps

:deps_stamp
if defined REQ_HASH >"%STAMP%" echo !REQ_HASH!

:deps_ready

REM ============================================================
REM 3) Playwright Chromium — 없을 때만 설치 (exe 에 통째로 번들된다)
REM ============================================================
dir /b "%LOCALAPPDATA%\ms-playwright\chromium-*" >nul 2>&1
if not errorlevel 1 goto :playwright_ready
echo [3/7] Playwright Chromium 을 내려받는 중... (최초 1회, 약 150MB)
"%VENV_PYTHON%" -m playwright install chromium || goto :fail_playwright

:playwright_ready

REM ============================================================
REM 4) yak_soldout.spec — 없을 때만 example 에서 복사
REM ============================================================
if exist "%APP%\yak_soldout.spec" goto :spec_ready
echo [4/7] yak_soldout.spec 이 없어 example 에서 복사합니다.
copy /y "%APP%\yak_soldout.example.spec" "%APP%\yak_soldout.spec" >nul || goto :fail_spec

:spec_ready

REM ============================================================
REM 5) build_config.json — 약국별 설정. 새로 만들었으면 여기서 멈춘다
REM ============================================================
if exist "%APP%\build_config.json" goto :config_ready
echo [5/7] build_config.json 이 없어 example 에서 복사했습니다.
copy /y "%APP%\build_config.example.json" "%APP%\build_config.json" >nul || goto :fail_config
echo.
echo   ----------------------------------------------------------
echo    빌드를 멈춥니다. 약국별 설정을 먼저 확인하세요.
echo   ----------------------------------------------------------
echo   apps\soldout\build_config.json 을 열어
echo     - pharmacy_name       : 약국 이름
echo     - primary_distributor : 기준 도매상
echo     - distributors        : 사용할 도매상 1, 안 쓰면 0
echo   을 수정한 뒤 build_soldout.bat 을 다시 실행하세요.
echo   (기본값 그대로 두면 example 의 약국명으로 빌드됩니다)
goto :fail

:config_ready

REM 어느 약국으로 빌드하는지 먼저 보여준다 (잘못된 대상 빌드 방지).
REM 값을 for /f 로 캡처하지 않는다 — 중첩 따옴표 때문에 파싱이 깨진다. 파이썬이 직접 출력한다.
echo.
pushd "%APP%" || goto :fail
"%VENV_PYTHON%" -c "import json;c=json.load(open('build_config.json',encoding='utf-8'));print('  빌드 대상 약국 :',c['pharmacy_name']);print('  기준 도매상    :',c['primary_distributor']);print('  사용 도매상    :',', '.join(k for k,v in c['distributors'].items() if v))"
set "CFG_RC=%ERRORLEVEL%"
popd
if not "%CFG_RC%"=="0" (
    echo [오류] build_config.json 을 읽을 수 없습니다. JSON 형식을 확인하세요.
    goto :fail
)
echo.

REM ============================================================
REM 6) 빌드 — 매번 깨끗한 상태에서 다시 수행
REM    (spec 이 ..\..\scrapers 를 참조하므로 반드시 apps\soldout 에서 실행)
REM ============================================================
echo [6/7] 이전 빌드 정리 후 PyInstaller 실행... (Chromium 번들 때문에 수 분 걸립니다)
taskkill /F /IM "%OUTNAME%.exe" >nul 2>&1
if exist "%APP%\build" rd /s /q "%APP%\build"
if exist "%APP%\dist" rd /s /q "%APP%\dist"

pushd "%APP%" || goto :fail
"%VENV_PYTHON%" -m PyInstaller yak_soldout.spec
set "PYI_RC=%ERRORLEVEL%"
popd
if not "%PYI_RC%"=="0" goto :fail_build

if not exist "%APP%\dist\%OUTNAME%\%OUTNAME%.exe" (
    echo [오류] 산출물을 찾을 수 없습니다: apps\soldout\dist\%OUTNAME%\%OUTNAME%.exe
    echo        spec 의 EXE/COLLECT name 을 바꿨다면 이 스크립트의 OUTNAME 도 맞춰주세요.
    goto :fail
)

REM ============================================================
REM 7) 배포용 ZIP — 약국명으로 이름을 붙인다
REM ============================================================
echo [7/7] 배포용 ZIP 을 만드는 중...
pushd "%APP%" || goto :fail
"%VENV_PYTHON%" -c "import json,shutil,os;n=json.load(open('build_config.json',encoding='utf-8'))['pharmacy_name'];p=shutil.make_archive('dist/품절약똑똑이for'+n,'zip','dist','%OUTNAME%');print();print('  [완료] 빌드 성공');print('    실행 파일 :',os.path.abspath(os.path.join('dist','%OUTNAME%','%OUTNAME%.exe')));print('    배포 ZIP  :',os.path.abspath(p))"
set "ZIP_RC=%ERRORLEVEL%"
popd
if not "%ZIP_RC%"=="0" goto :fail_zip

echo.
exit /b 0

:fail_venv
echo [오류] 가상환경 생성에 실패했습니다.
goto :fail

:fail_deps
echo [오류] 의존성 설치에 실패했습니다. 네트워크 연결을 확인하고 다시 실행하세요.
goto :fail

:fail_playwright
echo [오류] Playwright Chromium 설치에 실패했습니다. 네트워크 연결을 확인하고 다시 실행하세요.
goto :fail

:fail_spec
echo [오류] yak_soldout.example.spec 복사에 실패했습니다.
goto :fail

:fail_config
echo [오류] build_config.example.json 복사에 실패했습니다.
goto :fail

:fail_build
echo.
echo [오류] PyInstaller 빌드가 코드 %PYI_RC% 로 실패했습니다.
echo        실행 중인 %OUTNAME%.exe 가 있으면 종료한 뒤 다시 시도하세요.
goto :fail

:fail_zip
echo [오류] ZIP 생성에 실패했습니다. (빌드 산출물은 apps\soldout\dist\ 에 남아 있습니다)
goto :fail

:fail
echo.
pause
exit /b 1
