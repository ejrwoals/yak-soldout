"""
도매상 레지스트리 — 모든 도매상 메타데이터의 단일 진실 공급원 (Single Source of Truth)

새 도매상 추가 시 이 파일에만 항목을 추가하면 됩니다.
"""

from scrapers.geoweb_scraper import GeowebScraper
from scrapers.baekje_scraper import BaekjeScraper
from scrapers.incheon_scraper import IncheonScraper
from scrapers.geopharm_scraper import GeoPharmScraper
from scrapers.boksan_scraper import BoksanScraper
from scrapers.upharmmall_scraper import UpharmMallScraper

# 도매상 등록 순서 = 검색 실행 순서 (지오영은 항상 첫 번째 — 보험코드 수집 역할)
DISTRIBUTOR_REGISTRY = {
    "geoweb": {
        "id": "geoweb",
        "name": "지오영",
        "korean_key": "지오영",       # info.txt 키 prefix: 지오영아이디, 지오영비밀번호, 지오영활성화
        "scraper_class": GeowebScraper,
        "default_enabled": True,
        "default_color": "#0d9488",
        "extra_params": {"region": "seoul"},
        "region_options": {
            "seoul": "서울, 경기, 인천",
            "yeongnam": "영남",
        },
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
        "extra_params": {"region": "daegu"},
        "region_options": {
            "daegu": "대구",
            "daejeon": "대전",
            "gwangju": "광주",
            "seoul": "서울",
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
    "upharmmall": {
        "id": "upharmmall",
        "name": "유팜몰",
        "korean_key": "유팜몰",
        "scraper_class": UpharmMallScraper,
        "default_enabled": False,
        "default_color": "#059669",
        "extra_params": {},
    },
}
