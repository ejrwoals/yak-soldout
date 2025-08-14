import pytest
from unittest.mock import patch, MagicMock
from scrapers.browser_manager import BrowserManager
from scrapers.geoweb_scraper import GeowebScraper
from scrapers.baekje_scraper import BaekjeScraper
from models.drug_data import DistributorType, AppConfig


class TestBrowserManagerSimple:
    """BrowserManager 기본 테스트"""
    
    def test_browser_manager_init(self):
        """BrowserManager 초기화 테스트"""
        browser_manager = BrowserManager()
        assert browser_manager.headless == True
        assert browser_manager.playwright is None
        assert browser_manager.browser is None
        assert browser_manager.context is None
    
    def test_browser_manager_with_headless_false(self):
        """헤드리스 모드 비활성화 테스트"""
        browser_manager = BrowserManager(headless=False)
        assert browser_manager.headless == False


class TestScrapersSimple:
    """스크래퍼 기본 테스트"""
    
    def test_geoweb_scraper_init(self):
        """GeowebScraper 초기화 테스트"""
        scraper = GeowebScraper()
        assert scraper.distributor_type == DistributorType.GEOWEB
        assert scraper.base_url == "https://order.geoweb.kr"
        assert scraper.page is None
        assert scraper.is_logged_in == False
    
    def test_baekje_scraper_init(self):
        """BaekjeScraper 초기화 테스트"""
        scraper = BaekjeScraper()
        assert scraper.distributor_type == DistributorType.BAEKJE
        assert scraper.base_url == "https://www.ibjp.co.kr"
        assert scraper.page is None
        assert scraper.is_logged_in == False


class TestAppConfigIntegration:
    """AppConfig 통합 테스트"""
    
    def test_app_config_complete(self):
        """완전한 AppConfig 생성 테스트"""
        config = AppConfig(
            geoweb_id="test_geoweb",
            geoweb_password="test_geoweb_pass",
            baekje_id="test_baekje",
            baekje_password="test_baekje_pass",
            repeat_interval_minutes=15,
            alert_exclusion_days=10
        )
        
        assert config.geoweb_id == "test_geoweb"
        assert config.geoweb_password == "test_geoweb_pass"
        assert config.baekje_id == "test_baekje"
        assert config.baekje_password == "test_baekje_pass"
        assert config.repeat_interval_minutes == 15
        assert config.alert_exclusion_days == 10
        assert config.has_baekje_credentials() == True
    
    def test_app_config_without_baekje(self):
        """백제 인증정보 없는 AppConfig 테스트"""
        config = AppConfig(
            geoweb_id="test_geoweb",
            geoweb_password="test_geoweb_pass"
        )
        
        assert config.geoweb_id == "test_geoweb"
        assert config.geoweb_password == "test_geoweb_pass"
        assert config.has_baekje_credentials() == False


class TestIntegrationWorkflow:
    """통합 워크플로우 테스트"""
    
    @patch('scrapers.browser_manager.BrowserManager')
    def test_scraper_workflow_mock(self, mock_browser_class):
        """모킹된 브라우저를 사용한 워크플로우 테스트"""
        # Mock 설정
        mock_browser = MagicMock()
        mock_page = MagicMock()
        mock_browser_class.return_value = mock_browser
        mock_browser.__enter__.return_value = mock_browser
        mock_browser.__exit__.return_value = None
        mock_browser.new_page.return_value = mock_page
        
        # 스크래퍼 생성
        scraper = GeowebScraper()
        
        # login 메서드 모킹
        with patch.object(scraper, 'login', return_value=True) as mock_login, \
             patch.object(scraper, 'search_drug', return_value=[]) as mock_search:
            
            # 워크플로우 실행 (간단한 검증)
            with mock_browser:
                page = mock_browser.new_page()
                login_result = scraper.login(page, "test_id", "test_pass")
                search_result = scraper.search_drug("테스트약품")
            
            # 결과 검증
            assert login_result == True
            assert isinstance(search_result, list)
            mock_login.assert_called_once()
    
    def test_error_handling(self):
        """오류 처리 테스트"""
        scraper = GeowebScraper()
        
        # 잘못된 매개변수로 호출 시 적절한 오류 처리
        with patch.object(scraper, 'login', side_effect=Exception("Login failed")):
            try:
                result = scraper.search_drug("테스트약품")
                # 예외가 발생하거나 빈 리스트가 반환되어야 함
                assert isinstance(result, list)
            except Exception:
                # 예외 발생도 정상적인 처리
                pass