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
        """백제약품 로그인 (리뉴얼된 사이트용)"""
        try:
            self.page = page
            
            # 로그인 페이지로 이동
            self.page.goto(f"{self.base_url}/login.act")
            
            # 페이지 로딩 대기
            self.page.wait_for_load_state('domcontentloaded', timeout=10000)
            
            # 로그인 폼 입력 (placeholder 기반 셀렉터 사용)
            id_selector = 'input[placeholder="아이디를 입력해 주세요"]'
            if not self.wait_and_fill(id_selector, username):
                raise Exception("아이디 입력 실패")
            
            pwd_selector = 'input[placeholder="비밀번호를 입력해 주세요"]'
            if not self.wait_and_fill(pwd_selector, password):
                raise Exception("비밀번호 입력 실패")
            
            # 로그인 버튼 클릭 (Enter 키로 제출)
            self.page.keyboard.press('Enter')
            self.page.wait_for_load_state('domcontentloaded', timeout=10000)
            
            # 로그인 오류 확인 (가능한 오류 메시지 체크)
            error_selectors = [
                'div:has-text("아이디")',
                'div:has-text("비밀번호")', 
                'div:has-text("로그인")',
                'div:has-text("실패")',
                '.error',
                '.alert'
            ]
            
            for error_selector in error_selectors:
                try:
                    if self.page.query_selector(error_selector):
                        error_text = self.get_text_safe(error_selector)
                        if any(keyword in error_text for keyword in ['실패', '오류', '잘못', '확인']):
                            raise Exception(f"로그인 실패: {error_text}")
                except Exception:
                    continue
            
            # 로그인 성공 여부 확인 (메인 페이지의 특징적 요소 찾기)
            # 검색창 관련 요소들을 시도해보고, 하나라도 있으면 성공으로 간주
            success_indicators = [
                'input[placeholder*="검색"]',  # 검색 관련 입력 필드
                'input[placeholder*="상품"]',  # 상품 검색 필드  
                'input[placeholder*="약품"]',  # 약품 검색 필드
                'select',  # 검색 모드 선택 드롭다운
                'button:has-text("검색")',  # 검색 버튼
                '.search',  # 검색 관련 클래스
                '#search'   # 검색 관련 ID
            ]
            
            login_success = False
            for indicator in success_indicators:
                try:
                    self.page.wait_for_selector(indicator, timeout=3000)
                    print(f"로그인 성공 확인: {indicator} 요소 발견")
                    login_success = True
                    break
                except PlaywrightTimeoutError:
                    continue
            
            if not login_success:
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
        # 백제는 보험코드 기반 검색이 주 방식이므로 개별 약품명 검색은 구현하지 않음
        return []
    
    def _search_by_insurance_code(self, insurance_code: str) -> List[Drug]:
        """보험코드로 검색 (리뉴얼된 사이트용 - 디버깅 강화)"""
        drugs = []
        
        try:
            # 1. 검색창 찾기 및 입력
            search_selector = 'input[placeholder="품목명/보험코드 입력"]'
            
            if not self.wait_and_fill(search_selector, insurance_code):
                raise Exception("보험코드 입력 실패")
            
            # 2. 검색 실행
            self.page.keyboard.press('Enter')
            self.page.wait_for_timeout(3000)
            
            # 3. 재고 테이블만 선택 (상단 통합주문 테이블, 출고 이력 테이블 제외)
            stock_table_selectors = [
                'div.page_left > div.left_left > div:first-child tbody',  # 첫 번째 div 안의 tbody (재고 테이블)
                'div.left_left > div:first-child tbody tr',               # 백업 셀렉터
                'div:not([class*="출고"]):not([class*="이력"]) tbody tr'    # 출고/이력이 아닌 tbody
            ]
            
            stock_rows = []
            for selector in stock_table_selectors:
                try:
                    rows = self.page.query_selector_all(selector)
                    if rows:
                        stock_rows = rows
                        break
                except:
                    continue
            
            # 재고 테이블을 찾지 못한 경우 전체 테이블에서 필터링
            if not stock_rows:
                all_rows = self.page.query_selector_all('tbody tr')
                stock_rows = []
                for row in all_rows:
                    row_html = row.inner_html()
                    # 출고 이력 테이블의 특징적인 요소들로 필터링
                    if any(keyword in row_html for keyword in ['조회기간', '이력이', '출고', '유효기간']):
                        continue
                    stock_rows.append(row)
            
            # 4. 실제 데이터 행 찾기 및 파싱
            for child_index in range(1, min(len(stock_rows) + 1, 10)):  # 최대 10개 행까지 확인
                try:
                    # 패딩 행인지 확인
                    row = stock_rows[child_index - 1] if child_index <= len(stock_rows) else None
                    if not row:
                        continue
                        
                    row_html = row.inner_html()
                    if 'colspan=' in row_html and 'height: 0px' in row_html:
                        continue  # 가상 스크롤 패딩 행 건너뜀
                    
                    drug = self._parse_search_result_row_enhanced(child_index, insurance_code, row)
                    if drug:
                        drugs.append(drug)
                        
                except Exception as e:
                    print(f"   ❌ 행 {child_index} 파싱 실패: {e}")
            
        except Exception as e:
            print(f"❌ 백제약품 보험코드 검색 전체 오류 ({insurance_code}): {e}")
        
        return drugs
    
    
    def _parse_search_result_row_enhanced(self, row_index: int, insurance_code: str, row_element) -> Drug:
        """향상된 검색 결과 파싱 (실제 row 요소 사용)"""
        try:
            # 1. 약품명 추출
            name_selectors = [
                'td:nth-child(2)',        # 두 번째 td (보험코드 다음이 약품명)
                'td:nth-child(2) span',   # 두 번째 td의 span
                'td:nth-child(2) button', # 두 번째 td의 버튼 
                '.td-prd_name span',
                '.td-prd span', 
                'td span',
                'span'
            ]
            
            drug_name = ""
            for sel in name_selectors:
                try:
                    name_elem = row_element.query_selector(sel)
                    if name_elem:
                        name_text = name_elem.text_content()
                        if name_text and name_text.strip():
                            drug_name = name_text.strip()
                            break
                except:
                    continue
            
            # 시스템 메시지 필터링
            system_messages = [
                "조회기간 내의 이력이 없습니다",
                "검색된 결과가 없습니다",
                "데이터가 없습니다",
                "결과가 없습니다",
                "이력이 없습니다",
                "정보가 없습니다"
            ]
            
            if not drug_name or any(msg in drug_name for msg in system_messages):
                print(f"      ❌ 유효하지 않은 약품명 (시스템 메시지): '{drug_name}'")
                return None
            
            # 2. 재고 정보 추출 - 여러 셀렉터 시도
            stock_selectors = [
                '.td-inven p.q-table_stock',  # 품절인 경우
                '.td-inven p',                # 일반적인 경우
                'td.td-inven p',              # 백업 셀렉터
                '.q-table_stock',             # 클래스만
                'p'                           # 마지막 백업
            ]
            
            stock = ""
            for sel in stock_selectors:
                try:
                    stock_elem = row_element.query_selector(sel)
                    if stock_elem:
                        stock_text = stock_elem.text_content()
                        if stock_text and stock_text.strip():
                            stock = stock_text.strip()
                            break
                except:
                    continue
            
            # 재고 정보가 없으면 기본값
            if not stock:
                stock = "정보없음"
            
            # 3. Drug 객체 생성
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
            print(f"      ❌ 행 {row_index} 향상된 파싱 실패: {e}")
            return None

    def get_all_search_results(self, insurance_codes: Dict[str, str]) -> List[Drug]:
        """모든 보험코드에 대해 검색 수행"""
        return self.search_by_insurance_codes(insurance_codes)