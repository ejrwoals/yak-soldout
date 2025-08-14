import time
from typing import List, Dict
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError
from .base_scraper import BaseScraper
from models.drug_data import Drug, DistributorType


class BaekjeScraper(BaseScraper):
    """백제약품 웹사이트 스크래퍼"""
    
    def __init__(self):
        super().__init__(DistributorType.BAEKJE)
        self.base_url = "https://www.ibjp.co.kr"
    
    def login(self, page: Page, username: str, password: str) -> bool:
        """백제약품 로그인"""
        try:
            self.page = page
            
            # 로그인 페이지로 이동
            self.page.goto(f"{self.base_url}/login.act")
            
            # 로그인 폼 입력
            if not self.wait_and_fill('#loginId', username):
                raise Exception("아이디 입력 실패")
            
            if not self.wait_and_fill('#pwd', password):
                raise Exception("비밀번호 입력 실패")
            
            # 로그인 버튼 클릭 (Enter 키로 제출)
            self.page.keyboard.press('Enter')
            self.page.wait_for_timeout(2000)
            
            # 로그인 성공 여부 확인 (페이지 이동 또는 특정 요소 존재 확인)
            try:
                # 검색창이 있으면 로그인 성공으로 간주
                self.page.wait_for_selector('#SEARCH_NM', timeout=5000)
                self.is_logged_in = True
                return True
            except PlaywrightTimeoutError:
                raise Exception("로그인 후 메인 페이지 이동 실패")
            
        except Exception as e:
            print(f"백제약품 로그인 오류: {e}")
            return False
    
    def search_by_insurance_codes(self, insurance_codes: Dict[str, str]) -> List[Drug]:
        """보험코드로 약품 일괄 검색"""
        if not self.is_logged_in or not self.page:
            raise Exception("로그인이 필요합니다")
        
        all_drugs = []
        
        for insurance_code, original_name in insurance_codes.items():
            if not insurance_code.strip():
                continue
                
            try:
                drugs = self._search_by_insurance_code(insurance_code)
                all_drugs.extend(drugs)
            except Exception as e:
                print(f"백제약품 검색 오류 ({original_name}): {e}")
                continue
        
        return all_drugs
    
    def search_drug(self, drug_name: str) -> List[Drug]:
        """단일 약품 검색 (백제는 주로 보험코드로 검색하므로 빈 리스트 반환)"""
        # 백제는 보험코드 기반 검색이 주 방식이므로 개별 약품명 검색은 구현하지 않음
        return []
    
    def _search_by_insurance_code(self, insurance_code: str) -> List[Drug]:
        """보험코드로 검색"""
        drugs = []
        
        try:
            # 검색 모드를 보험코드로 변경
            self._set_search_mode_to_insurance_code()
            
            # 검색창에 보험코드 입력
            if not self.wait_and_fill('#SEARCH_NM', insurance_code):
                raise Exception("보험코드 입력 실패")
            
            # 검색 실행
            self.page.keyboard.press('Enter')
            self.page.wait_for_timeout(2000)
            
            # 검색 결과 파싱 (최대 3개 결과)
            for child_index in range(1, 4):
                try:
                    drug = self._parse_search_result_row(child_index, insurance_code)
                    if drug:
                        drugs.append(drug)
                except Exception as e:
                    if child_index == 1:
                        # 첫 번째 결과조차 없으면 오류 출력
                        print(f"백제약품 검색 결과 없음 ({insurance_code}): {e}")
                    break
            
        except Exception as e:
            print(f"백제약품 보험코드 검색 오류 ({insurance_code}): {e}")
        
        return drugs
    
    def _set_search_mode_to_insurance_code(self):
        """검색 모드를 보험코드로 설정"""
        try:
            # Select 요소 찾기
            select_selector = '#SEARCH_GB'
            self.page.wait_for_selector(select_selector, timeout=3000)
            
            # 보험코드 옵션 선택
            self.page.select_option(select_selector, label='보험코드')
            self.page.wait_for_timeout(1000)
            
        except Exception as e:
            print(f"검색 모드 변경 오류: {e}")
            # 기본적으로 보험코드 모드가 설정되어 있을 수 있으므로 계속 진행
    
    def _parse_search_result_row(self, row_index: int, insurance_code: str) -> Drug:
        """특정 행의 검색 결과 파싱"""
        try:
            # 행 셀렉터
            name_selector = f'#itemListTable > tbody > tr:nth-child({row_index}) > td:nth-child(2)'
            stock_selector = f'#itemListTable > tbody > tr:nth-child({row_index}) > td:nth-child(5)'
            
            # 약품명과 재고 정보 추출
            drug_name = self.get_text_safe(name_selector)
            stock = self.get_text_safe(stock_selector)
            
            if not drug_name:
                return None
            
            # Drug 객체 생성
            drug = self.create_drug(
                name=drug_name,
                insurance_code=insurance_code,
                main_stock=stock,
                incheon_stock="-",  # 백제는 인천센터 정보 없음
                notes="-",
                company="백제약품"
            )
            
            return drug
            
        except Exception as e:
            raise Exception(f"행 {row_index} 파싱 실패: {e}")
    
    def get_all_search_results(self, insurance_codes: Dict[str, str]) -> List[Drug]:
        """모든 보험코드에 대해 검색 수행"""
        return self.search_by_insurance_codes(insurance_codes)