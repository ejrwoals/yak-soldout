import time
from typing import List, Dict
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError
from .base_scraper import BaseScraper
from models.drug_data import Drug, DistributorType


class GeowebScraper(BaseScraper):
    """지오영 웹사이트 스크래퍼"""
    
    def __init__(self):
        super().__init__(DistributorType.GEOWEB)
        self.base_url = "https://order.geoweb.kr"
        self.insurance_code_dict = {}  # 보험코드 매핑 (백제 검색용)
    
    def login(self, page: Page, username: str, password: str) -> bool:
        """지오영 로그인"""
        try:
            self.page = page
            
            # 로그인 페이지로 이동
            self.page.goto(f"{self.base_url}/Member/Login")
            
            # 로그인 폼 입력
            if not self.wait_and_fill('#LoginID', username):
                raise Exception("아이디 입력 실패")
            
            if not self.wait_and_fill('#Password', password):
                raise Exception("비밀번호 입력 실패")
            
            # 로그인 버튼 클릭 (Enter 키로 제출)
            self.page.keyboard.press('Enter')
            # 로그인 후 네트워크/URL 전이 기반 대기로 전환
            self.page.wait_for_load_state('domcontentloaded', timeout=10000)
            
            # 로그인 오류 확인
            error_selector = '#baseDialog > div > section > div > div'
            try:
                if self.page.query_selector(error_selector):
                    error_text = self.get_text_safe(error_selector)
                    raise Exception(f"로그인 실패: {error_text}")
            except Exception:
                pass
            
            # 팝업 제거 (있을 때만 초단기 처리)
            self._handle_geoweb_popups()

            # 메인 페이지로 이동 확인 (실패 시 로그인 실패로 처리)
            if not self._ensure_main_page():
                raise Exception("로그인 후 메인 페이지 진입 실패")
            
            self.is_logged_in = True
            return True
            
        except Exception as e:
            print(f"지오영 로그인 오류: {e}")
            return False
    
    def search_drug(self, drug_name: str) -> List[Drug]:
        """지오영에서 약품 검색"""
        if not self.is_logged_in or not self.page:
            raise Exception("로그인이 필요합니다")

        # 메인 페이지 보장. 설문 페이지 등으로 리다이렉트된 경우 오류로 승격
        if not self._ensure_main_page():
            raise Exception("메인 페이지 확인 실패")

        # 검색창 찾기 및 입력 (실패 시 예외 전파)
        search_selector = '#txt_product'
        if not self.wait_and_fill(search_selector, drug_name):
            raise Exception("검색창 입력 실패")

        # 검색 실행
        self.page.keyboard.press('Enter')
        # 결과 영역 렌더링을 이벤트 기반으로 대기
        try:
            self.page.wait_for_selector('#tbodySearchProduct > tr', timeout=5000, state='attached')
        except Exception:
            pass

        # 팝업 제거
        self._handle_search_popups()

        # 검색 결과 파싱 (빈 리스트는 '진짜' 검색 결과 없음)
        return self._parse_search_results(drug_name)
    
    def _handle_geoweb_popups(self):
        """지오영 범용 팝업 처리 - 안전하고 범용적인 접근"""
        try:
            # 1순위: ESC 키로 모달 닫기 시도 (가장 안전)
            self.page.keyboard.press('Escape')
            time.sleep(0.5)
            
            # 2순위: X 버튼 (titlebar close button)
            close_buttons = [
                '.ui-dialog-titlebar-close',
                '.ui-dialog-close',
                'button[title="Close"]',
                'button[aria-label="Close"]'
            ]
            
            for selector in close_buttons:
                if self._try_click_safe(selector, "X 버튼"):
                    return
            
            # 3순위: 안전한 텍스트 기반 버튼들 (우선순위 순)
            safe_text_buttons = [
                'button:has-text("닫기")',
                'button:has-text("취소")',
                'button:has-text("다시 열지 않기")',
                'button:has-text("오늘 하루 열지 않기")',
                '.btn_not_open'
            ]
            
            for selector in safe_text_buttons:
                if self._try_click_with_safety_check(selector):
                    return
                    
        except Exception as e:
            print(f"팝업 처리 중 오류: {e}")
    
    def _try_click_safe(self, selector: str, description: str = "") -> bool:
        """안전한 클릭 시도"""
        try:
            element = self.page.query_selector(selector)
            if element:
                element.click(timeout=300, force=True)
                print(f"팝업 제거됨 ({description}): {selector}")
                time.sleep(0.3)
                return True
        except Exception:
            pass
        return False
    
    def _try_click_with_safety_check(self, selector: str) -> bool:
        """위험한 버튼 필터링 후 클릭"""
        try:
            element = self.page.query_selector(selector)
            if not element:
                return False
            
            # 버튼 텍스트 확인
            button_text = element.text_content() or ""
            button_text = button_text.strip().lower()
            
            # 위험한 키워드 필터링
            dangerous_keywords = [
                '참여', '이동', '구매', '신청', '등록', '가입',
                '확인', '동의', '승인', '결제', '주문'
            ]
            
            for keyword in dangerous_keywords:
                if keyword in button_text:
                    print(f"위험한 버튼 스킵: {button_text}")
                    return False
            
            # 안전한 버튼으로 판단되면 클릭
            element.click(timeout=300, force=True)
            print(f"팝업 제거됨 (안전 버튼): {button_text}")
            time.sleep(0.3)
            return True
            
        except Exception:
            pass
        return False
    
    def _handle_search_popups(self):
        """검색 중 팝업 처리 - 범용적 접근"""
        # 공통 팝업 처리 로직 재사용
        self.handle_common_popups()
    
    def _parse_search_results(self, original_drug_name: str) -> List[Drug]:
        """검색 결과 파싱"""
        drugs = []
        
        try:
            # 첫 번째 결과만 처리 (Legacy 코드와 동일)
            row_selector = '#tbodySearchProduct > tr:nth-child(1)'
            
            # 결과가 있는지 확인
            if not self.page.query_selector(row_selector):
                return drugs
            
            # 약품 정보 추출
            name_selector = f'{row_selector} > td.proName'
            stock_selector = f'{row_selector} > td.stock'
            code_selector = f'{row_selector} > td.code'
            company_selector = f'{row_selector} > td.phaCompany > span'
            
            drug_name = self.get_text_safe(name_selector)
            main_stock = self.get_text_safe(stock_selector)
            insurance_code = self.get_text_safe(code_selector)
            company = self.get_text_safe(company_selector)
            
            if not drug_name:
                return drugs
            
            # 타센터 재고 확인
            incheon_stock = self._get_incheon_stock()
            
            # 비고 정보
            notes = self._get_notes()
            
            # 보험코드 매핑 저장 (백제 검색용)
            if insurance_code:
                self.insurance_code_dict[insurance_code] = original_drug_name
            
            # Drug 객체 생성
            drug = self.create_drug(
                name=drug_name,
                insurance_code=insurance_code,
                main_stock=main_stock,
                incheon_stock=incheon_stock,
                notes=notes,
                company=company
            )
            
            drugs.append(drug)
            
        except Exception as e:
            print(f"지오영 검색 결과 파싱 오류: {e}")
        
        return drugs
    
    def _get_incheon_stock(self) -> str:
        """타센터 재고 확인"""
        try:
            incheon_selector = '#div-product-info > div.another_center_board.board_wrap > div > table > tbody > tr > td:nth-child(2)'
            incheon_stock = self.get_text_safe(incheon_selector, "0")
            return incheon_stock if incheon_stock != "0" else "품절"
        except Exception:
            return "품절"
    
    def _get_notes(self) -> str:
        """비고 정보 추출"""
        try:
            notes_selector = '#product-detail-note'
            return self.get_text_safe(notes_selector, "-")
        except Exception:
            return "-"
    
    def get_insurance_code_dict(self) -> Dict[str, str]:
        """백제 검색용 보험코드 딕셔너리 반환"""
        return self.insurance_code_dict.copy()
    
    def clear_insurance_code_dict(self):
        """보험코드 딕셔너리 초기화"""
        self.insurance_code_dict.clear()
    
    def _ensure_main_page(self):
        """메인 페이지인지 확인하고, 아니면 이동"""
        search_element = "#txt_product"  # 검색창 셀렉터
        
        try:
            # 검색창이 있는지 확인 (가시성 기준)
            self.page.wait_for_selector(search_element, timeout=1500, state='visible')
            print("메인 페이지 확인됨")
            return True
        except Exception:
            print("메인 페이지가 아님. 이동 중...")
            try:
                # 메인 페이지로 이동
                self.page.goto("https://order.geoweb.kr/", wait_until="domcontentloaded")
                
                # 팝업 제거
                self._handle_geoweb_popups()
                
                # 다시 검색창 확인
                self.page.wait_for_selector(search_element, timeout=3000, state='visible')
                print("메인 페이지로 이동 완료")
                return True
            except Exception as e:
                print(f"메인 페이지 이동 실패: {e}")
                return False