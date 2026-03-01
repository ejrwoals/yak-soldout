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
            self.page.wait_for_load_state('domcontentloaded', timeout=10000)
            
            # 로그인 폼 입력
            id_selector = 'input[placeholder="아이디를 입력해 주세요"]'
            if not self.wait_and_fill(id_selector, username):
                raise Exception("아이디 입력 실패")
            
            pwd_selector = 'input[placeholder="비밀번호를 입력해 주세요"]'
            if not self.wait_and_fill(pwd_selector, password):
                raise Exception("비밀번호 입력 실패")
            
            # 로그인 버튼 클릭
            self.page.keyboard.press('Enter')
            self.page.wait_for_load_state('domcontentloaded', timeout=10000)
            
            # 로그인 오류 확인
            error_selectors = [
                'div:has-text("아이디")', 'div:has-text("비밀번호")', 
                'div:has-text("로그인")', 'div:has-text("실패")',
                '.error', '.alert'
            ]
            
            for error_selector in error_selectors:
                try:
                    if self.page.query_selector(error_selector):
                        error_text = self.get_text_safe(error_selector)
                        if any(keyword in error_text for keyword in ['실패', '오류', '잘못', '확인']):
                            raise Exception(f"로그인 실패: {error_text}")
                except Exception:
                    continue
            
            # 로그인 성공 여부 확인
            main_search_selector = 'input[placeholder="품목명/보험코드 입력"]'
            try:
                self.page.wait_for_selector(main_search_selector, timeout=2000, state='visible')
                print("로그인 성공 확인: 메인 검색창 발견")
            except PlaywrightTimeoutError:
                raise Exception("로그인 후 메인 페이지 확인 실패")
            
            self.is_logged_in = True
            return True
            
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
        return []
    
    def _search_by_insurance_code(self, insurance_code: str, original_name: str = '') -> List[Drug]:
        """보험코드로 검색"""
        drugs = []
        
        try:
            # 검색창 입력
            search_selector = 'input[placeholder="품목명/보험코드 입력"]'
            if not self.wait_and_fill(search_selector, insurance_code):
                raise Exception("보험코드 입력 실패")
            
            # API 요청 감지 및 검색 실행
            with self.page.expect_response(lambda response: 'api' in response.url or 'search' in response.url.lower()) as response_info:
                self.page.keyboard.press('Enter')
                
            try:
                response = response_info.value
                if response.status == 200:
                    response_data = response.json()
                    
                    # API 결과 추출
                    api_results = None
                    if isinstance(response_data, list):
                        api_results = response_data
                    elif isinstance(response_data, dict):
                        for key in ['data', 'items', 'results', 'list', 'products']:
                            if key in response_data and isinstance(response_data[key], list):
                                api_results = response_data[key]
                                break
                    
                    if api_results:
                        return self._parse_api_results(api_results, insurance_code)
                        
            except Exception:
                pass
                    
        except Exception as e:
            print(f"백제약품 검색 오류 ({insurance_code}): {e}")
        
        return drugs
    
    def _parse_api_results(self, api_data, insurance_code):
        """직접 API 데이터에서 모든 결과 추출"""
        drugs = []
        try:
            for item in api_data:
                if isinstance(item, dict):
                    # 필드 추출
                    drug_name = item.get('ITEM_NM', '')
                    unit = item.get('UNIT', '')
                    stock = str(item.get('AVAIL_STOCK', ''))
                    
                    if drug_name:
                        drug = self.create_drug(
                            name=drug_name,
                            insurance_code=insurance_code,
                            main_stock=stock or "정보없음",
                            unit=unit
                        )
                        drugs.append(drug)
        except Exception as e:
            print(f"API 데이터 파싱 오류: {e}")
        
        return drugs
    

    def get_all_search_results(self, insurance_codes: Dict[str, str]) -> List[Drug]:
        """모든 보험코드에 대해 검색 수행"""
        return self.search_by_insurance_codes(insurance_codes)