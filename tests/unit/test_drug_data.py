import pytest
from datetime import datetime
from models.drug_data import Drug, DistributorType, PharmacyUsage, SearchResult, AppConfig


class TestDrug:
    """Drug 클래스 테스트"""
    
    def test_drug_creation(self):
        """Drug 객체 생성 테스트"""
        drug = Drug(
            name="타이레놀정",
            insurance_code="123456789",
            distributor=DistributorType.GEOWEB,
            main_stock="100",
            incheon_stock="50",
            notes="정상",
            company="한국얀센"
        )
        
        assert drug.name == "타이레놀정"
        assert drug.insurance_code == "123456789"
        assert drug.distributor == DistributorType.GEOWEB
        assert drug.main_stock == "100"
        assert drug.incheon_stock == "50"
        assert drug.notes == "정상"
        assert drug.company == "한국얀센"
        assert drug.is_excluded_from_alert == False
    
    def test_get_total_stock_int(self):
        """총 재고 계산 테스트"""
        # 정상적인 재고
        drug1 = Drug("약품1", "123", DistributorType.GEOWEB, "100", "50")
        assert drug1.get_total_stock_int() == 150
        
        # 콤마가 포함된 재고
        drug2 = Drug("약품2", "456", DistributorType.GEOWEB, "1,000", "500")
        assert drug2.get_total_stock_int() == 1500
        
        # 품절인 경우
        drug3 = Drug("약품3", "789", DistributorType.GEOWEB, "품절", "0")
        assert drug3.get_total_stock_int() == 0
        
        # 인천센터가 '-'인 경우
        drug4 = Drug("약품4", "101", DistributorType.GEOWEB, "200", "-")
        assert drug4.get_total_stock_int() == 200
    
    def test_has_stock(self):
        """재고 여부 확인 테스트"""
        # 재고 있음
        drug1 = Drug("약품1", "123", DistributorType.GEOWEB, "100", "50")
        assert drug1.has_stock() == True
        
        # 재고 없음
        drug2 = Drug("약품2", "456", DistributorType.GEOWEB, "품절", "0")
        assert drug2.has_stock() == False
        
        # 메인센터만 재고 있음
        drug3 = Drug("약품3", "789", DistributorType.GEOWEB, "100", "품절")
        assert drug3.has_stock() == True


class TestPharmacyUsage:
    """PharmacyUsage 클래스 테스트"""
    
    def test_pharmacy_usage_creation(self):
        """PharmacyUsage 객체 생성 테스트"""
        monthly_data = {
            '1월': 100, '2월': 120, '3월': 80, '4월': 90,
            '5월': 110, '6월': 0, '7월': 0, '8월': 0,
            '9월': 0, '10월': 0, '11월': 0, '12월': 0
        }
        
        usage = PharmacyUsage(
            insurance_code="123456789",
            drug_name="타이레놀정",
            current_stock=500,
            monthly_usage=monthly_data
        )
        
        assert usage.insurance_code == "123456789"
        assert usage.drug_name == "타이레놀정"
        assert usage.current_stock == 500
        assert usage.monthly_usage == monthly_data
    
    def test_monthly_average_calculation(self):
        """월평균 계산 테스트"""
        monthly_data = {'1월': 100, '2월': 200, '3월': 0, '4월': 300}
        
        usage = PharmacyUsage(
            insurance_code="123",
            drug_name="테스트약",
            current_stock=600,
            monthly_usage=monthly_data
        )
        
        # 0이 아닌 값들의 평균: (100 + 200 + 300) / 3 = 200
        assert usage.monthly_average == 200.0
        assert usage.stock_to_monthly_ratio == 3.0  # 600 / 200
    
    def test_empty_usage_data(self):
        """사용량 데이터가 없는 경우 테스트"""
        usage = PharmacyUsage(
            insurance_code="123",
            drug_name="테스트약",
            current_stock=100,
            monthly_usage={}
        )
        
        assert usage.monthly_average == 0.0
        assert usage.stock_to_monthly_ratio == float('inf')


class TestSearchResult:
    """SearchResult 클래스 테스트"""
    
    def test_search_result_creation(self):
        """SearchResult 객체 생성 테스트"""
        drug1 = Drug("약품1", "123", DistributorType.GEOWEB, "100", "50")
        drug2 = Drug("약품2", "456", DistributorType.BAEKJE, "품절", "0")
        
        result = SearchResult(
            timestamp=datetime.now(),
            found_drugs=[drug1],
            soldout_drugs=[drug2],
            alert_exclusions=["2024년 12월 15일 지오영 @ 약품3"],
            search_duration=120.5,
            errors=["검색 오류"]
        )
        
        assert len(result.found_drugs) == 1
        assert len(result.soldout_drugs) == 1
        assert len(result.alert_exclusions) == 1
        assert result.search_duration == 120.5
        assert len(result.errors) == 1
    
    def test_get_alert_drugs(self):
        """알림 대상 약품 필터링 테스트"""
        drug1 = Drug("약품1", "123", DistributorType.GEOWEB, "100", "50")
        drug1.is_excluded_from_alert = False
        
        drug2 = Drug("약품2", "456", DistributorType.GEOWEB, "200", "0")
        drug2.is_excluded_from_alert = True
        
        result = SearchResult(
            timestamp=datetime.now(),
            found_drugs=[drug1, drug2],
            soldout_drugs=[],
            alert_exclusions=[]
        )
        
        alert_drugs = result.get_alert_drugs()
        assert len(alert_drugs) == 1
        assert alert_drugs[0].name == "약품1"
    
    def test_has_alerts(self):
        """알림 여부 확인 테스트"""
        drug1 = Drug("약품1", "123", DistributorType.GEOWEB, "100", "50")
        drug1.is_excluded_from_alert = False
        
        result = SearchResult(
            timestamp=datetime.now(),
            found_drugs=[drug1],
            soldout_drugs=[],
            alert_exclusions=[]
        )
        
        assert result.has_alerts() == True
        
        # 알림 제외된 경우
        drug1.is_excluded_from_alert = True
        assert result.has_alerts() == False
    
    def test_to_dict_and_from_dict(self):
        """딕셔너리 변환 테스트"""
        drug = Drug("약품1", "123", DistributorType.GEOWEB, "100", "50", "정상", "제약회사")
        timestamp = datetime.now()
        
        original_result = SearchResult(
            timestamp=timestamp,
            found_drugs=[drug],
            soldout_drugs=[],
            alert_exclusions=["테스트 제외"],
            search_duration=60.0,
            errors=["테스트 오류"]
        )
        
        # 딕셔너리로 변환
        data = original_result.to_dict()
        
        # 딕셔너리에서 다시 객체 생성
        restored_result = SearchResult.from_dict(data)
        
        assert restored_result.timestamp.replace(microsecond=0) == timestamp.replace(microsecond=0)
        assert len(restored_result.found_drugs) == 1
        assert restored_result.found_drugs[0].name == "약품1"
        assert restored_result.found_drugs[0].distributor == DistributorType.GEOWEB
        assert restored_result.search_duration == 60.0
        assert restored_result.errors == ["테스트 오류"]


class TestAppConfig:
    """AppConfig 클래스 테스트"""
    
    def test_app_config_creation(self):
        """AppConfig 객체 생성 테스트"""
        config = AppConfig(
            geoweb_id="test_id",
            geoweb_password="test_pass",
            baekje_id="baekje_id",
            baekje_password="baekje_pass",
            repeat_interval_minutes=30,
            alert_exclusion_days=7
        )
        
        assert config.geoweb_id == "test_id"
        assert config.geoweb_password == "test_pass"
        assert config.baekje_id == "baekje_id"
        assert config.baekje_password == "baekje_pass"
        assert config.repeat_interval_minutes == 30
        assert config.alert_exclusion_days == 7
    
    def test_has_baekje_credentials(self):
        """백제 인증정보 여부 확인 테스트"""
        # 백제 인증정보 있음
        config1 = AppConfig(
            geoweb_id="test_id",
            geoweb_password="test_pass",
            baekje_id="baekje_id",
            baekje_password="baekje_pass"
        )
        assert config1.has_baekje_credentials() == True
        
        # 백제 인증정보 없음
        config2 = AppConfig(
            geoweb_id="test_id",
            geoweb_password="test_pass"
        )
        assert config2.has_baekje_credentials() == False
        
        # 백제 ID만 있는 경우
        config3 = AppConfig(
            geoweb_id="test_id",
            geoweb_password="test_pass",
            baekje_id="baekje_id"
        )
        assert config3.has_baekje_credentials() == False


class TestDistributorType:
    """DistributorType Enum 테스트"""
    
    def test_distributor_type_values(self):
        """DistributorType 값 테스트"""
        assert DistributorType.GEOWEB.value == "지오영"
        assert DistributorType.BAEKJE.value == "백제"
    
    def test_distributor_type_enum_behavior(self):
        """Enum 동작 테스트"""
        assert DistributorType.GEOWEB != DistributorType.BAEKJE
        assert str(DistributorType.GEOWEB.value) == "지오영"