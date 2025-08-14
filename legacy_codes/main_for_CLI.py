#!/usr/bin/env python3
"""
약품 재고 자동 검색 프로그램 - 메인 실행 파일

이 프로그램은 지오영과 백제약품에서 약품 재고를 자동으로 검색하고,
결과를 JSON 파일로 저장하여 Streamlit 프론트엔드에서 표시할 수 있도록 합니다.
"""

import time
import sys
from pathlib import Path
from datetime import datetime
from typing import List, Tuple

# 프로젝트 모듈 import
from models.config import ConfigManager
from models.drug_data import AppConfig, SearchResult
from utils.file_manager import FileManager
from utils.data_processor import DataProcessor
from utils.notifications import CrossPlatformNotifier, AlertManager
from scrapers.browser_manager import BrowserManager
from scrapers.geoweb_scraper import GeowebScraper
from scrapers.baekje_scraper import BaekjeScraper


class DrugStockChecker:
    """약품 재고 검색 메인 클래스"""
    
    def __init__(self):
        self.config_manager = ConfigManager()
        self.config: AppConfig = None
        self.file_manager: FileManager = None
        self.data_processor = DataProcessor()
        self.notifier = CrossPlatformNotifier()
        self.alert_manager: AlertManager = None
        
        # 상태 변수
        self.is_initialized = False
        self.should_stop = False
    
    def initialize(self) -> bool:
        """애플리케이션 초기화"""
        try:
            print("=== 약품 재고 자동 검색 프로그램 ===")
            print("초기화 중...")
            
            # 설정 로드
            self.config = self.config_manager.load_config()
            print(f"✓ 설정 파일 로드 완료")
            
            # 파일 매니저 초기화
            app_dir = self.config_manager.get_app_directory()
            self.file_manager = FileManager(app_dir)
            print(f"✓ 파일 매니저 초기화 완료")
            
            # 알림 매니저 초기화
            self.alert_manager = AlertManager(self.config.alert_exclusion_days)
            print(f"✓ 알림 매니저 초기화 완료")
            
            # 필수 파일 존재 확인
            self._check_required_files()
            print(f"✓ 필수 파일 확인 완료")
            
            # 브라우저 설치 확인 (필요 시)
            if not self._check_browser_installation():
                print("브라우저 설치 중...")
                BrowserManager.install_browsers()
            
            self.is_initialized = True
            print("✓ 초기화 완료!\n")
            return True
            
        except Exception as e:
            print(f"❌ 초기화 실패: {e}")
            return False
    
    def _check_required_files(self):
        """필수 파일 존재 확인"""
        try:
            # 약품 목록 파일 확인
            drug_list = self.file_manager.read_drug_list()
            if not drug_list:
                raise Exception("품절 약품 목록이 비어있습니다")
            
            # 월별 사용량 파일 확인
            usage_df = self.file_manager.read_usage_excel()
            if usage_df is None:
                print("⚠️ 월별 약품사용량 Excel 파일을 찾을 수 없습니다")
                print("⚠️ [컨설팅 통계] - [약품 통계] - [월별 약품사용량]에서 파일을 내보내주세요")
                
        except FileNotFoundError as e:
            raise Exception(f"필수 파일을 찾을 수 없습니다: {e}")
    
    def _check_browser_installation(self) -> bool:
        """브라우저 설치 상태 확인"""
        try:
            with BrowserManager() as browser_mgr:
                page = browser_mgr.new_page()
                page.goto("about:blank")
                return True
        except Exception:
            return False
    
    def run_search_cycle(self) -> SearchResult:
        """한 번의 검색 사이클 실행"""
        if not self.is_initialized:
            raise Exception("초기화되지 않았습니다. initialize()를 먼저 호출하세요.")
        
        start_time = time.time()
        print(f"🔍 검색 시작: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        try:
            # 1. 필요한 데이터 로드
            drug_list = self.file_manager.read_drug_list()
            exclusion_list = self.file_manager.read_alert_exclusions()
            
            print(f"📋 검색할 약품 수: {len(drug_list)}개")
            print(f"📋 알림 제외 목록: {len(exclusion_list)}개")
            
            # 2. 알림 제외 목록 처리
            cleaned_exclusions, excluded_names, none_stop_mode = \
                self.data_processor.process_alert_exclusions(exclusion_list, self.config.alert_exclusion_days)
            
            if none_stop_mode:
                print("⏰ 오래된 알림 제외 항목 정리 모드")
            
            # 3. 웹 스크래핑 실행
            all_drugs = []
            errors = []
            
            browser_mgr = BrowserManager()
            browser_mgr.start()
            try:
                # 지오영 검색
                print("\n🌐 지오영 검색 시작...")
                geoweb_drugs, geoweb_errors = self._search_geoweb(browser_mgr, drug_list, excluded_names)
                all_drugs.extend(geoweb_drugs)
                errors.extend(geoweb_errors)
                
                # 백제 검색 (설정된 경우)
                if self.config.has_baekje_credentials():
                    print("\n🏢 백제약품 검색 시작...")
                    # 지오영에서 얻은 보험코드 사용
                    geoweb_scraper = GeowebScraper()  # 임시로 인스턴스 생성하여 보험코드 딕셔너리 접근
                    baekje_drugs, baekje_errors = self._search_baekje(browser_mgr, geoweb_scraper.get_insurance_code_dict())
                    all_drugs.extend(baekje_drugs)
                    errors.extend(baekje_errors)
                else:
                    print("⚠️ 백제약품 인증정보가 없어 검색을 건너뜁니다")
            finally:
                browser_mgr.stop()
            
            # 4. 결과 분류
            found_drugs, soldout_drugs = self.data_processor.categorize_drugs(all_drugs, cleaned_exclusions)
            
            # 5. 검색 결과 생성
            duration = time.time() - start_time
            search_result = self.data_processor.create_search_result(
                found_drugs, soldout_drugs, cleaned_exclusions, duration, errors
            )
            
            # 6. 결과 저장
            self._save_search_result(search_result)
            
            # 7. 알림 처리
            self._handle_notifications(search_result, none_stop_mode)
            
            # 8. 파일 업데이트
            self._update_files(search_result, drug_list)
            
            print(f"✅ 검색 완료 (소요시간: {duration:.1f}초)")
            print(f"📊 발견된 재고: {len(found_drugs)}개, 품절: {len(soldout_drugs)}개")
            
            return search_result
            
        except Exception as e:
            print(f"❌ 검색 중 오류 발생: {e}")
            duration = time.time() - start_time
            
            # 오류 상황에서도 빈 결과 반환
            search_result = SearchResult(
                timestamp=datetime.now(),
                found_drugs=[],
                soldout_drugs=[],
                alert_exclusions=exclusion_list,
                search_duration=duration,
                errors=[str(e)]
            )
            
            self._save_search_result(search_result)
            return search_result
    
    def _search_geoweb(self, browser_mgr: BrowserManager, drug_list: List[str], 
                      excluded_names: List[str]) -> Tuple[List, List]:
        """지오영 검색"""
        scraper = GeowebScraper()
        page = browser_mgr.new_page()
        
        try:
            # 로그인
            if not scraper.login(page, self.config.geoweb_id, self.config.geoweb_password):
                raise Exception("지오영 로그인 실패")
            
            print("✓ 지오영 로그인 성공")
            
            # 약품 검색
            found_drugs, soldout_drugs, errors = scraper.batch_search_drugs(drug_list, excluded_names)
            
            all_drugs = found_drugs + soldout_drugs
            print(f"✓ 지오영 검색 완료: {len(all_drugs)}개 약품")
            
            return all_drugs, errors
            
        finally:
            page.close()
    
    def _search_baekje(self, browser_mgr: BrowserManager, insurance_codes: dict) -> Tuple[List, List]:
        """백제 검색"""
        if not insurance_codes:
            print("⚠️ 보험코드 정보가 없어 백제 검색을 건너뜁니다")
            return [], []
        
        scraper = BaekjeScraper()
        page = browser_mgr.new_page()
        
        try:
            # 로그인
            if not scraper.login(page, self.config.baekje_id, self.config.baekje_password):
                raise Exception("백제약품 로그인 실패")
            
            print("✓ 백제약품 로그인 성공")
            
            # 보험코드로 검색
            all_drugs = scraper.search_by_insurance_codes(insurance_codes)
            
            # 약품 분류 (임시)
            found_drugs = [drug for drug in all_drugs if drug.has_stock()]
            soldout_drugs = [drug for drug in all_drugs if not drug.has_stock()]
            
            print(f"✓ 백제약품 검색 완료: {len(all_drugs)}개 약품")
            
            return all_drugs, []
            
        except Exception as e:
            return [], [f"백제약품 검색 오류: {e}"]
        finally:
            page.close()
    
    def _save_search_result(self, search_result: SearchResult):
        """검색 결과 저장"""
        try:
            data = search_result.to_dict()
            self.file_manager.save_search_results(data)
            
            # 앱 상태도 저장
            state = {
                'status': 'completed' if not search_result.errors else 'completed_with_errors',
                'last_search': search_result.timestamp.isoformat(),
                'found_count': len(search_result.found_drugs),
                'soldout_count': len(search_result.soldout_drugs),
                'error_count': len(search_result.errors)
            }
            self.file_manager.save_app_state(state)
            
        except Exception as e:
            print(f"⚠️ 결과 저장 오류: {e}")
    
    def _handle_notifications(self, search_result: SearchResult, none_stop_mode: bool):
        """알림 처리"""
        alert_drugs = search_result.get_alert_drugs()
        
        if alert_drugs:
            if not none_stop_mode:
                # 일반 알림 모드
                print(f"🚨 재고 발견 알림: {len(alert_drugs)}개 약품")
                self.notifier.notify_stock_found(alert_drugs)
            else:
                # 논스톱 모드 (알림 제외 목록 정리 후)
                print(f"🔄 알림 제외 목록 정리 완료: {len(alert_drugs)}개 약품 발견")
    
    def _update_files(self, search_result: SearchResult, drug_list: List[str]):
        """파일 업데이트"""
        try:
            # 알림 제외 목록 업데이트
            if search_result.get_alert_drugs():
                updated_exclusions = self.alert_manager.add_to_exclusion_list(
                    search_result.get_alert_drugs(),
                    search_result.alert_exclusions
                )
                self.file_manager.write_alert_exclusions(updated_exclusions)
            
            # 약품 목록 파일 업데이트 (중복 제거)
            self.file_manager.write_drug_list(drug_list)
            
        except Exception as e:
            print(f"⚠️ 파일 업데이트 오류: {e}")
    
    def run_continuous(self):
        """연속 실행 모드"""
        if not self.is_initialized:
            if not self.initialize():
                return
        
        print(f"🔄 연속 실행 모드 시작 (간격: {self.config.repeat_interval_minutes}분)")
        print("Ctrl+C로 중단할 수 있습니다\n")
        
        try:
            while not self.should_stop:
                # 검색 실행
                search_result = self.run_search_cycle()
                
                # 재고 발견 시 간격 단축 (1분)
                if search_result.has_alerts():
                    wait_minutes = 1
                    print(f"⚡ 재고 발견으로 다음 검색까지 {wait_minutes}분 대기")
                else:
                    wait_minutes = self.config.repeat_interval_minutes
                    print(f"⏰ 다음 검색까지 {wait_minutes}분 대기")
                
                # 대기 (1분 단위로 체크하여 중단 가능)
                for i in range(wait_minutes):
                    if self.should_stop:
                        break
                    remaining = wait_minutes - i
                    if i % 5 == 0 or remaining <= 5:  # 5분마다 또는 마지막 5분은 표시
                        print(f"⏱️  남은 시간: {remaining}분")
                    time.sleep(60)
                
        except KeyboardInterrupt:
            print("\n👋 사용자가 중단했습니다.")
        except Exception as e:
            print(f"❌ 실행 중 오류: {e}")
        finally:
            self.should_stop = True
            print("🏁 프로그램을 종료합니다.")
    
    def stop(self):
        """실행 중단"""
        self.should_stop = True


def main():
    """메인 함수"""
    checker = DrugStockChecker()
    
    if len(sys.argv) > 1 and sys.argv[1] == "--once":
        # 한 번만 실행
        if checker.initialize():
            checker.run_search_cycle()
    else:
        # 연속 실행
        checker.run_continuous()


if __name__ == "__main__":
    main()