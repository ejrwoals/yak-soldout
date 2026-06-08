#!/usr/bin/env python3
"""
약품 재고 자동 검색 프로그램 - FastAPI 웹 서버

HTML/CSS/JavaScript 기반 프론트엔드를 제공하는 웹 서버입니다.
"""

import asyncio
import json
import concurrent.futures
import threading
import queue
import platform
import os
import webbrowser
import sys
import signal
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

# Windows asyncio 호환성 문제 해결 (전역 설정)
if platform.system() == "Windows":
    try:
        # Windows에서 Playwright subprocess 지원을 위해 ProactorEventLoop 사용
        if hasattr(asyncio, 'WindowsProactorEventLoopPolicy'):
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
            print("✅ Windows ProactorEventLoop 정책 적용됨")
        
        # subprocess 및 인코딩 관련 환경변수 설정
        os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
        os.environ.setdefault('PYTHONUTF8', '1')
        os.environ.setdefault('PLAYWRIGHT_DOWNLOAD_HOST', 'https://playwright.azureedge.net')
        
        # asyncio subprocess 문제 해결을 위한 추가 설정
        os.environ.setdefault('ASYNCIO_EVENT_LOOP', 'ProactorEventLoop')
        
        # 현재 이벤트 루프가 있으면 닫고 새로 생성
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                pass  # 실행 중인 루프는 건드리지 않음
            else:
                loop.close()
                # 새 루프 설정
                if hasattr(asyncio, 'new_event_loop'):
                    new_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(new_loop)
        except RuntimeError:
            # 루프가 없으면 새로 만들기
            if hasattr(asyncio, 'new_event_loop'):
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
        
    except Exception as e:
        print(f"⚠️ Windows 호환성 설정 중 오류 (무시 가능): {e}")

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi import Request
import uvicorn

# PyInstaller 환경에서 리소스 경로를 찾기 위한 함수
def resource_path(relative_path):
    """개발 및 PyInstaller 환경 모두에서 리소스의 절대 경로를 가져옵니다."""
    try:
        # PyInstaller는 임시 폴더를 만들고 _MEIPASS에 경로를 저장합니다
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    
    return os.path.join(base_path, relative_path)

# 프로젝트 모듈 import
from models.config import ConfigManager
from models.drug_data import SearchResult
from utils.file_manager import FileManager
from utils.data_processor import DataProcessor
from utils.notifications import AlertManager
from utils.app_state import AppState
from scrapers.registry import DISTRIBUTOR_REGISTRY
from models.build_config import get_visible_registry, get_pharmacy_name, get_primary_distributor
from utils.websocket_manager import ConnectionManager, broadcast_log
from utils.search_engine import execute_search, PreviewSearchSession
from utils.open_site_session import OpenSiteSession
from scrapers.browser_manager import BrowserManager
from scrapers.geoweb_scraper import GeowebScraper
from scrapers.baekje_scraper import BaekjeScraper

app = FastAPI(title="약품 재고 자동 검색", version="2.0.0")

# PyInstaller 환경인지 확인하고 경로 설정
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

# 전역 앱 상태 인스턴스
app_state = AppState()

# 미리보기 검색 세션 (브라우저 재사용)
preview_session = PreviewSearchSession()

# 바로가기 세션 (재고 카드 → headed 브라우저로 자동 로그인/검색)
open_site_session = OpenSiteSession()

# WebSocket 연결 관리자
manager = ConnectionManager()


@app.middleware("http")
async def no_cache_static(request: Request, call_next):
    """정적 파일(JS/CSS)과 페이지를 브라우저가 매번 재검증하도록 한다.

    StaticFiles 는 ETag/Last-Modified 만 보내고 Cache-Control 을 생략하기 때문에
    브라우저가 휴리스틱 캐싱으로 옛 파일을 그대로 사용하는 문제가 있다. 로컬 단일
    사용자 앱이므로 코드 수정이 항상 즉시 반영되도록 no-cache 로 강제한다.
    (no-cache = 사용 전 재검증; 변경 없으면 304 로 저렴하게 끝난다)
    """
    response = await call_next(request)
    path = request.url.path
    if path.startswith("/static") or path in ("/", "/checker"):
        response.headers["Cache-Control"] = "no-cache"
    return response


@app.get("/", response_class=HTMLResponse)
async def read_home(request: Request):
    """홈 화면 (앱 런처)"""
    return templates.TemplateResponse(request, "home.html")

@app.get("/checker", response_class=HTMLResponse)
async def read_checker(request: Request):
    """품절 약 서치앱 대시보드"""
    return templates.TemplateResponse(request, "index.html")

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket 엔드포인트 - 실시간 로그 스트리밍"""
    await manager.connect(websocket)
    try:
        while True:
            # 클라이언트로부터 메시지 대기 (연결 유지용)
            await websocket.receive_text()
    except WebSocketDisconnect:
        should_shutdown = manager.disconnect(websocket)
        if should_shutdown:
            # 페이지 새로고침/잠시 끊김으로 인한 오인 종료를 막기 위해
            # 짧은 grace period 후 다시 연결 수를 확인한다.
            def shutdown_server():
                import time
                time.sleep(3)
                if len(manager.active_connections) > 0:
                    return  # 그 사이 재연결됨 → 셧다운 취소

                print("\n🔴 브라우저가 닫혔습니다. 서버를 종료합니다...")
                if platform.system() == "Windows":
                    pid = os.getpid()
                    os.system(f"taskkill /F /PID {pid} /T >nul 2>&1")
                else:
                    os.kill(os.getpid(), signal.SIGTERM)

            shutdown_thread = threading.Thread(target=shutdown_server)
            shutdown_thread.daemon = True
            shutdown_thread.start()

@app.get("/api/build-info")
async def get_build_info():
    """빌드 정보 조회 (약국명 등)"""
    primary_info = DISTRIBUTOR_REGISTRY[get_primary_distributor()]
    return {
        "pharmacy_name": get_pharmacy_name(),
        "primary_distributor_name": primary_info['name'],
        "primary_distributor_url": primary_info.get('site_url', ''),
    }

@app.get("/api/status")
async def get_status():
    """현재 상태 조회 (실시간 메모리 기반)"""
    try:
        # 기본 정보
        drug_list = app_state.file_manager.read_drug_list()
        drug_list_json = app_state.file_manager.read_drug_list_json()
        
        # JSON 형식의 결과 표시 제외 목록 읽기
        exclusion_json_data = app_state.file_manager.read_alert_exclusions_json()
        exclusion_list_names = [item.get('drugName', '') for item in exclusion_json_data]  # 약품명만 추출 (기존 호환성 유지)
        
        
        # 실시간 검색 상태 (메모리에서)
        current_search = app_state.current_search.copy()
        
        # 설정 파일에서 값 읽기
        config_data = app_state.config_manager.get_raw_config()
        alert_exclusion_days = config_data.get('monitoring', {}).get('alert_exclusion_days', 7)

        # 도매상별 설정/활성화 상태 (레지스트리 루프)
        distributors_config = config_data.get('distributors', {})
        distributor_status = []
        for dist_id, dist_info in get_visible_registry().items():
            enabled = distributors_config.get(dist_id, {}).get('enabled', dist_info['default_enabled'])
            configured = bool(app_state.config and app_state.config.has_credentials(dist_id) and enabled)
            distributor_status.append({
                "id": dist_id,
                "name": dist_info['name'],
                "configured": configured,
                "enabled": enabled,
                "color": distributors_config.get(dist_id, {}).get('color', dist_info['default_color']),
                "supports_open_site": dist_info.get('supports_open_site', False),
            })

        return {
            "is_searching": app_state.is_searching,
            "config": {
                "distributors": distributor_status,
                "alert_exclusion_days": alert_exclusion_days
            },
            "files": {
                "drug_count": len(drug_list),
                "drug_list": drug_list_json,  # 전체 목록과 긴급 알림 정보 포함
                "exclusion_count": len(exclusion_list_names),
                "exclusion_list": exclusion_json_data[:5]  # 도매상 정보 포함한 전체 객체를 툴팁에 전달 (최대 5개)
            },
            "current_search": current_search
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/logs")
async def get_logs():
    """진행상황 로그 히스토리 조회 (페이지 재진입 시 복원용)"""
    return {"logs": manager.log_history}

@app.post("/api/logs/clear")
async def clear_logs():
    """진행상황 로그 히스토리 비우기 (사용자가 로그를 지울 때)"""
    manager.log_history.clear()
    return {"success": True}

@app.post("/api/search/start")
async def start_search():
    """검색 시작"""
    if app_state.is_searching:
        raise HTTPException(status_code=400, detail="이미 검색 중입니다")
    
    # 활성화된 도매상이 있는지 확인
    config_data = app_state.config_manager.get_raw_config()
    distributors_config = config_data.get('distributors', {})

    primary_id = get_primary_distributor()
    primary_name = DISTRIBUTOR_REGISTRY[primary_id]['name']
    if not app_state.config or not app_state.config.has_credentials(primary_id):
        raise HTTPException(status_code=400, detail=f"{primary_name} 계정 정보가 설정되지 않았습니다")

    any_active = any(
        distributors_config.get(dist_id, {}).get('enabled', info['default_enabled'])
        for dist_id, info in get_visible_registry().items()
    )
    if not any_active:
        raise HTTPException(status_code=400, detail="활성화된 도매상이 없습니다. 도매상 설정에서 최소 하나를 활성화해주세요")
    
    # 검색 데이터 초기화 (새 사이클 시작)
    app_state.reset_search_data()
    app_state.current_search["status"] = "searching"
    app_state.current_search["timestamp"] = datetime.now().isoformat()
    
    # 검색 시작
    app_state.is_searching = True
    app_state.search_task = asyncio.create_task(execute_search(app_state, manager))
    
    return {"message": "반복 검색을 시작했습니다"}

@app.post("/api/search/stop")
async def stop_search():
    """검색 중단"""
    if not app_state.is_searching:
        raise HTTPException(status_code=400, detail="검색 중이 아닙니다")
    
    app_state.is_searching = False
    
    if app_state.search_task and not app_state.search_task.done():
        app_state.search_task.cancel()
    
    await manager.broadcast_message(json.dumps({
        "type": "search_stopped",
        "message": "🛑 검색을 중단했습니다",
        "timestamp": datetime.now().isoformat()
    }))
    
    return {"message": "검색을 중단했습니다"}

@app.get("/api/distributor-settings")
async def get_distributor_settings():
    """도매상 설정 정보 조회"""
    try:
        config_data = app_state.config_manager.get_raw_config()
        distributors_config = config_data.get('distributors', {})

        # 레지스트리 기반 도매상 리스트 생성
        distributors = []
        for dist_id, dist_info in get_visible_registry().items():
            dist_conf = distributors_config.get(dist_id, {})
            entry = {
                "id": dist_id,
                "name": dist_info['name'],
                "enabled": dist_conf.get('enabled', dist_info['default_enabled']),
                "username": dist_conf.get('username', ''),
                "password": dist_conf.get('password', ''),
                "color": dist_conf.get('color', dist_info['default_color']),
            }
            # extra_params (region 등) 자동 추가
            for param_key, param_default in dist_info.get('extra_params', {}).items():
                entry[param_key] = dist_conf.get(param_key, param_default)
            # region_options가 있으면 함께 전달 (프론트엔드에서 드롭다운 생성)
            if 'region_options' in dist_info:
                entry['region_options'] = dist_info['region_options']
            distributors.append(entry)

        return {"distributors": distributors}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"설정 읽기 실패: {str(e)}")

@app.put("/api/distributor-settings")
async def update_distributor_settings(settings: dict):
    """도매상 설정 정보 업데이트"""
    try:
        # 유효성 검사
        distributors = settings.get('distributors', [])
        for dist in distributors:
            if dist.get('enabled', False):
                if not dist.get('username') or not dist.get('password'):
                    raise HTTPException(
                        status_code=400, 
                        detail=f"{dist.get('name', '알수없는 도매상')}의 아이디와 비밀번호를 입력해주세요"
                    )
        
        # 기존 설정 읽기
        config_data = app_state.config_manager.get_raw_config()
        distributors_config = config_data.setdefault('distributors', {})

        # 도매상 설정 업데이트
        name_to_id = {info['name']: dist_id for dist_id, info in get_visible_registry().items()}

        for dist in distributors:
            dist_id = name_to_id.get(dist['name'])
            if not dist_id:
                continue

            dist_entry = distributors_config.setdefault(dist_id, {})
            enabled = dist.get('enabled', False)
            dist_entry['enabled'] = enabled

            # 활성화된 경우에만 아이디/비밀번호 업데이트 (비활성화 시 기존 값 유지)
            if enabled:
                dist_entry['username'] = dist.get('username', '')
                dist_entry['password'] = dist.get('password', '')

            # extra_params (region 등) 업데이트
            for param_key in DISTRIBUTOR_REGISTRY[dist_id].get('extra_params', {}):
                if param_key in dist:
                    dist_entry[param_key] = dist[param_key]

            # color 업데이트 (활성화 여부와 무관하게 저장)
            if 'color' in dist:
                dist_entry['color'] = dist['color']

        # config.json 저장
        app_state.config_manager.save_raw_config(config_data)
        
        # 앱 설정 다시 로드
        app_state.config = app_state.config_manager.load_config()
        
        return {"message": "설정이 저장되었습니다"}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"설정 저장 실패: {str(e)}")

@app.get("/api/drug-list")
async def get_drug_list():
    """약품 목록 조회"""
    try:
        drug_list = app_state.file_manager.read_drug_list_json()
        return {"drugs": drug_list}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"약품 목록 읽기 실패: {str(e)}")

@app.put("/api/drug-list")
async def update_drug_list(data: dict):
    """약품 목록 업데이트"""
    try:
        drugs = data.get('drugs', [])
        
        # 유효성 검사
        if not isinstance(drugs, list):
            raise HTTPException(status_code=400, detail="약품 목록은 배열이어야 합니다")
        
        # 데이터 정리 및 중복 제거
        clean_drugs = []
        seen = set()
        for drug in drugs:
            if isinstance(drug, dict):
                drug_name = drug.get('drugName', '').strip()
                if drug_name and drug_name not in seen:
                    clean_drugs.append({
                        'drugName': drug_name,
                        'isUrgent': drug.get('isUrgent', False),
                        'dateAdded': drug.get('dateAdded', datetime.now().isoformat()[:19])
                    })
                    seen.add(drug_name)
            elif isinstance(drug, str):
                drug_name = drug.strip()
                if drug_name and drug_name not in seen:
                    clean_drugs.append({
                        'drugName': drug_name,
                        'isUrgent': False,
                        'dateAdded': datetime.now().isoformat()[:19]
                    })
                    seen.add(drug_name)
        
        # 파일에 저장
        app_state.file_manager.write_drug_list_json(clean_drugs)
        
        return {"message": f"약품 목록이 저장되었습니다 (총 {len(clean_drugs)}개)"}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"약품 목록 저장 실패: {str(e)}")

@app.post("/api/preview-search")
async def preview_search(data: dict):
    """약품 미리보기 검색 — primary 도매상에서 실시간 검색 (세션 재사용)"""
    query = data.get('query', '').strip()
    if not query:
        raise HTTPException(status_code=400, detail="검색어를 입력해주세요")

    # 이미 미리보기 검색 중이면 거부 (같은 세션 동시 사용 방지)
    if app_state.is_preview_searching:
        raise HTTPException(status_code=409, detail="이전 미리보기 검색이 진행 중입니다")

    # 자격 증명 확인
    primary_id = get_primary_distributor()
    try:
        creds = app_state.config.get_credentials(primary_id)
        if not creds.username or not creds.password:
            raise Exception()
    except Exception:
        raise HTTPException(status_code=400,
            detail="도매상 계정 정보가 설정되지 않았습니다")

    app_state.is_preview_searching = True
    try:
        result = await preview_session.search(app_state, query)
        return result
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="검색 시간이 초과되었습니다")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"검색 실패: {str(e)}")
    finally:
        app_state.is_preview_searching = False

@app.post("/api/preview-search/close")
async def close_preview_search():
    """미리보기 검색 세션 종료 — 모달 닫힐 때 호출"""
    try:
        await preview_session.close()
        return {"message": "미리보기 세션이 종료되었습니다"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"세션 종료 실패: {str(e)}")

@app.post("/api/open-distributor-site")
async def open_distributor_site(data: dict):
    """재고 카드 바로가기 — headed 브라우저로 자동 로그인+검색"""
    distributor_id = (data.get('distributor_id') or '').strip()
    drug_name = (data.get('drug_name') or '').strip()
    insurance_code = (data.get('insurance_code') or '').strip()

    if not distributor_id:
        raise HTTPException(status_code=400, detail="distributor_id가 필요합니다")
    if distributor_id not in DISTRIBUTOR_REGISTRY:
        raise HTTPException(status_code=400, detail=f"알 수 없는 도매상: {distributor_id}")

    dist_info = DISTRIBUTOR_REGISTRY[distributor_id]
    if not dist_info.get('supports_open_site', False):
        raise HTTPException(status_code=400, detail=f"{dist_info['name']}은(는) 바로가기를 지원하지 않습니다")

    if not drug_name and not insurance_code:
        raise HTTPException(status_code=400, detail="검색어(보험코드 또는 약품명)가 필요합니다")

    if not app_state.config or not app_state.config.has_credentials(distributor_id):
        raise HTTPException(status_code=400, detail=f"{dist_info['name']} 계정 정보가 설정되지 않았습니다")

    try:
        result = await open_site_session.open(
            app_state, distributor_id, drug_name, insurance_code
        )
        return result
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="브라우저 세션 시작이 시간 초과되었습니다")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"바로가기 실패: {str(e)}")

@app.post("/api/open-distributor-site/close")
async def close_open_distributor_site():
    """바로가기 세션 수동 종료"""
    try:
        await open_site_session.close()
        return {"message": "바로가기 세션이 종료되었습니다"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"세션 종료 실패: {str(e)}")

@app.on_event("shutdown")
async def _cleanup_sessions_on_shutdown():
    """서버 종료 시 열려있는 세션 정리 (Unix SIGTERM 경로)"""
    try:
        await open_site_session.close()
    except Exception as e:
        print(f"shutdown open_site_session 정리 오류(무시): {e}")
    try:
        await preview_session.close()
    except Exception as e:
        print(f"shutdown preview_session 정리 오류(무시): {e}")

@app.get("/api/exclusion-list")
async def get_exclusion_list():
    """결과 표시 제외 목록 조회 (JSON 형식)"""
    try:
        exclusion_list = app_state.file_manager.read_alert_exclusions_json()
        return {"exclusions": exclusion_list}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"결과 표시 제외 목록 읽기 실패: {str(e)}")

@app.put("/api/exclusion-list")
async def update_exclusion_list(data: dict):
    """결과 표시 제외 목록 업데이트 (JSON 형식)"""
    try:
        exclusions = data.get('exclusions', [])
        
        # 유효성 검사
        if not isinstance(exclusions, list):
            raise HTTPException(status_code=400, detail="결과 표시 제외 목록은 배열이어야 합니다")
        
        # 각 항목의 필수 필드 검증
        for item in exclusions:
            if not isinstance(item, dict):
                raise HTTPException(status_code=400, detail="각 항목은 객체여야 합니다")
            
            required_fields = ['date', 'distributor', 'drugName', 'isPinned']
            for field in required_fields:
                if field not in item:
                    raise HTTPException(status_code=400, detail=f"필수 필드 '{field}'가 없습니다")
        
        # 파일에 저장 (자동 정렬 포함)
        app_state.file_manager.write_alert_exclusions_json(exclusions)
        
        return {"message": f"결과 표시 제외 목록이 저장되었습니다 (총 {len(exclusions)}개)"}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"결과 표시 제외 목록 저장 실패: {str(e)}")

@app.put("/api/drug-urgent-toggle")
async def toggle_drug_urgent(data: dict):
    """특정 약품의 긴급 알림 상태 해제"""
    try:
        drug_name = data.get('drugName')
        if not drug_name:
            raise HTTPException(status_code=400, detail="약품명이 필요합니다")
        
        # 현재 약품 목록 로드
        drug_list = app_state.file_manager.read_drug_list_json()
        
        # 해당 약품 찾기 및 긴급 상태 해제
        found = False
        for drug in drug_list:
            if drug.get('drugName') == drug_name:
                drug['isUrgent'] = False
                drug['dateAdded'] = datetime.now().isoformat()[:19]  # 변경 시간 업데이트
                found = True
                break
        
        if not found:
            raise HTTPException(status_code=404, detail="해당 약품을 찾을 수 없습니다")
        
        # 파일에 저장
        app_state.file_manager.write_drug_list_json(drug_list)
        
        return {"message": f"'{drug_name}'의 긴급 알림이 해제되었습니다"}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"긴급 알림 해제 실패: {str(e)}")

@app.get("/api/system-settings")
async def get_system_settings():
    """시스템 설정 조회"""
    try:
        config_data = app_state.config_manager.get_raw_config()
        monitoring = config_data.get('monitoring', {})
        distributors_config = config_data.get('distributors', {})
        return {
            "repeat_interval_minutes": monitoring.get('repeat_interval_minutes', 30),
            "alert_exclusion_days": monitoring.get('alert_exclusion_days', 7),
            "distributor_enables": {
                dist_id: distributors_config.get(dist_id, {}).get('enabled', info['default_enabled'])
                for dist_id, info in get_visible_registry().items()
            },
            "distributor_names": {
                dist_id: info['name']
                for dist_id, info in get_visible_registry().items()
            },
            "distributor_urls": {
                dist_id: info.get('site_url', '')
                for dist_id, info in get_visible_registry().items()
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"시스템 설정 읽기 실패: {str(e)}")

@app.put("/api/system-settings")
async def update_system_settings(data: dict):
    """시스템 설정 업데이트"""
    try:
        repeat_interval = data.get('repeat_interval_minutes')
        alert_exclusion_days = data.get('alert_exclusion_days')
        distributor_enables = data.get('distributor_enables', {})

        # 유효성 검사
        if not repeat_interval or not isinstance(repeat_interval, int) or repeat_interval < 1 or repeat_interval > 1440:
            raise HTTPException(status_code=400, detail="반복 간격은 1분에서 1440분 사이의 정수여야 합니다")

        if not alert_exclusion_days or not isinstance(alert_exclusion_days, int) or alert_exclusion_days < 1 or alert_exclusion_days > 365:
            raise HTTPException(status_code=400, detail="알림 제외 기간은 1일에서 365일 사이의 정수여야 합니다")

        # 현재 설정 읽기
        config_data = app_state.config_manager.get_raw_config()

        # 모니터링 설정값 적용
        monitoring = config_data.setdefault('monitoring', {})
        monitoring['repeat_interval_minutes'] = repeat_interval
        monitoring['alert_exclusion_days'] = alert_exclusion_days

        # 도매상 활성화 상태 적용 (레지스트리 루프)
        if distributor_enables:
            distributors_config = config_data.setdefault('distributors', {})
            for dist_id, dist_info in get_visible_registry().items():
                distributors_config.setdefault(dist_id, {})['enabled'] = \
                    distributor_enables.get(dist_id, dist_info['default_enabled'])

        # config.json 저장
        app_state.config_manager.save_raw_config(config_data)

        # 앱 설정 다시 로드 (자격증명 미설정 시 실패해도 허용)
        try:
            app_state.config = app_state.config_manager.load_config()
        except Exception:
            pass

        return {"message": "시스템 설정이 저장되었습니다"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"시스템 설정 저장 실패: {str(e)}")

@app.post("/api/exclusion-add")
async def add_to_exclusion(data: dict):
    """특정 약품을 결과 표시 제외 목록에 추가"""
    try:
        drug_name = data.get('drugName')
        distributor = data.get('distributor', '')
        
        if not drug_name:
            raise HTTPException(status_code=400, detail="약품명이 필요합니다")
        
        # 현재 제외 목록 로드
        exclusion_list = app_state.file_manager.read_alert_exclusions_json()
        
        # 이미 목록에 있는지 확인 (약품명과 도매상 조합으로)
        for item in exclusion_list:
            if item.get('drugName') == drug_name and item.get('distributor') == distributor:
                return {"message": f"'{drug_name}'은(는) 이미 결과 표시 제외 목록에 있습니다"}
        
        # 새 항목 추가
        new_entry = {
            "date": datetime.now().isoformat()[:19],
            "distributor": distributor,
            "drugName": drug_name,
            "isPinned": False
        }
        
        exclusion_list.append(new_entry)
        
        # 파일에 저장 (자동 정렬됨)
        app_state.file_manager.write_alert_exclusions_json(exclusion_list)
        
        return {"message": f"'{drug_name}'을(를) 결과 표시 제외 목록에 추가했습니다"}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"결과 표시 제외 추가 실패: {str(e)}")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))

    print("🚀 약품 재고 자동 검색 웹 서버 시작")
    print("📱 브라우저를 자동으로 열고 있습니다...")

    # 서버 시작 후 브라우저 자동 열기
    def open_browser():
        import time
        time.sleep(1)  # 서버가 완전히 시작될 때까지 잠시 대기
        webbrowser.open(f"http://localhost:{port}")

    # 별도 스레드에서 브라우저 열기
    browser_thread = threading.Thread(target=open_browser)
    browser_thread.daemon = True
    browser_thread.start()

    uvicorn.run(
        "web_server:app",
        host="0.0.0.0",
        port=port,
        reload=False,  # reload 모드는 개발 중에 코드를 자주 수정할 경우에 사용하는 모드
        log_level="info"
    )