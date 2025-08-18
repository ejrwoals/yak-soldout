import platform
import subprocess
import sys
from typing import List, Dict
from models.drug_data import Drug


class CrossPlatformNotifier:
    """크로스 플랫폼 알림 시스템"""
    
    @staticmethod
    def show_alert(title: str, message: str, sound: bool = True):
        """플랫폼에 맞는 알림 표시"""
        system = platform.system()
        
        try:
            if system == "Windows":
                CrossPlatformNotifier._show_windows_alert(title, message, sound)
            elif system == "Darwin":  # macOS
                CrossPlatformNotifier._show_macos_alert(title, message, sound)
            else:  # Linux and others
                CrossPlatformNotifier._show_linux_alert(title, message)
        except Exception as e:
            # 알림 실패 시 콘솔에 출력
            print(f"알림 표시 실패: {e}")
            print(f"[{title}] {message}")
    
    @staticmethod
    def _show_windows_alert(title: str, message: str, sound: bool = True):
        """Windows 시스템 알림"""
        try:
            import ctypes
            # 메시지박스 표시 (0x40: 정보 아이콘, 0x1: OK 버튼)
            ctypes.windll.user32.MessageBoxW(0, message, title, 0x40 | 0x1)
            
            if sound:
                # 시스템 사운드 재생
                ctypes.windll.winmm.PlaySoundW("SystemAsterisk", 0x1)
        except Exception as e:
            print(f"Windows 알림 오류: {e}")
    
    @staticmethod
    def _show_macos_alert(title: str, message: str, sound: bool = True):
        """macOS 시스템 알림"""
        try:
            sound_option = 'sound name "Glass"' if sound else ''
            applescript = f'display notification "{message}" with title "{title}" {sound_option}'
            
            subprocess.run([
                "osascript", "-e", applescript
            ], check=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            print(f"macOS 알림 오류: {e}")
        except FileNotFoundError:
            print("osascript를 찾을 수 없습니다. macOS에서만 사용 가능합니다.")
    
    @staticmethod
    def _show_linux_alert(title: str, message: str):
        """Linux 시스템 알림"""
        try:
            subprocess.run([
                "notify-send", title, message
            ], check=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            print(f"Linux 알림 오류: {e}")
        except FileNotFoundError:
            print("notify-send를 찾을 수 없습니다. libnotify-bin 패키지를 설치해주세요.")
    
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
        system = platform.system()
        
        if system == "Windows":
            try:
                import ctypes
                return True
            except ImportError:
                return False
        elif system == "Darwin":
            try:
                result = subprocess.run(["which", "osascript"], 
                                      capture_output=True, text=True)
                return result.returncode == 0
            except Exception:
                return False
        else:  # Linux
            try:
                result = subprocess.run(["which", "notify-send"], 
                                      capture_output=True, text=True)
                return result.returncode == 0
            except Exception:
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