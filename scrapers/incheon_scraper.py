from typing import List, Dict
from playwright.sync_api import Page
from scrapers.base_scraper import BaseScraper
from models.drug_data import Drug, DistributorType


class IncheonScraper(BaseScraper):
    """인천약품 도매상 스크레이퍼"""

    LOGIN_URL = "https://inchunpharm.com/Homepage/contents/login/login.asp"

    def __init__(self):
        super().__init__(DistributorType.INCHEON)

    def login(self, page: Page, username: str, password: str) -> bool:
        """인천약품 로그인"""
        try:
            # 페이지 설정
            self.page = page

            # 로그인 페이지 이동
            page.goto(self.LOGIN_URL, wait_until='networkidle')

            # 아이디/비밀번호 입력
            self.wait_and_fill('#tx_id', username)
            self.wait_and_fill('#tx_pw', password)

            # 로그인 버튼 클릭
            self.wait_and_click('#frmLogin > div.login_btn > a')

            # 로그인 성공 확인 (검색창이 보이면 성공)
            page.wait_for_selector('#tx_insucd', state='visible', timeout=10000)

            self.is_logged_in = True
            print("✅ 인천약품 로그인 성공")
            return True

        except Exception as e:
            print(f"❌ 인천약품 로그인 실패: {e}")
            return False

    def search_by_insurance_codes(self, insurance_codes: Dict[str, str]) -> List[Drug]:
        """
        보험코드로 약품 검색 (백제약품과 유사한 방식)

        Args:
            insurance_codes: {약품명: 보험코드} 딕셔너리 (지오영에서 수집)

        Returns:
            검색 결과 Drug 리스트
        """
        results = []

        for drug_name, insurance_code in insurance_codes.items():
            try:
                drugs = self._search_by_insurance_code(insurance_code, drug_name)
                results.extend(drugs)
            except Exception as e:
                print(f"인천약품 검색 오류 ({drug_name}): {e}")
                continue

        return results

    def _search_by_insurance_code(self, insurance_code: str, original_drug_name: str) -> List[Drug]:
        """단일 보험코드로 검색"""
        # 검색창에 보험코드 입력
        self.wait_and_fill('#tx_insucd', insurance_code)

        # 조회 버튼 클릭
        self.wait_and_click('#btn_search2')

        # 페이지 로딩 대기 (네트워크 안정화)
        self.page.wait_for_load_state('networkidle')

        # 결과 없음 체크
        try:
            no_result_elem = self.page.query_selector(
                '#frmOrder > fieldset:nth-child(1) > div > table > tbody > tr > td'
            )
            if no_result_elem and '제품이 없습니다' in no_result_elem.inner_text():
                return []
        except:
            pass

        # 모든 행 추출
        rows = self.page.query_selector_all(
            '#frmOrder > fieldset:nth-child(1) > div > table > tbody > tr'
        )

        results = []
        for row in rows:
            try:
                # 각 필드 추출 (ElementHandle에서 직접 텍스트 추출)
                insurance_code_elem = row.query_selector('td:nth-child(1)')
                insurance_code_text = insurance_code_elem.inner_text().strip() if insurance_code_elem else ""

                company_elem = row.query_selector('td:nth-child(2)')
                company = company_elem.inner_text().strip() if company_elem else ""

                name_elem = row.query_selector('td.td_nm.N > a')
                name = name_elem.inner_text().strip() if name_elem else ""

                unit_elem = row.query_selector('td:nth-child(4)')
                unit = unit_elem.inner_text().strip() if unit_elem else ""

                stock_elem = row.query_selector('td:nth-child(7)')
                stock = stock_elem.inner_text().strip() if stock_elem else ""

                # 재고 정규화 (0 → "품절")
                stock = self.normalize_stock_value(stock)

                # Drug 객체 생성
                drug = self.create_drug(
                    name=name,
                    insurance_code=insurance_code_text,
                    main_stock=stock,
                    company=company,
                    unit=unit
                )

                results.append(drug)

            except Exception as e:
                print(f"인천약품 행 파싱 오류: {e}")
                continue

        return results

    def search_drug(self, drug_name: str) -> List[Drug]:
        """
        약품명으로 직접 검색 (현재 인천약품은 보험코드 검색만 지원)
        백제약품과 동일하게 빈 리스트 반환
        """
        return []
