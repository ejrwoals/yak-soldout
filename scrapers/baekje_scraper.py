from typing import List, Dict
from urllib.parse import urlencode
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError
from .base_scraper import BaseScraper
from models.drug_data import Drug, DistributorType


class BaekjeScraper(BaseScraper):
    """백제약품 웹사이트 스크래퍼"""

    def __init__(self):
        super().__init__(DistributorType.BAEKJE)
        self.base_url = "https://www.ibjp.co.kr"
        self.username = ""

    def login(self, page: Page, username: str, password: str) -> bool:
        """백제약품 로그인"""
        try:
            self.page = page
            self.username = username

            # 로그인 페이지로 이동
            self.page.goto(f"{self.base_url}/dist/login")
            self.page.wait_for_load_state('domcontentloaded', timeout=10000)

            # 로그인 폼 입력 (placeholder 기반 selector — 동적 ID 대응)
            id_selector = 'input[placeholder="아이디를 입력해 주세요"]'
            if not self.wait_and_fill(id_selector, username):
                raise Exception("아이디 입력 실패")

            pwd_selector = 'input[placeholder="비밀번호를 입력해 주세요"]'
            if not self.wait_and_fill(pwd_selector, password):
                raise Exception("비밀번호 입력 실패")

            # 로그인 버튼 클릭
            self.page.keyboard.press('Enter')

            # SPA 페이지 전환 대기 — URL 또는 검색창 등장으로 확인
            try:
                self.page.wait_for_url("**/dist/comOrd**", timeout=10000)
            except PlaywrightTimeoutError:
                raise Exception("로그인 후 페이지 이동 실패")

            # 로그인 성공 여부 확인: 검색창 등장 대기
            main_search_selector = 'input[placeholder="품목명/보험코드 입력"]'
            try:
                self.page.wait_for_selector(main_search_selector, timeout=5000, state='visible')
                print("로그인 성공 확인: 메인 검색창 발견")
            except PlaywrightTimeoutError:
                raise Exception("로그인 후 메인 페이지 확인 실패")

            # sessionStorage에서 JWT 인증 토큰 추출 (Quasar 프레임워크)
            raw_token = self.page.evaluate("""() => {
                const token = sessionStorage.getItem('accessToken');
                return token || null;
            }""")

            if raw_token and '|' in raw_token:
                self.auth_token = raw_token.split('|', 1)[1]
            else:
                self.auth_token = raw_token

            if not self.auth_token:
                raise Exception("인증 토큰 추출 실패")

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

    def open_for_user_interaction(self, query: str, original_drug_name: str = "") -> None:
        """바로가기용: 로그인 직후 도달하는 Quasar SPA 검색창에 query fill + Enter.

        백제는 JWT 기반 SPA지만 검색창에 Enter를 주면 SPA가 자체적으로
        API 호출 + 결과 렌더링을 수행한다. (결과 파싱은 여기서 하지 않음)
        """
        if not self.is_logged_in or not self.page:
            raise RuntimeError("로그인이 필요합니다")
        search_selector = 'input[placeholder="품목명/보험코드 입력"]'
        try:
            self.page.wait_for_selector(search_selector, timeout=5000, state='visible')
        except Exception:
            pass
        if not self.wait_and_fill(search_selector, query):
            # fill 실패해도 창은 열려있으므로 치명적 아님 — settle만 하고 반환
            self._wait_search_settled()
            return
        self.page.keyboard.press('Enter')
        self._wait_search_settled()
    
    def _search_by_insurance_code(self, insurance_code: str, original_name: str = '') -> List[Drug]:
        """보험코드로 직접 API 호출하여 검색 (브라우저 컨텍스트 내 fetch 사용)"""
        try:
            params = {
                "keyword": insurance_code,
                "custCd": self.username,
                "makerNm": "",
                "history": "N",
                "excludingOutOfOtock": "N",
                "custGbCd": "01",
                "ordMakerCd": "",
                "userGbCd": "30",
                "ing": "N",
                "eff": "N",
                "ingno": "AAAAAAAAAAAAA",
                "effno": "AAAAAAAAAAAAA",
                "searchAll": "Y",
                "professionalYn": "N",
                "generalYn": "N",
                "paymentYn": "N",
                "nonPaymentYn": "N",
                "searchOption": "0",
            }
            api_url = f"{self.base_url}/ord/itemSearch?{urlencode(params)}"

            # 브라우저 컨텍스트 내에서 fetch 호출 (JWT 토큰 포함)
            response_data = self.page.evaluate("""async ([url, token]) => {
                const res = await fetch(url, {
                    credentials: 'include',
                    headers: token ? { 'Authorization': 'Bearer ' + token } : {}
                });
                if (!res.ok) return null;
                return await res.json();
            }""", [api_url, self.auth_token or ''])

            if isinstance(response_data, list):
                return self._parse_api_results(response_data, insurance_code)

        except Exception as e:
            print(f"백제약품 검색 오류 ({insurance_code}): {e}")

        return []
    
    def _parse_api_results(self, api_data, insurance_code):
        """API 응답 데이터에서 약품 정보 추출"""
        drugs = []
        try:
            for item in api_data:
                if not isinstance(item, dict):
                    continue

                drug_name = item.get('ITEM_NM', '')
                if not drug_name:
                    continue

                unit = item.get('UNIT', '')
                stock = str(item.get('AVAIL_STOCK', ''))
                bohum_cd = item.get('BOHUM_CD', insurance_code)
                maker_nm = item.get('MAKER_NM', '')

                drug = self.create_drug(
                    name=drug_name,
                    insurance_code=bohum_cd or insurance_code,
                    main_stock=stock or "정보없음",
                    unit=unit,
                    company=maker_nm,
                )
                drugs.append(drug)
        except Exception as e:
            print(f"API 데이터 파싱 오류: {e}")

        return drugs
    

    def get_all_search_results(self, insurance_codes: Dict[str, str]) -> List[Drug]:
        """모든 보험코드에 대해 검색 수행"""
        return self.search_by_insurance_codes(insurance_codes)