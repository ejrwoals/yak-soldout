import pandas as pd
import numpy as np
import random
from typing import List, Dict, Tuple, Optional
from datetime import datetime
from models.drug_data import Drug, PharmacyUsage, SearchResult


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
    
    def merge_with_usage_data(self, drugs: List[Drug], usage_df: pd.DataFrame) -> pd.DataFrame:
        """도매 약품 데이터와 월별 사용량 데이터 병합"""
        if usage_df is None or usage_df.empty:
            return pd.DataFrame()
        
        # Drug 리스트를 DataFrame으로 변환
        drug_data = []
        for drug in drugs:
            drug_data.append({
                '도매 약품명': drug.name,
                '유팜 약품명': '',  # 나중에 병합으로 채워짐
                '도매': drug.distributor.value,
                '메인센터': drug.main_stock,
                '인천센터': drug.incheon_stock,
                '유팜 현재고': 0,  # 나중에 병합으로 채워짐
                '유팜 월평균 사용량': 0,  # 나중에 병합으로 채워짐
                '현재고/월평균': 0,  # 나중에 병합으로 채워짐
                '보험코드': drug.insurance_code
            })
        
        if not drug_data:
            return pd.DataFrame()
        
        result_df = pd.DataFrame(drug_data)
        
        # 사용량 데이터와 병합 (suffixes 사용하여 컬럼명 충돌 방지)
        merged_df = result_df.merge(usage_df, on='보험코드', how='left', suffixes=('', '_usage'))
        
        # 사용량 데이터의 컬럼을 메인 컬럼으로 업데이트
        if '유팜 약품명_usage' in merged_df.columns:
            merged_df['유팜 약품명'] = merged_df['유팜 약품명_usage'].fillna(merged_df['유팜 약품명'])
        if '유팜 현재고_usage' in merged_df.columns:
            merged_df['유팜 현재고'] = merged_df['유팜 현재고_usage'].fillna(merged_df['유팜 현재고'])
        if '유팜 월평균 사용량_usage' in merged_df.columns:
            merged_df['유팜 월평균 사용량'] = merged_df['유팜 월평균 사용량_usage'].fillna(merged_df['유팜 월평균 사용량'])
        if '현재고/월평균_usage' in merged_df.columns:
            merged_df['현재고/월평균'] = merged_df['현재고/월평균_usage'].fillna(merged_df['현재고/월평균'])
        
        # 중복 컬럼 제거
        columns_to_drop = [col for col in merged_df.columns if col.endswith('_usage')]
        merged_df = merged_df.drop(columns=columns_to_drop)
        
        # 현재고/월평균 < 3인 것만 필터링
        merged_df = merged_df[merged_df['현재고/월평균'] < 3]
        merged_df = merged_df.sort_values(by=['현재고/월평균'], ascending=True)
        merged_df = merged_df.reset_index(drop=True)
        
        # 컬럼 순서 정리
        month_columns = [col for col in usage_df.columns if col.endswith('월')]
        final_columns = [
            '도매 약품명', '유팜 약품명', '도매', '메인센터', '인천센터',
            '유팜 현재고', '유팜 월평균 사용량', '현재고/월평균', '보험코드'
        ] + month_columns
        
        available_columns = [col for col in final_columns if col in merged_df.columns]
        merged_df = merged_df[available_columns]
        
        return merged_df
    
    def generate_briefing(self, drug_row: pd.Series, created_time: str) -> str:
        """개별 약품 브리핑 생성"""
        try:
            # 총 재고 계산
            if drug_row['인천센터'] == '-':
                total_stock = int(drug_row['메인센터'].replace(",", ""))
            else:
                main = int(drug_row['메인센터'].replace(",", ""))
                incheon = int(drug_row['인천센터'].replace(",", ""))
                total_stock = main + incheon
            
            # 잔여 기간 계산
            ratio = drug_row['현재고/월평균']
            if ratio < 1:
                remain = f"{round(ratio * 30, 1)} 일"
            else:
                remain = f"{round(ratio, 2)} 개월"
            
            # 브리핑 생성
            briefing = f"""
### {drug_row['도매']}) {drug_row['도매 약품명']}
✔ 현재 {drug_row['도매']} 재고 {total_stock} 통 있습니다. (통 단위)
#️⃣ | Upharm {created_time} 데이터 기준 |
#️⃣ Upharm {int(drug_row['유팜 현재고'])} 개 재고 보유 (낱알로)
#️⃣ 월평균 {drug_row['유팜 월평균 사용량']} 개 사용 (낱알로)
    → Upharm 전산상, {remain} 사용분 보유

---
"""
            return briefing
            
        except Exception as e:
            print(f"브리핑 생성 오류: {e}")
            return f"### {drug_row.get('도매 약품명', 'Unknown')} - 브리핑 생성 실패\n"
    
    def generate_random_proposals(self, proposal_df: pd.DataFrame, 
                                created_time: str, count: int = 3) -> List[str]:
        """랜덤 재고 제안 생성"""
        if proposal_df.empty or len(proposal_df) == 0:
            return []
        
        proposals = []
        max_count = min(count, len(proposal_df))
        
        try:
            # 랜덤 인덱스 생성
            random_indices = [random.randint(0, len(proposal_df) - 1) for _ in range(max_count)]
            
            for idx in random_indices:
                briefing = self.generate_briefing(proposal_df.iloc[idx], created_time)
                proposals.append(briefing)
                
        except Exception as e:
            print(f"랜덤 제안 생성 오류: {e}")
        
        return proposals
    
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