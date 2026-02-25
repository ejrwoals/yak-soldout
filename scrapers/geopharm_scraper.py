from typing import List, Dict
from playwright.sync_api import Page
from scrapers.base_scraper import BaseScraper
from models.drug_data import Drug, DistributorType


class GeoPharmScraper(BaseScraper):
    """지오팜 도매상 스크레이퍼"""

    LOGIN_URL = "https://orderpharm.geo-pharm.com/login.php?url=/pharmorder/order.php"
    ORDER_URL = "https://orderpharm.geo-pharm.com/pharmorder/order.php"

    REGION_OPTIONS = {
        '01': '대구',
        '02': '대전',
        '03': '광주',
        '04': '서울'
    }

    def __init__(self):
        super().__init__(DistributorType.GEOPHARM)

    def login(self, page: Page, username: str, password: str, region: str = '01') -> bool:
        """지오팜 로그인"""
        try:
            self.page = page

            # 로그인 페이지 이동
            page.goto(self.LOGIN_URL, wait_until='networkidle')
            print(f"🌐 지오팜 로그인 페이지 로드 완료: {page.url}")

            # 지역 선택
            page.select_option('#loginarea', region)
            page.wait_for_timeout(300)
            print(f"🗺️ 지오팜 지역 선택: {region} ({self.REGION_OPTIONS.get(region, '알 수 없음')})")

            # 아이디/비밀번호 입력
            self.wait_and_fill('#user_id', username)
            self.wait_and_fill('#user_pwd', password)

            # 비밀번호 입력 후 Enter 로 로그인 (버튼 셀렉터보다 안정적)
            page.press('#user_pwd', 'Enter')

            # 페이지 전환 대기
            page.wait_for_load_state('networkidle')
            print(f"🌐 로그인 제출 후 URL: {page.url}")

            # 아직 로그인 페이지에 있으면 버튼 직접 클릭 시도
            if 'login' in page.url.lower():
                print("⚠️ 로그인 페이지 잔류 → 로그인 버튼 직접 클릭 시도")
                clicked = self.wait_and_click('input[type=submit]')
                if not clicked:
                    clicked = self.wait_and_click('#form input[type=submit]')
                page.wait_for_load_state('networkidle')
                print(f"🌐 버튼 클릭 후 URL: {page.url}")

            # 주문 페이지로 이동 (로그인 후 홈으로 가므로 직접 이동)
            page.goto(self.ORDER_URL, wait_until='networkidle')
            print(f"🌐 주문 페이지 이동 후 URL: {page.url}")

            # 검색창이 보이면 로그인 성공
            page.wait_for_selector('#item_name', state='visible', timeout=10000)

            self.is_logged_in = True
            print("✅ 지오팜 로그인 성공")
            return True

        except Exception as e:
            print(f"❌ 지오팜 로그인 실패: {e}")
            print(f"🌐 실패 시점 URL: {page.url}")
            return False

    def search_drug(self, drug_name: str) -> List[Drug]:
        """약품명으로 직접 검색 (지오팜은 보험코드 검색만 지원)"""
        return []

    def search_by_insurance_codes(self, insurance_codes: Dict[str, str]) -> List[Drug]:
        """
        보험코드로 약품 검색

        Args:
            insurance_codes: {보험코드: 약품명} 딕셔너리 (지오영에서 수집)

        Returns:
            검색 결과 Drug 리스트
        """
        results = []

        for insurance_code, drug_name in insurance_codes.items():
            try:
                drugs = self._search_by_insurance_code(insurance_code, drug_name)
                results.extend(drugs)
            except Exception as e:
                print(f"지오팜 검색 오류 ({drug_name}): {e}")
                continue

        return results

    def _ensure_order_page(self):
        """검색 페이지에 있는지 확인하고 필요시 이동"""
        try:
            self.page.wait_for_selector('#item_name', state='visible', timeout=3000)
        except Exception:
            self.page.goto(self.ORDER_URL, wait_until='networkidle')
            self.page.wait_for_selector('#item_name', state='visible', timeout=10000)

    def _search_by_insurance_code(self, insurance_code: str, original_drug_name: str) -> List[Drug]:
        """단일 보험코드로 검색"""
        self._ensure_order_page()

        # 검색창 초기화 후 보험코드 입력
        self.page.fill('#item_name', '')
        self.wait_and_fill('#item_name', insurance_code)

        # 검색 버튼 클릭 + iframe HTTP 응답 대기
        try:
            with self.page.expect_response(
                lambda r: 'sc_item_list_iframe.php' in r.url,
                timeout=10000
            ):
                self.wait_and_click('#item_list_view > input')
        except Exception as e:
            print(f"지오팜 iframe 응답 대기 실패 ({insurance_code}): {e}")

        # 렌더링 대기 (응답 수신 후 DOM 업데이트 시간 확보)
        self.page.wait_for_timeout(1500)

        # iframe 접근
        iframe = self.page.frame(name="item_list_iframe")
        if not iframe:
            print(f"지오팜: iframe을 찾을 수 없습니다 ({insurance_code})")
            return []

        # iframe 내 로딩 완료 대기
        try:
            iframe.wait_for_load_state('networkidle', timeout=5000)
        except Exception:
            pass

        # iframe 내 결과 로딩 대기 (hidden 상태도 허용)
        try:
            iframe.wait_for_selector('#SubContent', state='attached', timeout=5000)
        except Exception:
            return []

        # 결과 행 추출
        rows = iframe.query_selector_all('#SubContent table tbody tr')
        if not rows:
            rows = iframe.query_selector_all('#SubContent table tr')
        if not rows:
            return []

        # "No Data" 체크
        first_td = rows[0].query_selector('td')
        if first_td and 'No Data' in (first_td.inner_text() or ''):
            return []

        results = []
        for row in rows:
            try:
                company_elem = row.query_selector('td:nth-child(2)')
                company_raw = company_elem.inner_text().strip() if company_elem else ""
                # <b> 태그 포함 텍스트 추출 (inner_text가 태그 내 텍스트 반환)
                company = company_raw

                name_elem = row.query_selector('td:nth-child(3)')
                name = name_elem.inner_text().strip() if name_elem else ""

                unit_elem = row.query_selector('td:nth-child(4)')
                unit = unit_elem.inner_text().strip() if unit_elem else ""

                code_elem = row.query_selector('td:nth-child(5)')
                code = code_elem.inner_text().strip() if code_elem else insurance_code

                stock_elem = row.query_selector('td:nth-child(6)')
                stock = stock_elem.inner_text().strip() if stock_elem else ""

                # 약품명이 없는 행은 스킵
                if not name:
                    continue

                stock = self.normalize_stock_value(stock)

                drug = self.create_drug(
                    name=name,
                    insurance_code=code,
                    main_stock=stock,
                    company=company,
                    unit=unit
                )
                results.append(drug)

            except Exception as e:
                print(f"지오팜 행 파싱 오류: {e}")
                continue

        return results
