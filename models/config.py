import os
import chardet
from pathlib import Path
from typing import Optional, Dict
from .drug_data import AppConfig, DistributorCredentials

# 순환 임포트 방지를 위해 함수 내부에서 registry 임포트
def _get_registry():
    from scrapers.registry import DISTRIBUTOR_REGISTRY
    return DISTRIBUTOR_REGISTRY

# extra_params 파라미터 키 → 한국어 suffix 매핑
# 새 extra param 추가 시 여기에 추가
_EXTRA_PARAM_KO_SUFFIX = {
    "region": "지역",
}


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

    def _read_raw_config(self) -> Dict[str, str]:
        """info.txt 파일의 모든 key=value 쌍을 그대로 읽어 dict 반환"""
        if not self.config_path.exists():
            raise FileNotFoundError(f"설정 파일을 찾을 수 없습니다: {self.config_path}")

        encoding = self._detect_encoding(self.config_path)
        raw: Dict[str, str] = {}

        try:
            with open(self.config_path, 'r', encoding=encoding) as file:
                for line in file:
                    line = line.strip()
                    if not line or '=' not in line:
                        continue
                    try:
                        key, value = line.split('=', 1)
                        raw[key.strip()] = value.strip()
                    except ValueError as e:
                        print(f"설정 파일 파싱 오류 (line: {line}): {e}")
        except Exception as e:
            raise Exception(f"설정 파일 읽기 오류: {e}")

        return raw

    def load_config(self) -> AppConfig:
        """info.txt 파일에서 설정 로드 (레지스트리 기반 동적 파싱)"""
        raw = self._read_raw_config()
        registry = _get_registry()

        distributor_credentials: Dict[str, DistributorCredentials] = {}

        for dist_id, dist_info in registry.items():
            k = dist_info['korean_key']

            # 한국어 키 우선, 영어 키 fallback
            username = raw.get(f'{k}아이디') or raw.get(f'{dist_id}_id', '')
            password = raw.get(f'{k}비밀번호') or raw.get(f'{dist_id}_password', '')

            # 빈 값(길이 1 이하) 제거 — geoweb 제외
            if dist_id != 'geoweb':
                if len(username) <= 1:
                    username = ''
                if len(password) <= 1:
                    password = ''

            # extra_params 파싱 (region 등)
            extra: Dict[str, str] = {}
            for param_key, param_default in dist_info.get('extra_params', {}).items():
                ko_suffix = _EXTRA_PARAM_KO_SUFFIX.get(param_key, param_key)
                value = (raw.get(f'{k}{ko_suffix}')
                         or raw.get(f'{dist_id}_{param_key}')
                         or param_default)
                extra[param_key] = value

            if username or password:
                distributor_credentials[dist_id] = DistributorCredentials(
                    username=username,
                    password=password,
                    extra=extra,
                )

        # 필수 값 검증 (지오영)
        geoweb_creds = distributor_credentials.get('geoweb')
        if not geoweb_creds or not geoweb_creds.is_valid():
            raise ValueError("지오영 아이디와 비밀번호는 필수입니다")

        # 반복 간격 / 알림 제외 기간
        try:
            repeat_interval = int(raw.get('반복실행간격(분)') or raw.get('repeat_interval_minutes', 30))
        except ValueError:
            repeat_interval = 30

        try:
            alert_exclusion_days = int(raw.get('재고발견이후알림제외기간(일)') or raw.get('alert_exclusion_days', 7))
        except ValueError:
            print("info.txt / '재고발견이후알림제외기간' 설정 오류")
            alert_exclusion_days = 0

        return AppConfig(
            distributor_credentials=distributor_credentials,
            repeat_interval_minutes=repeat_interval,
            alert_exclusion_days=alert_exclusion_days,
        )
    
    def get_app_directory(self) -> Path:
        """앱 실행 디렉토리 반환"""
        return self.app_directory
    
    def get_data_directory(self) -> Path:
        """데이터 디렉토리 반환"""
        data_dir = self.app_directory / "data"
        data_dir.mkdir(exist_ok=True)
        return data_dir