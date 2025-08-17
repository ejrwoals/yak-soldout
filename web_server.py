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
from scrapers.browser_manager import BrowserManager
from scrapers.geoweb_scraper import GeowebScraper
from scrapers.baekje_scraper import BaekjeScraper

app = FastAPI(title="약품 재고 자동 검색", version="2.0.0")

# 정적 파일 서빙
app.mount("/static", StaticFiles(directory="static"), name="static")

# 템플릿 엔진
templates = Jinja2Templates(directory="templates")

# 전역 상태
class AppState:
    def __init__(self):
        self.config_manager = ConfigManager()
        self.app_dir = self.config_manager.get_app_directory()
        self.file_manager = FileManager(self.app_dir)
        self.data_processor = DataProcessor()
        self.config: Optional[AppConfig] = None
        self.alert_manager: Optional[AlertManager] = None
        
        # 검색 상태
        self.is_searching = False
        self.search_task: Optional[asyncio.Task] = None
        self.connected_clients: List[WebSocket] = []
        self.cycle_terminated = False  # 긴급 약품 발견으로 사이클 조기 종료 플래그
        
        # 실시간 검색 데이터 (메모리 기반)
        self.current_search = {
            "status": "idle",  # idle, searching, completed, error
            "timestamp": None,
            "progress": {"current": 0, "total": 0},
            "current_drug": None,
            "found_drugs": [],
            "soldout_drugs": [],
            "errors": [],
            "search_duration": 0
        }
        
        # 초기화
        self._initialize()
    
    def reset_search_data(self):
        """검색 데이터 초기화 (새 사이클 시작 시)"""
        self.cycle_terminated = False  # 사이클 종료 플래그 초기화
        self.current_search = {
            "status": "idle",
            "timestamp": None,
            "progress": {"current": 0, "total": 0},
            "current_drug": None,
            "found_drugs": [],
            "soldout_drugs": [],
            "errors": [],
            "search_duration": 0
        }
    
    def add_drug_result(self, drug_data: dict, is_found: bool):
        """개별 약품 검색 결과 추가"""
        if is_found:
            self.current_search["found_drugs"].append(drug_data)
        else:
            self.current_search["soldout_drugs"].append(drug_data)
        
        # 진행률 업데이트
        self.current_search["progress"]["current"] += 1
    
    def _initialize(self):
        """앱 초기화"""
        try:
            self.config = self.config_manager.load_config()
            self.alert_manager = AlertManager(self.config.alert_exclusion_days)
        except Exception as e:
            print(f"초기화 오류: {e}")

# 전역 앱 상태 인스턴스
app_state = AppState()

# WebSocket 연결 관리자
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        print(f"WebSocket 클라이언트 연결됨. 총 {len(self.active_connections)}개")
    
    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        print(f"WebSocket 클라이언트 연결 해제됨. 총 {len(self.active_connections)}개")
    
    async def broadcast_message(self, message: str):
        """모든 연결된 클라이언트에게 메시지 브로드캐스트"""
        if not self.active_connections:
            return
            
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception:
                disconnected.append(connection)
        
        # 연결이 끊어진 클라이언트 제거
        for conn in disconnected:
            self.disconnect(conn)

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
                "drug_list": [item.get('drugName', item) if isinstance(item, dict) else item for item in drug_list_json[:5]],  # 최대 5개까지만 툴팁에 표시
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
    app_state.search_task = asyncio.create_task(execute_search())
    
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

async def broadcast_log(message: str):
    """로그 메시지를 WebSocket으로 브로드캐스트"""
    await manager.broadcast_message(json.dumps({
        "type": "log",
        "message": message,
        "timestamp": datetime.now().isoformat()
    }))

async def execute_search():
    """반복 검색 실행 (비동기)"""
    cycle_count = 0
    
    try:
        # repeat_interval_minutes 설정 읽기
        config_file = app_state.file_manager.read_config_file()
        repeat_interval = int(config_file.get('repeat_interval_minutes', '30'))
        
        await broadcast_log(f"🔄 반복 사이클 시작 (간격: {repeat_interval}분)")
        
        while app_state.is_searching:  # 무한 루프 시작
            cycle_count += 1
            
            # 사이클 시작 알림
            await manager.broadcast_message(json.dumps({
                "type": "cycle_start",
                "message": f"🔄 사이클 #{cycle_count} 시작",
                "cycle_number": cycle_count,
                "timestamp": datetime.now().isoformat()
            }))
            
            await broadcast_log(f"🔍 사이클 #{cycle_count} 검색 시작")
            
            # 검색 데이터 초기화 (각 사이클마다)
            app_state.reset_search_data()
            app_state.current_search["status"] = "searching"
            app_state.current_search["timestamp"] = datetime.now().isoformat()
            
            # 진행 상황 전달용 큐
            progress_queue = queue.Queue()
            
            # 동기 검색 함수를 별도 스레드에서 실행
            loop = asyncio.get_event_loop()
            with concurrent.futures.ThreadPoolExecutor() as executor:
                # 큐를 인자로 전달
                search_task = loop.run_in_executor(executor, execute_search_sync, progress_queue)
                
                # 진행 상황 모니터링
                while not search_task.done():
                    if not app_state.is_searching:  # 중단 체크
                        search_task.cancel()
                        break
                        
                    try:
                        # 0.5초마다 큐 확인
                        await asyncio.sleep(0.5)
                        
                        # 큐에서 메시지 가져오기 (비블로킹)
                        try:
                            while True:
                                message = progress_queue.get_nowait()
                                
                                # 개별 약품 완료 메시지 처리
                                if message.startswith("DRUG_FOUND:"):
                                    drug_data = json.loads(message[11:])  # "DRUG_FOUND:" 제거
                                    await manager.broadcast_message(json.dumps(drug_data))
                                elif message.startswith("DRUG_SOLDOUT:"):
                                    soldout_data = json.loads(message[13:])
                                    await manager.broadcast_message(json.dumps(soldout_data))
                                elif message.startswith("DRUG_ERROR:"):
                                    err_data = json.loads(message[11:])
                                    await manager.broadcast_message(json.dumps(err_data))
                                elif message.startswith("URGENT_ALERT:"):
                                    urgent_data = json.loads(message[13:])  # "URGENT_ALERT:" 제거
                                    await manager.broadcast_message(json.dumps(urgent_data))
                                else:
                                    # 일반 로그 메시지
                                    await broadcast_log(message)
                        except queue.Empty:
                            pass
                            
                    except asyncio.CancelledError:
                        break
                
                # 최종 결과 가져오기
                if not search_task.cancelled():
                    result = await search_task
                else:
                    result = None
                
            # 중단 체크
            if not app_state.is_searching:
                await broadcast_log(f"🛑 사이클 #{cycle_count} 중단됨")
                break
            
            # 결과 처리
            if result:
                # execute_search_sync에서 추가한 카운트 사용
                found_count = result.get('found_count', 0)
                soldout_count = result.get('soldout_count', 0)
                error_count = result.get('error_count', 0)
                
                await broadcast_log(f"✅ 사이클 #{cycle_count} 완료! 재고 발견: {found_count}개, 품절: {soldout_count}개")
                
                # 검색 완료 알림
                await manager.broadcast_message(json.dumps({
                    "type": "search_completed",
                    "data": {
                        "found_count": found_count,
                        "soldout_count": soldout_count,
                        "error_count": error_count,
                        "cycle_number": cycle_count
                    },
                    "timestamp": datetime.now().isoformat()
                }))
            else:
                await broadcast_log(f"❌ 사이클 #{cycle_count} 검색 결과를 가져올 수 없었습니다")
                
                # 실패 알림도 전송
                await manager.broadcast_message(json.dumps({
                    "type": "search_completed",
                    "data": {
                        "found_count": 0,
                        "soldout_count": 0,
                        "error_count": 1,
                        "cycle_number": cycle_count
                    },
                    "timestamp": datetime.now().isoformat()
                }))
            
            # 다음 사이클까지 대기 (중단 체크와 함께)
            if app_state.is_searching:
                await broadcast_log(f"⏰ 다음 사이클까지 {repeat_interval}분 대기 중...")
                
                # 카운트다운과 함께 대기
                for remaining_minutes in range(repeat_interval, 0, -1):
                    if not app_state.is_searching:  # 대기 중에도 중단 체크
                        break
                    
                    # 매분마다 카운트다운 메시지 (처음 1분, 마지막 5분만 표시)
                    if remaining_minutes == repeat_interval or remaining_minutes <= 5:
                        await manager.broadcast_message(json.dumps({
                            "type": "cycle_countdown",
                            "message": f"⏰ 다음 사이클까지 {remaining_minutes}분 남음",
                            "remaining_minutes": remaining_minutes,
                            "next_cycle": cycle_count + 1,
                            "timestamp": datetime.now().isoformat()
                        }))
                    
                    # 1분 대기 (중단 체크와 함께)
                    for _ in range(60):  # 60초를 1초씩 나눠서 중단 체크
                        if not app_state.is_searching:
                            break
                        await asyncio.sleep(1)
                    
                    if not app_state.is_searching:
                        break
        
        await broadcast_log(f"🏁 반복 사이클 종료 (총 {cycle_count}회 실행)")
        
    except Exception as e:
        await broadcast_log(f"❌ 반복 사이클 중 오류: {e}")
        await manager.broadcast_message(json.dumps({
            "type": "search_error",
            "message": str(e),
            "timestamp": datetime.now().isoformat()
        }))
    finally:
        app_state.is_searching = False

def execute_search_sync(progress_queue=None):
    """동기 검색 실행 (별도 스레드에서 실행)"""
    
    def log_message(msg):
        """로그 메시지를 터미널과 큐에 모두 전송"""
        print(msg)
        if progress_queue:
            try:
                progress_queue.put_nowait(msg)
            except:
                pass
    
    try:
        # 데이터 로드
        drug_list = app_state.file_manager.read_drug_list()
        drug_list_json = app_state.file_manager.read_drug_list_json()
        exclusion_list = app_state.file_manager.read_alert_exclusions()
        
        # 긴급 알림 약품 목록 생성 (약품명 기준)
        urgent_drugs = {
            drug['drugName'] for drug in drug_list_json 
            if drug.get('isUrgent', False)
        }
        
        # 지오영에서 수집된 보험코드 -> 약품명 매핑 (백제 긴급 알림용)
        urgent_insurance_codes = set()
        # 백제 검색에 사용된 보험코드 매핑 저장용
        baekje_search_codes = {}
        
        # 진행률 설정
        app_state.current_search["progress"]["total"] = len(drug_list)
        app_state.current_search["progress"]["current"] = 0
        
        log_message(f"📋 검색할 약품 수: {len(drug_list)}개")
        
        # 알림 제외 목록 처리
        cleaned_exclusions, excluded_names, none_stop_mode = \
            app_state.data_processor.process_alert_exclusions(exclusion_list, app_state.config.alert_exclusion_days)
        
        # 웹 스크래핑 실행
        all_drugs = []
        errors = []
        
        # 활성화 플래그 확인
        config_file = app_state.file_manager.read_config_file()
        geoweb_active = config_file.get('지오영활성화', 'true').lower() == 'true'
        baekje_active = config_file.get('백제활성화', 'false').lower() == 'true'
        
        # 지오영 검색 (활성화된 경우)
        if geoweb_active and app_state.config.geoweb_id:
            log_message("🌐 지오영 검색 시작...")
            geoweb_drugs, geoweb_errors = search_geoweb_sync(drug_list, excluded_names, progress_queue, urgent_drugs)
            all_drugs.extend(geoweb_drugs)
            errors.extend(geoweb_errors)
            
            # 긴급 알림 약품의 보험코드 수집
            for drug in geoweb_drugs:
                if hasattr(drug, 'name') and hasattr(drug, 'insurance_code'):
                    if drug.name in urgent_drugs and drug.insurance_code:
                        urgent_insurance_codes.add(drug.insurance_code)
                        # log_message(f"📌 긴급 알림 약품 보험코드 수집: {drug.name} -> {drug.insurance_code}")
        else:
            log_message("⚠️ 지오영이 비활성화되어 있습니다")
        
        # 백제 검색 (활성화된 경우) - 사이클 조기 종료 체크
        if app_state.cycle_terminated:
            log_message("🚨 긴급 재고 발견으로 백제 검색 건너뛰기 - 사이클 조기 종료")
        elif baekje_active and app_state.config.has_baekje_credentials():
            log_message("🏢 백제약품 검색 시작...")
            # 지오영에서 수집한 보험코드 사용
            if hasattr(all_drugs, '__iter__') and len(all_drugs) > 0:
                # 지오영 결과에서 보험코드 수집
                insurance_codes = {}
                for drug in all_drugs:
                    if hasattr(drug, 'insurance_code') and drug.insurance_code:
                        insurance_codes[drug.insurance_code] = drug.name
                
                if insurance_codes:
                    # 백제 검색용 매핑 저장 (긴급 알림 판단용)
                    baekje_search_codes = insurance_codes.copy()
                    
                    baekje_drugs, baekje_errors = search_baekje_sync(insurance_codes, excluded_names, progress_queue, urgent_drugs)
                    all_drugs.extend(baekje_drugs)
                    errors.extend(baekje_errors)
                else:
                    log_message("⚠️ 지오영에서 보험코드를 수집하지 못했습니다")
            else:
                log_message("⚠️ 지오영 검색 결과가 없어 백제 검색을 건너뜁니다")
        elif baekje_active:
            log_message("⚠️ 백제약품이 활성화되어 있지만 계정 정보가 없습니다")
        
        # 결과 분류
        found_drugs, soldout_drugs = app_state.data_processor.categorize_drugs(all_drugs, cleaned_exclusions)
        
        # 긴급 알림은 이제 검색 중 즉시 처리됨 (위에서 조기 종료)
        
        # 메모리 상태 업데이트
        app_state.current_search["status"] = "completed"
        app_state.current_search["errors"] = errors
        
        log_message(f"✅ 검색 완료! 재고 발견: {len(found_drugs)}개, 품절: {len(soldout_drugs)}개")
        
        # 결과 딕셔너리 반환 (파일 저장 없이)
        result_dict = {
            'found_count': len(found_drugs),
            'soldout_count': len(soldout_drugs),
            'error_count': len(errors),
            'found_drugs': [drug.to_dict() if hasattr(drug, 'to_dict') else drug.__dict__ for drug in found_drugs],
            'soldout_drugs': [drug.to_dict() if hasattr(drug, 'to_dict') else drug.__dict__ for drug in soldout_drugs]
        }
        
        # 메모리 상태 최종 업데이트
        app_state.current_search["found_drugs"] = result_dict['found_drugs']
        app_state.current_search["soldout_drugs"] = result_dict['soldout_drugs']
        
        return result_dict
        
    except Exception as e:
        error_msg = f"❌ 동기 검색 중 오류: {e}"
        log_message(error_msg)
        app_state.current_search["status"] = "error"
        app_state.current_search["errors"].append(str(e))
        return None

def search_baekje_sync(insurance_codes: Dict[str, str], excluded_names: List[str], progress_queue=None, urgent_drugs=None) -> tuple:
    """백제약품 검색 (동기)"""
    
    def log_message(msg):
        """로그 메시지를 터미널과 큐에 모두 전송"""
        print(msg)
        if progress_queue:
            try:
                progress_queue.put_nowait(msg)
            except:
                pass
    
    all_drugs = []
    errors = []
    
    browser_mgr = BrowserManager()
    browser_mgr.start()
    
    try:
        scraper = BaekjeScraper()
        page = browser_mgr.new_page()
        
        # 로그인
        log_message("🤖 백제약품에 로그인하는 중입니다...")
        if not scraper.login(page, app_state.config.baekje_id, app_state.config.baekje_password):
            raise Exception("백제약품 로그인 실패")
        
        log_message("✓ 백제약품 로그인 성공")
        
        # 보험코드 기반 검색
        log_message(f"📋 검색할 보험코드 수: {len(insurance_codes)}개")
        
        for i, (insurance_code, original_name) in enumerate(insurance_codes.items(), 1):
            if not app_state.is_searching:  # 중단 확인
                break
                
            try:
                drugs = scraper._search_by_insurance_code(insurance_code)
                for drug in drugs:
                    drug.is_excluded_from_alert = drug.name in excluded_names
                    # 검색에 사용된 보험코드와 원래 약품명 정보 추가
                    drug.search_insurance_code = insurance_code
                    drug.original_drug_name = original_name
                    drug.distributor = "백제약품"  # 백제약품 검색 결과임을 명시
                
                # 검색 결과 로그
                if drugs:
                    log_message(f"🔍 백제 검색 완료 ({i}/{len(insurance_codes)}): {original_name} ({insurance_code}) - {len(drugs)}개 규격 발견")
                    
                    # 모든 규격을 별도로 처리
                    for drug_idx, drug in enumerate(drugs):
                        main_stock = drug.main_stock if drug.main_stock else "정보없음"
                        
                        # 재고 상황 표시
                        main_display = "품절" if main_stock == "품절" or main_stock == "0" else f"{main_stock}개"
                        unit_display = f" [{drug.unit}]" if drug.unit else ""
                        
                        log_message(f"   - {drug.name}{unit_display}: {main_display}")
                        
                        # 각 규격별로 재고 발견 여부 확인
                        has_stock = drug.has_stock() if hasattr(drug, 'has_stock') else (main_stock != "품절" and main_stock != "0")
                        
                        # 긴급 약품이면서 재고가 있는 경우 즉시 알림 및 사이클 종료
                        if urgent_drugs and original_name in urgent_drugs and has_stock:
                            # log_message(f"🚨 긴급 재고 발견! {original_name} (백제: {drug.name}) - 즉시 알림 전송 후 사이클 조기 종료")
                            
                            # 사이클 종료 플래그 설정
                            app_state.cycle_terminated = True
                            
                            # 즉시 긴급 알림 전송
                            urgent_alert_msg = {
                                "type": "urgent_alert",
                                "drug": {
                                    "name": drug.name,
                                    "main_stock": main_stock,
                                    "incheon_stock": "-",
                                    "company": "백제약품",
                                    "distributor": "백제약품",
                                    "original_drug_name": original_name,  # 지오영 원래 약품명 추가
                                    "unit": drug.unit  # 규격 정보 추가
                                },
                                "timestamp": datetime.now().isoformat()
                            }
                            if progress_queue:
                                try:
                                    progress_queue.put_nowait(f"URGENT_ALERT:{json.dumps(urgent_alert_msg)}")
                                except:
                                    pass
                            
                            # 현재 약품을 결과에 추가 후 즉시 종료
                            all_drugs.extend(drugs)
                            return all_drugs, errors
                        
                        # 메모리 상태에 개별 결과 추가 (각 규격별로)
                        drug_data = {
                            "name": f"{drug.name}{unit_display}",  # 약품명 + 규격 표시
                            "main_stock": main_stock,
                            "incheon_stock": "-",
                            "company": "백제약품",
                            "has_stock": has_stock,
                            "unit": drug.unit  # 규격 정보
                        }
                        app_state.add_drug_result(drug_data, has_stock)
                        
                        # 개별 약품 완료 메시지를 큐에 추가 (WebSocket 전송용)
                        if progress_queue:
                            try:
                                drug_found_msg = {
                                    "type": "drug_found",
                                    "drug": drug_data,
                                    "progress": {"current": i, "total": len(insurance_codes)}
                                }
                                progress_queue.put_nowait(f"DRUG_FOUND:{json.dumps(drug_found_msg)}")
                            except:
                                pass
                else:
                    log_message(f"❌ 백제 검색 실패 ({i}/{len(insurance_codes)}): {original_name} ({insurance_code}) - 검색 결과 없음")
                    errors.append(f"{original_name} ({insurance_code}): 검색 결과 없음")
                
                all_drugs.extend(drugs)
            except Exception as e:
                error_msg = f"{original_name} ({insurance_code}): {str(e)}"
                errors.append(error_msg)
                log_message(f"❌ {error_msg}")
        
        log_message(f"✓ 백제약품 검색 완료: {len(all_drugs)}개 약품")
        
    finally:
        browser_mgr.stop()
    
    return all_drugs, errors

def search_geoweb_sync(drug_list: List[str], excluded_names: List[str], progress_queue=None, urgent_drugs=None) -> tuple:
    """지오영 검색 (동기)"""
    
    def log_message(msg):
        """로그 메시지를 터미널과 큐에 모두 전송"""
        print(msg)
        if progress_queue:
            try:
                progress_queue.put_nowait(msg)
            except:
                pass
    
    all_drugs = []
    errors = []
    
    browser_mgr = BrowserManager()
    browser_mgr.start()
    
    try:
        scraper = GeowebScraper()
        page = browser_mgr.new_page()
        
        # 로그인
        log_message("🤖 지오영에 로그인하는 중입니다...")
        if not scraper.login(page, app_state.config.geoweb_id, app_state.config.geoweb_password):
            raise Exception("지오영 로그인 실패")
        
        log_message("✓ 지오영 로그인 성공")
        
        # 약품 검색
        for i, drug_name in enumerate(drug_list, 1):
            if not app_state.is_searching:  # 중단 확인
                break
                
            try:
                drugs = scraper.search_drug(drug_name)
                for drug in drugs:
                    drug.is_excluded_from_alert = drug.name in excluded_names
                    drug.distributor = "지오영"  # 지오영 검색 결과임을 명시
                
                # 재고 상황 로그 추가 및 실시간 상태 업데이트
                if drugs:
                    drug = drugs[0]  # 첫 번째 결과 사용
                    main_stock = drug.main_stock if drug.main_stock else "정보없음"
                    incheon_stock = drug.incheon_stock if drug.incheon_stock else "정보없음"
                    
                    # 재고 상황을 더 명확하게 표시
                    main_display = "품절" if main_stock == "품절" or main_stock == "0" else f"{main_stock}개"
                    incheon_display = "품절" if incheon_stock == "품절" or incheon_stock == "0" else f"{incheon_stock}개"
                    
                    # 한 줄로 통합된 로그 메시지
                    log_message(f"🔍 검색 완료 ({i}/{len(drug_list)}): {drug_name} ( 메인: {main_display} | 인천: {incheon_display} )")
                    
                    # 재고 발견 여부 확인
                    has_stock = drug.has_stock() if hasattr(drug, 'has_stock') else (main_stock != "품절" and main_stock != "0")
                    
                    # 긴급 약품이면서 재고가 있는 경우 즉시 알림 및 사이클 종료
                    if urgent_drugs and drug.name in urgent_drugs and has_stock:
                        # log_message(f"🚨 긴급 재고 발견! {drug.name} - 즉시 알림 전송 후 사이클 조기 종료")
                        
                        # 사이클 종료 플래그 설정
                        app_state.cycle_terminated = True
                        
                        # 즉시 긴급 알림 전송
                        urgent_alert_msg = {
                            "type": "urgent_alert",
                            "drug": {
                                "name": drug.name,
                                "main_stock": main_stock,
                                "incheon_stock": incheon_stock,
                                "company": getattr(drug, 'company', ''),
                                "distributor": "지오영"
                            },
                            "timestamp": datetime.now().isoformat()
                        }
                        if progress_queue:
                            try:
                                progress_queue.put_nowait(f"URGENT_ALERT:{json.dumps(urgent_alert_msg)}")
                            except:
                                pass
                        
                        # 현재 약품을 결과에 추가 후 즉시 종료
                        all_drugs.extend(drugs)
                        return all_drugs, errors
                    
                    # 메모리 상태에 개별 결과 추가
                    drug_data = {
                        "name": drug.name,
                        "main_stock": main_stock,
                        "incheon_stock": incheon_stock,
                        "company": getattr(drug, 'company', ''),
                        "has_stock": has_stock
                    }
                    app_state.add_drug_result(drug_data, has_stock)
                    
                    # 개별 약품 완료 메시지를 큐에 추가 (WebSocket 전송용)
                    if progress_queue:
                        try:
                            drug_found_msg = {
                                "type": "drug_found",
                                "drug": drug_data,
                                "progress": app_state.current_search["progress"].copy()
                            }
                            progress_queue.put_nowait(f"DRUG_FOUND:{json.dumps(drug_found_msg)}")
                        except:
                            pass
                else:
                    # 검색 결과 없음: 오류로 승격하여 프론트에 표시 (리다이렉트/검색 실패 구분 어려움 방지)
                    log_message(f"❌ 검색 실패 ({i}/{len(drug_list)}): {drug_name} ( 검색 결과 없음 )")

                    # 에러 집계 및 진행률 업데이트
                    errors.append(f"{drug_name}: 검색 결과 없음")
                    app_state.current_search["progress"]["current"] += 1
                    # 프론트로 오류 전송
                    if progress_queue:
                        try:
                            drug_error_msg = {
                                "type": "drug_error",
                                "drug": {"name": drug_name, "error": "검색 결과 없음"},
                                "progress": app_state.current_search["progress"].copy()
                            }
                            progress_queue.put_nowait(f"DRUG_ERROR:{json.dumps(drug_error_msg)}")
                        except:
                            pass
                
                all_drugs.extend(drugs)
            except Exception as e:
                error_msg = f"{drug_name}: {str(e)}"
                errors.append(error_msg)
                log_message(f"❌ {error_msg}")
                # 진행률 업데이트
                app_state.current_search["progress"]["current"] += 1
                # 에러도 프론트로 전송
                if progress_queue:
                    try:
                        drug_error_msg = {
                            "type": "drug_error",
                            "drug": {"name": drug_name, "error": str(e)},
                            "progress": app_state.current_search["progress"].copy()
                        }
                        progress_queue.put_nowait(f"DRUG_ERROR:{json.dumps(drug_error_msg)}")
                    except:
                        pass
        
        log_message(f"✓ 지오영 검색 완료: {len(all_drugs)}개 약품")
        
    finally:
        browser_mgr.stop()
    
    return all_drugs, errors

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