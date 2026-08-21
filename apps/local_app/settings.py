"""로컬 앱 설정 — 도매상 로그인 계정 (이 PC 안에만 보관).

자동주문 솔루션은 로컬 SQLite(품절약 서치앱 DB)를 쓰지 않으므로, 크롤링에 필요한
도매상 계정은 여기서 `local_app/.settings.json` 에 따로 보관한다.
**비밀번호는 Supabase(클라우드)로 올라가지 않는다** — 이 PC 밖으로 나가지 않는 값이다.

파일 형식:
    {"primary_distributor": "geoweb",
     "distributors": {"geoweb": {"username": "...", "password": "...", "region": "seoul"}}}

주의: 파일은 평문이다(레거시 SQLite `distributors` 테이블과 동일한 수준).
`.settings.json` 은 .gitignore 의 `*.json` 규칙으로 커밋되지 않는다.
"""

import json

from runtime_paths import DATA_DIR

SETTINGS_FILE = DATA_DIR / ".settings.json"

# 텍스트/보험코드 검색을 지원해 기준 도매상이 될 수 있는 도매상
# (레거시 models/build_config.py 의 _VALID_PRIMARY_DISTRIBUTORS 와 동일)
PRIMARY_CHOICES = ("geoweb", "upharmmall")
DEFAULT_PRIMARY = "geoweb"


def _registry():
    """scrapers 레지스트리 지연 임포트 (playwright 로딩을 필요한 순간까지 미룸)."""
    import repo_path  # noqa: F401  — 리포지토리 루트를 sys.path 에 올린다

    from scrapers.registry import DISTRIBUTOR_REGISTRY

    return DISTRIBUTOR_REGISTRY


def load() -> dict:
    """설정 전체 반환. 파일이 없거나 깨졌으면 기본값."""
    try:
        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    data.setdefault("primary_distributor", DEFAULT_PRIMARY)
    data.setdefault("distributors", {})
    if data["primary_distributor"] not in PRIMARY_CHOICES:
        data["primary_distributor"] = DEFAULT_PRIMARY
    return data


def _save(data: dict) -> None:
    SETTINGS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def get_primary() -> dict:
    """기준 도매상 자격증명 {dist_key, name, username, password, region}."""
    data = load()
    key = data["primary_distributor"]
    entry = data["distributors"].get(key) or {}
    return {
        "dist_key": key,
        "name": _registry()[key]["name"],
        "username": (entry.get("username") or "").strip(),
        "password": (entry.get("password") or "").strip(),
        "region": (entry.get("region") or "").strip(),
    }


def distributor_choices() -> list[dict]:
    """주문 도매상 선택 드롭다운용 — 레지스트리의 모든 도매상 {key, name, color}."""
    reg = _registry()
    return [
        {"key": k, "name": v["name"], "color": v.get("default_color", "")}
        for k, v in reg.items()
    ]


def describe() -> dict:
    """설정 화면용 — 비밀번호는 내려보내지 않고 설정 여부만 알린다."""
    data = load()
    key = data["primary_distributor"]
    entry = data["distributors"].get(key) or {}
    registry = _registry()
    choices = [
        {
            "key": k,
            "name": registry[k]["name"],
            "region_options": registry[k].get("region_options") or {},
            "default_region": (registry[k].get("extra_params") or {}).get("region", ""),
        }
        for k in PRIMARY_CHOICES
    ]
    return {
        "primary": key,
        "choices": choices,
        "username": entry.get("username") or "",
        "has_password": bool((entry.get("password") or "").strip()),
        "region": entry.get("region") or "",
    }


def save_distributor(dist_key: str, username: str, password: str | None, region: str = "") -> dict:
    """기준 도매상과 그 계정을 저장. password 가 None/빈 값이면 기존 비밀번호를 유지한다."""
    if dist_key not in PRIMARY_CHOICES:
        raise ValueError(f"기준 도매상으로 쓸 수 없는 도매상입니다: {dist_key!r}")

    data = load()
    entry = dict(data["distributors"].get(dist_key) or {})
    entry["username"] = (username or "").strip()
    if (password or "").strip():
        entry["password"] = password.strip()
    entry["region"] = (region or "").strip()

    data["primary_distributor"] = dist_key
    data["distributors"][dist_key] = entry
    _save(data)
    return describe()
