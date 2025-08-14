import os
import json
import chardet
import pandas as pd
import glob
import warnings
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

# xlrd 관련 경고 숨기기
warnings.filterwarnings("ignore", message=".*file size.*not 512.*")
warnings.filterwarnings("ignore", message=".*OLE2 inconsistency.*")


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
    
    def find_latest_usage_file(self, pattern: str = "월별 약품사용량_*.xls") -> Optional[Path]:
        """가장 최근의 월별 약품사용량 파일 찾기"""
        search_path = self.data_directory / pattern
        files = glob.glob(str(search_path))
        
        if not files:
            return None
        
        # 생성 시간 기준으로 정렬하여 최신 파일 반환
        latest_file = max(files, key=os.path.getctime)
        return Path(latest_file)
    
    def read_usage_excel(self, file_path: Optional[Path] = None) -> Optional[pd.DataFrame]:
        """월별 약품사용량 Excel 파일 읽기"""
        if file_path is None:
            file_path = self.find_latest_usage_file()
        
        if file_path is None or not file_path.exists():
            return None
        
        try:
            # Legacy 코드와 동일한 방식으로 처리
            for i in range(1, 10):
                files = sorted(glob.glob(str(self.data_directory / "월별 약품사용량_*.xls")), 
                             key=os.path.getctime)
                if len(files) < i:
                    break
                    
                current_file = Path(files[-i])
                df = pd.read_excel(current_file, header=3)
                
                # 4월 데이터가 있는지 확인 (충분한 데이터 확보 여부)
                if '4월' in df.columns and df['4월'].sum() > 0:
                    # 컬럼명 정리 (△, ▽ 제거)
                    df.columns = df.columns.str.replace('[△▽]', '', regex=True)
                    
                    # 필요한 컬럼만 추출
                    required_columns = ['청구코드', '약품명', '현재고',
                                      '1월', '2월', '3월', '4월', '5월', '6월',
                                      '7월', '8월', '9월', '10월', '11월', '12월']
                    
                    available_columns = [col for col in required_columns if col in df.columns]
                    df = df[available_columns]
                    
                    # 0을 NaN으로 변환 후, 전체가 NaN인 컬럼 제거
                    df = df.replace(0, pd.NA)
                    df = df.dropna(axis=1, how='all')
                    df = df.fillna(0).infer_objects(copy=False)
                    
                    # 월별 사용량 컬럼들 (청구코드, 약품명, 현재고 제외)
                    month_columns = [col for col in df.columns 
                                   if col not in ['청구코드', '약품명', '현재고']]
                    
                    # 마지막 컬럼은 불완전할 수 있으므로 제외
                    if month_columns:
                        month_columns = month_columns[:-1]
                    
                    # 월평균 사용량 계산
                    if month_columns:
                        df['월평균 사용'] = df[month_columns].mean(axis=1)
                        df['현재고/월평균'] = df['현재고'] / df['월평균 사용']
                        df = df.sort_values(by='현재고/월평균', ascending=True, ignore_index=True)
                    
                    # 컬럼명 변경 (Legacy 코드와 호환)
                    df.rename(columns={
                        '청구코드': '보험코드',
                        '약품명': '유팜 약품명',
                        '현재고': '유팜 현재고',
                        '월평균 사용': '유팜 월평균 사용량'
                    }, inplace=True)
                    
                    return df
            
            return None
            
        except Exception as e:
            print(f"Excel 파일 읽기 오류: {e}")
            return None
    
    def get_usage_file_creation_time(self, file_path: Optional[Path] = None) -> str:
        """사용량 파일의 생성 시간 반환"""
        if file_path is None:
            file_path = self.find_latest_usage_file()
        
        if file_path is None or not file_path.exists():
            return ""
        
        creation_time = os.path.getctime(file_path)
        return datetime.fromtimestamp(creation_time).strftime('%Y년 %m월 %d일')
    
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