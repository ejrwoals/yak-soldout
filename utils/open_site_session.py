"""
재고 카드 '바로가기' 세션 관리

사용자가 재고 카드의 바로가기 아이콘을 클릭하면 headless=False Playwright를
띄워 자동 로그인 + 약품 검색까지 수행한 뒤 사용자에게 제어권을 넘긴다.
이후 사용자가 창을 닫거나 IDLE_TIMEOUT이 경과하면 세션을 정리한다.

PreviewSearchSession과 동일한 단일 스레드 executor 패턴을 사용한다.
"""

import asyncio
import concurrent.futures
import threading
import time

from scrapers.browser_manager import BrowserManager
from scrapers.registry import DISTRIBUTOR_REGISTRY


class OpenSiteSession:
    """바로가기 전용 headed 브라우저 세션 (동시 1개만 유지)."""

    OPEN_TIMEOUT = 60.0   # 로그인 + 검색 완료까지 허용 시간(초)
    IDLE_TIMEOUT = 600    # 10분 안전 상한(초): 사용자가 창을 닫지 않고 방치해도 정리
    WATCHDOG_INTERVAL = 30  # 워치독 점검 주기(초)

    def __init__(self):
        self._browser_mgr = None
        self._scraper = None
        self._distributor_id = None
        self._opened_at = 0.0
        self._watchdog = None
        # Playwright 동기 API는 한 스레드에서만 호출해야 안정적
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)

    # --- 동기 내부 메서드 (executor 스레드에서 실행) ---

    def _open_internal(self, app_state, distributor_id: str,
                       drug_name: str, insurance_code: str) -> dict:
        """기존 세션 정리 → 새 headed 브라우저 시작 → 로그인 → 검색"""
        # 기존 세션 정리
        self._close_internal()

        if distributor_id not in DISTRIBUTOR_REGISTRY:
            raise ValueError(f"알 수 없는 도매상: {distributor_id}")

        dist_info = DISTRIBUTOR_REGISTRY[distributor_id]
        if not dist_info.get("supports_open_site", False):
            raise ValueError(f"{dist_info['name']}은(는) 바로가기를 지원하지 않습니다")

        creds = app_state.config.get_credentials(distributor_id)
        if not creds or not creds.is_valid():
            raise ValueError("도매상 계정 정보가 설정되지 않았습니다")

        query = (insurance_code or "").strip() or (drug_name or "").strip()
        if not query:
            raise ValueError("검색어(보험코드 또는 약품명)가 필요합니다")

        # headless=False이되, 로그인/검색 동안은 화면 밖에서 작동 → 완료 후 노출
        browser_mgr = BrowserManager(headless=False, start_hidden=True)
        browser_mgr.start()

        try:
            scraper_class = dist_info["scraper_class"]
            scraper = scraper_class()
            page = browser_mgr.new_page()

            login_extra = {
                k: creds.extra.get(k, v)
                for k, v in dist_info.get("extra_params", {}).items()
            }
            if not scraper.login(page, creds.username, creds.password, **login_extra):
                raise Exception(f"{dist_info['name']} 로그인 실패")

            scraper.open_for_user_interaction(query, drug_name or "")

            # 스크래퍼의 _wait_search_settled()에서 networkidle까지 대기했으므로,
            # 여기서는 프레임 컴포지팅 안정화를 위한 짧은 settle만 더 준다.
            time.sleep(0.3)

            # 로그인 + 검색이 완료된 시점에 창을 화면으로 가져온다.
            self._reveal_window(page)
        except Exception:
            try:
                browser_mgr.stop()
            except Exception:
                pass
            raise

        # 사용자 조작 대비: 창이 닫히면 browser_mgr.browser.is_connected()가 False
        self._browser_mgr = browser_mgr
        self._scraper = scraper
        self._distributor_id = distributor_id
        self._opened_at = time.time()

        self._start_watchdog()
        print(f"🪟 바로가기 세션 시작: {dist_info['name']} ← {query!r}")

        return {
            "status": "opened",
            "distributor_id": distributor_id,
            "distributor": dist_info["name"],
            "query": query,
        }

    def _reveal_window(self, page) -> None:
        """숨겨져 있던(화면 밖) 브라우저 창을 사용자에게 노출.

        Chromium CDP Browser.setWindowBounds 로 창 위치/크기/상태를 재설정하고
        page.bring_to_front()로 포커스를 가져온다. 실패해도 치명적이지 않으므로
        예외는 삼킨다(최악의 경우 창이 계속 숨겨져 있을 뿐, 사용자가 세션을 닫으면 정리됨).
        """
        try:
            cdp = page.context.new_cdp_session(page)
            try:
                info = cdp.send("Browser.getWindowForTarget")
                window_id = info.get("windowId")
                if window_id is not None:
                    cdp.send("Browser.setWindowBounds", {
                        "windowId": window_id,
                        "bounds": {
                            "left": 120,
                            "top": 80,
                            "width": 1280,
                            "height": 800,
                            "windowState": "normal",
                        },
                    })
            finally:
                try:
                    cdp.detach()
                except Exception:
                    pass
            try:
                page.bring_to_front()
            except Exception:
                pass
        except Exception as e:
            print(f"창 노출 실패(무시): {e}")

    def _close_internal(self):
        """브라우저 세션 정리 (executor 스레드)"""
        if self._watchdog is not None:
            try:
                self._watchdog.cancel()
            except Exception:
                pass
            self._watchdog = None

        if self._browser_mgr:
            try:
                self._browser_mgr.stop()
            except Exception as e:
                print(f"바로가기 세션 종료 오류(무시): {e}")
            self._browser_mgr = None
            self._scraper = None
            self._distributor_id = None
            self._opened_at = 0.0
            print("🔒 바로가기 세션 종료")

    def _is_expired(self) -> bool:
        return self._opened_at > 0 and (time.time() - self._opened_at) > self.IDLE_TIMEOUT

    def _is_browser_alive(self) -> bool:
        """사용자가 창을 닫았는지 확인"""
        if not self._browser_mgr or not self._browser_mgr.browser:
            return False
        try:
            return self._browser_mgr.browser.is_connected()
        except Exception:
            return False

    # --- 워치독 (Timer 스레드에서 실행 → executor로 위임) ---

    def _start_watchdog(self):
        self._watchdog = threading.Timer(self.WATCHDOG_INTERVAL, self._watchdog_tick)
        self._watchdog.daemon = True
        self._watchdog.start()

    def _watchdog_tick(self):
        """주기적 점검: 창이 닫혔거나 타임아웃이면 정리, 아니면 재예약"""
        try:
            if not self._browser_mgr:
                return  # 이미 정리됨

            should_close = self._is_expired() or not self._is_browser_alive()
            if should_close:
                # 정리는 executor 스레드에서 수행(Playwright 스레드 격리)
                try:
                    self._executor.submit(self._close_internal)
                except Exception as e:
                    print(f"워치독 정리 요청 실패: {e}")
                return

            # 계속 살아있으면 다음 점검 예약
            self._watchdog = threading.Timer(self.WATCHDOG_INTERVAL, self._watchdog_tick)
            self._watchdog.daemon = True
            self._watchdog.start()
        except Exception as e:
            print(f"바로가기 워치독 오류(무시): {e}")

    # --- 비동기 공개 메서드 (web_server에서 호출) ---

    async def open(self, app_state, distributor_id: str,
                   drug_name: str, insurance_code: str) -> dict:
        """headed 브라우저를 열고 자동 로그인+검색 수행"""
        loop = asyncio.get_event_loop()
        return await asyncio.wait_for(
            loop.run_in_executor(
                self._executor,
                self._open_internal,
                app_state, distributor_id, drug_name, insurance_code,
            ),
            timeout=self.OPEN_TIMEOUT,
        )

    async def close(self):
        """수동 세션 종료"""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(self._executor, self._close_internal)

    @property
    def is_active(self) -> bool:
        return self._browser_mgr is not None and self._is_browser_alive() and not self._is_expired()
