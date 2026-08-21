# -*- mode: python ; coding: utf-8 -*-
"""약국 주문 Agent 로컬 앱(apps/local_app) 배포 빌드 spec.

빌드는 반드시 apps/local_app/ 에서 실행한다 (datas 가 ../../scrapers 를 참조).
루트의 build_local_app.bat 이 이 파일을 사용한다.
"""
import os
import sys
from pathlib import Path


def get_playwright_path():
    """OS 에 맞는 Playwright 브라우저 설치 경로. 크롤링용으로 통째로 번들한다."""
    if sys.platform == "win32":
        return Path(os.getenv("LOCALAPPDATA")) / "ms-playwright"
    return None


playwright_browsers_path = get_playwright_path()
if not playwright_browsers_path or not playwright_browsers_path.exists():
    raise SystemExit(
        "Playwright 브라우저가 설치되어 있지 않습니다. "
        "'python -m playwright install chromium' 를 먼저 실행해주세요."
    )

block_cipher = None

a = Analysis(
    ['main.py'],          # PyWebView 창 + FastAPI 서버 진입점
    pathex=['../..'],     # 리포 루트 — 공유 패키지 scrapers/ 정적 분석용
    binaries=[],
    datas=[
        ('static', 'static'),
        # scrapers 는 리포 루트의 공유 패키지 (크롤링: 규격 수집·장바구니 담기)
        ('../../scrapers', 'scrapers'),
        # browser_manager 가 _MEIPASS/ms-playwright 에서 브라우저를 찾는다
        (str(playwright_browsers_path), 'ms-playwright'),
    ],
    hiddenimports=[
        # 같은 폴더 모듈 — main.py 는 app 만 임포트하므로 나머지는 명시한다
        'app',
        'drug_usage',
        'master_db',
        'master_import',
        'orders_repo',
        'repo_path',
        'runtime_paths',
        'settings',
        'supabase_client',
        'unit_collector',
        # uvicorn 은 프로토콜 구현을 동적 임포트한다
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
        # PyWebView Windows 백엔드 (Edge WebView2)
        'webview.platforms.edgechromium',
        'webview.platforms.winforms',
        'playwright',
        'playwright.sync_api',
        'playwright.async_api',
        'supabase',
        'httpx',
        'pandas',
        'rapidfuzz',
        'openpyxl',
        'xlrd',
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

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='자동주문',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,        # PyWebView 창이 UI — 콘솔 로그가 필요하면 True 로
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='자동주문',
)
