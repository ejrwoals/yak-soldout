import os
import chardet
from pathlib import Path
from typing import Optional
from .drug_data import AppConfig


class ConfigManager:
    """설정 파일 관리 클래스"""
    
    def __init__(self, config_file: str = "info.txt"):
        self.config_file = config_file
        self.app_directory = Path(__file__).parent.parent
        self.config_path = self.app_directory / config_file
    
    def _detect_encoding(self, file_path: Path) -> str:
        """파일 인코딩 자동 감지"""
        with open(file_path, 'rb') as file:
            raw_data = file.read()
            result = chardet.detect(raw_data)
            return result['encoding'] or 'utf-8'
    
    def load_config(self) -> AppConfig:
        """info.txt 파일에서 설정 로드"""
        if not self.config_path.exists():
            raise FileNotFoundError(f"설정 파일을 찾을 수 없습니다: {self.config_path}")
        
        encoding = self._detect_encoding(self.config_path)
        
        # 기본값 설정
        config_data = {
            'geoweb_id': None,
            'geoweb_password': None,
            'baekje_id': None,
            'baekje_password': None,
            'incheon_id': None,
            'incheon_password': None,
            'repeat_interval_minutes': 30,
            'alert_exclusion_days': 7
        }
        
        try:
            with open(self.config_path, 'r', encoding=encoding) as file:
                lines = file.readlines()
                
                for line in lines:
                    line = line.strip()
                    if not line or '=' not in line:
                        continue
                        
                    try:
                        key, value = line.split('=', 1)
                        key = key.strip()
                        value = value.strip()
                        
                        # Legacy 한국어 키와 새로운 영어 키 모두 지원
                        if key in ['지오영아이디', 'geoweb_id']:
                            config_data['geoweb_id'] = value
                        elif key in ['지오영비밀번호', 'geoweb_password']:
                            config_data['geoweb_password'] = value
                        elif key in ['백제아이디', 'baekje_id']:
                            if len(value) > 1:  # 빈 값이 아닌 경우만
                                config_data['baekje_id'] = value
                        elif key in ['백제비밀번호', 'baekje_password']:
                            if len(value) > 1:  # 빈 값이 아닌 경우만
                                config_data['baekje_password'] = value
                        elif key in ['인천약품아이디', 'incheon_id']:
                            if len(value) > 1:  # 빈 값이 아닌 경우만
                                config_data['incheon_id'] = value
                        elif key in ['인천약품비밀번호', 'incheon_password']:
                            if len(value) > 1:  # 빈 값이 아닌 경우만
                                config_data['incheon_password'] = value
                        elif key in ['반복실행간격(분)', 'repeat_interval_minutes']:
                            config_data['repeat_interval_minutes'] = int(value)
                        elif key in ['재고발견이후알림제외기간(일)', 'alert_exclusion_days']:
                            try:
                                config_data['alert_exclusion_days'] = int(value)
                            except ValueError:
                                print("info.txt / '재고발견이후알림제외기간' 설정 오류")
                                config_data['alert_exclusion_days'] = 0
                    
                    except ValueError as e:
                        print(f"설정 파일 파싱 오류 (line: {line}): {e}")
                        continue
        
        except Exception as e:
            raise Exception(f"설정 파일 읽기 오류: {e}")
        
        # 필수 값 검증
        if not config_data['geoweb_id'] or not config_data['geoweb_password']:
            raise ValueError("지오영 아이디와 비밀번호는 필수입니다")
        
        return AppConfig(
            geoweb_id=config_data['geoweb_id'],
            geoweb_password=config_data['geoweb_password'],
            baekje_id=config_data['baekje_id'],
            baekje_password=config_data['baekje_password'],
            incheon_id=config_data['incheon_id'],
            incheon_password=config_data['incheon_password'],
            repeat_interval_minutes=config_data['repeat_interval_minutes'],
            alert_exclusion_days=config_data['alert_exclusion_days']
        )
    
    def get_app_directory(self) -> Path:
        """앱 실행 디렉토리 반환"""
        return self.app_directory
    
    def get_data_directory(self) -> Path:
        """데이터 디렉토리 반환"""
        data_dir = self.app_directory / "data"
        data_dir.mkdir(exist_ok=True)
        return data_dir