"""
WebSocket 연결 관리 모듈

실시간 통신을 위한 WebSocket 연결 관리와 메시지 브로드캐스팅을 담당합니다.
"""

import json
from datetime import datetime
from typing import List
from fastapi import WebSocket


class ConnectionManager:
    """WebSocket 연결 관리 클래스"""
    
    LOG_HISTORY_MAX = 300  # 보관할 최근 로그 라인 수

    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.browser_opened = False  # 브라우저가 열렸는지 추적
        # 페이지를 다시 열었을 때(예: 홈 → 체커) 진행상황 로그를 복원하기 위한 버퍼.
        # 연결 수와 무관하게 누적되며, 각 항목은 {message, timestamp} 형태.
        self.log_history: List[dict] = []
    
    async def connect(self, websocket: WebSocket):
        """새로운 WebSocket 연결 추가"""
        await websocket.accept()
        self.active_connections.append(websocket)
        self.browser_opened = True  # 브라우저가 연결되었음을 표시
        print(f"WebSocket 클라이언트 연결됨. 총 {len(self.active_connections)}개")
    
    def disconnect(self, websocket: WebSocket):
        """WebSocket 연결 해제"""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        print(f"WebSocket 클라이언트 연결 해제됨. 총 {len(self.active_connections)}개")
        
        # 브라우저가 열렸었고 모든 연결이 끊어지면 서버 종료 신호
        if self.browser_opened and len(self.active_connections) == 0:
            return True  # 서버 종료 신호
        return False
    
    def _record_history(self, message: str):
        """로그 패널에 표시되는 메시지를 히스토리 버퍼에 누적한다.

        broadcast_message 는 모든 WebSocket 메시지의 단일 통로이므로 여기서
        로그성 메시지(type: log/cycle/search 등)만 골라 텍스트로 정규화해 저장한다.
        약품 결과(drug_found 등)는 '검색 결과' 컬럼에서 별도로 복원되므로 제외한다.
        """
        try:
            data = json.loads(message)
        except (ValueError, TypeError):
            return

        mtype = data.get("type")
        ts = data.get("timestamp") or datetime.now().isoformat()
        text = None

        if mtype in ("log", "cycle_start", "cycle_countdown",
                     "search_started", "search_stopped", "search_error"):
            text = data.get("message")
        elif mtype == "search_completed":
            d = data.get("data", {})
            cycle = d.get("cycle_number")
            cinfo = f" (사이클 #{cycle})" if cycle else ""
            text = (f"🎉 검색 완료{cinfo}! 재고: {d.get('found_count', 0)}개, "
                    f"품절: {d.get('soldout_count', 0)}개")
        elif mtype == "urgent_alert":
            drug = data.get("drug", {})
            text = (f"🚨 [긴급 알림] {drug.get('name', '')} 재고 발견! "
                    f"({drug.get('distributor', '')})")

        if not text:
            return

        self.log_history.append({"message": text, "timestamp": ts})
        if len(self.log_history) > self.LOG_HISTORY_MAX:
            del self.log_history[:-self.LOG_HISTORY_MAX]

    async def broadcast_message(self, message: str):
        """모든 연결된 클라이언트에게 메시지 브로드캐스트"""
        # 연결 여부와 무관하게 로그 히스토리는 누적한다 (복원용)
        self._record_history(message)

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


async def broadcast_log(manager: ConnectionManager, message: str):
    """로그 메시지를 WebSocket으로 브로드캐스트"""
    await manager.broadcast_message(json.dumps({
        "type": "log",
        "message": message,
        "timestamp": datetime.now().isoformat()
    }))