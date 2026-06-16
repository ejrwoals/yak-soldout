import os
import sys
import json
import chardet
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

import db

def resource_path(relative_path):
    """개발 및 PyInstaller 환경 모두에서 리소스의 절대 경로를 가져옵니다."""
    try:
        # PyInstaller는 임시 폴더를 만들고 _MEIPASS에 경로를 저장합니다
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    
    return os.path.join(base_path, relative_path)



class FileManager:
    """파일 관리 및 데이터 입출력을 담당하는 클래스"""
    
    def __init__(self, app_directory: Path):
        self.app_directory = app_directory
        self.data_directory = app_directory / "data"
        self.data_directory.mkdir(exist_ok=True)
    
    def _detect_encoding(self, file_path: Path) -> str:
        """파일 인코딩 자동 감지"""
        try:
            with open(file_path, 'rb') as file:
                raw_data = file.read()
                result = chardet.detect(raw_data)
                return result['encoding'] or 'utf-8'
        except Exception:
            return 'utf-8'
    
    def read_drug_list(self, filename: str = "geoweb-soldout-list.json") -> List[str]:
        """모니터링 대상 약품명 목록 (watch_list, drugName 문자열만)

        filename 인자는 기존 시그니처 호환용으로만 남겨둠 (DB에서 조회).
        """
        try:
            rows = db.query_all("SELECT drug_name FROM watch_list ORDER BY drug_name")
            return [r["drug_name"] for r in rows]
        except Exception as e:
            print(f"약품 목록 읽기 오류: {e}")
            return []

    def read_drug_list_json(self, filename: str = "geoweb-soldout-list.json") -> List[Dict[str, Any]]:
        """모니터링 대상 약품 목록 (watch_list, 전체 객체)"""
        try:
            rows = db.query_all(
                "SELECT drug_name, is_urgent, date_added FROM watch_list ORDER BY drug_name"
            )
            return [
                {
                    "drugName": r["drug_name"],
                    "isUrgent": bool(r["is_urgent"]),
                    "dateAdded": r["date_added"],
                }
                for r in rows
            ]
        except Exception as e:
            print(f"약품 목록 읽기 오류: {e}")
            return []

    def write_drug_list(self, drug_list: List[str], filename: str = "geoweb-soldout-list.json"):
        """품절 약품 목록 쓰기 (이전 버전 호환용 — 문자열 리스트)"""
        # 문자열 리스트를 객체 리스트로 변환
        drug_objects = []
        for drug in drug_list:
            if isinstance(drug, str):
                drug_objects.append({
                    "drugName": drug,
                    "isUrgent": False,
                    "dateAdded": datetime.now().isoformat()[:19]
                })
            else:
                drug_objects.append(drug)

        self.write_drug_list_json(drug_objects, filename)

    def write_drug_list_json(self, drug_list: List[Dict[str, Any]], filename: str = "geoweb-soldout-list.json"):
        """모니터링 대상 약품 목록 전체 교체 (watch_list)

        전체 리스트를 받아 테이블 내용을 통째로 교체한다(라우트가 read→modify→write
        패턴으로 호출하므로). drugName 기준으로 중복 제거하며, 기존 insurance_code
        링크는 약품명으로 보존한다.
        """
        # 중복 제거 (drugName 기준, 첫 항목 유지)
        seen = set()
        unique_drugs = []
        for drug in drug_list:
            drug_name = (drug.get('drugName', '') or '').strip()
            if drug_name and drug_name not in seen:
                seen.add(drug_name)
                unique_drugs.append(drug)

        try:
            with db.transaction() as conn:
                # 기존 insurance_code 링크 보존용 매핑
                existing = {
                    r["drug_name"]: r["insurance_code"]
                    for r in conn.execute("SELECT drug_name, insurance_code FROM watch_list")
                }
                conn.execute("DELETE FROM watch_list")
                for drug in unique_drugs:
                    name = (drug.get('drugName', '') or '').strip()
                    conn.execute(
                        """INSERT INTO watch_list (drug_name, insurance_code, is_urgent, date_added)
                           VALUES (?, ?, ?, ?)""",
                        (
                            name,
                            existing.get(name),
                            1 if drug.get('isUrgent') else 0,
                            drug.get('dateAdded') or datetime.now().isoformat()[:19],
                        ),
                    )
        except Exception as e:
            print(f"약품 목록 쓰기 오류: {e}")


    def read_alert_exclusions_json(self, filename: str = "exclusion-list.json") -> List[Dict[str, Any]]:
        """결과 표시 제외 목록 조회 (exclusion_list)

        정렬: 비고정 항목(상단) → 고정 항목(하단), 각각 날짜 내림차순.
        """
        try:
            rows = db.query_all(
                """SELECT drug_name, distributor, date, is_pinned
                   FROM exclusion_list
                   ORDER BY is_pinned, date DESC"""
            )
            return [
                {
                    "date": r["date"],
                    "distributor": r["distributor"],
                    "drugName": r["drug_name"],
                    "isPinned": bool(r["is_pinned"]),
                }
                for r in rows
            ]
        except Exception as e:
            print(f"결과 표시 제외 목록 읽기 오류: {e}")
            return []

    def write_alert_exclusions_json(self, exclusion_list: List[Dict[str, Any]], filename: str = "exclusion-list.json"):
        """결과 표시 제외 목록 전체 교체 (exclusion_list)"""
        try:
            with db.transaction() as conn:
                conn.execute("DELETE FROM exclusion_list")
                for item in exclusion_list:
                    name = (item.get('drugName', '') or '').strip()
                    if not name:
                        continue
                    conn.execute(
                        """INSERT OR IGNORE INTO exclusion_list (drug_name, distributor, date, is_pinned)
                           VALUES (?, ?, ?, ?)""",
                        (
                            name,
                            item.get('distributor', '') or '',
                            item.get('date', '') or datetime.now().isoformat()[:19],
                            1 if item.get('isPinned') else 0,
                        ),
                    )
        except Exception as e:
            print(f"결과 표시 제외 목록 쓰기 오류: {e}")
    
    
    
    
    
    def save_search_results(self, data: Dict[str, Any], filename: str = "search_results.json"):
        """검색 결과를 JSON으로 저장"""
        file_path = self.data_directory / filename
        
        try:
            with open(file_path, 'w', encoding='utf-8') as file:
                json.dump(data, file, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"검색 결과 저장 실패: {e}")
    
    def load_search_results(self, filename: str = "search_results.json") -> Optional[Dict[str, Any]]:
        """저장된 검색 결과 로드"""
        file_path = self.data_directory / filename
        
        if not file_path.exists():
            return None
        
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                return json.load(file)
        except Exception as e:
            print(f"검색 결과 로드 오류: {e}")
            return None
    
    def save_app_state(self, state: Dict[str, Any], filename: str = "app_state.json"):
        """앱 상태 저장"""
        file_path = self.data_directory / filename
        
        # 타임스탬프 추가
        state['last_updated'] = datetime.now().isoformat()
        
        with open(file_path, 'w', encoding='utf-8') as file:
            json.dump(state, file, ensure_ascii=False, indent=2)
    
    def load_app_state(self, filename: str = "app_state.json") -> Dict[str, Any]:
        """앱 상태 로드"""
        file_path = self.data_directory / filename
        
        if not file_path.exists():
            return {}
        
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                return json.load(file)
        except Exception as e:
            print(f"앱 상태 로드 오류: {e}")
            return {}