import streamlit as st
import time
import pandas as pd
import numpy as np
import ctypes  # for popup message
import re
import chardet # 파일 인코딩을 자동으로 감지
import os
import glob
import random
from datetime import datetime

# =================== 셀레니움 세팅 =========================== #
# 참고 사이트 :
# https://discuss.streamlit.io/t/selenium-web-scraping-on-streamlit-cloud/21820/6 
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.support.ui import Select  # Select tag 제어를 위해 사용
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.firefox import GeckoDriverManager

firefoxOptions = Options()
firefoxOptions.add_argument("--headless")
service = Service(GeckoDriverManager().install())
driver = webdriver.Firefox(options=firefoxOptions, service=service)
## ==============================================================================================
def merge_monthly(result_df, monthly_use_df, monthly_columns):
    # result_df의 '보험코드'에 대응하는 monthly_use_df의 '보험코드'를 찾아서 '유팜 현재고', '유팜 월평균 사용량', '현재고/월평균' 값을 result_df의 새로운 컬럼으로 추가하기
    proposal_df = result_df.copy()
    proposal_df.reset_index(names=['도매 약품명'], inplace=True)  # 인덱스를 초기화하고 기존 인덱스를 컬럼으로 추가
    proposal_df = proposal_df.merge(monthly_use_df, on='보험코드', how='left')
    proposal_df = proposal_df[proposal_df['현재고/월평균'] < 3]
    proposal_df.sort_values(by=['현재고/월평균'], ascending=True, inplace=True)
    proposal_df.reset_index(inplace=True)
    new_columns = ['도매 약품명', '유팜 약품명', '도매', '메인센터', '인천센터',
                    '유팜 현재고', '유팜 월평균 사용량', '현재고/월평균', '보험코드'] + monthly_columns
    proposal_df = proposal_df[new_columns]
    return proposal_df

# 약품 하나씩 마크다운 브리핑 출력
def briefing(chunk, created_time):
    # chunk.columns = ['도매 약품명', '유팜 약품명', '도매', '메인센터', '인천센터',
    #                  '유팜 현재고', '유팜 월평균 사용량', '현재고/월평균', '보험코드'] + 1 ~ 12월
    
    if chunk['인천센터'] == '-':
        jaego = int(chunk['메인센터'].replace(",", ""))
    else:
        jaego = int(chunk['메인센터'].replace(",", "")) + int(chunk['인천센터'].replace(",", ""))

    if chunk['현재고/월평균'] < 1:
        remain = f"{round(chunk['현재고/월평균']*30,1)} 일"
    else:
        remain = f"{round(chunk['현재고/월평균'],2)} 개월"
    
    md = f'''
    ### {chunk['도매']})  {chunk['도매 약품명']}
    ✔ 현재 {chunk['도매']} 재고 {jaego} 통 있습니다. (통 단위)
    #️⃣ | Upharm {created_time} 데이터 기준 |
    #️⃣  Upharm {int(chunk['유팜 현재고'])} 개 재고 보유 (낱알로)
    #️⃣  월평균 {chunk['유팜 월평균 사용량']} 개 사용 (낱알로)
        →  Upharm 전산상, {remain} 사용분 보유\n---\n
    '''
    return md

def main():
    st.set_page_config(layout="wide")
    st.markdown("<h1 style='text-align: center;'>품절 약품 재고 자동 체크</h1>", 
                unsafe_allow_html=True)
    st.markdown("<h1 style='text-align: center;'>New version</h1>", 
    unsafe_allow_html=True)
    st.markdown("<h4 style='text-align: center; color: red;'>- 백제, 지오영, 대웅TheSHOP -</h4>", 
                unsafe_allow_html=True)
    st.markdown("<h4 style='text-align: right; color: grey;'>by ChaJM</h4>", 
                unsafe_allow_html=True)
    st.markdown("<h6 style='text-align: left; color: grey;'>(마지막 버전 업데이트 날짜 : 2024-11-23)</h6>", 
                unsafe_allow_html=True)
    
    ## ============================== 필요한 파일 읽어오는 단계 ======================================
    # 변수 초기화
    id_G50 = None
    password_G50 = None
    id_BJ = None
    password_BJ = None
    id_DW = None
    password_DW = None
    TIME_INTERVAL = None  # 실행 간격(time interval) 설정
    time_interval = None

    # 파일 경로
    desktop_path = r'C:\Users\USER\Videos\Desktop' # 바탕화면 경로
    user_folder_path = r'C:\Users\USER' # user 폴더 경로
    consulting_statistics_path = r'C:\@Pharm\EXCEL' # 유팜 컨설팅 통계에서 Excel로 내보내기 하면 저장되는 경로

    # info.txt 파일 경로
    file_path = os.path.join(desktop_path,'info.txt')

    try:
        # 파일 열기
        with open(file_path, 'rb') as file:
            result = chardet.detect(file.read())
        with open(file_path, 'r', encoding=result['encoding']) as file:
            # 파일의 각 줄을 읽어오기
            lines = file.readlines()

            id_BJ = None
            password_BJ = None
            id_DW = None
            password_DW = None

            # 각 줄을 순회하며 정보 추출
            for line in lines:
                # 각 줄을 =을 기준으로 분리하여 key와 value로 나누기
                key, value = line.strip().split('=')
                key = key.strip()
                # key에 따라 변수에 할당
                if key == '지오영아이디':
                    id_G50 = value.strip()
                elif key == '지오영비밀번호':  # 지오영 아이디, 비번은 꼭 입력해야함. 보험코드 정보를 읽어와야 하므로
                    password_G50 = value.strip()
                elif key == '백제아이디':
                    if len(value) == 1:
                        pass
                    else:
                        id_BJ = value.strip()
                elif key == '백제비밀번호':  
                    if len(value) == 1:
                        pass
                    else: # 백제 비번이 빈칸일 경우 백제 검색과정 스킵함.
                        password_BJ = value.strip()
                elif key == '대웅아이디':
                    if len(value) == 1:
                        pass
                    else:
                        id_DW = value.strip()
                elif key == '대웅비밀번호':  
                    if len(value) == 1:
                        pass
                    else: # 대웅더샵 비번이 빈칸일 경우 대웅더샵 검색과정 스킵함.
                        password_DW = value.strip()
                elif key == '반복실행간격(분)':
                    TIME_INTERVAL = int(value.strip())
                elif key == '재고발견이후알림제외기간(일)':
                    # 재고발견이후알림제외기간 설정 : 재고를 발견한 이후 N일 동안은 해당 약의 재고 발견 알림을 받지 않음. (0 일 경우, 알림을 제외하지 않고 계속 받음)
                    # 99 처럼 큰 값을 입력해놓고, 내가 직접 알림제외.txt 파일을 편집하면서 운영해도 됨.
                    try:
                        no_alarm_period = int(value.strip())
                    except:
                        print("info.txt / '재고발견이후알림제외기간' 설정 오류")
                        no_alarm_period = 0
                else:
                    pass

    except FileNotFoundError:
        print(f"Error: 파일 '{file_path}'을 찾을 수 없습니다.")
    except Exception as e:
        print("[info.txt 파트 에러] :", e)

    # 알림 제외.txt 파일 읽어와서 과거에 이미 재고를 발견했던 약들은 알림을 하지 않도록 함
    with open(os.path.join(desktop_path, '알림 제외.txt'), 'rb') as file:
        result = chardet.detect(file.read())
    with open(os.path.join(desktop_path, '알림 제외.txt'), 'r', encoding=result['encoding']) as file:
        lines = file.readlines()
    history = []
    overlab_test = []
    now = datetime.now()

    none_stop_mode = False  # default값은 False로 해둠. 즉, 재고 발견하면 그 즉시 검색 멈추고 알림 팝업 띄우게 설정.
    
    for line in lines:
        t = line.split('@')[0].strip('\n ')
        date_part = t.split('일')[0] + '일'
        date = datetime.strptime(date_part, '%Y년 %m월 %d일')
        days_diff = (now - date).days

        # ========== 오후 4시 이후에만 작동하도록 설정 ===============
        current_time = time.localtime(time.time()) # 현재 시간을 가져옵니다.
        if 16 <= current_time.tm_hour < 18:  # 오후 4 ~ 6시 사이에만 작동
            # 오래된 line은 스킵함으로써 알림 제외 리스트에서 지움.
            if days_diff > no_alarm_period: # 설정한 기간보다 지난 약들은 제외. >=로 하지 않는 이유는 0으로 설정했을떄 당일에 귀찮게 계속 알림 뜨는걸 방지하기 위함
                none_stop_mode = True  # 알림 제외 리스트에서 삭제되는 약이 1개라도 있는 경우에는 none_stop_mode를 켜서 발견한 약들을 한번에 다 띄워주게끔 함.(귀찮게 알람 단발로 계속 울리는 것 방지용)
                pass 
            else:
                history.append(line.strip('\n'))
                overlab_test.append(line.split('@')[1].strip('\n '))
        else: # 그 외에 시간이라면 그냥 그대로 복붙
            history.append(line.strip('\n'))
            overlab_test.append(line.split('@')[1].strip('\n '))
        # ===========================================================

    # 지오영 품절 목록.txt 파일을 불러옴
    with open(os.path.join(desktop_path, '지오영 품절 목록.txt'), 'rb') as file:
        result = chardet.detect(file.read())
    with open(os.path.join(desktop_path, '지오영 품절 목록.txt'), 'r', encoding=result['encoding']) as file:
        lines = file.readlines()
    drug_list = [line.strip('\n') for line in lines]

    # 유팜 월별 약품사용량.xls 파일 읽어오기
    try:
        for i in range(1, 10):
            latest_file_path = sorted(glob.glob(os.path.join(consulting_statistics_path,   # '월별 약품사용량_' 으로 시작하는 모든 파일명 중 가장 최근 파일 찾기
                                                       '월별 약품사용량_*.xls')), key=os.path.getctime)[-i] # '월별 약품사용량_*.xls')), key=os.path.getctime)[-i]
            created_time = datetime.fromtimestamp(os.path.getctime(latest_file_path)).strftime('%Y년 %m월 %d일')  # 파일 생성 날짜 
            monthly_use_df = pd.read_excel(latest_file_path, header=3)
            
            if monthly_use_df['4월'].sum() == 0:  
                # 4월 데이터가 없다는 것은 현재 시점이 1,2,3월 중 하나라는 뜻. 그러면 3개월 이상의 충분한 데이터가 없으므로 다른 파일을 탐색.
                monthly_use_df = None
            else:
                break

        # 컬럼명에 포함된 △ 이나 ▽ 문자 제거
        monthly_use_df.columns = monthly_use_df.columns.str.replace('[△▽]', '', regex=True)

        monthly_use_df = monthly_use_df[['청구코드', '약품명', '현재고',
                '1월', '2월', '3월', '4월', '5월', '6월',
                '7월', '8월', '9월', '10월', '11월', '12월']]
                
        # 사용량이 전부 0인 달은 drop하기
        monthly_use_df = monthly_use_df.replace(0, np.nan)
        monthly_use_df = monthly_use_df.dropna(axis=1, how='all')  # how='all'로 할 경우 모든 값이 NaN일때만 column을 drop함.
        monthly_use_df = monthly_use_df.fillna(0) # NaN 값을 0으로 다시 채움

        columns = list(monthly_use_df.columns)[:-1] # 마지막 열은 아직 한달이 채 완료되지 않은 달일 수 있므로 제외함.
        columns.remove('약품명')
        columns.remove('현재고')
        columns.remove('청구코드')
        
        # 월평균 사용량 계산
        monthly_use_df['월평균 사용'] = monthly_use_df[columns].mean(axis=1)
        
        # 월평균 사용량 대비 현재고의 비율을 계산하고, 오름차순으로 정렬
        monthly_use_df['현재고/월평균'] = monthly_use_df['현재고'] / monthly_use_df['월평균 사용']
        monthly_use_df = monthly_use_df.sort_values(by='현재고/월평균', ascending=True, ignore_index=True)

        monthly_use_df.rename(columns={'청구코드':'보험코드',
                                       '약품명':'유팜 약품명',
                                       '현재고':'유팜 현재고',
                                       '월평균 사용':'유팜 월평균 사용량'}, inplace=True)

    except IndexError:
        # 파일이 존재하지 않는 경우
        monthly_use_df = None
    
    if history is None:
        st.write("⚠️ 바탕화면에 '알림 제외.txt' 파일이 없습니다. ⚠️")
        error_message = "바탕화면에 '알림 제외.txt' 파일이 없습니다."
        print(error_message)
        return None
    
    if monthly_use_df is None:
        st.write("⚠️ 유팜 컨설팅 통계 - {} 경로에서 월별 약품사용량 Excel 파일을 읽어오지 못했습니다. ⚠️".format(consulting_statistics_path))
        st.write("⚠️ [컨설팅 통계] - [약품 통계] - [월별 약품사용량]에서 excel 파일로 내보내기를 하고 재실행 해주세요 ⚠️")
        error_message = "유팜 컨설팅 통계 - 월별 약품사용량 Excel 파일을 읽어오지 못했습니다."
        print(error_message)
        return None
    else:
        st.markdown("<p style='text-align: left; color: green;'> ✅ 월별 약품사용량.xls 파일을 정상적으로 읽었습니다 ({} 생성된 파일) ✅ </p>".format(created_time), 
                    unsafe_allow_html=True)
    
    if drug_list is None:
        st.write("⚠️ 바탕화면에 '지오영 품절 목록.txt' 파일이 없습니다. ⚠️")
        error_message = "바탕화면에 '지오영 품절 목록.txt' 파일이 없습니다."
        print(error_message)
        return None
    else:
        st.markdown("<p style='text-align: left; color: green;'> ✅ 지오영 품절 목록.txt 파일을 정상적으로 읽었습니다 ✅ </p>", 
                    unsafe_allow_html=True)
        st.markdown("""---""")
        st.write('\n\n')
        print("...재고 검색중...")
        
        bohum_code_dict_G50 = {} # key : 보험코드 / value : 지오영 약이름
        result_dict = {}
        soldout_dict = {}

        # placeholder로 웹페이지 구조 잡기
        placeholder_0 = st.empty()   # 임시 확인용
        # placeholder_0.dataframe(monthly_use_df)
        placeholder_1 = st.empty()   # 로그인 및 검색 상황, 검색 완료 시간 등 [현재 상태]를 보여주는 곳
        placeholder_2 = st.empty()   # 현재 모두 품절 or 재고 발견! 문구
        placeholder_2_2 = st.empty() # 다음 검색까지 몇분 남았는지 표시
        placeholder_3 = st.empty()   # 알람 필요한 재고가 발견된 경우, 발견된 재고 df를 띄워줌
        placeholder_3_1 = st.empty() # 발견 재고 브리핑
        placeholder_3_2 = st.empty() # 발견 재고 브리핑
        st.write('\n\n')
        with st.expander("| 검토 제안 |"):
            placeholder_3_3 = st.empty()
            placeholder_3_3.text('** 현재 도매상에 있는 약품들 중, 재고 확충을 하면 좋을만한 약품들을 제안합니다. **')
            placeholder_3_4 = st.empty()
            placeholder_3_5 = st.empty()
            placeholder_3_6 = st.empty()
        st.write('\n\n') 
        with st.expander("| 품절약 목록 |"):
            placeholder_4 = st.empty()   # [품절약 목록]
            placeholder_4.text('검색중...')
            placeholder_5 = st.empty()   # dataframe 표시
        st.write('\n\n')
        with st.expander("| 알림 제외 목록 |"):
            placeholder_6 = st.empty()
            placeholder_6.text('** 한 번 재고를 발견한 약은 이후 {}일동안 재고 발견 알림이 울리지 않습니다 **'.format(no_alarm_period))
            placeholder_7 = st.empty()   # list 표시
        st.markdown("""---""")
        placeholder_last = st.empty()  # End
        placeholder_last.text("- End -")
        st.write('\n\n')
        st.write('| 검색 실패 로그 |')
        
        ## ============================== 지오영 시작 ==================================================
        placeholder_1.text('🤖 지오영에 로그인하는 중입니다...')
        driver.get("https://order.geoweb.kr/Member/Login")
        login_id = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.CSS_SELECTOR, '#LoginID')))
        login_id.send_keys(id_G50)

        login_pw = driver.find_element(By.CSS_SELECTOR, '#Password')
        login_pw.send_keys(password_G50)

        login_pw.send_keys(Keys.RETURN)
        time.sleep(2)

        try:
            wrong_pw = driver.find_element(By.CSS_SELECTOR, '#baseDialog > div > section > div > div')
            st.write('에러 : 지오영 ' + wrong_pw.text)
            print(wrong_pw)
            if wrong_pw:
                driver.close()
            print('로그인 에러')
        except:
            # 팝업창 제거
            try:
                ad_popup_css = 'button.ui-button:nth-child(1) > span:nth-child(1)'
                ad_popup = driver.find_element(By.CSS_SELECTOR, ad_popup_css)
                ad_popup.click()
                print('광고 팝업창 닫음')
                time.sleep(1)
            except:
                pass
            try:
                sulmun_css = '.btn_not_open'
                sulmun_popup = driver.find_element(By.CSS_SELECTOR, sulmun_css)
                sulmun_popup.click()
                print('설문조사 팝업창 닫음')
                time.sleep(1)
            except:
                pass

            # 약 재고 체크
            for drug in drug_list:
                placeholder_1.text('🤖 지오영 재고를 체크하는 중입니다... \n검색중 : %s'%drug)  
                search = driver.find_element(By.CSS_SELECTOR, '#txt_product')
                search.clear() # 검색창 비우기
                search.send_keys(drug)
                search.send_keys(Keys.RETURN)
                time.sleep(2)
                
                # 팝업창 제거
                try:
                    popup_selector = '#wrap > div.ui-dialog.ui-widget.ui-widget-content.ui-corner-all.ui-front.ui-dialog-buttons.ui-draggable.ui-resizable > div.ui-dialog-buttonpane.ui-widget-content.ui-helper-clearfix > div > button:nth-child(2) > span'
                    popup = driver.find_element(By.CSS_SELECTOR, popup_selector)
                    popup.click()
                    time.sleep(1)
                except:
                    pass
                
                # 지오영은 맨 첫번째 줄의 약만 읽어옴
                try:
                    # 기본 : 동부센터
                    name_css = '#tbodySearchProduct > tr:nth-child(1) > td.proName'
                    name = WebDriverWait(driver, 2).until(EC.presence_of_element_located((By.CSS_SELECTOR, name_css))).text
                    name = name.replace('\n', ' ')  # 약 이름에 줄바꿈이 포함되어 있다면 제거
                    stock = driver.find_element(By.CSS_SELECTOR, '#tbodySearchProduct > tr:nth-child(1) > td.stock').text
                    
                    # 앞에서 재고 발견했던 약품은 다음 검색에서 제외시키는 작업
                    # if name in overlab_test:
                    #     continue

                    # 보험코드
                    bohum_code = driver.find_element(By.CSS_SELECTOR, '#tbodySearchProduct > tr:nth-child(1) > td.code').text
                
                    # 백제 검색을 위한 밑 작업
                    bohum_code_dict_G50.setdefault(bohum_code, drug)

                    # 제약사
                    company = driver.find_element(By.CSS_SELECTOR, '#tbodySearchProduct > tr:nth-child(1) > td.phaCompany > span').text

                    # 인천센터 재고
                    try:
                        incheon_css = '#div-product-info > div.another_center_board.board_wrap > div > table > tbody > tr > td:nth-child(2)'
                        incheon = driver.find_element(By.CSS_SELECTOR, incheon_css).text
                    except:
                        incheon = '0' # 인천센터 재고 미확인이지만 뒤에 경우의수 처리 때 편하게 하려고 그냥 0으로 간주

                    # 비고
                    try:
                        bigo = driver.find_element(By.CSS_SELECTOR, '#product-detail-note').text # 비고 메시지
                    except:
                        bigo = '-'
                    
                    # [경우의 수 처리]
                    if stock == '0':
                        stock = '품절'
                        if incheon == '0':
                            incheon = '품절'
                            # 지오영 둘 다 품절인 경우
                            soldout_dict.setdefault(name, ["지오영", stock, incheon, bigo, bohum_code, name in overlab_test])
                            time_interval = TIME_INTERVAL
                        else:
                            # 인천센터 재고 있는 경우!
                            result_dict.setdefault(name, ["지오영", stock, incheon, bigo, bohum_code, name in overlab_test])
                            found_time = time.strftime('%Y년 %m월 %d일 %X', time.localtime(time.time()))
                            if name not in overlab_test:  # 알림을 받아야하고, 
                                done_log = found_time + ' 지오영 @ ' + name
                                done_list.append(done_log)      
                                if not none_stop_mode:    # 즉시 종료 모드라면
                                    break                 # 끝내기
                                else:                     # 즉시 종료 모드가 아니라면
                                    pass                  # 넘어가기
                            else:                         # 알림을 안 받아도 되면
                                pass                      # 넘어가기
                            
                    else:
                        # 지오영 메인센터 재고 있는 경우!
                        result_dict.setdefault(name, ["지오영", stock, incheon, bigo, bohum_code, name in overlab_test])
                        found_time = time.strftime('%Y년 %m월 %d일 %X', time.localtime(time.time()))
                        if name not in overlab_test:  # 알림을 받아야하고, 
                            done_log = found_time + ' 지오영 @ ' + name
                            done_list.append(done_log)
                            if not none_stop_mode:    # 즉시 종료 모드라면
                                break                 # 끝내기
                            else:                     # 즉시 종료 모드가 아니라면
                                pass                  # 넘어가기
                        else:                         # 알림을 안 받아도 되면
                            pass                      # 넘어가기
                        
                except:
                    st.write(drug, ': 지오영 검색 실패')
                
        ## ================================== 지오영 끝 ===============================================
        
        if not password_BJ:
            pass # 백제 비밀번호가 없을 경우, 백제 검색 과정을 skip 함.
        else:
            ## ============================= 백제 ================================================
            placeholder_1.text('🤖 백제약품에 로그인하는 중입니다...')
            driver.get("https://www.ibjp.co.kr/login.act")
            login_id = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.CSS_SELECTOR, '#loginId')))
            login_id.send_keys(id_BJ)

            login_pw = driver.find_element(By.CSS_SELECTOR, '#pwd')
            login_pw.send_keys(password_BJ)

            login_pw.send_keys(Keys.RETURN)
            time.sleep(2)

            # 약 재고 체크
            for code in bohum_code_dict_G50.keys():
                if code.strip() == '': # 지오영에 가끔 보험코드 안 써있는 약들도 있어서.. 
                        pass         # 이런건 어쩔 수 없이 백제 검색 pass ㅠㅠ
                
                search = WebDriverWait(driver, 3).until(EC.presence_of_element_located((By.CSS_SELECTOR, '#SEARCH_NM')))

                # 보험코드 검색 모드로 변경 (Select tag 제어)
                select_mode = Select(driver.find_element(By.CSS_SELECTOR, '#SEARCH_GB'))
                time.sleep(1)
                select_mode.select_by_visible_text("보험코드")
                
                # 검색창에 보험코드 검색
                search.clear() # 검색창 비우기
                search.send_keys(code)
                search.send_keys(Keys.RETURN)
                time.sleep(2)
                
                # 첫번째 child
                try:
                    name_css = '#itemListTable > tbody > tr:nth-child(1) > td:nth-child(2)'
                    name = WebDriverWait(driver, 2).until(EC.presence_of_element_located((By.CSS_SELECTOR, name_css))).text
                    name = name.replace('\n', ' ')  # 약 이름에 줄바꿈이 포함되어 있다면 제거
                    
                    # 앞에서 재고 발견했던 약품은 다음 검색에서 제외시키는 작업
                    # if name in overlab_test:
                    #     continue

                    placeholder_1.text('🤖 백제약품 재고를 체크하는 중입니다... \n검색중 : %s'%name)

                    stock_css = '#itemListTable > tbody > tr:nth-child(1) > td:nth-child(5)'
                    stock = driver.find_element(By.CSS_SELECTOR, stock_css).text

                    # [ 경우의수 처리 ]
                    if stock == '품절':
                        soldout_dict.setdefault(name, ["백제", stock, "-", "-", code, name in overlab_test])
                        time_interval = TIME_INTERVAL
                    else:
                        # 백제에 재고 있음!
                        result_dict.setdefault(name, ["백제", stock, "-", "-", code, name in overlab_test])
                        found_time = time.strftime('%Y년 %m월 %d일 %X', time.localtime(time.time()))
                        if name not in overlab_test:  # 알림을 받아야하고, 
                            done_log = found_time + ' 백제 @ ' + name
                            done_list.append(done_log)
                            if not none_stop_mode:    # 즉시 종료 모드라면
                                break                 # 끝내기
                            else:                     # 즉시 종료 모드가 아니라면
                                pass                  # 넘어가기
                        else:                         # 알림을 안 받아도 되면
                            pass                      # 넘어가기

                except:
                    st.write(bohum_code_dict_G50[code], ' : 백제 검색 실패')

                # 두번째~세번째 child
                for n in range(2, 4):
                    name_child = '#itemListTable > tbody > tr:nth-child(%d) > td:nth-child(2)'%n
                    stock_child = '#itemListTable > tbody > tr:nth-child(%d) > td:nth-child(5)'%n
                    try:
                        name = driver.find_element(By.CSS_SELECTOR, name_child).text
                        name = name.replace('\n', ' ')  # 약 이름에 줄바꿈이 포함되어 있다면 제거
                        stock = driver.find_element(By.CSS_SELECTOR, stock_child).text
                        
                        # 앞에서 재고 발견했던 약품은 다음 검색에서 제외시키는 작업
                        # if name in overlab_test:
                        #     continue
                        
                        # [ 경우의수 처리 ]
                        if stock == '품절':
                            soldout_dict.setdefault(name, ["백제", stock, "-", "-", code, name in overlab_test])
                            time_interval = TIME_INTERVAL
                        else:
                            # 백제에 재고 있음!
                            result_dict.setdefault(name, ["백제", stock, "-", "-", code, name in overlab_test])
                            found_time = time.strftime('%Y년 %m월 %d일 %X', time.localtime(time.time()))
                            if name not in overlab_test:  # 알림을 받아야하고, 
                                done_log = found_time + ' 백제 @ ' + name
                                done_list.append(done_log)
                                if not none_stop_mode:    # 즉시 종료 모드라면
                                    break                 # 끝내기
                                else:                     # 즉시 종료 모드가 아니라면
                                    pass                  # 넘어가기
                            else:                         # 알림을 안 받아도 되면
                                pass                      # 넘어가기
                            
                    except:
                        pass    
        # =========================================================================================
        
        if not password_DW:
            pass # 더샵 비밀번호가 없을 경우, 대웅더샵 검색 과정을 skip 함.
        else:
            ## ============================= 대웅 더샵 ==============================================
            placeholder_1.text('🤖 대웅TheSHOP에 로그인하는 중입니다...')
            driver.get("https://www.shop.co.kr/front/intro/login")
            driver.implicitly_wait(10)

            login_id = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.CSS_SELECTOR, '#userId')))
            login_id.send_keys(id_DW)

            login_pw = driver.find_element(By.CSS_SELECTOR, '#userPwd')
            login_pw.send_keys(password_DW)

            login_pw.send_keys(Keys.RETURN)
            driver.implicitly_wait(10)

            # 약 재고 체크
            for code in bohum_code_dict_G50.keys():
                # print('='*5, bohum_code_dict_G50[code] ,'='*5)
                if code.strip() == '': # 지오영에 가끔 보험코드 안 써있는 약들도 있어서..
                    # print('지오영에 보험코드 안 써있는 약이라 스킵')
                    continue         # 이런건 어쩔 수 없이 검색 pass하고 실패 메시지 프린트 안함.
                
                # 가끔 한번에 검색 안될때 있어서 한번 더 retry 하는 코드 넣음ㅠ
                retry = 2
                for _ in range(retry):
                    try:
                        search = WebDriverWait(driver, 3).until(EC.presence_of_element_located((By.CSS_SELECTOR, '#search_input')))
                        if search:
                            # 검색창에 보험코드 검색
                            search.clear() # 검색창 비우기
                            search.send_keys(code)
                            search.send_keys(Keys.RETURN)
                            time.sleep(2)
                            break
                    except: # 더샵 로그인하고 맨처음에 딱 한 번만 에러나는듯..?
                        continue
                
                # 첫번째 child
                try:
                    first_name_css = '#__next > div.layout_wrapper__Lo3KL.layout_search__K3p2f > div:nth-child(2) > div > div > div.search-result_inner__GdwKA.search-result_result_box__kcXDW > div > div.search-result_result_wrap__1Ti_h > div > div > div > div > div > div > div > div > div > div > div.item_name_box__jVarh > div.item_d_flex__T2jvP.item_item_name__xXO0T > div > strong' # 이걸로 하면 에러 훨씬 덜 남.
                    # 예전꺼 : '#__next > div.layout_wrapper__Lo3KL.layout_search__K3p2f > div > div > div > div.search-result_inner__GdwKA.search-result_result_box__kcXDW > div.search-result_result_inner__qyG3b > div.search-result_result_wrap__1Ti_h > div > div > div > div > div > div > div > div > ul > li.item_active__zQEsj > div > div.item_info_box__bi2tB > div.item_d_flex__T2jvP.item_name_box__jVarh > div'
                                     
                    first_name = driver.find_element(By.CSS_SELECTOR, first_name_css).text
                    first_name = first_name.replace('\n', ' ')  # 약 이름에 줄바꿈이 포함되어 있다면 제거
                    
                    try:  # last_name : 몇 T짜리인지 규격 정보가 있다면 읽어옴    
                        last_name_css = '#__next > div.layout_wrapper__Lo3KL.layout_search__K3p2f > div:nth-child(2) > div > div > div.search-result_inner__GdwKA.search-result_result_box__kcXDW > div > div.search-result_result_wrap__1Ti_h > div > div > div > div > div > div > div > ul > li.item_active__zQEsj > div > div.item_info_box__bi2tB > div.item_d_flex__T2jvP.item_name_box__jVarh > div'  # 이걸로 하면 에러 훨씬 덜 남.
                        # 예전꺼 : '#__next > div.layout_wrapper__Lo3KL.layout_search__K3p2f > div > div > div > div.search-result_inner__GdwKA.search-result_result_box__kcXDW > div.search-result_result_inner__qyG3b > div.search-result_result_wrap__1Ti_h > div > div > div > div > div > div > div > div > ul > li.item_active__zQEsj > div > div.item_info_box__bi2tB > div.item_d_flex__T2jvP.item_name_box__jVarh > div.item_name__Bp_mI'
                        last_name = driver.find_element(By.CSS_SELECTOR, last_name_css).text
                        last_name = last_name.replace('\n', ' ')  # 약 이름에 줄바꿈이 포함되어 있다면 제거
                        name = first_name + ' ' + last_name
                    except:
                        # print('last_name 없음')
                        name = first_name

                    # 앞에서 재고 발견했던 약품은 다음 검색에서 제외시키는 작업
                    # if name in overlab_test:
                    #     continue

                    placeholder_1.text('🤖 대웅TheSHOP 재고를 체크하는 중입니다... \n검색중 : %s'%name)

                    stock_css_list_DW = [  # 총 6가지 css_selecter 경우의 수가 있음...;
                        '#__next > div.layout_wrapper__Lo3KL.layout_search__K3p2f > div > div > div > div.search-result_inner__GdwKA.search-result_result_box__kcXDW > div.search-result_result_inner__qyG3b > div.search-result_result_wrap__1Ti_h > div > div > div > div > div > div > div > ul > li > div > div.item_price__3pavd > strong',
                        '#__next > div.layout_wrapper__Lo3KL.layout_search__K3p2f > div:nth-child(2) > div > div > div.search-result_inner__GdwKA.search-result_result_box__kcXDW > div > div.search-result_result_wrap__1Ti_h > div > div > div > div > div:nth-child(1) > div > div > div > div.item_d_flex__T2jvP.item_result_item__XdNLs > div.item_name_box__jVarh > div.item_d_flex__T2jvP.item_result_opt__RA1Vn > div.item_price__3pavd > strong',
                        '#__next > div.layout_wrapper__Lo3KL.layout_search__K3p2f > div > div > div > div.search-result_inner__GdwKA.search-result_result_box__kcXDW > div.search-result_result_inner__qyG3b > div.search-result_result_wrap__1Ti_h > div > div > div > div > div > div > div > ul > li.item_soldout__nJaFL.item_active__zQEsj > div > div.item_price__3pavd > strong',
                        '#__next > div.layout_wrapper__Lo3KL.layout_search__K3p2f > div > div > div > div.search-result_inner__GdwKA.search-result_result_box__kcXDW > div.search-result_result_inner__qyG3b > div.search-result_result_wrap__1Ti_h > div > div > div > div > div:nth-child(1) > div > div > ul > li > div > div.item_price__3pavd > strong',
                        '#__next > div.layout_wrapper__Lo3KL.layout_search__K3p2f > div > div > div > div.search-result_inner__GdwKA.search-result_result_box__kcXDW > div.search-result_result_inner__qyG3b > div.search-result_result_wrap__1Ti_h > div > div > div > div > div:nth-child(1) > div > div > ul > li.item_active__zQEsj > div > div.item_price__3pavd > strong',
                        '#__next > div.layout_wrapper__Lo3KL.layout_search__K3p2f > div:nth-child(2) > div > div > div.search-result_inner__GdwKA.search-result_result_box__kcXDW > div > div.search-result_result_wrap__1Ti_h > div > div > div > div > div > div > div > div > div.item_d_flex__T2jvP.item_result_item__XdNLs > div.item_name_box__jVarh > div.item_d_flex__T2jvP.item_result_opt__RA1Vn > div.item_price__3pavd > strong'
                    ] 
                    
                    for stock_css in stock_css_list_DW:
                        try:
                            stock = driver.find_element(By.CSS_SELECTOR, stock_css).text
                            if stock:
                                break  # find_element에서 에러 안나면 for문 종료됨.
                        except:
                            # print('css_selector 못찾음')
                            pass
                        
                    # [ 경우의수 처리 ]
                    if stock == '품절':
                        soldout_dict.setdefault(name, ["대웅TheSHOP", stock, "-", "-", code, name in overlab_test])
                        time_interval = TIME_INTERVAL
                    else:
                        # 대웅더샵에 재고 있음!
                        result_dict.setdefault(name, ["대웅TheSHOP", '확인 요망', "-", "-", code, name in overlab_test])
                        found_time = time.strftime('%Y년 %m월 %d일 %X', time.localtime(time.time()))
                        if name not in overlab_test:  # 알림을 받아야하고, 
                            done_log = found_time + ' 더샵 @ ' + name
                            done_list.append(done_log)
                            if not none_stop_mode:    # 즉시 종료 모드라면
                                break                 # 끝내기
                            else:                     # 즉시 종료 모드가 아니라면
                                pass                  # 넘어가기
                        else:                         # 알림을 안 받아도 되면
                            pass                      # 넘어가기
                        
                except Exception as e:
                    st.write(bohum_code_dict_G50[code], ' : 대웅TheSHOP 검색 실패')
                    

                # 두번째~세번째 child
                for n in range(2, 4):
                    # print(n, '번째 child')
                    last_name_css = '#__next > div.layout_wrapper__Lo3KL.layout_search__K3p2f > div > div > div > div.search-result_inner__GdwKA.search-result_result_box__kcXDW > div.search-result_result_inner__qyG3b > div.search-result_result_wrap__1Ti_h > div > div > div > div > div > div > div > ul > li:nth-child(%d) > div > div.item_info_box__bi2tB > div.item_d_flex__T2jvP.item_name_box__jVarh > div.item_name__Bp_mI'%n
                    try:
                        last_name = driver.find_element(By.CSS_SELECTOR, last_name_css).text
                        
                        name = first_name + ' ' + last_name

                        # 앞에서 재고 발견했던 약품은 다음 검색에서 제외시키는 작업
                        # if name in overlab_test:
                        #     continue

                        stock_css_list_DW = [  # 3가지 css_selecter 경우의 수가 있음
                            '#__next > div.layout_wrapper__Lo3KL.layout_search__K3p2f > div > div > div > div.search-result_inner__GdwKA.search-result_result_box__kcXDW > div.search-result_result_inner__qyG3b > div.search-result_result_wrap__1Ti_h > div > div > div > div > div > div > div > ul > li:nth-child(%d) > div > div.item_price__3pavd > strong'%n,
                            '#__next > div.layout_wrapper__Lo3KL.layout_search__K3p2f > div > div > div > div.search-result_inner__GdwKA.search-result_result_box__kcXDW > div.search-result_result_inner__qyG3b > div.search-result_result_wrap__1Ti_h > div > div > div > div > div > div > div > ul > li:nth-child(%d) > div > div.item_price__3pavd > strong'%n,
                            '#__next > div.layout_wrapper__Lo3KL.layout_search__K3p2f > div:nth-child(2) > div > div > div.search-result_inner__GdwKA.search-result_result_box__kcXDW > div > div.search-result_result_wrap__1Ti_h > div > div > div > div > div:nth-child(%d) > div > div > div > div.item_d_flex__T2jvP.item_result_item__XdNLs > div.item_name_box__jVarh > div.item_d_flex__T2jvP.item_result_opt__RA1Vn > div.item_price__3pavd > strong'%n
                        ] 
                        
                        for stock_css in stock_css_list_DW:
                            try:
                                stock = driver.find_element(By.CSS_SELECTOR, stock_css).text
                                if stock:
                                    break  # find_element에서 에러 안나면 for문 종료됨.
                            except:
                                # print('css_selector 못찾음')
                                pass
                        
                        # [ 경우의수 처리 ]
                        if stock == '품절':
                            soldout_dict.setdefault(name, ["대웅TheSHOP", stock, "-", "-", code, name in overlab_test])
                            time_interval = TIME_INTERVAL
                        else:
                            # 대웅더샵에 재고 있음!
                            result_dict.setdefault(name, ["대웅TheSHOP", '확인 요망', "-", "-", code, name in overlab_test])
                            found_time = time.strftime('%Y년 %m월 %d일 %X', time.localtime(time.time()))
                            if name not in overlab_test:  # 알림을 받아야하고, 
                                done_log = found_time + ' 더샵 @ ' + name
                                done_list.append(done_log)
                                if not none_stop_mode:    # 즉시 종료 모드라면
                                    break                 # 끝내기
                                else:                     # 즉시 종료 모드가 아니라면
                                    pass                  # 넘어가기
                            else:                         # 알림을 안 받아도 되면
                                pass                      # 넘어가기
                            
                    except:
                        # print(n, '번째 child 에러')
                        pass    
        ## =========================================================================================
             
        # 발견한 재고 표시
        check_time = time.strftime('%Y년 %m월 %d일 %X', time.localtime(time.time()))
        placeholder_1.text('🤖 약품 재고 검색 완료 (마지막 검색한 시간 : %s)'%check_time)
        print('재고 검색 완료 (시각 : %s)'%check_time)

        driver.close() # Firefox 드라이버 종료

        result_df = pd.DataFrame.from_dict(data=result_dict, orient='index', columns=['도매', '메인센터', '인천센터', '비고', '보험코드', '알림 제외 여부'])
        alarm_df = result_df[result_df['알림 제외 여부'] == False] # 알림을 받을 약들만 출력
        
        if not alarm_df.empty: # 재고를 발견했다면
            if none_stop_mode:
                print('알림 제외 목록.txt 재점검 작업 완료')
                placeholder_2.text('알림 제외 목록.txt 재점검 작업 완료')  
            else:
                print('재고 발견!!')
                placeholder_2.warning(' 재고 발견!!(발견 시각 : %s)'%found_time, icon="⚠️")

                # 윈도우 알림창 및 알림 소리 출력
                ctypes.windll.user32.MessageBoxW(0, "재고가 발견되었습니다!", "재고 발견!", 0x40|0x1)
                ctypes.windll.winmm.PlaySoundW("SystemAsterisk", 0x1)

            # 발견한 약품 출력
            placeholder_3.dataframe(alarm_df[['도매', '메인센터', '인천센터', '비고']])
            print(alarm_df[['도매', '메인센터', '인천센터', '비고']])

            # 발견한 약이 mothly_use_df에 있을 경우 검토제안 1개만 출력
            brief_alarm_df = merge_monthly(alarm_df, monthly_use_df, columns)
            brief_alarm_df['메인센터'] = brief_alarm_df['메인센터'].replace('품절', '0')
            brief_alarm_df['인천센터'] = brief_alarm_df['인천센터'].replace('품절', '0')
            st.dataframe(brief_alarm_df)
            if brief_alarm_df.empty:
                pass
            elif len(brief_alarm_df) == 1:
                brief_1 = briefing(brief_alarm_df.iloc[0], created_time)
                print(brief_1)
                placeholder_3_1.markdown(brief_1)
            else:
                # 최대 2개까지만 출력
                brief_1 = briefing(brief_alarm_df.iloc[0], created_time)
                print(brief_1)
                placeholder_3_1.markdown(brief_1)
                
                brief_2 = briefing(brief_alarm_df.iloc[1], created_time)
                print(brief_2)
                placeholder_3_2.markdown(brief_2)
        
            # 재고를 발견했다면, 다음 검색을 1분 후에 다시 돌리게끔 설정
            time_interval = 1

        else:
            placeholder_2.subheader('현재 모두 품절입니다ㅠ')
        ## ================================================================================================

        # 품절인 약 목록 출력
        soldout_df = pd.DataFrame.from_dict(data=soldout_dict, orient='index', columns=['도매','메인센터', '인천센터', '비고', '보험코드', '알림 제외 여부'])
        soldout_df = soldout_df.sort_values(by=['알림 제외 여부', '도매'], ascending=[False, True])
        placeholder_4.text('')
        placeholder_5.dataframe(soldout_df[['도매', '메인센터', '인천센터', '비고', '알림 제외 여부']])

        # 재고를 발견한 품목은 다음 알림에서 제외하기 위해 history와 합집합 하여 [알림제외.txt]에 덮어쓰기
        union = set(done_list).union(set(history))
        union_list = sorted(list(union))

        # history.txt 파일에 저장하는 작업
        with open(os.path.join(desktop_path, '알림 제외.txt'), 'w', encoding='utf-8') as file:
            for item in union_list:
                file.write('%s\n'%item)

        with open(os.path.join(desktop_path, '지오영 품절 목록.txt'), 'w', encoding='utf-8') as file:
            drug_list = list(set(drug_list)) # 중복 제거를 위함
            drug_list = sorted(drug_list)
            for item in drug_list:
                file.write('%s\n' %item.strip('\n'))
        
        proposal_df = merge_monthly(result_df, monthly_use_df, columns)
        proposal_df['메인센터'] = proposal_df['메인센터'].replace('품절', '0')
        proposal_df['인천센터'] = proposal_df['인천센터'].replace('품절', '0') 
        # placeholder_3_3.dataframe(proposal_df)
        
        # 검토제안 출력 (랜덤하게 3개만 출력)
        placeholder_3_3.text('')
        rand_nums = [random.randint(0, len(proposal_df)-1) for _ in range(3)]
        placeholder_3_4.markdown(briefing(proposal_df.iloc[rand_nums[0]], created_time))
        placeholder_3_5.markdown(briefing(proposal_df.iloc[rand_nums[1]], created_time))
        placeholder_3_6.markdown(briefing(proposal_df.iloc[rand_nums[2]], created_time))
        

        # 알림 제외 목록 출력
        placeholder_7.write(union_list)
        print('-----------------------------------------------------------------')

        ## ================================================================ 일정 시간마다 반복 실행=========
        # time_interval에서 설정한 분 마다 반복 실행되도록 하기
        for i in range(time_interval):
            placeholder_2_2.text('(재검색까지 남은 시간 : %d분)'%(time_interval - i))
            time.sleep(60) # 1분
        st.rerun()
        ## ===============================================================================================

done_list = []
print('...Web Application 실행중...')
main()
# =========================================================== #



