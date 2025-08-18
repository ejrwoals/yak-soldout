"""
앱 전역 상태 관리 모듈

웹 서버의 전역 상태를 관리하는 AppState 클래스를 제공합니다.
"""

import asyncio
from datetime import datetime
from typing import List, Optional, Any
from pathlib import Path

from models.config import ConfigManager, AppConfig
from utils.file_manager import FileManager
from utils.data_processor import DataProcessor
from utils.notifications import AlertManager


class AppState:
    """앱 전역 상태 관리 클래스"""
    
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
        self.connected_clients: List[Any] = []  # WebSocket 타입은 순환 import 방지를 위해 Any 사용
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