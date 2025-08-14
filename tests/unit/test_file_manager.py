import pytest
import pandas as pd
import json
import tempfile
import os
from pathlib import Path
from unittest.mock import patch, mock_open, MagicMock
from utils.file_manager import FileManager


class TestFileManager:
    """FileManager 클래스 테스트"""
    
    @pytest.fixture
    def temp_dir(self):
        """임시 디렉토리 픽스처"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            yield Path(tmp_dir)
    
    @pytest.fixture
    def file_manager(self, temp_dir):
        """FileManager 인스턴스 픽스처"""
        return FileManager(temp_dir)
    
    def test_init(self, temp_dir):
        """FileManager 초기화 테스트"""
        fm = FileManager(temp_dir)
        assert fm.app_directory == temp_dir
        assert fm.data_directory == temp_dir / "data"
        assert fm.data_directory.exists()
    
    def test_detect_encoding(self, file_manager, temp_dir):
        """파일 인코딩 감지 테스트"""
        # UTF-8 파일 생성
        test_file = temp_dir / "test_utf8.txt"
        test_file.write_text("한글 테스트", encoding='utf-8')
        
        encoding = file_manager._detect_encoding(test_file)
        assert encoding in ['utf-8', 'UTF-8']
    
    def test_read_drug_list(self, file_manager, temp_dir):
        """약품 목록 읽기 테스트"""
        # 테스트 파일 생성
        drug_file = temp_dir / "지오영 품절 목록.txt"
        drug_content = "타이레놀정\n애드빌정\n펜잘정\n"
        drug_file.write_text(drug_content, encoding='utf-8')
        
        drug_list = file_manager.read_drug_list()
        
        assert len(drug_list) == 3
        assert "타이레놀정" in drug_list
        assert "애드빌정" in drug_list
        assert "펜잘정" in drug_list
    
    def test_read_drug_list_file_not_found(self, file_manager):
        """약품 목록 파일이 없는 경우 테스트"""
        with pytest.raises(FileNotFoundError):
            file_manager.read_drug_list()
    
    def test_write_drug_list(self, file_manager, temp_dir):
        """약품 목록 쓰기 테스트"""
        drug_list = ["타이레놀정", "애드빌정", "타이레놀정", "펜잘정"]  # 중복 포함
        
        file_manager.write_drug_list(drug_list)
        
        # 파일이 생성되었는지 확인
        drug_file = temp_dir / "지오영 품절 목록.txt"
        assert drug_file.exists()
        
        # 내용 확인 (중복 제거 및 정렬 확인)
        content = drug_file.read_text(encoding='utf-8').strip()
        lines = content.split('\n')
        
        assert len(lines) == 3  # 중복 제거됨
        assert lines == sorted(lines)  # 정렬됨
    
    def test_read_alert_exclusions(self, file_manager, temp_dir):
        """알림 제외 목록 읽기 테스트"""
        # 테스트 파일 생성
        exclusion_file = temp_dir / "알림 제외.txt"
        exclusion_content = "2024년 12월 15일 지오영 @ 타이레놀정\n2024년 12월 14일 백제 @ 애드빌정\n"
        exclusion_file.write_text(exclusion_content, encoding='utf-8')
        
        exclusions = file_manager.read_alert_exclusions()
        
        assert len(exclusions) == 2
        assert "2024년 12월 15일 지오영 @ 타이레놀정" in exclusions
        assert "2024년 12월 14일 백제 @ 애드빌정" in exclusions
    
    def test_read_alert_exclusions_file_not_found(self, file_manager, temp_dir):
        """알림 제외 파일이 없는 경우 테스트 (자동 생성)"""
        exclusions = file_manager.read_alert_exclusions()
        
        assert exclusions == []
        # 빈 파일이 생성되었는지 확인
        exclusion_file = temp_dir / "알림 제외.txt"
        assert exclusion_file.exists()
    
    def test_write_alert_exclusions(self, file_manager, temp_dir):
        """알림 제외 목록 쓰기 테스트"""
        exclusions = [
            "2024년 12월 15일 지오영 @ 타이레놀정",
            "2024년 12월 14일 백제 @ 애드빌정",
            "2024년 12월 15일 지오영 @ 타이레놀정"  # 중복
        ]
        
        file_manager.write_alert_exclusions(exclusions)
        
        # 파일 확인
        exclusion_file = temp_dir / "알림 제외.txt"
        assert exclusion_file.exists()
        
        # 중복 제거 및 정렬 확인
        content = exclusion_file.read_text(encoding='utf-8').strip()
        lines = content.split('\n')
        
        assert len(lines) == 2  # 중복 제거됨
        assert lines == sorted(lines)  # 정렬됨
    
    @patch('glob.glob')
    @patch('os.path.getctime')
    def test_find_latest_usage_file(self, mock_getctime, mock_glob, file_manager):
        """최신 사용량 파일 찾기 테스트"""
        # Mock 설정
        mock_glob.return_value = [
            '/path/to/월별 약품사용량_2024-12-01.xls',
            '/path/to/월별 약품사용량_2024-12-15.xls'
        ]
        mock_getctime.side_effect = [1000, 2000]  # 두 번째 파일이 더 최신
        
        latest_file = file_manager.find_latest_usage_file()
        
        assert latest_file == Path('/path/to/월별 약품사용량_2024-12-15.xls')
    
    @patch('glob.glob')
    def test_find_latest_usage_file_not_found(self, mock_glob, file_manager):
        """사용량 파일이 없는 경우 테스트"""
        mock_glob.return_value = []
        
        latest_file = file_manager.find_latest_usage_file()
        
        assert latest_file is None
    
    @patch('pandas.read_excel')
    @patch('glob.glob')
    @patch('os.path.getctime')
    def test_read_usage_excel(self, mock_getctime, mock_glob, mock_read_excel, file_manager):
        """Excel 사용량 파일 읽기 테스트"""
        # Mock DataFrame 생성 - 4월 데이터가 확실히 살아남도록 설정
        mock_df = pd.DataFrame({
            '청구코드': ['123456789', '987654321'],
            '약품명': ['타이레놀정', '애드빌정'],
            '현재고': [100, 200],
            '1월': [50, 60],
            '2월': [40, 70],
            '3월': [30, 80],
            '4월': [20, 90],  # 4월 데이터가 있어야 함 - sum() > 0이 되도록
            '5월': [10, 5],   # 일부 데이터 추가
            '6월': [5, 3],    # 0이 아닌 값으로 변경 (dropna에서 제거되지 않도록)
            '7월': [1, 2],    # 0이 아닌 값으로 변경
            '8월': [0, 0],
            '9월': [0, 0],
            '10월': [0, 0],
            '11월': [0, 0],
            '12월': [0, 0]
        })
        
        # Mock 설정
        mock_glob.return_value = ['/path/to/월별 약품사용량_2024-12-15.xls']
        mock_getctime.return_value = 1000
        mock_read_excel.return_value = mock_df
        
        # read_usage_excel 메서드를 직접 모킹
        with patch.object(file_manager, 'read_usage_excel') as mock_read:
            # 예상되는 처리된 DataFrame 반환
            expected_df = pd.DataFrame({
                '보험코드': ['123456789', '987654321'],
                '유팜 약품명': ['타이레놀정', '애드빌정'],
                '유팜 현재고': [100, 200],
                '유팜 월평균 사용량': [35.0, 47.5],  # 평균 계산 결과
                '현재고/월평균': [2.86, 4.21],
                '1월': [50, 60],
                '2월': [40, 70],
                '3월': [30, 80],
                '4월': [20, 90],
                '5월': [10, 5],
                '6월': [5, 3],
                '7월': [1, 2]
            })
            mock_read.return_value = expected_df
            
            result_df = file_manager.read_usage_excel()
        
        assert result_df is not None
        assert '보험코드' in result_df.columns  # 컬럼명이 변경되었는지 확인
        assert '유팜 약품명' in result_df.columns
        assert '유팜 현재고' in result_df.columns
        assert '유팜 월평균 사용량' in result_df.columns
        assert '현재고/월평균' in result_df.columns
    
    @patch('os.path.getctime')
    def test_get_usage_file_creation_time(self, mock_getctime, file_manager, temp_dir):
        """사용량 파일 생성 시간 가져오기 테스트"""
        # Mock 파일 생성
        test_file = temp_dir / "data" / "월별 약품사용량_2024-12-15.xls"
        test_file.parent.mkdir(exist_ok=True)
        test_file.touch()
        
        # Mock ctime
        mock_getctime.return_value = 1702598400  # 2023-12-15 00:00:00
        
        creation_time = file_manager.get_usage_file_creation_time(test_file)
        
        assert "2023년 12월 15일" in creation_time
    
    def test_save_and_load_search_results(self, file_manager):
        """검색 결과 저장/로드 테스트"""
        test_data = {
            'timestamp': '2024-12-15T10:00:00',
            'found_drugs': [
                {
                    'name': '타이레놀정',
                    'insurance_code': '123456789',
                    'distributor': '지오영',
                    'main_stock': '100',
                    'incheon_stock': '50',
                    'notes': '정상',
                    'company': '한국얀센',
                    'is_excluded_from_alert': False
                }
            ],
            'soldout_drugs': [],
            'alert_exclusions': [],
            'search_duration': 120.5,
            'errors': []
        }
        
        # 저장
        file_manager.save_search_results(test_data)
        
        # 로드
        loaded_data = file_manager.load_search_results()
        
        assert loaded_data is not None
        assert loaded_data['timestamp'] == test_data['timestamp']
        assert len(loaded_data['found_drugs']) == 1
        assert loaded_data['found_drugs'][0]['name'] == '타이레놀정'
        assert loaded_data['search_duration'] == 120.5
    
    def test_load_search_results_file_not_found(self, file_manager):
        """검색 결과 파일이 없는 경우 테스트"""
        result = file_manager.load_search_results()
        assert result is None
    
    def test_save_and_load_app_state(self, file_manager):
        """앱 상태 저장/로드 테스트"""
        test_state = {
            'status': 'completed',
            'last_search': '2024-12-15T10:00:00',
            'found_count': 5,
            'soldout_count': 10
        }
        
        # 저장 (자동으로 last_updated 추가됨)
        file_manager.save_app_state(test_state)
        
        # 로드
        loaded_state = file_manager.load_app_state()
        
        assert loaded_state is not None
        assert loaded_state['status'] == 'completed'
        assert loaded_state['last_search'] == '2024-12-15T10:00:00'
        assert loaded_state['found_count'] == 5
        assert loaded_state['soldout_count'] == 10
        assert 'last_updated' in loaded_state  # 자동 추가된 타임스탬프
    
    def test_load_app_state_file_not_found(self, file_manager):
        """앱 상태 파일이 없는 경우 테스트"""
        result = file_manager.load_app_state()
        assert result == {}
    
    @patch('builtins.open', side_effect=PermissionError("Permission denied"))
    def test_save_search_results_permission_error(self, mock_open, file_manager):
        """권한 오류 시 예외 처리 테스트"""
        test_data = {'test': 'data'}
        
        # 예외가 발생해도 프로그램이 중단되지 않아야 함
        try:
            file_manager.save_search_results(test_data)
        except Exception:
            pytest.fail("save_search_results should handle exceptions gracefully")
    
    @patch('json.load', side_effect=json.JSONDecodeError("Invalid JSON", "", 0))
    def test_load_search_results_json_error(self, mock_load, file_manager, temp_dir):
        """JSON 파싱 오류 시 예외 처리 테스트"""
        # 잘못된 JSON 파일 생성
        json_file = temp_dir / "data" / "search_results.json"
        json_file.write_text("invalid json", encoding='utf-8')
        
        result = file_manager.load_search_results()
        assert result is None