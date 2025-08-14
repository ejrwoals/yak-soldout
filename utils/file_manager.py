import os
import json
import chardet
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime



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
    
    def read_drug_list(self, filename: str = "지오영 품절 목록.txt") -> List[str]:
        """품절 약품 목록 파일 읽기"""
        file_path = self.app_directory / filename
        
        if not file_path.exists():
            raise FileNotFoundError(f"파일을 찾을 수 없습니다: {file_path}")
        
        encoding = self._detect_encoding(file_path)
        
        with open(file_path, 'r', encoding=encoding) as file:
            lines = file.readlines()
        
        return [line.strip() for line in lines if line.strip()]
    
    def write_drug_list(self, drug_list: List[str], filename: str = "지오영 품절 목록.txt"):
        """품절 약품 목록 파일 쓰기"""
        file_path = self.app_directory / filename
        
        # 중복 제거 및 정렬
        unique_drugs = sorted(list(set(drug_list)))
        
        with open(file_path, 'w', encoding='utf-8') as file:
            for drug in unique_drugs:
                file.write(f'{drug.strip()}\n')
    
    def read_alert_exclusions(self, filename: str = "알림 제외.txt") -> List[str]:
        """알림 제외 목록 파일 읽기"""
        file_path = self.app_directory / filename
        
        if not file_path.exists():
            # 파일이 없으면 빈 파일 생성
            with open(file_path, 'w', encoding='utf-8') as file:
                pass
            return []
        
        encoding = self._detect_encoding(file_path)
        
        with open(file_path, 'r', encoding=encoding) as file:
            lines = file.readlines()
        
        return [line.strip() for line in lines if line.strip()]
    
    def write_alert_exclusions(self, exclusion_list: List[str], filename: str = "알림 제외.txt"):
        """알림 제외 목록 파일 쓰기"""
        file_path = self.app_directory / filename
        
        # 정렬된 리스트로 저장
        sorted_list = sorted(list(set(exclusion_list)))
        
        with open(file_path, 'w', encoding='utf-8') as file:
            for item in sorted_list:
                file.write(f'{item}\n')
    
    
    
    
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