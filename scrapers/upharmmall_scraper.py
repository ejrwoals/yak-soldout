import time
from typing import List, Dict
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError
from .base_scraper import BaseScraper
from models.drug_data import Drug, DistributorType


class UpharmMallScraper(BaseScraper):
    """유팜몰(upharmmall.co.kr) 도매상 스크레이퍼

    ASP.NET 기반 사이트로, XHR(AJAX)을 통해 검색 결과를 로드합니다.
    보험코드를 이용하여 약품을 검색하고 HTML 테이블에서 결과를 파싱합니다.
    """

    LOGIN_URL = "https://www.upharmmall.co.kr/Member/Login.aspx"
    ORDER_URL = "https://www.upharmmall.co.kr/WosN/Shop/Cust/SimpleOrder"

    # 결과 테이블 셀렉터
    ROW_SELECTOR = 'tr[id^="tr_"]'

    def __init__(self):
        super().__init__(DistributorType.UPHARMMALL)

    def login(self, page: Page, username: str, password: str) -> bool:
        """유팜몰 로그인"""
        try:
            self.page = page

            # 로그인 페이지 이동
            self.page.goto(self.LOGIN_URL, wait_until='domcontentloaded')

            # 아이디/비밀번호 입력
            if not self.wait_and_fill('#ctl00_ContentPlaceHolder1_txtUserID', username):
                raise Exception("아이디 입력 실패")
            if not self.wait_and_fill('#ctl00_ContentPlaceHolder1_txtPwd', password):
                raise Exception("비밀번호 입력 실패")

            # 로그인 버튼 클릭 (ASP.NET postback → 페이지 전환 발생)
            login_btn = self.page.query_selector('#ctl00_ContentPlaceHolder1_ibtnLogin')
            if login_btn:
                with self.page.expect_navigation(wait_until='domcontentloaded', timeout=15000):
                    login_btn.click()
            else:
                with self.page.expect_navigation(wait_until='domcontentloaded', timeout=15000):
                    self.page.keyboard.press('Enter')

            print(f"🌐 유팜몰 로그인 후 URL: {self.page.url}")

            # 로그인 실패 체크 (로그인 페이지에 머물러 있으면 실패)
            if 'Login.aspx' in self.page.url:
                raise Exception("로그인 실패 (아이디/비밀번호 확인 필요)")

            # 주문 페이지로 이동
            if not self._ensure_order_page():
                raise Exception("로그인 후 주문 페이지 진입 실패")

            self.is_logged_in = True
            print("✅ 유팜몰 로그인 성공")
            return True

        except Exception as e:
            print(f"❌ 유팜몰 로그인 실패: {e}")
            return False

    def search_drug(self, drug_name: str) -> List[Drug]:
        """약품명으로 직접 검색 (유팜몰은 보험코드 검색만 사용하므로 빈 리스트 반환)"""
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
                print(f"유팜몰 검색 오류 ({original_name}): {e}")
                continue

        return all_drugs

    def _search_by_insurance_code(self, insurance_code: str, original_drug_name: str = "") -> List[Drug]:
        """보험코드로 검색"""
        if not self.is_logged_in or not self.page:
            raise Exception("로그인이 필요합니다")

        if not self._ensure_order_page():
            raise Exception("주문 페이지 접근 실패")

        # 검색창에 보험코드 입력
        if not self.wait_and_fill('#itemName', insurance_code):
            raise Exception("검색창 입력 실패")

        # 검색 버튼 클릭
        self.wait_and_click('#btnSearch')

        # AJAX 응답 + DOM 업데이트 대기
        time.sleep(0.5)
        try:
            self.page.wait_for_load_state('networkidle', timeout=5000)
        except:
            pass
        time.sleep(0.5)

        # 결과 없음 체크 (visible한 경우만 — 이 요소는 항상 DOM에 존재하므로 visibility 필수)
        try:
            no_result_elem = self.page.query_selector('td.tspace01')
            if no_result_elem and no_result_elem.is_visible():
                if '검색된 상품이 없습니다' in no_result_elem.inner_text():
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
                print(f"유팜몰 행 파싱 오류: {e}")
                continue

        return results

    def _parse_row(self, row) -> Drug:
        """개별 행에서 약품 정보 추출

        실제 셀렉터 (유팜몰):
        - 보험코드: td:nth-child(1) > a > span
        - 제약회사: td:nth-child(2) > a > span
        - 약품명: td:nth-child(3) > a > span
        - 규격: td:nth-child(5) > a > span
        - 재고: td:nth-child(7) > a > span (숫자, 0이면 품절)
        """
        # 보험코드
        insurance_code_elem = row.query_selector('td:nth-child(1) > a > span')
        insurance_code = insurance_code_elem.inner_text().strip() if insurance_code_elem else ""

        # 제약회사
        company_elem = row.query_selector('td:nth-child(2) > a > span')
        company = company_elem.inner_text().strip() if company_elem else ""

        # 약품명
        name_elem = row.query_selector('td:nth-child(3) > a > span')
        name = name_elem.inner_text().strip() if name_elem else ""

        if not name:
            return None

        # 규격
        unit_elem = row.query_selector('td:nth-child(5) > a > span')
        unit = unit_elem.inner_text().strip() if unit_elem else ""

        # 재고 (숫자, 0이면 품절)
        stock = ""
        stock_elem = row.query_selector('td:nth-child(7) > a > span')
        if stock_elem:
            stock = stock_elem.inner_text().strip()

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
            search_btn = self.page.query_selector('#btnSearch')
            if search_btn:
                return True
        except Exception:
            pass

        # 주문 페이지로 이동 (ERR_ABORTED 대비 재시도)
        for attempt in range(2):
            try:
                self.page.goto(self.ORDER_URL, wait_until='domcontentloaded', timeout=15000)

                # 검색 버튼 확인
                self.page.wait_for_selector('#btnSearch', timeout=5000)
                print("유팜몰 주문 페이지 이동 완료")
                return True
            except Exception as e:
                if attempt == 0:
                    print(f"유팜몰 주문 페이지 이동 재시도... ({e})")
                    time.sleep(1)
                else:
                    print(f"유팜몰 주문 페이지 이동 실패: {e}")
                    return False

    def _handle_popups(self):
        """팝업 처리 (유팜몰은 로그인 후 팝업 없음)"""
        pass
