# -*- mode: python ; coding: utf-8 -*-
import os
import sys
from pathlib import Path

# --- Playwright 브라우저 경로를 자동으로 찾는 코드 추가 ---
def get_playwright_path():
    """
    현재 운영 체제에 맞는 Playwright 브라우저 설치 경로를 반환합니다.
    """
    if sys.platform == "win32":
        return Path(os.getenv("LOCALAPPDATA")) / "ms-playwright"
    # macOS나 Linux를 위한 경로도 필요하다면 여기에 추가할 수 있습니다.
    # elif sys.platform == "darwin":
    #     return Path.home() / "Library/Caches/ms-playwright"
    return None

playwright_browsers_path = get_playwright_path()
if not playwright_browsers_path or not playwright_browsers_path.exists():
    raise SystemExit("Playwright 브라우저가 설치되어 있지 않습니다. 'playwright install' 명령어를 먼저 실행해주세요.")
# ---------------------------------------------------------


block_cipher = None

# Analysis 객체 - 필요한 모든 파일과 데이터를 정의
a = Analysis(
    ['run_app.py'],  # 메인 진입점
    pathex=['../..'],  # 리포 루트 — 공유 패키지 scrapers/ 정적 분석용
    binaries=[],
    # 모노레포 구조: 이 spec 은 apps/soldout/ 에서 실행한다 (pyinstaller yak_soldout.spec).
    # scrapers 는 리포 루트의 공유 패키지라 ../../ 로 참조한다.
    datas=[
        ('templates', 'templates'),
        ('static', 'static'),
        ('build_config.json', '.'),
        # 시드 JSON 은 SQLite 이전 완료 후 더 이상 없음 — 빌드 머신에 있으면 주석 해제
        # ('geoweb-soldout-list.json', '.'),
        # ('exclusion-list.json', '.'),
        ('web_server.py', '.'),
        ('models', 'models'),
        ('utils', 'utils'),
        ('../../scrapers', 'scrapers'),
        # --- 수정된 부분: Playwright 브라우저 폴더 전체를 포함 ---
        (str(playwright_browsers_path), 'ms-playwright'),
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
    console=False,  # 콘솔 창 표시 (서버 로그 확인용), 실제 배포시에는 False로 변경
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