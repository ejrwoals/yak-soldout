import pandas as pd
from typing import List, Dict, Tuple, Optional
from datetime import datetime
from models.drug_data import Drug, SearchResult


class DataProcessor:
    """데이터 처리 및 분석 클래스"""
    
    def __init__(self):
        pass
    
    def process_alert_exclusions(self, exclusion_list: List[str], 
                               exclusion_days: int) -> Tuple[List[str], List[str], bool]:
        """알림 제외 목록 처리"""
        now = datetime.now()
        current_hour = now.hour
        
        cleaned_exclusions = []
        excluded_drug_names = []
        none_stop_mode = False
        
        # 오후 4-6시에만 오래된 항목 정리
        if 16 <= current_hour < 18:
            for exclusion in exclusion_list:
                if '@' not in exclusion:
                    cleaned_exclusions.append(exclusion)
                    continue
                
                try:
                    date_part = exclusion.split('@')[0].strip()
                    drug_part = exclusion.split('@')[1].strip()
                    
                    # 날짜 파싱
                    date_str = date_part.split('일')[0] + '일'
                    exclusion_date = datetime.strptime(date_str, '%Y년 %m월 %d일')
                    
                    days_diff = (now - exclusion_date).days
                    
                    if days_diff > exclusion_days:
                        # 오래된 항목 제거 (none_stop_mode 활성화)
                        none_stop_mode = True
                    else:
                        # 유지
                        cleaned_exclusions.append(exclusion)
                        excluded_drug_names.append(drug_part)
                        
                except Exception as e:
                    print(f"알림 제외 날짜 파싱 오류: {e}")
                    cleaned_exclusions.append(exclusion)
        else:
            # 일반 시간대에는 그대로 유지
            for exclusion in exclusion_list:
                cleaned_exclusions.append(exclusion)
                if '@' in exclusion:
                    try:
                        drug_part = exclusion.split('@')[1].strip()
                        excluded_drug_names.append(drug_part)
                    except IndexError:
                        continue
        
        return cleaned_exclusions, excluded_drug_names, none_stop_mode
    
    
    
    
    def categorize_drugs(self, drugs: List[Drug], exclusion_list: List[str]) -> Tuple[List[Drug], List[Drug]]:
        """약품을 재고 있음/품절로 분류"""
        found_drugs = []
        soldout_drugs = []
        
        for drug in drugs:
            # 알림 제외 여부 설정
            drug.is_excluded_from_alert = self._is_in_exclusion_list(drug.name, exclusion_list)
            
            if drug.has_stock():
                found_drugs.append(drug)
            else:
                soldout_drugs.append(drug)
        
        return found_drugs, soldout_drugs
    
    def _is_in_exclusion_list(self, drug_name: str, exclusion_list: List[str]) -> bool:
        """알림 제외 목록에 있는지 확인"""
        for exclusion in exclusion_list:
            if '@' in exclusion:
                try:
                    excluded_name = exclusion.split('@')[1].strip()
                    if excluded_name == drug_name:
                        return True
                except IndexError:
                    continue
        return False
    
    def create_search_result(self, found_drugs: List[Drug], soldout_drugs: List[Drug],
                           exclusions: List[str], duration: float, 
                           errors: List[str] = None) -> SearchResult:
        """검색 결과 객체 생성"""
        return SearchResult(
            timestamp=datetime.now(),
            found_drugs=found_drugs,
            soldout_drugs=soldout_drugs,
            alert_exclusions=exclusions,
            search_duration=duration,
            errors=errors or []
        )
    
    def prepare_display_dataframes(self, search_result: SearchResult) -> Dict[str, pd.DataFrame]:
        """Streamlit 표시용 DataFrame 준비"""
        dataframes = {}
        
        # 발견된 약품 DataFrame
        if search_result.found_drugs:
            found_data = []
            for drug in search_result.found_drugs:
                found_data.append({
                    '도매': drug.distributor.value,
                    '메인센터': drug.main_stock,
                    '인천센터': drug.incheon_stock,
                    '비고': drug.notes,
                    '알림 제외 여부': drug.is_excluded_from_alert
                })
            dataframes['found'] = pd.DataFrame(found_data)
        
        # 품절 약품 DataFrame
        if search_result.soldout_drugs:
            soldout_data = []
            for drug in search_result.soldout_drugs:
                soldout_data.append({
                    '도매': drug.distributor.value,
                    '메인센터': drug.main_stock,
                    '인천센터': drug.incheon_stock,
                    '비고': drug.notes,
                    '알림 제외 여부': drug.is_excluded_from_alert
                })
            soldout_df = pd.DataFrame(soldout_data)
            # 알림 제외 여부와 도매별로 정렬
            soldout_df = soldout_df.sort_values(by=['알림 제외 여부', '도매'], ascending=[False, True])
            dataframes['soldout'] = soldout_df
        
        return dataframes