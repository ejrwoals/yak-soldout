"""
빌드 설정 관리 — build_config.json 기반 약국별 배포 커스터마이징

Fallback 규칙:
- build_config.json 없음 → 전체 도매상 표시 (개발 환경)
- distributors 키에 누락된 도매상 → 표시 (기본값 1)
- 명시적으로 0인 도매상만 숨김
- pharmacy_name 없음 → "for XXX" 텍스트 미표시
- primary_distributor 없음 → "geoweb" (기본값)
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


# 텍스트 검색(약품명→보험코드 수집)을 지원하는 도매상만 기준 도매상이 될 수 있음
_VALID_PRIMARY_DISTRIBUTORS = {"geoweb", "upharmmall"}


def get_primary_distributor() -> str:
    """기준 도매상 ID 반환. 미설정 또는 유효하지 않으면 'geoweb'."""
    primary = get_build_config().get("primary_distributor", "geoweb")
    if primary not in _VALID_PRIMARY_DISTRIBUTORS:
        return "geoweb"
    return primary


def get_visible_registry() -> Dict[str, Any]:
    """빌드 설정 기반으로 UI에 표시할 도매상만 필터링한 레지스트리 반환.

    primary 도매상이 항상 맨 앞에 오도록 정렬하여 반환한다.
    """
    from scrapers.registry import DISTRIBUTOR_REGISTRY

    primary_id = get_primary_distributor()
    dist_visibility = get_build_config().get("distributors", {})

    if not dist_visibility:
        # build_config.json 없거나 distributors 키 없음 → 전체 표시
        visible_ids = list(DISTRIBUTOR_REGISTRY.keys())
    else:
        visible_ids = [
            did for did in DISTRIBUTOR_REGISTRY
            if did == primary_id or dist_visibility.get(did, 1) != 0
        ]

    # primary 도매상이 맨 앞에 오도록 정렬
    if primary_id in visible_ids:
        visible_ids.remove(primary_id)
        visible_ids.insert(0, primary_id)

    return {did: DISTRIBUTOR_REGISTRY[did] for did in visible_ids}
