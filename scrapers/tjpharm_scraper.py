import time
from typing import List, Dict
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError
from .base_scraper import BaseScraper
from scrapers.drug_data import Drug, DistributorType


class TjpharmScraper(BaseScraper):
    """티제이팜(TJP) 웹사이트 스크래퍼 (브라우저 컨텍스트 fetch API 기반)"""

    BASE_URL = "https://tjp.co.kr"

    def __init__(self):
        super().__init__(DistributorType.TJPHARM)

    def login(self, page: Page, username: str, password: str) -> bool:
        """티제이팜 로그인"""
        try:
            self.page = page

            # 로그인 페이지 이동
            self.page.goto(f"{self.BASE_URL}/login.php?login_p=2")
            self.page.wait_for_load_state("domcontentloaded", timeout=10000)

            # 아이디/비밀번호 입력
            if not self.wait_and_fill('input[name="userid"]', username):
                raise Exception("아이디 입력 실패")
            if not self.wait_and_fill('input[name="userpwd"]', password):
                raise Exception("비밀번호 입력 실패")

            # Enter로 로그인 제출
            self.page.keyboard.press("Enter")

            # 로그인 후 공지사항 페이지 리다이렉트 대기
            try:
                self.page.wait_for_url("**/Notices/**", timeout=10000)
            except PlaywrightTimeoutError:
                raise Exception("로그인 후 페이지 이동 실패")

            # 주문 페이지로 이동 (검색 세션 상태 확보)
            self.page.goto(f"{self.BASE_URL}/Order/")
            self.page.wait_for_load_state("domcontentloaded", timeout=10000)

            self.is_logged_in = True
            return True

        except Exception as e:
            print(f"티제이팜 로그인 오류: {e}")
            return False

    def search_drug(self, drug_name: str) -> List[Drug]:
        """단일 약품명 검색 (티제이팜은 보험코드 기반이므로 빈 리스트 반환)"""
        return []

    def open_for_user_interaction(self, query: str, original_drug_name: str = "") -> None:
        """바로가기용: /Order/ 페이지에서 검색창 입력 + 검색 버튼 클릭까지."""
        if not self.is_logged_in or not self.page:
            raise RuntimeError("로그인이 필요합니다")
        # login()에서 이미 /Order/로 이동한 상태
        if not self.wait_and_fill('#search_name_2', query):
            raise RuntimeError("검색창 입력 실패")
        self.wait_and_click('#search_div_1 > div:nth-child(3) > button')
        self._wait_search_settled('#table_id_1')

    def search_by_insurance_codes(self, insurance_codes: Dict[str, str]) -> List[Drug]:
        """보험코드로 약품 일괄 검색"""
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
                print(f"티제이팜 검색 오류 ({original_name}): {e}")

        return all_drugs

    def _search_by_insurance_code(self, insurance_code: str, original_name: str = '') -> List[Drug]:
        """보험코드로 단일 검색 (브라우저 컨텍스트 내 fetch 사용)

        티제이팜은 보험코드를 name 필드에 넣고 hiCode는 비워두는 방식으로 검색
        """
        try:
            timestamp = int(time.time())
            url = f"{self.BASE_URL}/Order/item_api.php?b86a3dd3={timestamp}"

            response_data = self.page.evaluate("""async ([url, insuranceCode]) => {
                const body = new URLSearchParams();
                body.append('makerName', '');
                body.append('name', insuranceCode);
                body.append('hiCode', '');

                const res = await fetch(url, {
                    method: 'POST',
                    credentials: 'include',
                    headers: {
                        'Content-Type': 'application/x-www-form-urlencoded',
                        'X-Requested-With': 'XMLHttpRequest',
                        'Accept': 'application/json, text/javascript, */*; q=0.01'
                    },
                    body: body.toString()
                });
                const text = await res.text();
                try {
                    return {ok: res.ok, status: res.status, data: JSON.parse(text)};
                } catch(e) {
                    return {ok: res.ok, status: res.status, parseError: e.message, raw: text.substring(0, 300)};
                }
            }""", [url, insurance_code])

            if not response_data or not response_data.get("ok"):
                return []

            data = response_data.get("data", {})
            if not data or data.get("StatusCode") != 200:
                return []

            # HiCode로 필터링하여 정확한 보험코드 약품만 반환
            result_set = [
                item for item in data.get("ResultSet", [])
                if str(item.get("HiCode", "")) == str(insurance_code)
            ]
            return self._parse_results(result_set, insurance_code)

        except Exception as e:
            print(f"티제이팜 검색 오류 ({insurance_code}): {e}")
            return []

    def _parse_results(self, result_set: list, insurance_code: str) -> List[Drug]:
        """API 결과에서 Drug 목록 추출"""
        drugs = []
        for item in result_set:
            if not isinstance(item, dict):
                continue

            drug_name = item.get("ItemName", "")
            if not drug_name:
                continue

            inv = (
                (item.get("InvQty") or 0)
                + (item.get("InvQty2") or 0)
                + (item.get("InvQty3") or 0)
                + (item.get("InvQty4") or 0)
            )

            drug = self.create_drug(
                name=drug_name,
                insurance_code=item.get("HiCode", insurance_code),
                main_stock=str(inv) if inv > 0 else "0",
                unit=item.get("ItemSize", ""),
                company=item.get("MkSName", ""),
            )
            drugs.append(drug)

        return drugs
