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
        exclusion_list = app_state.file_manager.read_alert_exclusions()
        
        
        # 실시간 검색 상태 (메모리에서)
        current_search = app_state.current_search.copy()
        
        return {
            "is_searching": app_state.is_searching,
            "config": {
                "geoweb_configured": bool(app_state.config and app_state.config.geoweb_id),
                "baekje_configured": bool(app_state.config and app_state.config.has_baekje_credentials())
            },
            "files": {
                "drug_count": len(drug_list),
                "drug_list": drug_list[:5],  # 최대 5개까지만 툴팁에 표시
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
    
    if not app_state.config or not app_state.config.geoweb_id:
        raise HTTPException(status_code=400, detail="지오영 계정 정보가 설정되지 않았습니다")
    
    # 검색 데이터 초기화 (새 사이클 시작)
    app_state.reset_search_data()
    app_state.current_search["status"] = "searching"
    app_state.current_search["timestamp"] = datetime.now().isoformat()
    
    # 검색 시작
    app_state.is_searching = True
    app_state.search_task = asyncio.create_task(execute_search())
    
    # 사이클 시작 알림
    await manager.broadcast_message(json.dumps({
        "type": "cycle_start",
        "message": "🔄 새로운 검색 사이클을 시작합니다",
        "timestamp": datetime.now().isoformat()
    }))
    
    await manager.broadcast_message(json.dumps({
        "type": "search_started",
        "message": "🔍 검색을 시작합니다...",
        "timestamp": datetime.now().isoformat()
    }))
    
    return {"message": "검색을 시작했습니다"}

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

async def broadcast_log(message: str):
    """로그 메시지를 WebSocket으로 브로드캐스트"""
    await manager.broadcast_message(json.dumps({
        "type": "log",
        "message": message,
        "timestamp": datetime.now().isoformat()
    }))

async def execute_search():
    """검색 실행 (비동기)"""
    try:
        await broadcast_log("🔍 검색 시작")
        
        # 진행 상황 전달용 큐
        progress_queue = queue.Queue()
        
        # 동기 검색 함수를 별도 스레드에서 실행
        loop = asyncio.get_event_loop()
        with concurrent.futures.ThreadPoolExecutor() as executor:
            # 큐를 인자로 전달
            search_task = loop.run_in_executor(executor, execute_search_sync, progress_queue)
            
            # 진행 상황 모니터링
            while not search_task.done():
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
                            else:
                                # 일반 로그 메시지
                                await broadcast_log(message)
                    except queue.Empty:
                        pass
                        
                except asyncio.CancelledError:
                    break
            
            # 최종 결과 가져오기
            result = await search_task
            
        # 결과 처리
        if result:
            # execute_search_sync에서 추가한 카운트 사용
            found_count = result.get('found_count', 0)
            soldout_count = result.get('soldout_count', 0)
            error_count = result.get('error_count', 0)
            
            await broadcast_log(f"✅ 검색 완료! 재고 발견: {found_count}개, 품절: {soldout_count}개")
            
            # 검색 완료 알림
            await manager.broadcast_message(json.dumps({
                "type": "search_completed",
                "data": {
                    "found_count": found_count,
                    "soldout_count": soldout_count,
                    "error_count": error_count
                },
                "timestamp": datetime.now().isoformat()
            }))
        else:
            await broadcast_log("❌ 검색 결과를 가져올 수 없었습니다")
            
            # 실패 알림도 전송
            await manager.broadcast_message(json.dumps({
                "type": "search_completed",
                "data": {
                    "found_count": 0,
                    "soldout_count": 0,
                    "error_count": 1
                },
                "timestamp": datetime.now().isoformat()
            }))
        
    except Exception as e:
        await broadcast_log(f"❌ 검색 중 오류: {e}")
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
        exclusion_list = app_state.file_manager.read_alert_exclusions()
        
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
        
        # 지오영 검색 (동기)
        log_message("🌐 지오영 검색 시작...")
        geoweb_drugs, geoweb_errors = search_geoweb_sync(drug_list, excluded_names, progress_queue)
        all_drugs.extend(geoweb_drugs)
        errors.extend(geoweb_errors)
        
        # 백제 검색 (설정된 경우)
        if app_state.config.has_baekje_credentials():
            log_message("🏢 백제약품 검색 시작...")
            log_message("⚠️ 백제약품 검색은 아직 구현되지 않았습니다")
        
        # 결과 분류
        found_drugs, soldout_drugs = app_state.data_processor.categorize_drugs(all_drugs, cleaned_exclusions)
        
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

def search_geoweb_sync(drug_list: List[str], excluded_names: List[str], progress_queue=None) -> tuple:
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