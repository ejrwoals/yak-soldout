import platform
import sys
from typing import List, Dict
from models.drug_data import Drug

# 크로스 플랫폼 알림 라이브러리
NOTIFICATION_AVAILABLE = False
try:
    from plyer import notification
    NOTIFICATION_AVAILABLE = True
except ImportError:
    NOTIFICATION_AVAILABLE = False


class CrossPlatformNotifier:
    """크로스 플랫폼 알림 시스템"""
    
    @staticmethod
    def show_alert(title: str, message: str, sound: bool = True):
        """시스템 알림 표시 (크로스 플랫폼)"""
        if NOTIFICATION_AVAILABLE:
            try:
                CrossPlatformNotifier._show_notification(title, message)
            except Exception as e:
                # 알림 실패 시 콘솔 출력
                print(f"알림 실패: {e}")
                print(f"[{title}] {message}")
        else:
            # plyer 사용 불가 시 플랫폼별 fallback
            system = platform.system()
            if system == "Windows":
                CrossPlatformNotifier._show_windows_messagebox(title, message, sound)
            else:
                print(f"[{title}] {message}")
    
    @staticmethod
    def _show_notification(title: str, message: str):
        """Plyer를 사용한 크로스 플랫폼 알림"""
        notification.notify(
            title=title,
            message=message,
            app_name="약국 재고 알리미",
            timeout=10  # 10초간 표시
        )
    
    @staticmethod
    def _show_windows_messagebox(title: str, message: str, sound: bool = True):
        """Windows 메시지박스 (fallback)"""
        import ctypes
        
        # 메시지박스 표시 (0x40: 정보 아이콘, 0x1: OK 버튼)
        ctypes.windll.user32.MessageBoxW(0, message, title, 0x40 | 0x1)
        
        if sound:
            # 시스템 사운드 재생
            ctypes.windll.winmm.PlaySoundW("SystemAsterisk", 0x1)
    
    @staticmethod
    def notify_stock_found(found_drugs: List[Drug]):
        """재고 발견 알림"""
        if not found_drugs:
            return
        
        count = len(found_drugs)
        
        if count == 1:
            drug = found_drugs[0]
            title = "재고 발견!"
            message = f"{drug.distributor.value}에서 {drug.name} 재고를 발견했습니다!"
        else:
            title = f"재고 발견! ({count}개)"
            drug_names = [drug.name for drug in found_drugs[:3]]  # 최대 3개까지만 표시
            message = f"{', '.join(drug_names)}{'...' if count > 3 else ''} 재고를 발견했습니다!"
        
        CrossPlatformNotifier.show_alert(title, message, sound=True)
    
    @staticmethod
    def is_notification_supported() -> bool:
        """현재 플랫폼에서 알림이 지원되는지 확인"""
        if NOTIFICATION_AVAILABLE:
            return True
        elif platform.system() == "Windows":
            # Windows는 ctypes fallback 사용 가능
            return True
        else:
            # 다른 OS에서 plyer 없으면 콘솔 출력만
            return False


class AlertManager:
    """결과 표시 제외 관리"""
    
    def __init__(self, exclusion_days: int = 7):
        self.exclusion_days = exclusion_days
    
    def should_show_alert(self, drug_name: str, exclusion_list: List[str]) -> bool:
        """해당 약품에 대해 알림을 표시해야 하는지 확인 (단순 비교)"""
        # exclusion_list는 이미 약품명만 포함한 리스트
        return drug_name not in exclusion_list
    
    def create_exclusion_entry(self, drug_name: str, distributor: str) -> Dict:
        """제외 목록에 추가할 JSON 항목 생성"""
        from datetime import datetime
        
        return {
            "date": datetime.now().isoformat()[:19],
            "distributor": distributor,
            "drugName": drug_name,
            "isPinned": False
        }