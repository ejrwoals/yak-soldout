import re
import json
import time
from typing import List, Dict, Optional, Tuple
from urllib.parse import urlencode
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError
from .base_scraper import BaseScraper
from models.drug_data import Drug, DistributorType


class HmpMallScraper(BaseScraper):
    """HMP몰(hmpmall.co.kr) 도매 통합 플랫폼 스크레이퍼

    HMP몰은 ~20개 입점 도매상의 재고를 통합 검색하는 플랫폼입니다.
    보험코드로 검색 후 JSON API를 호출하여 도매상별 재고를 합산합니다.
    """

    LOGIN_URL = "https://www.hmpmall.co.kr/login.do"
    SEARCH_URL = "https://www.hmpmall.co.kr/search/searchTwoStepList.do"
    SELLER_API_URL = "https://www.hmpmall.co.kr/search/SearchProductSellerListJson.do"
    HOME_URL = "https://www.hmpmall.co.kr/home.do"

    def __init__(self):
        super().__init__(DistributorType.HMPMALL)
        self.business_sido_code = "41"  # 기본값: 경기

    def login(self, page: Page, username: str, password: str, region: str = "41") -> bool:
        """HMP몰 로그인"""
        try:
            self.page = page
            self.business_sido_code = region

            self.page.goto(self.LOGIN_URL, wait_until='domcontentloaded')

            if not self.wait_and_fill('#memId', username):
                raise Exception("아이디 입력 실패")
            if not self.wait_and_fill('#memPw', password):
                raise Exception("비밀번호 입력 실패")

            # 로그인 버튼 클릭 (a 태그)
            login_selector = '#loginForm > div > div > div > div.loginArea > div.enterAccount > ul > li:nth-child(3) > a'
            try:
                self.page.wait_for_selector(login_selector, timeout=5000)
                with self.page.expect_navigation(wait_until='domcontentloaded', timeout=15000):
                    self.page.click(login_selector)
            except PlaywrightTimeoutError:
                # 네비게이션이 발생하지 않을 수 있음 (AJAX 로그인)
                self.page.click(login_selector)
                time.sleep(2)

            # 로그인 실패 체크
            if 'login' in self.page.url.lower() and 'home' not in self.page.url.lower():
                raise Exception("로그인 실패 (아이디/비밀번호 확인 필요)")

            self._handle_popups()

            self.is_logged_in = True
            print("✅ HMP몰 로그인 성공")
            return True

        except Exception as e:
            print(f"❌ HMP몰 로그인 실패: {e}")
            return False

    def search_drug(self, drug_name: str) -> List[Drug]:
        """약품명으로 직접 검색 (HMP몰은 보험코드 검색만 사용)"""
        return []

    def _search_by_insurance_code(self, insurance_code: str, original_drug_name: str = "") -> List[Drug]:
        """보험코드로 검색 → productMasterId 추출 → JSON API로 재고 합산"""
        if not self.is_logged_in or not self.page:
            raise Exception("로그인이 필요합니다")

        # 1단계: 보험코드로 검색 페이지 호출
        params = {
            'insuranceCode': insurance_code,
            'searchKeyword': insurance_code,
            'headerSearchKeyword': insurance_code,
            'makingId': 'insuranceCode',
            'skip': '1',
            'max': '20',
        }
        search_url = f"{self.SEARCH_URL}?{urlencode(params)}"

        try:
            self.page.goto(search_url, wait_until='domcontentloaded', timeout=15000)
        except PlaywrightTimeoutError:
            print(f"HMP몰 검색 페이지 로딩 타임아웃: {insurance_code}")
            return []

        time.sleep(0.5)

        # 2단계: HTML에서 productMasterId, fromGubun 추출
        product_master_id, from_gubun = self._extract_product_master_id()

        if not product_master_id:
            return []

        # 3단계: JSON API로 도매상별 재고 조회
        seller_data = self._fetch_seller_stock(product_master_id, from_gubun)

        if not seller_data:
            return []

        # 4단계: 상품 기본 정보 + 재고 합산 → Drug 객체 생성
        product_info = seller_data.get('productBasicInfo', {})
        sellers = seller_data.get('sellerSaleProductList', [])

        total_stock, available_count, total_count = self._aggregate_stock(sellers)

        # 상품 정보 추출
        product_name = product_info.get('productName', original_drug_name)
        manufacturer = product_info.get('manufacturerName', '')
        standard = product_info.get('productStandard', '')
        packing = product_info.get('packingUnit', '')
        unit = f"{standard} {packing}".strip() if standard or packing else ""

        # notes 생성 (프론트엔드에서 "N/M 업체 재고 합산" 형태로 파싱)
        if available_count > 0:
            notes = f"{available_count}/{total_count} 업체 재고 합산"
        else:
            notes = f"0/{total_count} 업체 전체 품절"

        stock_str = str(total_stock) if total_stock > 0 else "0"

        drug = self.create_drug(
            name=product_name,
            insurance_code=insurance_code,
            main_stock=stock_str,
            notes=notes,
            company=manufacturer,
            unit=unit,
        )

        return [drug]

    def _extract_product_master_id(self) -> Tuple[Optional[str], Optional[str]]:
        """검색 결과 HTML에서 productMasterId와 fromGubun 추출"""
        try:
            # JavaScript 변수에서 추출: var productMasterId = '209897';
            result = self.page.evaluate("""() => {
                // script 태그 내 변수 확인
                const scripts = document.querySelectorAll('div.search_product_list_box script');
                for (const script of scripts) {
                    const match = script.textContent.match(/var\\s+productMasterId\\s*=\\s*'(\\d+)'/);
                    if (match) return match[1];
                }
                // hidden form 필드에서 확인
                const input = document.querySelector('#searchProdubtSellerFrm input[name="productMasterId"]');
                if (input && input.value) return input.value;
                return null;
            }""")

            if not result:
                print("HMP몰 productMasterId 추출 실패 (검색 결과 없음)")
                return None, None

            product_master_id = result

            # fromGubun 추출
            from_gubun = self.page.evaluate("""() => {
                const input = document.querySelector('input[name="fromGubun"]');
                return input ? input.value : '';
            }""") or ""

            return product_master_id, from_gubun

        except Exception as e:
            print(f"HMP몰 productMasterId 추출 오류: {e}")
            return None, None

    def _fetch_seller_stock(self, product_master_id: str, from_gubun: str) -> Optional[Dict]:
        """JSON API를 호출하여 도매상별 재고 데이터 조회"""
        try:
            params = {
                'productMasterId': product_master_id,
                'fromGubun': from_gubun,
                'preProductMasterId': product_master_id,
                'businessSidoCode': self.business_sido_code,
            }
            api_url = f"{self.SELLER_API_URL}?{urlencode(params)}"

            self.page.goto(api_url, wait_until='domcontentloaded', timeout=10000)
            time.sleep(0.3)

            # JSON 응답 파싱
            content = self.page.evaluate("() => document.body.innerText")

            if not content:
                print("HMP몰 JSON API 응답이 비어있습니다")
                return None

            return json.loads(content)

        except json.JSONDecodeError as e:
            print(f"HMP몰 JSON 파싱 오류: {e}")
            return None
        except Exception as e:
            print(f"HMP몰 재고 API 호출 오류: {e}")
            return None

    def _aggregate_stock(self, sellers: List[Dict]) -> Tuple[int, int, int]:
        """모든 입점 도매상의 재고를 합산

        Returns:
            (total_stock, available_count, total_count)
        """
        total_stock = 0
        available_count = 0
        total_count = len(sellers)

        for seller in sellers:
            qty = seller.get('stockQuantity', 0)
            if isinstance(qty, int) and qty > 0:
                total_stock += qty
                available_count += 1
            elif isinstance(qty, str):
                try:
                    qty_int = int(qty.replace(',', ''))
                    if qty_int > 0:
                        total_stock += qty_int
                        available_count += 1
                except ValueError:
                    pass

        return total_stock, available_count, total_count

    def _handle_popups(self):
        """로그인 후 팝업 처리"""
        try:
            self.page.keyboard.press('Escape')
            time.sleep(0.3)

            close_selectors = [
                'button[class*="close"]',
                'button:has-text("닫기")',
                '[data-dismiss="modal"]',
                '.popup_close',
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
            print(f"HMP몰 팝업 처리 중 오류: {e}")
