"""
검색 엔진 모듈

약품 검색과 관련된 모든 로직을 담당합니다.
지오영, 백제약품 검색 및 검색 사이클 관리를 포함합니다.
"""

import asyncio
import json
import time
import concurrent.futures
import queue
from datetime import datetime
from typing import Dict, List, Any

import db
from scrapers.browser_manager import BrowserManager
from scrapers.registry import DISTRIBUTOR_REGISTRY
from models.build_config import get_visible_registry, get_primary_distributor
from utils.websocket_manager import broadcast_log
from utils.notifications import CrossPlatformNotifier


async def execute_search(app_state, manager):
    """반복 검색 실행 (비동기)"""
    cycle_count = 0
    
    try:
        # repeat_interval_minutes 설정 읽기
        config_data = app_state.config_manager.get_raw_config()
        repeat_interval = config_data.get('monitoring', {}).get('repeat_interval_minutes', 30)
        
        await broadcast_log(manager, f"🔄 반복 사이클 시작 (간격: {repeat_interval}분)")
        
        while app_state.is_searching:  # 무한 루프 시작
            cycle_count += 1
            
            # 사이클 시작 알림
            await manager.broadcast_message(json.dumps({
                "type": "cycle_start",
                "message": f"🔄 사이클 #{cycle_count} 시작",
                "cycle_number": cycle_count,
                "timestamp": datetime.now().isoformat()
            }))
            
            # 검색 데이터 초기화 (각 사이클마다)
            app_state.reset_search_data()
            app_state.current_search["status"] = "searching"
            app_state.current_search["timestamp"] = datetime.now().isoformat()
            
            # 진행 상황 전달용 큐
            progress_queue = queue.Queue()
            
            # 동기 검색 함수를 별도 스레드에서 실행
            loop = asyncio.get_event_loop()
            with concurrent.futures.ThreadPoolExecutor() as executor:
                # 큐를 인자로 전달
                search_task = loop.run_in_executor(executor, execute_search_sync, app_state, progress_queue)
                
                # 진행 상황 모니터링
                while not search_task.done():
                    if not app_state.is_searching:  # 중단 체크
                        search_task.cancel()
                        break
                        
                    try:
                        # 0.5초마다 큐 확인
                        await asyncio.sleep(0.5)
                        
                        # 큐에서 메시지 가져오기 (비블로킹)
                        try:
                            while True:
                                message = progress_queue.get_nowait()
                                
                                # 개별 약품 완료 메시지 처리
                                if message.startswith("DRUG_FOUND:"):
                                    drug_data = json.loads(message[11:])  # "DRUG_FOUND:" 제거
                                    await manager.broadcast_message(json.dumps(drug_data))
                                elif message.startswith("DRUG_SOLDOUT:"):
                                    soldout_data = json.loads(message[13:])
                                    await manager.broadcast_message(json.dumps(soldout_data))
                                elif message.startswith("DRUG_ERROR:"):
                                    err_data = json.loads(message[11:])
                                    await manager.broadcast_message(json.dumps(err_data))
                                elif message.startswith("URGENT_ALERT:"):
                                    urgent_data = json.loads(message[13:])  # "URGENT_ALERT:" 제거
                                    await manager.broadcast_message(json.dumps(urgent_data))
                                    
                                    # 시스템 알림 표시
                                    try:
                                        drug_info = urgent_data.get('drug', {})
                                        drug_name = drug_info.get('name', '알 수 없는 약품')
                                        distributor = drug_info.get('distributor', '알 수 없는 도매상')
                                        
                                        title = "🚨 긴급 재고 발견!"
                                        message = f"{distributor}에서 {drug_name} 재고를 발견했습니다!"
                                        
                                        CrossPlatformNotifier.show_alert(title, message, sound=True)
                                    except Exception as e:
                                        print(f"시스템 알림 표시 실패: {e}")
                                else:
                                    # 일반 로그 메시지
                                    await broadcast_log(manager, message)
                        except queue.Empty:
                            pass
                            
                    except asyncio.CancelledError:
                        break
                
                # 최종 결과 가져오기
                if not search_task.cancelled():
                    result = await search_task
                else:
                    result = None
                
            # 중단 체크
            if not app_state.is_searching:
                await broadcast_log(manager, f"🛑 사이클 #{cycle_count} 중단됨")
                break
            
            # 결과 처리
            if result:
                # execute_search_sync에서 추가한 카운트 사용
                found_count = result.get('found_count', 0)
                soldout_count = result.get('soldout_count', 0)
                error_count = result.get('error_count', 0)
                
                # 검색 완료 알림
                await manager.broadcast_message(json.dumps({
                    "type": "search_completed",
                    "data": {
                        "found_count": found_count,
                        "soldout_count": soldout_count,
                        "error_count": error_count,
                        "cycle_number": cycle_count
                    },
                    "timestamp": datetime.now().isoformat()
                }))
            else:
                await broadcast_log(manager, f"❌ 사이클 #{cycle_count} 검색 결과를 가져올 수 없었습니다")
                
                # 실패 알림도 전송
                await manager.broadcast_message(json.dumps({
                    "type": "search_completed",
                    "data": {
                        "found_count": 0,
                        "soldout_count": 0,
                        "error_count": 1,
                        "cycle_number": cycle_count
                    },
                    "timestamp": datetime.now().isoformat()
                }))
            
            # 다음 사이클까지 대기 (중단 체크와 함께)
            if app_state.is_searching:
                await broadcast_log(manager, f"⏰ 다음 사이클까지 {repeat_interval}분 대기 중...")
                
                # 카운트다운과 함께 대기
                for remaining_minutes in range(repeat_interval, 0, -1):
                    if not app_state.is_searching:  # 대기 중에도 중단 체크
                        break
                    
                    # 매분마다 카운트다운 메시지 (처음 1분, 마지막 5분만 표시)
                    if remaining_minutes == repeat_interval or remaining_minutes <= 5:
                        await manager.broadcast_message(json.dumps({
                            "type": "cycle_countdown",
                            "message": f"⏰ 다음 사이클까지 {remaining_minutes}분 남음",
                            "remaining_minutes": remaining_minutes,
                            "next_cycle": cycle_count + 1,
                            "timestamp": datetime.now().isoformat()
                        }))
                    
                    # 1분 대기 (중단 체크와 함께)
                    for _ in range(60):  # 60초를 1초씩 나눠서 중단 체크
                        if not app_state.is_searching:
                            break
                        await asyncio.sleep(1)
                    
                    if not app_state.is_searching:
                        break
        
        await broadcast_log(manager, f"🏁 반복 사이클 종료 (총 {cycle_count}회 실행)")
        
    except Exception as e:
        await broadcast_log(manager, f"❌ 반복 사이클 중 오류: {e}")
        await manager.broadcast_message(json.dumps({
            "type": "search_error",
            "message": str(e),
            "timestamp": datetime.now().isoformat()
        }))
    finally:
        app_state.is_searching = False


def execute_search_sync(app_state, progress_queue=None):
    """동기 검색 실행 (별도 스레드에서 실행)"""
    
    def log_message(msg):
        """로그 메시지를 터미널과 큐에 모두 전송"""
        print(msg)
        if progress_queue:
            try:
                progress_queue.put_nowait(msg)
            except:
                pass

    # 검색 사이클 기록용 (search_sessions / search_results)
    session_id = None
    t0 = time.time()

    try:
        # 검색 사이클 세션 시작
        try:
            session_id = db.start_search_session(datetime.now().isoformat()[:19])
        except Exception as e:
            log_message(f"⚠️ 검색 세션 생성 실패(기록 생략): {e}")

        # 데이터 로드
        drug_list = app_state.file_manager.read_drug_list()
        drug_list_json = app_state.file_manager.read_drug_list_json()
        exclusion_list = app_state.file_manager.read_alert_exclusions_json()
        
        # 긴급 알림 약품 목록 생성 (약품명 기준)
        urgent_drugs = {
            drug['drugName'] for drug in drug_list_json 
            if drug.get('isUrgent', False)
        }
        
        # 지오영에서 수집된 보험코드 -> 약품명 매핑 (백제 긴급 알림용)
        urgent_insurance_codes = set()
        # 백제 검색에 사용된 보험코드 매핑 저장용
        baekje_search_codes = {}
        
        # 진행률 설정
        app_state.current_search["progress"]["total"] = len(drug_list)
        app_state.current_search["progress"]["current"] = 0
        
        log_message(f"📋 검색할 약품 수: {len(drug_list)}개")
        
        # 만료된 제외 항목(비고정 & 기간 초과)을 DB에서 직접 삭제
        removed = db.delete_expired_exclusions(
            app_state.config.alert_exclusion_days, datetime.now().isoformat()
        )
        if removed:
            exclusion_list = app_state.file_manager.read_alert_exclusions_json()
            log_message(f"🧹 만료된 제외 항목 {removed}개 자동 삭제")

        # 도매상별 제외 약품명 매핑 생성 (만료 삭제 후 남은 목록 기준)
        _, excluded_by_distributor = \
            app_state.data_processor.process_alert_exclusions(exclusion_list, app_state.config.alert_exclusion_days)

        # 웹 스크래핑 실행
        all_drugs = []
        errors = []

        # 활성화 플래그 확인
        config_data = app_state.config_manager.get_raw_config()
        distributors_config = config_data.get('distributors', {})

        # 기준 도매상 검색 (항상 먼저 실행 — 보험코드 수집 역할)
        primary_id = get_primary_distributor()
        primary_name = DISTRIBUTOR_REGISTRY[primary_id]['name']
        primary_active = distributors_config.get(primary_id, {}).get('enabled', True)
        if primary_active and app_state.config.has_credentials(primary_id):
            log_message(f"🌐 {primary_name} 검색 시작...")
            primary_drugs, primary_errors = search_primary_sync(
                primary_id, app_state, drug_list,
                excluded_by_distributor.get(primary_name, []), progress_queue, urgent_drugs
            )
            all_drugs.extend(primary_drugs)
            errors.extend(primary_errors)
        else:
            log_message(f"⚠️ {primary_name}이(가) 비활성화되어 있습니다")

        # 기준 도매상 결과에서 보험코드 수집 (나머지 도매상 검색에 사용)
        insurance_codes = {}
        for drug in all_drugs:
            if hasattr(drug, 'insurance_code') and drug.insurance_code:
                insurance_codes[drug.insurance_code] = drug.name

        # 나머지 도매상 — build_config 기반 가시 레지스트리 루프
        for dist_id, dist_info in get_visible_registry().items():
            if dist_id == primary_id:
                continue

            dist_name = dist_info['name']
            active = distributors_config.get(dist_id, {}).get('enabled', False)

            if not active:
                continue

            if app_state.cycle_terminated:
                log_message(f"🔔 긴급 재고 발견으로 {dist_name} 검색 건너 뜀")
                continue

            if not app_state.config.has_credentials(dist_id):
                log_message(f"⚠️ {dist_name}이(가) 활성화되어 있지만 계정 정보가 없습니다")
                continue

            if not insurance_codes:
                log_message(f"⚠️ {primary_name}에서 보험코드를 수집하지 못해 {dist_name} 검색을 건너뜁니다")
                continue

            log_message(f"🏢 {dist_name} 검색 시작...")
            try:
                drugs, errs = search_distributor_sync(
                    dist_id, app_state, insurance_codes,
                    excluded_by_distributor.get(dist_name, []),
                    progress_queue, urgent_drugs
                )
                all_drugs.extend(drugs)
                errors.extend(errs)
            except Exception as e:
                error_msg = f"{dist_name} 검색 실패: {str(e)}"
                errors.append(error_msg)
                log_message(f"❌ {error_msg} — 다음 도매상으로 넘어갑니다")

        # 결과 분류 (모든 도매상의 excluded 약품명을 합친 리스트로 전달)
        all_excluded_names = []
        for distributor_names in excluded_by_distributor.values():
            all_excluded_names.extend(distributor_names)
        found_drugs, soldout_drugs = app_state.data_processor.categorize_drugs(all_drugs, all_excluded_names)
        
        # 긴급 알림은 이제 검색 중 즉시 처리됨 (위에서 조기 종료)
        
        # 메모리 상태 업데이트
        app_state.current_search["status"] = "completed"
        app_state.current_search["errors"] = errors
         
        # 결과 딕셔너리 반환 (파일 저장 없이)
        result_dict = {
            'found_count': len(found_drugs),
            'soldout_count': len(soldout_drugs),
            'error_count': len(errors),
            'found_drugs': [drug.to_dict() if hasattr(drug, 'to_dict') else drug.__dict__ for drug in found_drugs],
            'soldout_drugs': [drug.to_dict() if hasattr(drug, 'to_dict') else drug.__dict__ for drug in soldout_drugs]
        }
        
        # 메모리 상태 최종 업데이트
        app_state.current_search["found_drugs"] = result_dict['found_drugs']
        app_state.current_search["soldout_drugs"] = result_dict['soldout_drugs']

        # 사이클 결과를 DB에 기록 (세션 단위 단일 트랜잭션)
        if session_id is not None:
            try:
                db.save_search_results(
                    session_id,
                    result_dict['found_drugs'],
                    result_dict['soldout_drugs'],
                    errors,
                    round(time.time() - t0, 2),
                    status="completed",
                )
            except Exception as e:
                log_message(f"⚠️ 검색 결과 DB 저장 실패: {e}")

        return result_dict

    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        error_msg = f"❌ 동기 검색 중 오류: {str(e)}\n상세 오류:\n{error_details}"
        log_message(error_msg)
        print(f"DEBUG - 오류 타입: {type(e).__name__}")
        print(f"DEBUG - 오류 메시지: {str(e)}")
        print(f"DEBUG - 상세 스택트레이스:\n{error_details}")
        app_state.current_search["status"] = "error"
        app_state.current_search["errors"].append(str(e))
        if session_id is not None:
            try:
                db.fail_search_session(session_id, round(time.time() - t0, 2))
            except Exception:
                pass
        return None


def search_distributor_sync(dist_id: str, app_state, insurance_codes: Dict[str, str], excluded_names: List[str], progress_queue=None, urgent_drugs=None) -> tuple:
    """레지스트리 기반 보험코드 도매상 통합 검색 (동기)

    지오영을 제외한 모든 보험코드 기반 도매상에 공통으로 사용됩니다.
    새 도매상 추가 시 scrapers/registry.py에만 항목을 추가하면 됩니다.
    """
    dist_info = DISTRIBUTOR_REGISTRY[dist_id]
    ScraperClass = dist_info['scraper_class']
    dist_name = dist_info['name']

    def log_message(msg):
        print(msg)
        if progress_queue:
            try:
                progress_queue.put_nowait(msg)
            except:
                pass

    all_drugs = []
    errors = []

    browser_mgr = BrowserManager()
    browser_mgr.start()

    try:
        scraper = ScraperClass()
        page = browser_mgr.new_page()

        # 로그인 (extra_params에서 region 등 추가 인자 자동 전달)
        log_message(f"🤖 {dist_name}에 로그인하는 중입니다...")
        creds = app_state.config.get_credentials(dist_id)
        login_extra = {k: creds.extra.get(k, v) for k, v in dist_info.get('extra_params', {}).items()}
        if not scraper.login(page, creds.username, creds.password, **login_extra):
            raise Exception(f"{dist_name} 로그인 실패")

        log_message(f"✓ {dist_name} 로그인 성공")
        log_message(f"📋 검색할 약품 수: {len(insurance_codes)}개")

        for i, (insurance_code, original_name) in enumerate(insurance_codes.items(), 1):
            if not app_state.is_searching:
                break

            try:
                drugs = scraper._search_by_insurance_code(insurance_code, original_name)
                for drug in drugs:
                    unit_display = f" [{drug.unit}]" if drug.unit else ""
                    full_name = f"{drug.name}{unit_display}"
                    drug.is_excluded_from_alert = full_name in excluded_names
                    drug.search_insurance_code = insurance_code
                    drug.original_drug_name = original_name
                    drug.distributor = dist_name

                if drugs:
                    log_message(f"🔍 {dist_name} 검색 완료 ({i}/{len(insurance_codes)}): {original_name} ({insurance_code}) - {len(drugs)}개 규격 발견")

                    urgent_stock_found = False
                    urgent_drugs_list = []

                    for drug in drugs:
                        main_stock = drug.main_stock if drug.main_stock else "정보없음"
                        main_display = "품절" if main_stock in ("품절", "0") else f"{main_stock}개"
                        unit_display = f" [{drug.unit}]" if drug.unit else ""

                        log_message(f"   - {drug.name}{unit_display}: {main_display}")

                        has_stock = drug.has_stock() if hasattr(drug, 'has_stock') else (main_stock not in ("품절", "0"))

                        if urgent_drugs and original_name in urgent_drugs and has_stock and not drug.is_excluded_from_alert:
                            urgent_stock_found = True
                            urgent_drugs_list.append({
                                "name": drug.name,
                                "main_stock": main_stock,
                                "unit": drug.unit,
                                "unit_display": unit_display,
                                "main_display": main_display
                            })

                        drug_data = {
                            "name": f"{drug.name}{unit_display}",
                            "insurance_code": getattr(drug, 'insurance_code', '') or insurance_code,
                            "main_stock": main_stock,
                            "incheon_stock": "-",
                            "company": drug.company if hasattr(drug, 'company') else dist_name,
                            "distributor": dist_name,
                            "has_stock": has_stock,
                            "unit": drug.unit,
                            "notes": drug.notes if hasattr(drug, 'notes') and drug.notes != "-" else ""
                        }
                        app_state.add_drug_result(drug_data, has_stock)

                        if progress_queue and not drug.is_excluded_from_alert:
                            try:
                                drug_found_msg = {
                                    "type": "drug_found",
                                    "drug": drug_data,
                                    "progress": {"current": i, "total": len(insurance_codes)}
                                }
                                progress_queue.put_nowait(f"DRUG_FOUND:{json.dumps(drug_found_msg)}")
                            except:
                                pass

                    if urgent_stock_found:
                        app_state.cycle_terminated = True

                        if urgent_drugs_list:
                            base_name = urgent_drugs_list[0]['name']
                            unit_specs = [spec['unit_display'] for spec in urgent_drugs_list]
                            specs_display = f"{base_name} {', '.join(unit_specs)}"
                            detailed_specs = [f"{spec['unit_display']}: {spec['main_display']}" for spec in urgent_drugs_list]
                            detailed_display = f"{base_name}\n" + "\n".join(detailed_specs)
                        else:
                            specs_display = "재고 발견"
                            detailed_display = "재고 발견"

                        urgent_alert_msg = {
                            "type": "urgent_alert",
                            "drug": {
                                "name": f"{dist_name} 재고 발견: {specs_display}",
                                "main_stock": detailed_display,
                                "incheon_stock": "-",
                                "company": dist_name,
                                "distributor": dist_name,
                                "original_drug_name": original_name,
                                "specifications": urgent_drugs_list
                            },
                            "timestamp": datetime.now().isoformat()
                        }
                        if progress_queue:
                            try:
                                progress_queue.put_nowait(f"URGENT_ALERT:{json.dumps(urgent_alert_msg)}")
                            except:
                                pass

                        all_drugs.extend(drugs)
                        return all_drugs, errors
                else:
                    log_message(f"❌ {dist_name} 검색 실패 ({i}/{len(insurance_codes)}): {original_name} ({insurance_code}) - 검색 결과 없음")
                    errors.append(f"{original_name} ({insurance_code}): 검색 결과 없음")

                all_drugs.extend(drugs)
            except Exception as e:
                error_msg = f"{original_name} ({insurance_code}): {str(e)}"
                errors.append(error_msg)
                log_message(f"❌ {error_msg}")

        log_message(f"✓ {dist_name} 검색 완료: {len(all_drugs)}개 약품")

    finally:
        browser_mgr.stop()

    return all_drugs, errors


def search_primary_sync(primary_id: str, app_state, drug_list: List[str], excluded_names: List[str], progress_queue=None, urgent_drugs=None) -> tuple:
    """기준 도매상 검색 (동기) — 약품명 텍스트로 검색하고 보험코드를 수집

    primary_id에 해당하는 도매상에 로그인 후, drug_list의 각 약품명을
    search_drug()으로 검색합니다. 결과에서 보험코드를 수집하여
    나머지 도매상의 보험코드 기반 검색에 활용됩니다.
    """
    dist_info = DISTRIBUTOR_REGISTRY[primary_id]
    ScraperClass = dist_info['scraper_class']
    dist_name = dist_info['name']

    def log_message(msg):
        """로그 메시지를 터미널과 큐에 모두 전송"""
        print(msg)
        if progress_queue:
            try:
                progress_queue.put_nowait(msg)
            except:
                pass

    all_drugs = []
    errors = []

    browser_mgr = BrowserManager()
    browser_mgr.start()

    try:
        scraper = ScraperClass()
        page = browser_mgr.new_page()

        # 로그인 (extra_params에서 region 등 추가 인자 자동 전달)
        log_message(f"🤖 {dist_name}에 로그인하는 중입니다...")
        creds = app_state.config.get_credentials(primary_id)
        login_extra = {k: creds.extra.get(k, v) for k, v in dist_info.get('extra_params', {}).items()}
        if not scraper.login(page, creds.username, creds.password, **login_extra):
            raise Exception(f"{dist_name} 로그인 실패")

        log_message(f"✓ {dist_name} 로그인 성공")

        # 약품 검색
        for i, drug_name in enumerate(drug_list, 1):
            if not app_state.is_searching:  # 중단 확인
                break

            try:
                drugs = scraper.search_drug(drug_name)
                for drug in drugs:
                    drug.is_excluded_from_alert = drug.name in excluded_names
                    drug.distributor = dist_name

                # 재고 상황 로그 추가 및 실시간 상태 업데이트
                if drugs:
                    drug = drugs[0]  # 첫 번째 결과 사용
                    main_stock = drug.main_stock if drug.main_stock else "정보없음"

                    # 타센터 재고 (지오영 전용 — 다른 도매상은 해당 없음)
                    if primary_id == 'geoweb':
                        geoweb_region = login_extra.get('region', 'seoul')
                        incheon_stock = "-" if geoweb_region in ("yeongnam", "daejeon") else (drug.incheon_stock if drug.incheon_stock else "정보없음")
                    else:
                        incheon_stock = "-"

                    # 재고 상황을 더 명확하게 표시
                    main_display = "품절" if main_stock in ("품절", "0") else f"{main_stock}개"

                    # 한 줄로 통합된 로그 메시지
                    if primary_id == 'geoweb' and incheon_stock != "-":
                        incheon_display = "품절" if incheon_stock in ("품절", "0") else f"{incheon_stock}개"
                        log_message(f"🔍 검색 완료 ({i}/{len(drug_list)}): {drug_name} ( 재고: {main_display} | 타센터: {incheon_display} )")
                    else:
                        log_message(f"🔍 검색 완료 ({i}/{len(drug_list)}): {drug_name} ( 재고: {main_display} )")

                    # 재고 발견 여부 확인
                    has_stock = drug.has_stock() if hasattr(drug, 'has_stock') else (main_stock not in ("품절", "0"))

                    # 긴급 약품이면서 재고가 있고 exclusion list에 없는 경우만 알림
                    if urgent_drugs and drug.name in urgent_drugs and has_stock and not drug.is_excluded_from_alert:
                        # 사이클 종료 플래그 설정
                        app_state.cycle_terminated = True

                        # 즉시 긴급 알림 전송
                        urgent_alert_msg = {
                            "type": "urgent_alert",
                            "drug": {
                                "name": drug.name,
                                "main_stock": main_stock,
                                "incheon_stock": incheon_stock,
                                "company": getattr(drug, 'company', ''),
                                "distributor": dist_name
                            },
                            "timestamp": datetime.now().isoformat()
                        }
                        if progress_queue:
                            try:
                                progress_queue.put_nowait(f"URGENT_ALERT:{json.dumps(urgent_alert_msg)}")
                            except:
                                pass

                        # 현재 약품을 결과에 추가 후 즉시 종료
                        all_drugs.extend(drugs)
                        return all_drugs, errors

                    # 메모리 상태에 개별 결과 추가
                    drug_data = {
                        "name": drug.name,
                        "insurance_code": getattr(drug, 'insurance_code', ''),
                        "main_stock": main_stock,
                        "incheon_stock": incheon_stock,
                        "company": getattr(drug, 'company', ''),
                        "distributor": dist_name,
                        "has_stock": has_stock
                    }
                    app_state.add_drug_result(drug_data, has_stock)

                    # 개별 약품 완료 메시지를 큐에 추가 (WebSocket 전송용)
                    # exclusion된 약품은 프론트엔드로 전송하지 않음
                    if progress_queue and not drug.is_excluded_from_alert:
                        try:
                            drug_found_msg = {
                                "type": "drug_found",
                                "drug": drug_data,
                                "progress": app_state.current_search["progress"].copy()
                            }
                            progress_queue.put_nowait(f"DRUG_FOUND:{json.dumps(drug_found_msg)}")
                        except:
                            pass
                else:
                    # 검색 결과 없음: 오류로 승격하여 프론트에 표시
                    log_message(f"❌ 검색 실패 ({i}/{len(drug_list)}): {drug_name} ( 검색 결과 없음 )")

                    # 에러 집계 및 진행률 업데이트
                    errors.append(f"{drug_name}: 검색 결과 없음")
                    app_state.current_search["progress"]["current"] += 1
                    # 프론트로 오류 전송
                    if progress_queue:
                        try:
                            drug_error_msg = {
                                "type": "drug_error",
                                "drug": {"name": drug_name, "error": "검색 결과 없음"},
                                "progress": app_state.current_search["progress"].copy()
                            }
                            progress_queue.put_nowait(f"DRUG_ERROR:{json.dumps(drug_error_msg)}")
                        except:
                            pass

                all_drugs.extend(drugs)
            except Exception as e:
                error_msg = f"{drug_name}: {str(e)}"
                errors.append(error_msg)
                log_message(f"❌ {error_msg}")
                # 진행률 업데이트
                app_state.current_search["progress"]["current"] += 1
                # 에러도 프론트로 전송
                if progress_queue:
                    try:
                        drug_error_msg = {
                            "type": "drug_error",
                            "drug": {"name": drug_name, "error": str(e)},
                            "progress": app_state.current_search["progress"].copy()
                        }
                        progress_queue.put_nowait(f"DRUG_ERROR:{json.dumps(drug_error_msg)}")
                    except:
                        pass

        log_message(f"✓ {dist_name} 검색 완료: {len(all_drugs)}개 약품")

    finally:
        browser_mgr.stop()

    return all_drugs, errors


class PreviewSearchSession:
    """미리보기 검색 세션 — 브라우저/로그인 상태를 유지하여 반복 검색을 빠르게 처리"""

    # 세션 타임아웃 (초) — 마지막 검색 후 이 시간이 지나면 자동 정리
    SESSION_TIMEOUT = 120

    def __init__(self):
        self._browser_mgr = None
        self._scraper = None
        self._primary_id = None
        self._last_used = 0.0
        # 단일 스레드 executor — Playwright 동기 API는 같은 스레드에서 사용해야 안정적
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)

    # --- 동기 내부 메서드 (executor 스레드에서 실행) ---

    def _ensure_session(self, app_state):
        """세션이 없거나 만료되었으면 브라우저 시작 + 로그인"""
        primary_id = get_primary_distributor()

        # 기존 세션이 유효하면 재사용
        if (self._browser_mgr and self._scraper
                and self._scraper.is_logged_in
                and self._primary_id == primary_id
                and not self._is_expired()):
            return

        # 기존 세션 정리 후 새로 시작
        self._close_internal()

        dist_info = DISTRIBUTOR_REGISTRY[primary_id]
        ScraperClass = dist_info['scraper_class']

        self._browser_mgr = BrowserManager()
        self._browser_mgr.start()

        self._scraper = ScraperClass()
        page = self._browser_mgr.new_page()

        creds = app_state.config.get_credentials(primary_id)
        login_extra = {k: creds.extra.get(k, v)
                       for k, v in dist_info.get('extra_params', {}).items()}
        if not self._scraper.login(page, creds.username, creds.password, **login_extra):
            self._close_internal()
            raise Exception("로그인 실패")

        self._primary_id = primary_id
        self._last_used = time.time()
        print("✅ 미리보기 검색 세션 시작")

    def _search_internal(self, app_state, query: str) -> dict:
        """검색 실행 (executor 스레드)"""
        self._ensure_session(app_state)
        self._last_used = time.time()

        drugs = self._scraper.search_drug_all(query)

        dist_info = DISTRIBUTOR_REGISTRY[self._primary_id]
        results = [{
            "name": drug.name,
            "insurance_code": drug.insurance_code,
            "company": drug.company,
            "unit": drug.unit,
            "stock": drug.main_stock,
        } for drug in drugs]

        return {
            "results": results,
            "distributor": dist_info['name'],
            "query": query
        }

    def _close_internal(self):
        """브라우저 세션 정리 (executor 스레드)"""
        if self._browser_mgr:
            try:
                self._browser_mgr.stop()
            except Exception as e:
                print(f"미리보기 세션 종료 오류: {e}")
            self._browser_mgr = None
            self._scraper = None
            self._primary_id = None
            print("🔒 미리보기 검색 세션 종료")

    def _is_expired(self) -> bool:
        return time.time() - self._last_used > self.SESSION_TIMEOUT

    # --- 비동기 공개 메서드 (web_server에서 호출) ---

    async def search(self, app_state, query: str) -> dict:
        """비동기 검색 — 세션 자동 생성/재사용"""
        loop = asyncio.get_event_loop()
        return await asyncio.wait_for(
            loop.run_in_executor(self._executor, self._search_internal, app_state, query),
            timeout=30.0
        )

    async def close(self):
        """비동기 세션 종료"""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(self._executor, self._close_internal)

    @property
    def is_active(self) -> bool:
        return self._browser_mgr is not None and not self._is_expired()