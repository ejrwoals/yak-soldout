import json
from pathlib import Path
from typing import Dict, Any
from scrapers.drug_data import AppConfig, DistributorCredentials

import db

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

    # ------------------------------------------------------------------
    # distributors: DB(distributors 테이블) / monitoring: config.json
    # (SQLite 마이그레이션 — 자격증명·활성화·색상·지역은 DB로 이전)
    # ------------------------------------------------------------------
    def _read_monitoring(self) -> Dict[str, Any]:
        try:
            return self._read_config_json().get('monitoring', {})
        except FileNotFoundError:
            return {}

    def _write_monitoring(self, monitoring: Dict[str, Any]):
        """config.json은 monitoring만 보관 (distributors는 DB로 이전)."""
        try:
            existing = self._read_config_json()
        except FileNotFoundError:
            existing = {}
        existing['monitoring'] = monitoring
        existing.pop('distributors', None)  # DB로 이전됨 — 파일에서 제거
        self._write_config_json(existing)

    def _read_distributors_from_db(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        for r in db.query_all(
            "SELECT dist_key, enabled, username, password, color, region FROM distributors"
        ):
            entry: Dict[str, Any] = {
                "enabled": bool(r["enabled"]),
                "username": r["username"] or "",
                "password": r["password"] or "",
            }
            # color/region은 값이 있을 때만 포함 (없으면 라우트가 레지스트리 기본값 사용)
            if r["color"] is not None:
                entry["color"] = r["color"]
            if r["region"] is not None:
                entry["region"] = r["region"]
            result[r["dist_key"]] = entry
        return result

    def _save_distributors_to_db(self, distributors: Dict[str, Any]):
        with db.transaction() as conn:
            for dist_key, d in (distributors or {}).items():
                if not isinstance(d, dict):
                    continue
                conn.execute(
                    """
                    INSERT INTO distributors (dist_key, enabled, username, password, color, region)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(dist_key) DO UPDATE SET
                        enabled  = excluded.enabled,
                        username = excluded.username,
                        password = excluded.password,
                        color    = excluded.color,
                        region   = excluded.region
                    """,
                    (
                        dist_key,
                        1 if d.get('enabled', True) else 0,
                        d.get('username', ''),
                        d.get('password', ''),
                        d.get('color'),
                        d.get('region'),
                    ),
                )

    def get_raw_config(self) -> Dict[str, Any]:
        """원시 설정 반환 (API 엔드포인트용). distributors=DB, monitoring=config.json."""
        return {
            "distributors": self._read_distributors_from_db(),
            "monitoring": self._read_monitoring(),
        }

    def save_raw_config(self, data: Dict[str, Any]):
        """원시 설정 저장 (API 엔드포인트용). distributors→DB, monitoring→config.json."""
        self._save_distributors_to_db(data.get('distributors', {}))
        self._write_monitoring(data.get('monitoring', {}))

    def load_config(self) -> AppConfig:
        """설정 로드 (distributors=DB, monitoring=config.json)"""
        registry = _get_registry()

        distributor_credentials: Dict[str, DistributorCredentials] = {}
        distributors = self._read_distributors_from_db()

        for dist_id, dist_info in registry.items():
            dist_data = distributors.get(dist_id, {})
            username = dist_data.get('username', '')
            password = dist_data.get('password', '')

            # 공백만 입력된 경우 빈 값으로 처리
            username = username.strip()
            password = password.strip()

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

        # 필수 값 검증 (기준 도매상)
        from models.build_config import get_primary_distributor
        primary_id = get_primary_distributor()
        primary_name = registry.get(primary_id, {}).get('name', primary_id)
        primary_creds = distributor_credentials.get(primary_id)
        if not primary_creds or not primary_creds.is_valid():
            raise ValueError(f"{primary_name} 아이디와 비밀번호는 필수입니다")

        monitoring = self._read_monitoring()
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
