import platform
import subprocess
import sys
from typing import List
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
    """알림 제외 관리"""
    
    def __init__(self, exclusion_days: int = 7):
        self.exclusion_days = exclusion_days
    
    def should_show_alert(self, drug_name: str, exclusion_list: List[str]) -> bool:
        """해당 약품에 대해 알림을 표시해야 하는지 확인"""
        from datetime import datetime, timedelta
        
        current_time = datetime.now()
        
        # 시간 제한 확인 (오후 4-6시에만 알림 제외 목록 정리)
        if 16 <= current_time.hour < 18:
            # 알림 제외 목록에서 오래된 항목 확인
            for exclusion in exclusion_list:
                if '@' in exclusion:
                    try:
                        date_part = exclusion.split('@')[0].strip()
                        drug_part = exclusion.split('@')[1].strip()
                        
                        if drug_part == drug_name:
                            # 날짜 파싱
                            date_str = date_part.split('일')[0] + '일'
                            exclusion_date = datetime.strptime(date_str, '%Y년 %m월 %d일')
                            
                            # 제외 기간 확인
                            days_diff = (current_time - exclusion_date).days
                            if days_diff <= self.exclusion_days:
                                return False  # 알림 제외
                    except Exception as e:
                        print(f"알림 제외 날짜 파싱 오류: {e}")
                        continue
        else:
            # 일반 시간대에는 단순히 이름만 확인
            for exclusion in exclusion_list:
                if '@' in exclusion:
                    drug_part = exclusion.split('@')[1].strip()
                    if drug_part == drug_name:
                        return False  # 알림 제외
        
        return True  # 알림 표시
    
    def add_to_exclusion_list(self, found_drugs: List[Drug], 
                            existing_exclusions: List[str]) -> List[str]:
        """발견된 약품을 알림 제외 목록에 추가"""
        from datetime import datetime
        
        current_time = datetime.now()
        timestamp = current_time.strftime('%Y년 %m월 %d일 %X')
        
        new_exclusions = []
        for drug in found_drugs:
            if not drug.is_excluded_from_alert:
                exclusion_entry = f"{timestamp} {drug.distributor.value} @ {drug.name}"
                new_exclusions.append(exclusion_entry)
        
        # 기존 제외 목록과 합집합
        all_exclusions = set(existing_exclusions).union(set(new_exclusions))
        return sorted(list(all_exclusions))