from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Tuple
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError
from models.drug_data import Drug, DistributorType


class BaseScraper(ABC):
    """모든 스크래퍼의 기본 클래스"""
    
    def __init__(self, distributor_type: DistributorType):
        self.distributor_type = distributor_type
        self.page: Optional[Page] = None
        self.is_logged_in = False
    
    @abstractmethod
    def login(self, page: Page, username: str, password: str) -> bool:
        """로그인 수행 (각 사이트별로 구현)"""
        pass
    
    @abstractmethod
    def search_drug(self, drug_name: str) -> List[Drug]:
        """약품 검색 (각 사이트별로 구현)"""
        pass
    
    def set_page(self, page: Page):
        """페이지 설정"""
        self.page = page
    
    def wait_and_click(self, selector: str, timeout: int = 5000) -> bool:
        """요소 대기 후 클릭"""
        try:
            self.page.wait_for_selector(selector, timeout=timeout)
            self.page.click(selector)
            return True
        except PlaywrightTimeoutError:
            return False
        except Exception as e:
            print(f"클릭 오류 ({selector}): {e}")
            return False
    
    def wait_and_fill(self, selector: str, text: str, timeout: int = 5000) -> bool:
        """요소 대기 후 텍스트 입력"""
        try:
            self.page.wait_for_selector(selector, timeout=timeout)
            self.page.fill(selector, text)
            return True
        except PlaywrightTimeoutError:
            return False
        except Exception as e:
            print(f"입력 오류 ({selector}): {e}")
            return False
    
    def get_text_safe(self, selector: str, default: str = "") -> str:
        """안전한 텍스트 추출"""
        try:
            element = self.page.query_selector(selector)
            if element:
                text = element.text_content()
                return text.strip() if text else default
            return default
        except Exception as e:
            print(f"텍스트 추출 오류 ({selector}): {e}")
            return default
    
    def remove_popup_if_exists(self, selectors: List[str]) -> bool:
        """팝업 제거 (여러 셀렉터 시도)"""
        for selector in selectors:
            try:
                if self.page.query_selector(selector):
                    self.page.click(selector)
                    print(f"팝업 제거됨: {selector}")
                    self.page.wait_for_timeout(1000)
                    return True
            except Exception:
                continue
        return False
    
    def handle_common_popups(self):
        """범용적이고 안전한 팝업 처리"""
        try:
            # 1순위: ESC 키 (가장 안전)
            self.page.keyboard.press('Escape')
            self.page.wait_for_timeout(300)
            
            # 2순위: X 버튼들
            close_selectors = [
                'button[class*="close"]',
                '[data-dismiss="modal"]',
                'button[title*="close" i]',
                'button[aria-label*="close" i]',
                '.ui-dialog-titlebar-close'
            ]
            
            for selector in close_selectors:
                if self._safe_click_button(selector):
                    return
            
            # 3순위: 안전한 텍스트 버튼들
            safe_buttons = [
                'button:has-text("닫기")',
                'button:has-text("취소")', 
                'button:has-text("Close")',
                'button:has-text("Cancel")'
            ]
            
            for selector in safe_buttons:
                if self._safe_click_button(selector):
                    return
                    
        except Exception as e:
            print(f"공통 팝업 처리 오류: {e}")
    
    def _safe_click_button(self, selector: str) -> bool:
        """안전한 버튼 클릭"""
        try:
            element = self.page.query_selector(selector)
            if element:
                # 버튼 텍스트 안전성 검사
                button_text = element.text_content() or ""
                if self._is_safe_button_text(button_text):
                    element.click(timeout=300, force=True)
                    print(f"안전한 팝업 버튼 클릭: {button_text.strip()}")
                    self.page.wait_for_timeout(300)
                    return True
        except Exception:
            pass
        return False
    
    def _is_safe_button_text(self, text: str) -> bool:
        """버튼 텍스트 안전성 검사"""
        if not text:
            return True  # 텍스트가 없으면 X 버튼 등으로 간주
        
        text_lower = text.strip().lower()
        
        # 위험한 키워드들
        dangerous_keywords = [
            '참여', '이동', '구매', '신청', '등록', '가입',
            '확인', '동의', '승인', '결제', '주문', '진행',
            'submit', 'proceed', 'continue', 'buy', 'purchase'
        ]
        
        for keyword in dangerous_keywords:
            if keyword in text_lower:
                return False
        
        return True
    
    def normalize_stock_value(self, stock_text: str) -> str:
        """재고 값 정규화"""
        if not stock_text:
            return "품절"
        
        stock_text = stock_text.strip()
        
        # 0 또는 빈 값은 품절로 처리
        if stock_text in ['0', '', '-']:
            return "품절"
        
        return stock_text
    
    def clean_drug_name(self, name: str) -> str:
        """약품명 정리 (줄바꿈 제거 등)"""
        if not name:
            return ""
        
        return name.replace('\n', ' ').strip()
    
    def extract_insurance_code(self, text: str) -> str:
        """보험코드 추출 및 정리"""
        if not text:
            return ""
        
        return text.strip()
    
    def create_drug(self, name: str, insurance_code: str, main_stock: str, 
                   incheon_stock: str = "-", notes: str = "-", company: str = "", unit: str = "") -> Drug:
        """Drug 객체 생성"""
        return Drug(
            name=self.clean_drug_name(name),
            insurance_code=self.extract_insurance_code(insurance_code),
            distributor=self.distributor_type,
            main_stock=self.normalize_stock_value(main_stock),
            incheon_stock=self.normalize_stock_value(incheon_stock),
            notes=notes,
            company=company,
            unit=unit,
            is_excluded_from_alert=False
        )
    
    def batch_search_drugs(self, drug_names: List[str], 
                          exclusion_list: List[str] = None) -> Tuple[List[Drug], List[Drug], List[str]]:
        """약품 일괄 검색"""
        if exclusion_list is None:
            exclusion_list = []
        
        found_drugs = []
        soldout_drugs = []
        errors = []
        
        for drug_name in drug_names:
            try:
                print(f"검색 중: {drug_name} ({self.distributor_type.value})")
                
                # 검색 수행
                search_results = self.search_drug(drug_name)
                
                for drug in search_results:
                    # 알림 제외 목록 확인
                    drug.is_excluded_from_alert = self._is_in_exclusion_list(
                        drug.name, exclusion_list
                    )
                    
                    # 재고 여부에 따라 분류
                    if drug.has_stock():
                        found_drugs.append(drug)
                    else:
                        soldout_drugs.append(drug)
                
            except Exception as e:
                error_msg = f"{drug_name}: {self.distributor_type.value} 검색 실패 - {str(e)}"
                errors.append(error_msg)
                print(error_msg)
        
        return found_drugs, soldout_drugs, errors
    
    def _is_in_exclusion_list(self, drug_name: str, exclusion_list: List[str]) -> bool:
        """알림 제외 목록에 있는지 확인"""
        for exclusion in exclusion_list:
            if '@' in exclusion:
                try:
                    excluded_name = exclusion.split('@')[1].strip()
                    if excluded_name == drug_name:
                        return True
                except IndexError:
                    continue
        return False
