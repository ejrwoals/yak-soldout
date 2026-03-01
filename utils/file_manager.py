import os
import sys
import json
import chardet
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

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
        """품절 약품 목록 파일 읽기 (JSON 형식)"""
        file_path = self.app_directory / filename
        
        if not file_path.exists():
            # JSON 파일이 없으면 빈 파일 생성
            self.write_drug_list([], filename)
            return []
        
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                data = json.load(file)
                if isinstance(data, list):
                    # 객체 형태라면 drugName 추출, 문자열이라면 그대로 반환
                    return [
                        item.get('drugName', item) if isinstance(item, dict) else item 
                        for item in data
                    ]
                return []
        except (json.JSONDecodeError, Exception) as e:
            print(f"약품 목록 JSON 파일 읽기 오류: {e}")
            return []
    
    def read_drug_list_json(self, filename: str = "geoweb-soldout-list.json") -> List[Dict[str, Any]]:
        """품절 약품 목록 파일 읽기 (전체 JSON 객체 반환)"""
        file_path = self.app_directory / filename
        
        if not file_path.exists():
            # JSON 파일이 없으면 빈 파일 생성
            self.write_drug_list_json([], filename)
            return []
        
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                data = json.load(file)
                if isinstance(data, list):
                    # 문자열 데이터를 객체로 변환
                    result = []
                    for item in data:
                        if isinstance(item, str):
                            result.append({
                                "drugName": item,
                                "isUrgent": False,
                                "dateAdded": datetime.now().isoformat()[:19]
                            })
                        elif isinstance(item, dict):
                            result.append(item)
                    return result
                return []
        except (json.JSONDecodeError, Exception) as e:
            print(f"약품 목록 JSON 파일 읽기 오류: {e}")
            return []
    
    def write_drug_list(self, drug_list: List[str], filename: str = "geoweb-soldout-list.json"):
        """품절 약품 목록 파일 쓰기 (이전 버전 호환용)"""
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
        """품절 약품 목록 파일 쓰기 (JSON 형식)"""
        file_path = self.app_directory / filename
        
        # 중복 제거 및 정렬 (drugName 기준)
        seen = set()
        unique_drugs = []
        for drug in drug_list:
            drug_name = drug.get('drugName', '')
            if drug_name and drug_name not in seen:
                seen.add(drug_name)
                unique_drugs.append(drug)
        
        # drugName으로 정렬
        unique_drugs.sort(key=lambda x: x.get('drugName', ''))
        
        try:
            with open(file_path, 'w', encoding='utf-8') as file:
                json.dump(unique_drugs, file, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"약품 목록 JSON 파일 쓰기 오류: {e}")
    
    
    def read_alert_exclusions_json(self, filename: str = "exclusion-list.json") -> List[Dict[str, Any]]:
        """JSON 형식의 결과 표시 제외 목록 파일 읽기"""
        file_path = self.app_directory / filename
        
        if not file_path.exists():
            # 파일이 없으면 빈 배열로 초기화
            self.write_alert_exclusions_json([], filename)
            return []
        
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                data = json.load(file)
                return data if isinstance(data, list) else []
        except (json.JSONDecodeError, Exception) as e:
            print(f"JSON 파일 읽기 오류: {e}")
            return []
    
    def write_alert_exclusions_json(self, exclusion_list: List[Dict[str, Any]], filename: str = "exclusion-list.json"):
        """JSON 형식의 결과 표시 제외 목록 파일 쓰기"""
        file_path = self.app_directory / filename
        
        # 정렬: 비핀 항목(상단) -> 핀 항목(하단), 각각 날짜 최신순
        def sort_key(item):
            is_pinned = item.get('isPinned', False)
            date_str = item.get('date', '1970-01-01T00:00:00')
            try:
                # ISO 형식 날짜를 파싱하여 정렬 키로 사용
                from datetime import datetime
                date_obj = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                # 핀된 항목은 나중에 오도록 (1), 비핀 항목은 먼저 오도록 (0)
                # 날짜는 최신순이므로 음수로 변환
                return (1 if is_pinned else 0, -date_obj.timestamp())
            except:
                # 날짜 파싱 실패 시 기본값
                return (1 if is_pinned else 0, 0)
        
        sorted_list = sorted(exclusion_list, key=sort_key)
        
        try:
            with open(file_path, 'w', encoding='utf-8') as file:
                json.dump(sorted_list, file, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"JSON 파일 쓰기 오류: {e}")
    
    
    
    
    
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