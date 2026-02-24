import time
from typing import List, Dict
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError
from .base_scraper import BaseScraper
from models.drug_data import Drug, DistributorType


class BoksanScraper(BaseScraper):
    """복산(NicePharm) 도매상 스크레이퍼

    복산나이스 플랫폼(wos.nicepharm.com)은 클래식 ASP 기반으로,
    인천약품(inchunpharm.com)과 동일한 NicePharm 플랫폼을 사용합니다.
    보험코드를 이용하여 약품을 검색하고 HTML 테이블에서 결과를 파싱합니다.
    """

    LOGIN_URL = "https://wos.nicepharm.com/Contents/Main/Main9.asp"
    ORDER_URL = "https://wos.nicepharm.com/Service/Order/Order.asp"

    # 결과 테이블 셀렉터
    ROW_SELECTOR = '#frmOrder > fieldset:nth-child(2) > div > table > tbody > tr'

    def __init__(self):
        super().__init__(DistributorType.BOKSAN)

    def login(self, page: Page, username: str, password: str) -> bool:
        """복산 로그인"""
        try:
            self.page = page

            # 로그인 페이지 이동
            self.page.goto(self.LOGIN_URL, wait_until='domcontentloaded')

            # 아이디/비밀번호 입력
            if not self.wait_and_fill('#tx_id', username):
                raise Exception("아이디 입력 실패")
            if not self.wait_and_fill('#tx_pw', password):
                raise Exception("비밀번호 입력 실패")

            # 로그인 버튼 클릭 (input[type="image"])
            login_btn = self.page.query_selector('#frmLogin input[type="image"]')
            if login_btn:
                login_btn.click()
            else:
                self.page.keyboard.press('Enter')

            # 페이지 로딩 대기
            self.page.wait_for_load_state('domcontentloaded', timeout=15000)

            # 팝업 처리 (로그인 후 공지사항 등)
            self._handle_popups()

            # 주문 페이지로 이동하여 로그인 성공 확인
            if not self._ensure_order_page():
                raise Exception("로그인 후 주문 페이지 진입 실패")

            self.is_logged_in = True
            print("✅ 복산 로그인 성공")
            return True

        except Exception as e:
            print(f"❌ 복산 로그인 실패: {e}")
            return False

    def search_drug(self, drug_name: str) -> List[Drug]:
        """약품명으로 직접 검색 (복산은 보험코드 검색만 사용하므로 빈 리스트 반환)"""
        return []

    def search_by_insurance_codes(self, insurance_codes: Dict[str, str]) -> List[Drug]:
        """보험코드 딕셔너리로 약품 일괄 검색"""
        if not self.is_logged_in or not self.page:
            raise Exception("로그인이 필요합니다")

        all_drugs = []

        for insurance_code, original_name in insurance_codes.items():
            if not insurance_code.strip():
                continue

            try:
                drugs = self._search_by_insurance_code(insurance_code, original_name)
                all_drugs.extend(drugs)
            except Exception as e:
                print(f"복산 검색 오류 ({original_name}): {e}")
                continue

        return all_drugs

    def _search_by_insurance_code(self, insurance_code: str, original_drug_name: str = "") -> List[Drug]:
        """보험코드로 검색"""
        if not self.is_logged_in or not self.page:
            raise Exception("로그인이 필요합니다")

        if not self._ensure_order_page():
            raise Exception("주문 페이지 접근 실패")

        # 검색창에 보험코드 입력
        if not self.wait_and_fill('#tx_physic', insurance_code):
            raise Exception("검색창 입력 실패")

        # 조회 버튼 클릭
        self.wait_and_click('#btn_search2')

        # 페이지 로딩 대기 (form POST로 전체 페이지 리로드)
        self.page.wait_for_load_state('networkidle')

        # 결과 없음 체크
        try:
            no_result_elem = self.page.query_selector(
                f'{self.ROW_SELECTOR} > td'
            )
            if no_result_elem and '없습니다' in no_result_elem.inner_text():
                return []
        except:
            pass

        # 모든 결과 행 추출
        rows = self.page.query_selector_all(self.ROW_SELECTOR)

        results = []
        for row in rows:
            try:
                drug = self._parse_row(row)
                if drug:
                    results.append(drug)
            except Exception as e:
                print(f"복산 행 파싱 오류: {e}")
                continue

        return results

    def _parse_row(self, row) -> Drug:
        """개별 행에서 약품 정보 추출

        실제 셀렉터 (NicePharm 복산):
        - 보험코드: td:nth-child(1)
        - 제약회사: td:nth-child(2)
        - 약품명: td.td_nm.N > a
        - 규격: td:nth-child(4)
        - 재고: td:nth-child(8) (span 안에 있을 수 있음)
        """
        # 보험코드
        insurance_code_elem = row.query_selector('td:nth-child(1)')
        insurance_code = insurance_code_elem.inner_text().strip() if insurance_code_elem else ""

        # 제약회사
        company_elem = row.query_selector('td:nth-child(2)')
        company = company_elem.inner_text().strip() if company_elem else ""

        # 약품명
        name_elem = row.query_selector('td.td_nm.N > a')
        name = name_elem.inner_text().strip() if name_elem else ""

        if not name:
            return None

        # 규격
        unit_elem = row.query_selector('td:nth-child(4)')
        unit = unit_elem.inner_text().strip() if unit_elem else ""

        # 재고 (td:nth-child(8), span 안에 있을 수 있음)
        stock = ""
        stock_td = row.query_selector('td:nth-child(8)')
        if stock_td:
            stock_span = stock_td.query_selector('span')
            if stock_span:
                stock = stock_span.inner_text().strip()
            else:
                stock = stock_td.inner_text().strip()

        # 재고 정규화
        stock = self.normalize_stock_value(stock)

        # Drug 객체 생성
        drug = self.create_drug(
            name=name,
            insurance_code=insurance_code,
            main_stock=stock,
            company=company,
            unit=unit
        )

        return drug

    def _ensure_order_page(self) -> bool:
        """주문 페이지에 있는지 확인하고, 필요시 이동"""
        try:
            # 검색 버튼이 있는지 확인
            search_btn = self.page.query_selector('#btn_search2')
            if search_btn:
                return True
        except Exception:
            pass

        # 주문 페이지로 이동
        try:
            self.page.goto(self.ORDER_URL, wait_until='domcontentloaded', timeout=15000)
            self._handle_popups()

            # 검색 버튼 확인
            self.page.wait_for_selector('#btn_search2', timeout=5000)
            print("복산 주문 페이지 이동 완료")
            return True
        except Exception as e:
            print(f"복산 주문 페이지 이동 실패: {e}")
            return False

    def _handle_popups(self):
        """팝업 처리 (클래식 ASP 사이트의 팝업)"""
        try:
            # ESC로 팝업 닫기 시도
            self.page.keyboard.press('Escape')
            time.sleep(0.3)

            # 닫기 버튼들 시도
            close_selectors = [
                '.btn-popClose',
                'button:has-text("닫기")',
                'a:has-text("닫기")',
            ]

            for selector in close_selectors:
                try:
                    elements = self.page.query_selector_all(selector)
                    for elem in elements:
                        if elem.is_visible():
                            text = elem.text_content() or ""
                            if self._is_safe_button_text(text):
                                elem.click(timeout=300, force=True)
                                time.sleep(0.2)
                except Exception:
                    continue

        except Exception as e:
            print(f"복산 팝업 처리 중 오류: {e}")
