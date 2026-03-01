"""
도매상 레지스트리 — 모든 도매상 메타데이터의 단일 진실 공급원 (Single Source of Truth)

새 도매상 추가 시 이 파일에만 항목을 추가하면 됩니다.
"""

from scrapers.geoweb_scraper import GeowebScraper
from scrapers.baekje_scraper import BaekjeScraper
from scrapers.incheon_scraper import IncheonScraper
from scrapers.geopharm_scraper import GeoPharmScraper
from scrapers.boksan_scraper import BoksanScraper

# 도매상 등록 순서 = 검색 실행 순서 (지오영은 항상 첫 번째 — 보험코드 수집 역할)
DISTRIBUTOR_REGISTRY = {
    "geoweb": {
        "id": "geoweb",
        "name": "지오영",
        "korean_key": "지오영",       # info.txt 키 prefix: 지오영아이디, 지오영비밀번호, 지오영활성화
        "scraper_class": GeowebScraper,
        "default_enabled": True,
        "default_color": "#0d9488",
        "extra_params": {},           # 추가 로그인 파라미터 schema: { param_key: default_value }
    },
    "baekje": {
        "id": "baekje",
        "name": "백제약품",
        "korean_key": "백제",
        "scraper_class": BaekjeScraper,
        "default_enabled": False,
        "default_color": "#3b82f6",
        "extra_params": {},
    },
    "incheon": {
        "id": "incheon",
        "name": "인천약품",
        "korean_key": "인천약품",
        "scraper_class": IncheonScraper,
        "default_enabled": False,
        "default_color": "#d97706",
        "extra_params": {},
    },
    "geopharm": {
        "id": "geopharm",
        "name": "지오팜",
        "korean_key": "지오팜",
        "scraper_class": GeoPharmScraper,
        "default_enabled": False,
        "default_color": "#e11d48",
        "extra_params": {"region": "01"},   # region 파라미터, info.txt: 지오팜지역
        "region_options": {                  # 지오팜 전용: 지역 선택 옵션
            "01": "대구",
            "02": "대전",
            "03": "광주",
            "04": "서울",
        },
    },
    "boksan": {
        "id": "boksan",
        "name": "복산",
        "korean_key": "복산",
        "scraper_class": BoksanScraper,
        "default_enabled": False,
        "default_color": "#7c3aed",
        "extra_params": {},
    },
}
