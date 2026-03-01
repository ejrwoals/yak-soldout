import json
from pathlib import Path
from typing import Dict, Any
from .drug_data import AppConfig, DistributorCredentials

# 순환 임포트 방지를 위해 함수 내부에서 registry 임포트
def _get_registry():
    from scrapers.registry import DISTRIBUTOR_REGISTRY
    return DISTRIBUTOR_REGISTRY

# 마이그레이션 전용: info.txt의 한국어 suffix → JSON 키 매핑
_MIGRATION_EXTRA_PARAM_KO = {
    "region": "지역",
}


class ConfigManager:
    """설정 파일 관리 클래스 (config.json 기반)"""

    CONFIG_FILENAME = "config.json"
    LEGACY_FILENAME = "info.txt"

    def __init__(self, config_file: str = CONFIG_FILENAME):
        self.app_directory = Path(__file__).parent.parent
        self.config_path = self.app_directory / config_file
        self.legacy_path = self.app_directory / self.LEGACY_FILENAME

        # info.txt → config.json 자동 마이그레이션
        if not self.config_path.exists() and self.legacy_path.exists():
            self._migrate_from_info_txt()

    def _migrate_from_info_txt(self):
        """info.txt에서 config.json으로 일회성 마이그레이션"""
        registry = _get_registry()

        # 기존 info.txt 파싱 (인코딩 자동 감지)
        with open(self.legacy_path, 'rb') as f:
            raw_bytes = f.read()
        try:
            import chardet
            encoding = chardet.detect(raw_bytes)['encoding'] or 'utf-8'
        except ImportError:
            encoding = 'utf-8'

        raw: Dict[str, str] = {}
        for line in raw_bytes.decode(encoding).splitlines():
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            raw[key.strip()] = value.strip()

        # 새 JSON 구조 빌드
        distributors: Dict[str, Any] = {}
        for dist_id, dist_info in registry.items():
            k = dist_info['korean_key']
            default_enabled = dist_info['default_enabled']

            entry: Dict[str, Any] = {
                "enabled": raw.get(f'{k}활성화', str(default_enabled).lower()).lower() == 'true',
                "username": raw.get(f'{k}아이디', ''),
                "password": raw.get(f'{k}비밀번호', ''),
            }

            # extra_params (region 등)
            for param_key, param_default in dist_info.get('extra_params', {}).items():
                ko_suffix = _MIGRATION_EXTRA_PARAM_KO.get(param_key, param_key)
                entry[param_key] = raw.get(f'{k}{ko_suffix}', param_default)

            distributors[dist_id] = entry

        config_data = {
            "distributors": distributors,
            "monitoring": {
                "repeat_interval_minutes": int(raw.get('repeat_interval_minutes',
                    raw.get('반복실행간격(분)', '30'))),
                "alert_exclusion_days": int(raw.get('alert_exclusion_days',
                    raw.get('재고발견이후알림제외기간(일)', '7'))),
            },
        }

        # config.json 저장
        self._write_config_json(config_data)

        # info.txt 백업
        backup_path = self.app_directory / "info.txt.bak"
        self.legacy_path.rename(backup_path)
        print(f"마이그레이션 완료: {self.LEGACY_FILENAME} → {self.CONFIG_FILENAME}")

    def _read_config_json(self) -> Dict[str, Any]:
        """config.json 읽기"""
        if not self.config_path.exists():
            raise FileNotFoundError(f"설정 파일을 찾을 수 없습니다: {self.config_path}")
        with open(self.config_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _write_config_json(self, data: Dict[str, Any]):
        """config.json 쓰기"""
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def get_raw_config(self) -> Dict[str, Any]:
        """config.json의 원시 데이터 반환 (API 엔드포인트용)"""
        try:
            return self._read_config_json()
        except FileNotFoundError:
            return {"distributors": {}, "monitoring": {}}

    def save_raw_config(self, data: Dict[str, Any]):
        """config.json에 원시 데이터 저장 (API 엔드포인트용)"""
        self._write_config_json(data)

    def load_config(self) -> AppConfig:
        """config.json에서 설정 로드"""
        data = self._read_config_json()
        registry = _get_registry()

        distributor_credentials: Dict[str, DistributorCredentials] = {}
        distributors = data.get('distributors', {})

        for dist_id, dist_info in registry.items():
            dist_data = distributors.get(dist_id, {})
            username = dist_data.get('username', '')
            password = dist_data.get('password', '')

            # 빈 값(길이 1 이하) 제거 — geoweb 제외
            if dist_id != 'geoweb':
                if len(username) <= 1:
                    username = ''
                if len(password) <= 1:
                    password = ''

            # extra_params (region 등)
            extra: Dict[str, str] = {}
            for param_key, param_default in dist_info.get('extra_params', {}).items():
                extra[param_key] = dist_data.get(param_key, param_default)

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

        monitoring = data.get('monitoring', {})
        return AppConfig(
            distributor_credentials=distributor_credentials,
            repeat_interval_minutes=monitoring.get('repeat_interval_minutes', 30),
            alert_exclusion_days=monitoring.get('alert_exclusion_days', 7),
        )

    def get_app_directory(self) -> Path:
        """앱 실행 디렉토리 반환"""
        return self.app_directory

    def get_data_directory(self) -> Path:
        """데이터 디렉토리 반환"""
        data_dir = self.app_directory / "data"
        data_dir.mkdir(exist_ok=True)
        return data_dir
