# 🏥 약품 재고 자동 검색 시스템 (yak-soldout)

> 약국을 위한 도매상 품절 약품 자동 모니터링 시스템

주요 의약품 도매상(지오영, 백제약품)에서 품절된 약품의 재고 상황을 자동으로 모니터링하고 실시간으로 알림을 제공하는 시스템입니다. 

FastAPI 기반의 웹 인터페이스와 Playwright를 활용한 안정적인 웹 자동화 기술을 사용하여 효율성을 높입니다.

## ✨ 주요 기능

- 🔍 **실시간 재고 검색**: 지오영, 백제약품 도매상 자동 로그인 및 재고 확인
- 📱 **웹 인터페이스**: 실시간 WebSocket 업데이트가 포함된 웹 대시보드
- 📊 **Excel 연동**: 약국 관리 시스템의 월별 사용량 통계와 연동
- 🔔 **스마트 알림**: 품절약 재고 발견시 알림 시스템
- 📈 **진행 상황 추적**: 약품 검색 진행률 실시간 표시
- 🏗️ **모듈형 설계**: 확장 가능한 아키텍처와 포괄적인 테스트 커버리지

## 🚀 빠른 시작

### 1. 환경 설정

```bash
# 저장소 클론
git clone https://github.com/your-username/yak-soldout.git
cd yak-soldout

# 가상환경 생성 (권장)
python -m venv venv

# 가상환경 활성화
# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate

# 의존성 설치
pip install -r requirements.txt

# Playwright 브라우저 설치 (처음 실행 시 필수)
python -m playwright install chromium
```

### 2. 설정 파일 준비

프로젝트 루트 디렉터리에 다음 파일들을 생성하세요:

```bash
# 로그인 정보 설정 (info.example.txt를 참고하여 생성)
cp info.example.txt info.txt
# info.txt 파일을 열어 실제 도매상 계정 정보 입력
```

# 품절 약품 목록 
지오영 품절 목록.txt 파일 안에 줄바꿈으로 구분하여 약품명 적기 (지오영에 써 있는 것 복붙)
```
디카맥스1000정(PTP) 90T 다림바이오텍
디카맥스디정(PTP) 90T 다림바이오텍
딜테란서방캅셀90mg 30C 근화
```

# 알림 제외 목록 (선택사항)
```
touch 알림\ 제외.txt
```

### 3. 실행 방법

#### 🌐 웹 인터페이스 실행 (권장)

```bash
# 웹 서버 시작
python web_server.py

# 브라우저에서 접속
# http://localhost:8000
```

#### 🔍 디버그 모드 (브라우저 화면 보기)

브라우저 창을 보면서 실행하고 싶다면:

```bash
# 웹 인터페이스 디버그 모드
HEADLESS=false python web_server.py

# Windows에서는
set HEADLESS=false && python web_server.py
```

## 📁 프로젝트 구조

```
( 추후 프로젝트 완료시에 채워 넣을 예정 )
```

## 🔧 고급 설정

### 검색 간격 및 알림 설정

설정은 `models/config.py`에서 수정할 수 있습니다:

- `repeat_interval_minutes`: 검색 반복 간격 (분)
- `alert_exclusion_days`: 알림 제외 기간 (일)

## 📊 데이터 파일

### 필수 파일

1. **info.txt**: 도매상 로그인 정보
2. **지오영 품절 목록.txt**: 모니터링할 약품 목록 (한 줄에 하나씩)

### 선택사항 파일

1. **알림 제외.txt**: 알림에서 제외할 약품 목록
2. **data/월별 약품사용량_*.xls**: 유팜 시스템에서 내보낸 사용량 통계

### Excel 파일 연동

약국 관리 시스템에서 다음과 같이 Excel 파일을 내보내세요:
1. **[컨설팅 통계] → [약품 통계] → [월별 약품사용량]**
2. 내보낸 파일을 `data/` 폴더에 저장

## 🧪 테스트

```bash
# 전체 테스트 실행
python -m pytest

# 특정 모듈 테스트
python -m pytest tests/unit/
python -m pytest tests/integration/
```

## 🐛 문제 해결

### 브라우저 설치 문제

```bash
# Playwright 브라우저 재설치
python -m playwright install chromium --force

# 시스템 의존성 설치 (Ubuntu/Debian)
sudo python -m playwright install-deps chromium
```

**⚠️ 주의사항**: 이 시스템은 교육 및 약국 업무 효율성 향상 목적으로 개발되었습니다. 도매상 이용 약관을 준수하여 사용하시기 바랍니다.
