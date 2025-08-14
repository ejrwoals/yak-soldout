#!/usr/bin/env python3
"""
약품 재고 자동 검색 프로그램 - Streamlit 웹 인터페이스

백엔드 로직이 통합된 실시간 웹 애플리케이션입니다.
"""

import streamlit as st
import pandas as pd
import time
import json
import threading
import queue
import warnings
from datetime import datetime, timedelta
from pathlib import Path

# 경고 메시지 숨기기
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", message=".*file size.*not 512.*")
warnings.filterwarnings("ignore", message=".*OLE2 inconsistency.*")
warnings.filterwarnings("ignore", category=UserWarning)

# pandas 옵션 설정
import pandas as pd
pd.set_option('mode.chained_assignment', None)
from typing import Optional, Dict, Any, List

# 프로젝트 모듈 import
from models.config import ConfigManager
from models.drug_data import SearchResult, Drug, AppConfig
from utils.file_manager import FileManager
from utils.data_processor import DataProcessor
from utils.notifications import CrossPlatformNotifier, AlertManager
from scrapers.browser_manager import BrowserManager
from scrapers.geoweb_scraper import GeowebScraper
from scrapers.baekje_scraper import BaekjeScraper


class StreamlitApp:
    """Streamlit 웹 애플리케이션 클래스"""
    
    def __init__(self):
        self.config_manager = ConfigManager()
        self.app_dir = self.config_manager.get_app_directory()
        self.file_manager = FileManager(self.app_dir)
        self.data_processor = DataProcessor()
        self.notifier = CrossPlatformNotifier()
        
        # 애플리케이션 상태
        self.config: Optional[AppConfig] = None
        self.alert_manager: Optional[AlertManager] = None
        self.is_searching = False
        self.should_stop = False
        
        # 실시간 로그 파일 경로  
        self.log_file = self.app_dir / "current_search.log"
        self.search_thread = None
    
    @st.cache_data(ttl=3600)  # 1시간 캐시
    def _load_usage_excel_cached(_self):
        """월별 사용량 Excel 파일을 캐시하여 로드"""
        return _self.file_manager.read_usage_excel()
    
    @st.cache_data(ttl=600)  # 10분 캐시  
    def _load_config_cached(_self):
        """설정을 캐시하여 로드"""
        return _self.config_manager.load_config()
    
    def run(self):
        """Streamlit 앱 실행"""
        self._setup_page_config()
        self._render_header()
        
        # 앱 초기화
        if not self._initialize_app():
            return
        
        # 메인 컨텐츠
        self._render_main_content()
    
    def _setup_page_config(self):
        """페이지 설정"""
        st.set_page_config(
            page_title="약품 재고 자동 체크",
            page_icon="💊",
            layout="wide"
        )
    
    def _render_header(self):
        """헤더 렌더링"""
        st.markdown(
            "<h1 style='text-align: center;'>품절 약품 재고 자동 체크</h1>", 
            unsafe_allow_html=True
        )
        st.markdown(
            "<h4 style='text-align: center; color: orange;'>- 지오영, 백제약품 -</h4>", 
            unsafe_allow_html=True
        )
        st.markdown(
            "<h4 style='text-align: right; color: grey;'>by ChaJM</h4>", 
            unsafe_allow_html=True
        )
        st.markdown(
            "<h6 style='text-align: left; color: grey;'>(마지막 업데이트 날짜: 2025-08-13)</h6>", 
            unsafe_allow_html=True
        )
    
    def _initialize_app(self) -> bool:
        """앱 초기화"""
        try:
            # 설정 로드
            self.config = self.config_manager.load_config()
            self.alert_manager = AlertManager(self.config.alert_exclusion_days)
            
            # 필수 파일 확인
            self._check_required_files()
            
            # 월별 사용량 파일 확인
            usage_df = self.file_manager.read_usage_excel()
            if usage_df is not None:
                created_time = self.file_manager.get_usage_file_creation_time()
                
                # 파일 생성일과 현재 날짜 비교 (3개월 기준)
                try:
                    # created_time에서 날짜 부분만 추출 (예: "2025년 08월 13일" 형식)
                    date_part = created_time.split()[0:3]  # ["2025년", "08월", "13일"]
                    year = int(date_part[0].replace("년", ""))
                    month = int(date_part[1].replace("월", ""))
                    day = int(date_part[2].replace("일", ""))
                    file_date = datetime(year, month, day)
                    
                    # 현재 날짜에서 3개월 전 계산
                    three_months_ago = datetime.now() - timedelta(days=90)  # 대략 3개월
                    
                    if file_date >= three_months_ago:
                        # 3개월 이내 - 메시지 표시 안함
                        pass
                    else:
                        # 3개월 이상 된 파일 - 업데이트 권장 메시지 표시
                        st.markdown(
                            f"<p style='color: orange;'>⚠️ 월별 약품사용량 파일이 오래되었습니다 ({created_time} 생성) ⚠️</p>", 
                            unsafe_allow_html=True
                        )
                        st.markdown(
                            "<p style='color: orange;'>⚠️ [컨설팅 통계] - [약품 통계] - [월별 약품사용량]에서 최신 파일로 교체해 주세요</p>", 
                            unsafe_allow_html=True
                        )
                        
                except Exception:
                    # 날짜 파싱 실패 시 기본 메시지
                    st.markdown(
                        f"<p style='color: green;'>✅ 월별 약품사용량.xls 파일을 정상적으로 읽었습니다 ({created_time} 생성된 파일) ✅</p>", 
                        unsafe_allow_html=True
                    )
                
                # 세션 상태에 저장
                st.session_state['usage_df'] = usage_df
                st.session_state['usage_created_time'] = created_time
            else:
                st.error("⚠️ 월별 약품사용량 Excel 파일을 찾을 수 없습니다")
                st.error("⚠️ [컨설팅 통계] - [약품 통계] - [월별 약품사용량]에서 파일을 내보내주세요")
                return False
            
            # 약품 목록 확인
            drug_list = self.file_manager.read_drug_list()
            st.markdown(
                f"<p style='color: green;'>✅ 지오영 품절 목록.txt 에서 {len(drug_list)}개 약품을 확인했습니다. ✅</p>", 
                unsafe_allow_html=True
            )
            
            st.markdown("---")
            return True
            
        except Exception as e:
            st.error(f"❌ 초기화 실패: {e}")
            return False
    
    def _check_required_files(self):
        """필수 파일 존재 확인"""
        required_files = [
            "info.txt",
            "지오영 품절 목록.txt", 
            "알림 제외.txt"
        ]
        
        for filename in required_files:
            file_path = self.app_dir / filename
            if not file_path.exists():
                if filename == "알림 제외.txt":
                    # 알림 제외 파일이 없으면 생성
                    self.file_manager.write_alert_exclusions([])
                else:
                    raise FileNotFoundError(f"필수 파일을 찾을 수 없습니다: {filename}")
    
    def _render_main_content(self):
        """메인 컨텐츠 렌더링"""
        # 컨트롤 패널
        self._render_control_panel()
        
        # 실시간 로그 표시 (항상 표시)
        st.markdown("### 🔍 실시간 검색 진행상황")
        log_placeholder = st.empty()  # placeholder 사용
        self._display_real_time_logs(log_placeholder)
        st.markdown("---")
        
        # 상태 표시
        status_placeholder = st.empty()
        alert_placeholder = st.empty()
        countdown_placeholder = st.empty()
        
        # 결과 표시 영역
        results_placeholder = st.empty()
        briefing_placeholder_1 = st.empty()
        briefing_placeholder_2 = st.empty()
        
        # 확장 가능한 섹션들
        with st.expander("| 검토 제안 |"):
            proposal_info = st.empty()
            proposal_info.text("** 현재 도매상에 있는 약품들 중, 재고 확충을 하면 좋을만한 약품들을 제안합니다. **")
            proposal_placeholder_1 = st.empty()
            proposal_placeholder_2 = st.empty()
            proposal_placeholder_3 = st.empty()
        
        with st.expander("| 품절약 목록 |"):
            soldout_status = st.empty()
            soldout_placeholder = st.empty()
        
        with st.expander("| 알림 제외 목록 |"):
            exclusion_info = st.empty()
            exclusion_placeholder = st.empty()
        
        st.markdown("---")
        st.text("- End -")
        st.write('\n\n')
        st.write('| 검색 실패 로그 |')
        error_placeholder = st.empty()
        
        # 정적 데이터 표시
        self._render_static_data(
            status_placeholder, alert_placeholder, countdown_placeholder,
            results_placeholder, briefing_placeholder_1, briefing_placeholder_2,
            proposal_placeholder_1, proposal_placeholder_2, proposal_placeholder_3,
            soldout_status, soldout_placeholder,
            exclusion_info, exclusion_placeholder, error_placeholder
        )
        
        # 자동 새로고침 (로그 파일 기반으로 검색 중 확인)
        is_searching = (hasattr(self, 'search_thread') and 
                       self.search_thread and 
                       self.search_thread.is_alive()) or self.log_file.exists()
        
        if is_searching or st.session_state.get('auto_refresh', False):
            # 2초마다 새로고침 (더 빠른 로그 업데이트)
            time.sleep(2)
            st.rerun()
    
    def _render_control_panel(self):
        """컨트롤 패널 렌더링"""
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if st.button("🔍 한 번 검색", type="primary", disabled=self.is_searching):
                self._start_single_search()
        
        with col2:
            if st.button("🔄 연속 검색 시작", disabled=self.is_searching):
                self._start_continuous_search()
        
        with col3:
            if st.button("⏹️ 검색 중단", disabled=not self.is_searching):
                self._stop_search()
        
        # 검색 상태 표시
        if self.is_searching:
            st.info("🔄 검색이 진행 중입니다...")
        
        # 브라우저 설치 확인
        if st.button("🌐 브라우저 설치"):
            self._install_browsers()
    
    def _start_single_search(self):
        """단일 검색 시작"""
        if not self.is_searching:
            # 로그 초기화
            st.session_state['search_logs'] = []
            
            # 검색 스레드 시작
            self.should_stop = False
            self.is_searching = True
            self.search_thread = threading.Thread(target=self._run_search_cycle, args=(False,))
            self.search_thread.start()
            st.rerun()
    
    def _start_continuous_search(self):
        """연속 검색 시작"""
        if not self.is_searching:
            # 로그 초기화
            st.session_state['search_logs'] = []
            
            # 연속 검색 스레드 시작
            self.should_stop = False
            self.is_searching = True
            self.search_thread = threading.Thread(target=self._run_search_cycle, args=(True,))
            self.search_thread.start()
            st.rerun()
    
    def _stop_search(self):
        """검색 중단"""
        self.should_stop = True
        self.is_searching = False
        if self.search_thread and self.search_thread.is_alive():
            self.search_thread.join(timeout=5)
        st.success("✅ 검색이 중단되었습니다.")
        st.rerun()
    
    def _install_browsers(self):
        """브라우저 설치"""
        with st.spinner("브라우저 설치 중..."):
            try:
                BrowserManager.install_browsers()
                st.success("✅ 브라우저 설치 완료!")
            except Exception as e:
                st.error(f"❌ 브라우저 설치 실패: {e}")
    
    def _log_message(self, message: str):
        """로그 메시지를 파일과 터미널에 출력"""
        # 터미널에 실시간 출력
        print(message)
        
        # 파일에 실시간 로그 기록
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                timestamp = datetime.now().strftime("%H:%M:%S")
                f.write(f"{timestamp} - {message}\n")
        except Exception:
            pass  # 파일 쓰기 실패 시 무시
    
    def _run_search_cycle(self, continuous: bool = False):
        """검색 사이클 실행 (별도 스레드에서 실행)"""
        try:
            while not self.should_stop:
                # 검색 실행
                search_result = self._execute_search()
                
                # 결과 저장
                if search_result:
                    data = search_result.to_dict()
                    self.file_manager.save_search_results(data)
                
                # 연속 검색이 아니거나 중단 요청이 있으면 종료
                if not continuous or self.should_stop:
                    break
                
                # 재고 발견 시 1분, 아니면 설정된 간격만큼 대기
                if search_result and search_result.has_alerts():
                    wait_minutes = 1
                    self._log_message(f"⚡ 재고 발견으로 다음 검색까지 {wait_minutes}분 대기")
                else:
                    wait_minutes = self.config.repeat_interval_minutes
                    self._log_message(f"⏰ 다음 검색까지 {wait_minutes}분 대기")
                
                # 1분씩 대기하면서 중단 신호 확인
                for i in range(wait_minutes):
                    if self.should_stop:
                        break
                    time.sleep(60)
                    remaining = wait_minutes - i - 1
                    if remaining > 0:
                        self._log_message(f"⏱️ 남은 시간: {remaining}분")
        
        except Exception as e:
            self._log_message(f"❌ 검색 중 오류: {e}")
        
        finally:
            self.is_searching = False
    
    def _execute_search(self) -> Optional[SearchResult]:
        """실제 검색 실행"""
        # 로그 파일 초기화 (검색 시작 시)
        if self.log_file.exists():
            self.log_file.unlink()
        
        start_time = time.time()
        self._log_message(f"🔍 검색 시작: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        try:
            # 데이터 로드
            drug_list = self.file_manager.read_drug_list()
            exclusion_list = self.file_manager.read_alert_exclusions()
            
            self._log_message(f"📋 검색할 약품 수: {len(drug_list)}개")
            
            # 알림 제외 목록 처리
            cleaned_exclusions, excluded_names, none_stop_mode = \
                self.data_processor.process_alert_exclusions(exclusion_list, self.config.alert_exclusion_days)
            
            # 웹 스크래핑 실행
            all_drugs = []
            errors = []
            
            with BrowserManager() as browser_mgr:
                # 지오영 검색
                self._log_message("🌐 지오영 검색 시작...")
                geoweb_drugs, geoweb_errors = self._search_geoweb(browser_mgr, drug_list, excluded_names)
                all_drugs.extend(geoweb_drugs)
                errors.extend(geoweb_errors)
                
                # 백제 검색
                if self.config.has_baekje_credentials():
                    self._log_message("🏢 백제약품 검색 시작...")
                    # 지오영에서 얻은 보험코드 사용
                    geoweb_scraper = GeowebScraper()
                    baekje_drugs, baekje_errors = self._search_baekje(browser_mgr, geoweb_scraper.get_insurance_code_dict())
                    all_drugs.extend(baekje_drugs)
                    errors.extend(baekje_errors)
                else:
                    self._log_message("⚠️ 백제약품 인증정보가 없어 검색을 건너뜁니다")
            
            # 결과 분류
            found_drugs, soldout_drugs = self.data_processor.categorize_drugs(all_drugs, cleaned_exclusions)
            
            # 검색 결과 생성
            duration = time.time() - start_time
            search_result = self.data_processor.create_search_result(
                found_drugs, soldout_drugs, cleaned_exclusions, duration, errors
            )
            
            # 알림 처리
            self._handle_notifications(search_result, none_stop_mode)
            
            # 파일 업데이트
            self._update_files(search_result, drug_list)
            
            self._log_message(f"✅ 검색 완료 (소요시간: {duration:.1f}초)")
            self._log_message(f"📊 발견된 재고: {len(found_drugs)}개, 품절: {len(soldout_drugs)}개")
            
            return search_result
            
        except Exception as e:
            duration = time.time() - start_time
            self._log_message(f"❌ 검색 중 오류 발생: {e}")
            
            # 오류 상황에서도 빈 결과 반환
            search_result = SearchResult(
                timestamp=datetime.now(),
                found_drugs=[],
                soldout_drugs=[],
                alert_exclusions=exclusion_list if 'exclusion_list' in locals() else [],
                search_duration=duration,
                errors=[str(e)]
            )
            
            return search_result
    
    def _search_geoweb(self, browser_mgr: BrowserManager, drug_list: List[str], 
                      excluded_names: List[str]) -> tuple[List[Drug], List[str]]:
        """지오영 검색"""
        scraper = GeowebScraper()
        page = browser_mgr.new_page()
        
        try:
            # 로그인
            self._log_message("🤖 지오영에 로그인하는 중입니다...")
            if not scraper.login(page, self.config.geoweb_id, self.config.geoweb_password):
                raise Exception("지오영 로그인 실패")
            
            self._log_message("✓ 지오영 로그인 성공")
            
            # 약품 검색
            all_drugs = []
            errors = []
            
            for drug_name in drug_list:
                if self.should_stop:
                    break
                    
                self._log_message(f"🤖 지오영 재고를 체크하는 중입니다... 검색중: {drug_name}")
                
                try:
                    drugs = scraper.search_drug(drug_name)
                    for drug in drugs:
                        drug.is_excluded_from_alert = drug.name in excluded_names
                    all_drugs.extend(drugs)
                except Exception as e:
                    error_msg = f"{drug_name}: 지오영 검색 실패 - {str(e)}"
                    errors.append(error_msg)
                    self._log_message(f"❌ {error_msg}")
            
            found_drugs = [drug for drug in all_drugs if drug.has_stock()]
            soldout_drugs = [drug for drug in all_drugs if not drug.has_stock()]
            
            self._log_message(f"✓ 지오영 검색 완료: 재고 {len(found_drugs)}개, 품절 {len(soldout_drugs)}개")
            
            return all_drugs, errors
            
        finally:
            page.close()
    
    def _search_baekje(self, browser_mgr: BrowserManager, insurance_codes: dict) -> tuple[List[Drug], List[str]]:
        """백제 검색"""
        if not insurance_codes:
            self._log_message("⚠️ 보험코드 정보가 없어 백제 검색을 건너뜁니다")
            return [], []
        
        scraper = BaekjeScraper()
        page = browser_mgr.new_page()
        
        try:
            # 로그인
            self._log_message("🤖 백제약품에 로그인하는 중입니다...")
            if not scraper.login(page, self.config.baekje_id, self.config.baekje_password):
                raise Exception("백제약품 로그인 실패")
            
            self._log_message("✓ 백제약품 로그인 성공")
            
            # 보험코드로 검색
            all_drugs = []
            for insurance_code, original_name in insurance_codes.items():
                if self.should_stop:
                    break
                    
                self._log_message(f"🤖 백제약품 재고를 체크하는 중입니다... 검색중: {original_name}")
                
                try:
                    drugs = scraper._search_by_insurance_code(insurance_code)
                    all_drugs.extend(drugs)
                except Exception as e:
                    self._log_message(f"❌ {original_name}: 백제 검색 실패 - {str(e)}")
            
            found_drugs = [drug for drug in all_drugs if drug.has_stock()]
            soldout_drugs = [drug for drug in all_drugs if not drug.has_stock()]
            
            self._log_message(f"✓ 백제약품 검색 완료: 재고 {len(found_drugs)}개, 품절 {len(soldout_drugs)}개")
            
            return all_drugs, []
            
        except Exception as e:
            return [], [f"백제약품 검색 오류: {e}"]
        finally:
            page.close()
    
    def _handle_notifications(self, search_result: SearchResult, none_stop_mode: bool):
        """알림 처리"""
        alert_drugs = search_result.get_alert_drugs()
        
        if alert_drugs:
            if not none_stop_mode:
                self._log_message(f"🚨 재고 발견 알림: {len(alert_drugs)}개 약품")
                try:
                    self.notifier.notify_stock_found(alert_drugs)
                except Exception as e:
                    self._log_message(f"⚠️ 알림 표시 실패: {e}")
            else:
                self._log_message(f"🔄 알림 제외 목록 정리 완료: {len(alert_drugs)}개 약품 발견")
    
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
            
            # 약품 목록 파일 업데이트
            self.file_manager.write_drug_list(drug_list)
            
        except Exception as e:
            self._log_message(f"⚠️ 파일 업데이트 오류: {e}")
    
    def _display_real_time_logs(self, placeholder):
        """실시간 로그 표시 (파일 기반)"""
        try:
            # 검색 중인지 확인
            is_searching = hasattr(self, 'search_thread') and self.search_thread and self.search_thread.is_alive()
            
            # 로그 파일에서 읽기
            if self.log_file.exists() and is_searching:
                with open(self.log_file, "r", encoding="utf-8") as f:
                    log_lines = f.readlines()
                
                # 최근 20줄만 표시
                recent_lines = log_lines[-20:] if len(log_lines) > 20 else log_lines
                log_text = ''.join(recent_lines).strip()
                
                if log_text:
                    placeholder.text_area(
                        "진행 상황:", 
                        value=log_text, 
                        height=300, 
                        disabled=True
                    )
                else:
                    placeholder.info("🔄 검색 시작 중...")
            elif is_searching:
                placeholder.info("🔄 검색 시작 중...")
            else:
                # 검색이 끝났으면 로그 파일 정리
                if self.log_file.exists():
                    self.log_file.unlink()  # 파일 삭제
                
                placeholder.success("✅ 검색 완료 또는 대기 중")
                
        except Exception as e:
            placeholder.error(f"로그 표시 오류: {e}")
    
    def _auto_refresh_loop(self, *placeholders):
        """자동 새로고침 루프"""
        # 5초마다 데이터 새로고침
        time.sleep(5)
        self._render_dynamic_data(*placeholders)
        st.rerun()
    
    def _render_static_data(self, *placeholders):
        """정적 데이터 렌더링 (자동 새로고침 꺼진 상태)"""
        self._render_dynamic_data(*placeholders)
    
    def _render_dynamic_data(self, status_placeholder, alert_placeholder, countdown_placeholder,
                           results_placeholder, briefing_placeholder_1, briefing_placeholder_2,
                           proposal_placeholder_1, proposal_placeholder_2, proposal_placeholder_3,
                           soldout_status, soldout_placeholder,
                           exclusion_info, exclusion_placeholder, error_placeholder):
        """동적 데이터 렌더링"""
        
        # 최신 검색 결과 로드
        search_data = self.file_manager.load_search_results()
        app_state = self.file_manager.load_app_state()
        
        if search_data:
            search_result = SearchResult.from_dict(search_data)
            self._render_search_results(
                search_result, status_placeholder, alert_placeholder, countdown_placeholder,
                results_placeholder, briefing_placeholder_1, briefing_placeholder_2,
                proposal_placeholder_1, proposal_placeholder_2, proposal_placeholder_3,
                soldout_status, soldout_placeholder,
                exclusion_info, exclusion_placeholder, error_placeholder
            )
        else:
            status_placeholder.info("🔍 검색 결과가 없습니다. 검색을 시작해주세요.")
    
    def _render_search_results(self, search_result: SearchResult, *placeholders):
        """검색 결과 렌더링"""
        (status_placeholder, alert_placeholder, countdown_placeholder,
         results_placeholder, briefing_placeholder_1, briefing_placeholder_2,
         proposal_placeholder_1, proposal_placeholder_2, proposal_placeholder_3,
         soldout_status, soldout_placeholder,
         exclusion_info, exclusion_placeholder, error_placeholder) = placeholders
        
        # 상태 표시
        last_search_time = search_result.timestamp.strftime('%Y년 %m월 %d일 %X')
        status_placeholder.text(f'🤖 약품 재고 검색 완료 (마지막 검색한 시간 : {last_search_time})')
        
        # 알림 표시
        alert_drugs = search_result.get_alert_drugs()
        if alert_drugs:
            alert_placeholder.warning(f'재고 발견!! (발견 시각 : {last_search_time})', icon="⚠️")
            
            # 발견된 약품 DataFrame 표시
            dataframes = self.data_processor.prepare_display_dataframes(search_result)
            if 'found' in dataframes:
                results_placeholder.dataframe(dataframes['found'][['도매', '메인센터', '인천센터', '비고']])
            
            # 브리핑 표시
            self._render_briefings(search_result, briefing_placeholder_1, briefing_placeholder_2)
            
        else:
            alert_placeholder.subheader('현재 모두 품절입니다ㅠ')
        
        # 검토 제안 표시
        self._render_proposals(search_result, proposal_placeholder_1, proposal_placeholder_2, proposal_placeholder_3)
        
        # 품절약 목록 표시
        dataframes = self.data_processor.prepare_display_dataframes(search_result)
        soldout_status.text('')
        if 'soldout' in dataframes:
            soldout_placeholder.dataframe(dataframes['soldout'])
        
        # 알림 제외 목록 표시
        try:
            config = self.config_manager.load_config()
            exclusion_info.text(f'** 한 번 재고를 발견한 약은 이후 {config.alert_exclusion_days}일동안 재고 발견 알림이 울리지 않습니다 **')
            exclusion_placeholder.write(search_result.alert_exclusions)
        except Exception:
            exclusion_info.text('** 알림 제외 목록을 불러올 수 없습니다 **')
        
        # 오류 로그 표시
        if search_result.errors:
            error_text = '\n'.join(search_result.errors)
            error_placeholder.text(error_text)
    
    def _render_briefings(self, search_result: SearchResult, 
                         briefing_placeholder_1, briefing_placeholder_2):
        """브리핑 렌더링"""
        try:
            usage_df = st.session_state.get('usage_df')
            usage_created_time = st.session_state.get('usage_created_time', '')
            
            if usage_df is None:
                return
            
            # 알림 약품들과 사용량 데이터 병합
            alert_drugs = search_result.get_alert_drugs()
            brief_alarm_df = self.data_processor.merge_with_usage_data(alert_drugs, usage_df)
            
            if not brief_alarm_df.empty:
                # '품절'을 '0'으로 변경
                brief_alarm_df['메인센터'] = brief_alarm_df['메인센터'].replace('품절', '0')
                brief_alarm_df['인천센터'] = brief_alarm_df['인천센터'].replace('품절', '0')
                
                # 브리핑 생성
                if len(brief_alarm_df) >= 1:
                    brief_1 = self.data_processor.generate_briefing(brief_alarm_df.iloc[0], usage_created_time)
                    briefing_placeholder_1.markdown(brief_1)
                
                if len(brief_alarm_df) >= 2:
                    brief_2 = self.data_processor.generate_briefing(brief_alarm_df.iloc[1], usage_created_time)
                    briefing_placeholder_2.markdown(brief_2)
                    
        except Exception as e:
            print(f"브리핑 렌더링 오류: {e}")
    
    def _render_proposals(self, search_result: SearchResult,
                         proposal_placeholder_1, proposal_placeholder_2, proposal_placeholder_3):
        """검토 제안 렌더링"""
        try:
            usage_df = st.session_state.get('usage_df')
            usage_created_time = st.session_state.get('usage_created_time', '')
            
            if usage_df is None:
                return
            
            # 모든 발견된 약품(알림 제외 포함)과 사용량 데이터 병합
            proposal_df = self.data_processor.merge_with_usage_data(search_result.found_drugs, usage_df)
            
            if not proposal_df.empty:
                proposal_df['메인센터'] = proposal_df['메인센터'].replace('품절', '0')
                proposal_df['인천센터'] = proposal_df['인천센터'].replace('품절', '0')
                
                # 랜덤 제안 3개 생성
                proposals = self.data_processor.generate_random_proposals(proposal_df, usage_created_time, 3)
                
                if len(proposals) >= 1:
                    proposal_placeholder_1.markdown(proposals[0])
                if len(proposals) >= 2:
                    proposal_placeholder_2.markdown(proposals[1])
                if len(proposals) >= 3:
                    proposal_placeholder_3.markdown(proposals[2])
                    
        except Exception as e:
            print(f"제안 렌더링 오류: {e}")


def main():
    """메인 함수"""
    app = StreamlitApp()
    app.run()


if __name__ == "__main__":
    main()