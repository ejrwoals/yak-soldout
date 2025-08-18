import pandas as pd
from typing import List, Dict, Tuple, Optional
from datetime import datetime
from models.drug_data import Drug, SearchResult


class DataProcessor:
    """데이터 처리 및 분석 클래스"""
    
    def __init__(self):
        pass
    
    def process_alert_exclusions(self, exclusion_list: List[Dict], 
                               exclusion_days: int) -> Tuple[List[Dict], Dict[str, List[str]]]:
        """결과 표시 제외 목록 처리 (JSON 형식, 도매상별로 구분)"""
        now = datetime.now()
        cleaned_exclusions = []
        excluded_by_distributor = {"지오영": [], "백제약품": []}
        
        for exclusion in exclusion_list:
            if not isinstance(exclusion, dict):
                continue
            
            drug_name = exclusion.get('drugName', '')
            distributor = exclusion.get('distributor', '')
            date_str = exclusion.get('date', '')
            is_pinned = exclusion.get('isPinned', False)
            
            # 핀된 항목은 항상 유지
            if is_pinned:
                cleaned_exclusions.append(exclusion)
                if distributor in excluded_by_distributor:
                    excluded_by_distributor[distributor].append(drug_name)
                continue
            
            # 날짜 확인 (exclusion_days 이내의 항목만 유지)
            try:
                exclusion_date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                days_diff = (now - exclusion_date).days
                
                if days_diff <= exclusion_days:
                    cleaned_exclusions.append(exclusion)
                    if distributor in excluded_by_distributor:
                        excluded_by_distributor[distributor].append(drug_name)
                # 오래된 항목은 자동 제거 (cleaned_exclusions에 추가하지 않음)
                    
            except Exception as e:
                # 날짜 파싱 실패 시 유지
                print(f"결과 표시 제외 날짜 파싱 오류: {e}")
                cleaned_exclusions.append(exclusion)
                if distributor in excluded_by_distributor:
                    excluded_by_distributor[distributor].append(drug_name)
        
        return cleaned_exclusions, excluded_by_distributor
    
    def categorize_drugs(self, drugs: List[Drug], exclusion_list: List[str]) -> Tuple[List[Drug], List[Drug]]:
        """약품을 재고 있음/품절로 분류"""
        found_drugs = []
        soldout_drugs = []
        
        for drug in drugs:
            # 결과 표시 제외 여부 설정
            drug.is_excluded_from_alert = self._is_in_exclusion_list(drug.name, exclusion_list)
            
            if drug.has_stock():
                found_drugs.append(drug)
            else:
                soldout_drugs.append(drug)
        
        return found_drugs, soldout_drugs
    
    def _is_in_exclusion_list(self, drug_name: str, exclusion_list: List[str]) -> bool:
        """결과 표시 제외 목록에 있는지 확인 (약품명 리스트로 간단하게 확인)"""
        return drug_name in exclusion_list
    
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
                    '결과 표시 제외 여부': drug.is_excluded_from_alert
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
                    '결과 표시 제외 여부': drug.is_excluded_from_alert
                })
            soldout_df = pd.DataFrame(soldout_data)
            # 결과 표시 제외 여부와 도매별로 정렬
            soldout_df = soldout_df.sort_values(by=['결과 표시 제외 여부', '도매'], ascending=[False, True])
            dataframes['soldout'] = soldout_df
        
        return dataframes