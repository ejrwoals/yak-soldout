"""
빌드 설정 관리 — build_config.json 기반 약국별 배포 커스터마이징

Fallback 규칙:
- build_config.json 없음 → 전체 도매상 표시 (개발 환경)
- distributors 키에 누락된 도매상 → 표시 (기본값 1)
- 명시적으로 0인 도매상만 숨김
- pharmacy_name 없음 → "for XXX" 텍스트 미표시
"""
import json
import os
import sys
from typing import Dict, Any, Optional

_cache: Optional[Dict[str, Any]] = None


def _resource_path(relative_path: str) -> str:
    """개발 및 PyInstaller 환경 모두에서 리소스의 절대 경로를 가져옵니다."""
    try:
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


def get_build_config() -> Dict[str, Any]:
    """build_config.json 로드 (캐시됨). 파일 없으면 빈 dict 반환."""
    global _cache
    if _cache is not None:
        return _cache
    try:
        with open(_resource_path("build_config.json"), "r", encoding="utf-8") as f:
            _cache = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        _cache = {}
    return _cache


def get_pharmacy_name() -> str:
    """약국 이름 반환. 미설정 시 빈 문자열."""
    return get_build_config().get("pharmacy_name", "")


def get_visible_registry() -> Dict[str, Any]:
    """빌드 설정 기반으로 UI에 표시할 도매상만 필터링한 레지스트리 반환."""
    from scrapers.registry import DISTRIBUTOR_REGISTRY

    dist_visibility = get_build_config().get("distributors", {})
    if not dist_visibility:
        # build_config.json 없거나 distributors 키 없음 → 전체 표시
        return dict(DISTRIBUTOR_REGISTRY)

    return {
        did: info for did, info in DISTRIBUTOR_REGISTRY.items()
        if dist_visibility.get(did, 1) != 0
    }
