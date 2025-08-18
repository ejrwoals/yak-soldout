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
    
    def __init__(self):
        self.active_connections: List[WebSocket] = []
    
    async def connect(self, websocket: WebSocket):
        """새로운 WebSocket 연결 추가"""
        await websocket.accept()
        self.active_connections.append(websocket)
        print(f"WebSocket 클라이언트 연결됨. 총 {len(self.active_connections)}개")
    
    def disconnect(self, websocket: WebSocket):
        """WebSocket 연결 해제"""
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


async def broadcast_log(manager: ConnectionManager, message: str):
    """로그 메시지를 WebSocket으로 브로드캐스트"""
    await manager.broadcast_message(json.dumps({
        "type": "log",
        "message": message,
        "timestamp": datetime.now().isoformat()
    }))