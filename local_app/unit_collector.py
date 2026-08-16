#!/usr/bin/env python3
"""약품 DB 규격(포장단위) 수집기 — 크롤링은 로컬, 결과는 Supabase 에 저장.

약품 마스터는 약국이 올린 엑셀로 만들어지는데 엑셀에는 규격 컬럼이 없다. 그래서 unit 이
빈 행을 **기준 도매상**(지오영/유팜몰)에 보험코드로 하나씩 검색해, 검색 결과의 규격을
모아 채운다. 도매상 사이트는 데이터센터 IP 를 막으므로 크롤링은 이 로컬 앱에서만 돌고,
결과만 Supabase `drug_master` 로 write-back 한다.

레거시 utils/unit_collector.py 의 수집 규칙(같은 보험코드의 distinct 규격을 모두 수집,
코드 단위 캐시, 중단 요청)을 그대로 옮겼고 달라진 점은 세 가지다:
- 대상/저장: 로컬 SQLite → Supabase (약국 스코프, RLS)
- 기준 도매상 계정: build_config.json + 품절앱 DB → local_app/.settings.json (settings.py)
- 진행 상황: WebSocket 브로드캐스트 → SSE 구독 (app.py 의 /collect-units/stream)
"""

import asyncio
import concurrent.futures
import time
from typing import Callable, Dict, List

import master_db
import repo_path  # noqa: F401  — 리포지토리 루트를 sys.path 에 올린다 (scrapers 임포트용)

# 한 행에 여러 규격을 저장할 때의 구분자 (예: "30T, 100T, 1000T")
UNIT_SEP = ", "


def _collect_units(row_code: str, candidates: List[Dict[str, str]]) -> str:
    """이 보험코드로 검색된 결과의 모든 distinct 규격을 발견 순서대로 합쳐 반환한다.

    같은 보험코드가 여러 규격(예: 100T/30T)을 가질 수 있으므로 하나만 고르지 않고 전부 모은다.
    검색 결과에 다른 코드가 섞여 들어오는 경우를 대비해 동일 보험코드 후보를 우선 사용하고,
    매칭이 전혀 없을 때만 전체 후보로 폴백한다.
    """
    code = (row_code or "").strip()
    same_code = [c for c in candidates if (c.get("insurance_code") or "").strip() == code]
    pool = same_code or candidates

    units: List[str] = []
    for c in pool:
        u = (c.get("unit") or "").strip()
        if u and u not in units:
            units.append(u)
    return UNIT_SEP.join(units)


class UnitCollector:
    """규격 일괄 수집 세션 (배치, 1회성). 앱당 한 번에 하나만 돈다."""

    def __init__(self):
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self._running = False
        self._stop = False
        self._browser_mgr = None
        self._scraper = None
        self._subscribers: list[asyncio.Queue] = []

    @property
    def is_running(self) -> bool:
        return self._running

    def request_stop(self) -> None:
        """진행 중인 수집을 다음 행 경계에서 중단하도록 요청."""
        self._stop = True

    # --- 진행상황 구독 (SSE) ---
    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        if q in self._subscribers:
            self._subscribers.remove(q)

    def _fanout(self, payload: dict) -> None:
        for q in list(self._subscribers):
            try:
                q.put_nowait(payload)
            except Exception:
                pass

    def _emit(self, loop: asyncio.AbstractEventLoop, payload: dict) -> None:
        """수집 스레드 → 메인 이벤트 루프로 진행상황 전달."""
        try:
            loop.call_soon_threadsafe(self._fanout, payload)
        except Exception as e:
            print(f"[unit_collector] 진행상황 전송 실패: {e}")

    # --- 브라우저/로그인 ---
    def _start_session(self, creds: dict) -> None:
        from scrapers.browser_manager import BrowserManager
        from scrapers.registry import DISTRIBUTOR_REGISTRY

        dist_info = DISTRIBUTOR_REGISTRY[creds["dist_key"]]
        ScraperClass = dist_info["scraper_class"]

        self._browser_mgr = BrowserManager()
        self._browser_mgr.start()
        self._scraper = ScraperClass()
        page = self._browser_mgr.new_page()

        # region 등 도매상별 추가 로그인 파라미터 — 설정값이 없으면 레지스트리 기본값
        login_extra = {k: (creds.get(k) or v) for k, v in dist_info.get("extra_params", {}).items()}
        if not self._scraper.login(page, creds["username"], creds["password"], **login_extra):
            self._close_session()
            raise Exception(f"{creds['name']} 로그인 실패 — 계정 정보를 확인하세요")

    def _close_session(self) -> None:
        if self._browser_mgr:
            try:
                self._browser_mgr.stop()
            except Exception as e:
                print(f"[unit_collector] 세션 종료 오류: {e}")
            self._browser_mgr = None
            self._scraper = None

    # --- 동기 배치 (executor 스레드) ---
    def _run_sync(self, get_client: Callable, pharmacy_id: str, creds: dict,
                  loop: asyncio.AbstractEventLoop) -> dict:
        dist_name = creds["name"]
        rows = master_db.rows_missing_unit(get_client(), pharmacy_id)
        total = len(rows)
        self._emit(loop, {
            "type": "unit_collect_started", "total": total, "distributor": dist_name,
        })

        print("\n" + "=" * 60)
        print(f"📦 규격 수집 시작 — 대상 {total}건 · 기준 도매상: {dist_name}")
        print("=" * 60)

        updated = notfound = failed = 0
        done = 0

        if total == 0:
            print("✅ 수집할 빈 규격 행이 없습니다.")
            return {"type": "unit_collect_done", "updated": 0, "notfound": 0,
                    "failed": 0, "total": 0, "stopped": False}

        try:
            print(f"🔐 {dist_name} 로그인 중…")
            self._start_session(creds)
            print(f"✅ {dist_name} 로그인 완료. 검색을 시작합니다.")
        except Exception as e:
            print(f"❌ 로그인 실패: {e}")
            self._emit(loop, {"type": "unit_collect_error", "message": str(e)})
            return {"type": "unit_collect_done", "updated": 0, "notfound": 0,
                    "failed": total, "total": total, "stopped": False, "error": str(e)}

        # 같은 보험코드는 한 번만 검색 (code → 후보 리스트 캐시)
        cache: Dict[str, List[Dict[str, str]]] = {}
        try:
            for row in rows:
                if self._stop:
                    break
                code = (row["insurance_code"] or "").strip()
                done += 1
                unit = ""
                prefix = f"[{done}/{total}] {row['name']} ({code})"
                try:
                    if code in cache:
                        cached = True
                    else:
                        cached = False
                        drugs = self._scraper.search_drug_all(code)
                        cache[code] = [{
                            "name": d.name,
                            "insurance_code": d.insurance_code,
                            "unit": d.unit,
                        } for d in drugs]
                        time.sleep(0.25)  # 도매상 부하 완화
                    unit = _collect_units(code, cache[code])
                    hit = len(cache[code])
                    tag = " (캐시)" if cached else ""
                    if unit:
                        master_db.set_unit(get_client(), row["id"], unit)
                        updated += 1
                        result = "ok"
                        print(f"  ✓ {prefix}{tag} → 규격 {unit}  [검색 {hit}건]")
                    else:
                        notfound += 1
                        result = "notfound"
                        print(f"  · {prefix}{tag} → 규격 없음  [검색 {hit}건]")
                except Exception as e:
                    failed += 1
                    result = "error"
                    print(f"  ✗ {prefix} → 오류: {e}")

                self._emit(loop, {
                    "type": "unit_collect_progress",
                    "done": done, "total": total,
                    "name": row["name"], "code": code,
                    "unit": unit, "result": result,
                })
        finally:
            self._close_session()

        print("-" * 60)
        head = "⏹️  수집 중단됨" if self._stop else "🏁 수집 완료"
        print(f"{head} — 처리 {done}/{total} · 채움 {updated} · 미발견 {notfound} · 실패 {failed}")
        print("=" * 60 + "\n")

        return {
            "type": "unit_collect_done",
            "updated": updated, "notfound": notfound, "failed": failed,
            "total": total, "stopped": self._stop,
        }

    # --- 비동기 공개 메서드 ---
    async def run(self, get_client: Callable, pharmacy_id: str, creds: dict) -> dict:
        """규격 일괄 수집 실행. 완료 시 요약 dict 반환.

        get_client 는 호출할 때마다 **유효한** Supabase 클라이언트를 돌려주는 함수여야 한다
        (수집이 길어져 access token 이 만료되면 갱신된 세션으로 계속 쓰기 위함).
        """
        if self._running:
            raise RuntimeError("이미 규격 수집이 진행 중입니다")
        self._running = True
        self._stop = False
        loop = asyncio.get_running_loop()
        try:
            summary = await loop.run_in_executor(
                self._executor, self._run_sync, get_client, pharmacy_id, creds, loop
            )
            self._emit(loop, summary)
            return summary
        finally:
            self._running = False
            self._stop = False
