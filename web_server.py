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
from models.config import ConfigManager, AppConfig
from models.drug_data import SearchResult
from utils.file_manager import FileManager
from utils.data_processor import DataProcessor
from utils.notifications import AlertManager
from utils.app_state import AppState
from utils.websocket_manager import ConnectionManager, broadcast_log
from utils.search_engine import execute_search
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

# WebSocket 연결 관리자
manager = ConnectionManager()

@app.get("/", response_class=HTMLResponse)
async def read_index(request: Request):
    """메인 페이지"""
    return templates.TemplateResponse("index.html", {"request": request})

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
            print("\n🔴 브라우저가 닫혔습니다. 서버를 종료합니다...")
            # 서버 종료를 위해 별도 스레드에서 시그널 전송
            def shutdown_server():
                import time
                time.sleep(0.5)  # 로그 출력을 위한 짧은 대기
                
                # Windows에서 강제 종료
                if platform.system() == "Windows":
                    # 현재 프로세스 ID 가져오기
                    pid = os.getpid()
                    # 부모 프로세스(reload 모드)까지 함께 종료
                    os.system(f"taskkill /F /PID {pid} /T >nul 2>&1")
                else:
                    # Unix 계열에서는 SIGTERM 신호 전송
                    os.kill(os.getpid(), signal.SIGTERM)
            
            shutdown_thread = threading.Thread(target=shutdown_server)
            shutdown_thread.daemon = True
            shutdown_thread.start()

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
        
        # 설정 파일에서 alert_exclusion_days 값 읽기
        config_file = app_state.file_manager.read_config_file()
        alert_exclusion_days = int(config_file.get('alert_exclusion_days', '7'))
        
        return {
            "is_searching": app_state.is_searching,
            "config": {
                "geoweb_configured": bool(app_state.config and app_state.config.geoweb_id and
                                        app_state.file_manager.read_config_file().get('지오영활성화', 'true').lower() == 'true'),
                "baekje_configured": bool(app_state.config and app_state.config.has_baekje_credentials() and
                                        app_state.file_manager.read_config_file().get('백제활성화', 'false').lower() == 'true'),
                "incheon_configured": bool(app_state.config and app_state.config.has_incheon_credentials() and
                                        app_state.file_manager.read_config_file().get('인천약품활성화', 'false').lower() == 'true'),
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

@app.post("/api/search/start")
async def start_search():
    """검색 시작"""
    if app_state.is_searching:
        raise HTTPException(status_code=400, detail="이미 검색 중입니다")
    
    # 활성화된 도매상이 있는지 확인
    config_file = app_state.file_manager.read_config_file()
    geoweb_active = config_file.get('지오영활성화', 'true').lower() == 'true'
    baekje_active = config_file.get('백제활성화', 'false').lower() == 'true'
    
    if not app_state.config or not app_state.config.geoweb_id:
        raise HTTPException(status_code=400, detail="지오영 계정 정보가 설정되지 않았습니다")
        
    if not geoweb_active and not baekje_active:
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
        # info.txt 파일에서 설정 읽기
        config_data = app_state.file_manager.read_config_file()
        
        # 동적으로 도매상 리스트 생성
        distributors = []
        
        # 지오영 정보 (항상 표시)
        distributors.append({
            "id": "geoweb",
            "name": "지오영",
            "enabled": config_data.get('지오영활성화', 'true').lower() == 'true',
            "username": config_data.get('지오영아이디', ''),
            "password": config_data.get('지오영비밀번호', '')
        })
        
        # 백제약품 정보 (항상 표시)
        distributors.append({
            "id": "baekje",
            "name": "백제약품",
            "enabled": config_data.get('백제활성화', 'false').lower() == 'true',
            "username": config_data.get('백제아이디', ''),
            "password": config_data.get('백제비밀번호', '')
        })

        # 인천약품 정보 (항상 표시)
        distributors.append({
            "id": "incheon",
            "name": "인천약품",
            "enabled": config_data.get('인천약품활성화', 'false').lower() == 'true',
            "username": config_data.get('인천약품아이디', ''),
            "password": config_data.get('인천약품비밀번호', '')
        })

        # info.txt에서 새로운 도매상 자동 감지 (아이디/비밀번호 패턴)
        for key, value in config_data.items():
            if key.endswith('아이디') and key not in ['지오영아이디', '백제아이디', '인천약품아이디']:
                distributor_name = key.replace('아이디', '')
                password_key = distributor_name + '비밀번호'
                active_key = distributor_name + '활성화'
                
                distributors.append({
                    "id": distributor_name.lower(),
                    "name": distributor_name,
                    "enabled": config_data.get(active_key, 'false').lower() == 'true',
                    "username": value or '',
                    "password": config_data.get(password_key, '')
                })
        
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
        config_data = app_state.file_manager.read_config_file()
        
        # 도매상 설정 업데이트
        for dist in distributors:
            dist_name = dist['name']
            enabled = dist.get('enabled', False)
            username = dist.get('username', '')
            password = dist.get('password', '')
            
            # 한국어 이름을 키로 사용
            if dist_name == "지오영":
                config_data['지오영활성화'] = 'true' if enabled else 'false'
                # 활성화된 경우에만 아이디/비밀번호 업데이트 (비활성화 시에는 기존 값 유지)
                if enabled:
                    config_data['지오영아이디'] = username
                    config_data['지오영비밀번호'] = password
                    
            elif dist_name == "백제약품":
                config_data['백제활성화'] = 'true' if enabled else 'false'
                # 활성화된 경우에만 아이디/비밀번호 업데이트 (비활성화 시에는 기존 값 유지)
                if enabled:
                    config_data['백제아이디'] = username
                    config_data['백제비밀번호'] = password

            elif dist_name == "인천약품":
                config_data['인천약품활성화'] = 'true' if enabled else 'false'
                # 활성화된 경우에만 아이디/비밀번호 업데이트 (비활성화 시에는 기존 값 유지)
                if enabled:
                    config_data['인천약품아이디'] = username
                    config_data['인천약품비밀번호'] = password

            else:
                # 새로운 도매상
                config_data[f'{dist_name}활성화'] = 'true' if enabled else 'false'
                # 활성화된 경우에만 아이디/비밀번호 업데이트 (비활성화 시에는 기존 값 유지)
                if enabled:
                    config_data[f'{dist_name}아이디'] = username
                    config_data[f'{dist_name}비밀번호'] = password
        
        # info.txt 파일 저장
        app_state.file_manager.write_config_file(config_data)
        
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
        config_data = app_state.file_manager.read_config_file()
        return {
            "repeat_interval_minutes": config_data.get('repeat_interval_minutes', '30'),
            "alert_exclusion_days": config_data.get('alert_exclusion_days', '7')
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"시스템 설정 읽기 실패: {str(e)}")

@app.put("/api/system-settings")
async def update_system_settings(data: dict):
    """시스템 설정 업데이트"""
    try:
        repeat_interval = data.get('repeat_interval_minutes')
        alert_exclusion_days = data.get('alert_exclusion_days')
        
        # 유효성 검사
        if not repeat_interval or not isinstance(repeat_interval, int) or repeat_interval < 1 or repeat_interval > 1440:
            raise HTTPException(status_code=400, detail="반복 간격은 1분에서 1440분 사이의 정수여야 합니다")
        
        if not alert_exclusion_days or not isinstance(alert_exclusion_days, int) or alert_exclusion_days < 1 or alert_exclusion_days > 365:
            raise HTTPException(status_code=400, detail="알림 제외 기간은 1일에서 365일 사이의 정수여야 합니다")
        
        # 현재 설정 읽기
        try:
            config_data = app_state.file_manager.read_config_file()
        except FileNotFoundError:
            # 파일이 없으면 기본 설정으로 시작
            config_data = {}
        
        # 새 설정값 적용
        config_data['repeat_interval_minutes'] = str(repeat_interval)
        config_data['alert_exclusion_days'] = str(alert_exclusion_days)
        
        # 파일에 저장
        app_state.file_manager.write_config_file(config_data)
        
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
    print("🚀 약품 재고 자동 검색 웹 서버 시작")
    print("📱 브라우저를 자동으로 열고 있습니다...")
    
    # 서버 시작 후 브라우저 자동 열기
    def open_browser():
        import time
        time.sleep(1)  # 서버가 완전히 시작될 때까지 잠시 대기
        webbrowser.open("http://localhost:8000")
    
    # 별도 스레드에서 브라우저 열기
    browser_thread = threading.Thread(target=open_browser)
    browser_thread.daemon = True
    browser_thread.start()
    
    uvicorn.run(
        "web_server:app",
        host="0.0.0.0",
        port=8000,
        reload=False,  # reload 모드는 개발 중에 코드를 자주 수정할 경우에 사용하는 모드
        log_level="info"
    )