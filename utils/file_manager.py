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
    
    def read_config_file(self, filename: str = "info.txt") -> Dict[str, str]:
        """info.txt 설정 파일 읽기"""
        file_path = self.app_directory / filename
        
        if not file_path.exists():
            raise FileNotFoundError(f"파일을 찾을 수 없습니다: {file_path}")
        
        config_data = {}
        encoding = self._detect_encoding(file_path)
        
        with open(file_path, 'r', encoding=encoding) as file:
            for line in file.readlines():
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    config_data[key] = value
        
        return config_data
    
    def write_config_file(self, config_data: Dict[str, str], filename: str = "info.txt"):
        """info.txt 설정 파일 쓰기"""
        file_path = self.app_directory / filename
        
        # 기존 주석과 구조 유지하면서 업데이트
        lines = []
        
        # 헤더 주석
        lines.append("# 약품 재고 모니터링 시스템 설정 파일")
        lines.append("# 각 항목에 실제 계정 정보를 입력하세요")
        lines.append("")
        
        # 지오영 섹션
        lines.append("# 지오영(Geoweb) 계정 정보")
        lines.append(f"지오영활성화={config_data.get('지오영활성화', 'true')}")
        lines.append(f"지오영아이디={config_data.get('지오영아이디', '')}")
        lines.append(f"지오영비밀번호={config_data.get('지오영비밀번호', '')}")
        lines.append("")
        
        # 백제약품 섹션
        lines.append("# 백제약품(Baekje) 계정 정보")
        lines.append(f"백제활성화={config_data.get('백제활성화', 'false')}")
        lines.append(f"백제아이디={config_data.get('백제아이디', '')}")
        lines.append(f"백제비밀번호={config_data.get('백제비밀번호', '')}")
        lines.append("")
        
        # 기타 도매상들 (동적으로 추가된 것들)
        other_distributors = []
        for key, value in config_data.items():
            if key.endswith('아이디') and key not in ['지오영아이디', '백제아이디']:
                distributor_name = key.replace('아이디', '')
                password_key = distributor_name + '비밀번호'
                other_distributors.append((distributor_name, key, password_key))
        
        if other_distributors:
            lines.append("# 기타 도매상 계정 정보")
            for dist_name, id_key, pw_key in other_distributors:
                active_key = f"{dist_name}활성화"
                lines.append(f"{active_key}={config_data.get(active_key, 'false')}")
                lines.append(f"{id_key}={config_data.get(id_key, '')}")
                lines.append(f"{pw_key}={config_data.get(pw_key, '')}")
            lines.append("")
        
        # 모니터링 설정
        lines.append("# 모니터링 설정")
        lines.append(f"repeat_interval_minutes={config_data.get('repeat_interval_minutes', '30')}")
        lines.append(f"alert_exclusion_days={config_data.get('alert_exclusion_days', '7')}")
        
        # 파일 저장
        with open(file_path, 'w', encoding='utf-8') as file:
            file.write('\n'.join(lines))
    
    
    
    
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