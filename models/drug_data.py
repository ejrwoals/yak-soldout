from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class DistributorType(Enum):
    GEOWEB = "지오영"
    BAEKJE = "백제"
    INCHEON = "인천약품"
    GEOPHARM = "지오팜"
    BOKSAN = "복산"
    UPHARMMALL = "유팜몰"
    HMPMALL = "HMP몰"


@dataclass
class Drug:
    """약품 정보를 담는 데이터 클래스"""
    name: str
    insurance_code: str
    distributor: DistributorType
    main_stock: str
    incheon_stock: str = "-"
    notes: str = "-"
    company: str = ""
    unit: str = ""  # 규격 정보 (예: 100T, 500T)
    is_excluded_from_alert: bool = False

    def get_total_stock_int(self) -> int:
        """총 재고를 정수로 반환 (품절인 경우 0)"""
        try:
            main = 0 if self.main_stock in ['품절', '0', '-'] else int(self.main_stock.replace(',', ''))
            incheon = 0 if self.incheon_stock in ['품절', '0', '-'] else int(self.incheon_stock.replace(',', ''))
            return main + incheon
        except ValueError:
            return 0

    def has_stock(self) -> bool:
        """재고가 있는지 확인"""
        return self.get_total_stock_int() > 0



@dataclass
class SearchResult:
    """검색 결과를 담는 데이터 클래스"""
    timestamp: datetime
    found_drugs: List[Drug]
    soldout_drugs: List[Drug]
    alert_exclusions: List[str]
    search_duration: float = 0.0
    errors: List[str] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []

    def get_alert_drugs(self) -> List[Drug]:
        """알림이 필요한 약품들만 반환"""
        return [drug for drug in self.found_drugs if not drug.is_excluded_from_alert]

    def has_alerts(self) -> bool:
        """알림할 약품이 있는지 확인"""
        return len(self.get_alert_drugs()) > 0

    def to_dict(self) -> Dict[str, Any]:
        """JSON 저장을 위한 딕셔너리 변환"""
        return {
            'timestamp': self.timestamp.isoformat(),
            'found_drugs': [
                {
                    'name': drug.name,
                    'insurance_code': drug.insurance_code,
                    'distributor': drug.distributor.value,
                    'main_stock': drug.main_stock,
                    'incheon_stock': drug.incheon_stock,
                    'notes': drug.notes,
                    'company': drug.company,
                    'is_excluded_from_alert': drug.is_excluded_from_alert
                } for drug in self.found_drugs
            ],
            'soldout_drugs': [
                {
                    'name': drug.name,
                    'insurance_code': drug.insurance_code,
                    'distributor': drug.distributor.value,
                    'main_stock': drug.main_stock,
                    'incheon_stock': drug.incheon_stock,
                    'notes': drug.notes,
                    'company': drug.company,
                    'is_excluded_from_alert': drug.is_excluded_from_alert
                } for drug in self.soldout_drugs
            ],
            'alert_exclusions': self.alert_exclusions,
            'search_duration': self.search_duration,
            'errors': self.errors
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SearchResult':
        """딕셔너리에서 SearchResult 생성"""
        return cls(
            timestamp=datetime.fromisoformat(data['timestamp']),
            found_drugs=[
                Drug(
                    name=d['name'],
                    insurance_code=d['insurance_code'],
                    distributor=DistributorType(d['distributor']),
                    main_stock=d['main_stock'],
                    incheon_stock=d['incheon_stock'],
                    notes=d['notes'],
                    company=d['company'],
                    is_excluded_from_alert=d['is_excluded_from_alert']
                ) for d in data['found_drugs']
            ],
            soldout_drugs=[
                Drug(
                    name=d['name'],
                    insurance_code=d['insurance_code'],
                    distributor=DistributorType(d['distributor']),
                    main_stock=d['main_stock'],
                    incheon_stock=d['incheon_stock'],
                    notes=d['notes'],
                    company=d['company'],
                    is_excluded_from_alert=d['is_excluded_from_alert']
                ) for d in data['soldout_drugs']
            ],
            alert_exclusions=data['alert_exclusions'],
            search_duration=data.get('search_duration', 0.0),
            errors=data.get('errors', [])
        )


@dataclass
class DistributorCredentials:
    """도매상 인증 정보"""
    username: str
    password: str
    extra: Dict[str, str] = field(default_factory=dict)  # {"region": "01"} 등 추가 파라미터

    def is_valid(self) -> bool:
        return bool(self.username and self.password)


@dataclass
class AppConfig:
    """애플리케이션 설정"""
    distributor_credentials: Dict[str, DistributorCredentials]  # key: dist_id (e.g. "geoweb")
    repeat_interval_minutes: int = 30
    alert_exclusion_days: int = 7

    def has_credentials(self, dist_id: str) -> bool:
        """해당 도매상의 인증정보가 있는지 확인"""
        creds = self.distributor_credentials.get(dist_id)
        return creds is not None and creds.is_valid()

    def get_credentials(self, dist_id: str) -> Optional[DistributorCredentials]:
        """해당 도매상의 인증정보 반환"""
        return self.distributor_credentials.get(dist_id)

    # 지오영은 필수 도매상(보험코드 수집)이므로 하위 호환성 property 유지
    @property
    def geoweb_id(self) -> Optional[str]:
        creds = self.distributor_credentials.get('geoweb')
        return creds.username if creds else None

    @property
    def geoweb_password(self) -> Optional[str]:
        creds = self.distributor_credentials.get('geoweb')
        return creds.password if creds else None
