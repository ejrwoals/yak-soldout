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
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi import Request
import uvicorn

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

# 정적 파일 서빙
app.mount("/static", StaticFiles(directory="static"), name="static")

# 템플릿 엔진
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
        manager.disconnect(websocket)

@app.get("/api/status")
async def get_status():
    """현재 상태 조회 (실시간 메모리 기반)"""
    try:
        # 기본 정보
        drug_list = app_state.file_manager.read_drug_list()
        drug_list_json = app_state.file_manager.read_drug_list_json()
        
        # JSON 형식의 알림 제외 목록 읽기
        exclusion_json_data = app_state.file_manager.read_alert_exclusions_json()
        exclusion_list = [item.get('drugName', '') for item in exclusion_json_data]  # 약품명만 추출
        
        
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
                "alert_exclusion_days": alert_exclusion_days
            },
            "files": {
                "drug_count": len(drug_list),
                "drug_list": drug_list_json,  # 전체 목록과 긴급 알림 정보 포함
                "exclusion_count": len(exclusion_list),
                "exclusion_list": exclusion_list[:5]  # 최대 5개까지만 툴팁에 표시
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
        
        # info.txt에서 새로운 도매상 자동 감지 (아이디/비밀번호 패턴)
        for key, value in config_data.items():
            if key.endswith('아이디') and key not in ['지오영아이디', '백제아이디']:
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
    """알림 제외 목록 조회 (JSON 형식)"""
    try:
        exclusion_list = app_state.file_manager.read_alert_exclusions_json()
        return {"exclusions": exclusion_list}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"알림 제외 목록 읽기 실패: {str(e)}")

@app.put("/api/exclusion-list")
async def update_exclusion_list(data: dict):
    """알림 제외 목록 업데이트 (JSON 형식)"""
    try:
        exclusions = data.get('exclusions', [])
        
        # 유효성 검사
        if not isinstance(exclusions, list):
            raise HTTPException(status_code=400, detail="알림 제외 목록은 배열이어야 합니다")
        
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
        
        return {"message": f"알림 제외 목록이 저장되었습니다 (총 {len(exclusions)}개)"}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"알림 제외 목록 저장 실패: {str(e)}")

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


if __name__ == "__main__":
    print("🚀 약품 재고 자동 검색 웹 서버 시작")
    print("📱 브라우저에서 http://localhost:8000 을 열어보세요")
    
    uvicorn.run(
        "web_server:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )