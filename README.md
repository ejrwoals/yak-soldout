# 🏥 약품 재고 자동 검색 시스템 (yak-soldout)

> 약국을 위한 도매상 품절 약품 자동 모니터링 시스템

주요 의약품 도매상(지오영, 백제약품)에서 품절된 약품의 재고 상황을 자동으로 모니터링하고 실시간으로 알림을 제공하는 시스템입니다. 

FastAPI 기반의 웹 인터페이스와 Playwright를 활용한 안정적인 웹 자동화 기술을 사용하여 효율성을 높입니다.

## ✨ 주요 기능

- 🔍 **실시간 재고 검색**: 지오영, 백제약품 도매상 자동 로그인 및 재고 확인
- 📱 **웹 인터페이스**: 실시간 WebSocket 업데이트가 포함된 웹 대시보드
- 🔔 **스마트 알림**: 품절약 재고 발견시 알림 시스템 (날짜별 제외 관리)
- 📈 **진행 상황 추적**: 약품 검색 진행률 실시간 표시
- 🏗️ **모듈형 설계**: 확장 가능한 아키텍처와 포괄적인 테스트 커버리지
- ⚙️ **설정 관리**: 웹 UI를 통한 도매상 계정, 약품 목록, 알림 제외 목록 관리
- 🔒 **안전한 스크래핑**: 팝업 자동 처리 및 안전한 요소 클릭 보장

## 🛠️ 기술 스택

- **Backend**: FastAPI, Python 3.8+
- **Web Scraping**: Playwright (Chromium)
- **Frontend**: HTML5, CSS3, Vanilla JavaScript
- **Real-time Communication**: WebSocket
- **Data Processing**: pandas, numpy
- **Testing**: pytest (단위 테스트 & 통합 테스트)
- **File Handling**: chardet (인코딩 자동 감지)

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
geoweb-soldout-list.json 파일 안에 JSON 형태로 약품명과 긴급 알림 설정 입력
```json
[
  {
    "drugName": "디카맥스1000정(PTP) 90T 다림바이오텍",
    "isUrgent": false,
    "dateAdded": "2025-08-17T10:00:00"
  },
  {
    "drugName": "디카맥스디정(PTP) 90T 다림바이오텍", 
    "isUrgent": true,
    "dateAdded": "2025-08-17T10:00:00"
  }
]
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
2. **geoweb-soldout-list.json**: 모니터링할 약품 목록 (JSON 형식, 긴급 알림 설정 포함)

### 선택사항 파일

1. **알림 제외.json**: 알림에서 제외할 약품 목록

## 🔌 API 엔드포인트

### REST API
- `GET /` - 메인 웹 인터페이스
- `GET /api/status` - 현재 상태 조회
- `POST /api/search/start` - 검색 시작
- `POST /api/search/stop` - 검색 중단
- `GET /api/distributor-settings` - 도매상 설정 조회
- `PUT /api/distributor-settings` - 도매상 설정 업데이트
- `GET /api/drug-list` - 약품 목록 조회
- `PUT /api/drug-list` - 약품 목록 업데이트
- `GET /api/exclusion-list` - 알림 제외 목록 조회
- `PUT /api/exclusion-list` - 알림 제외 목록 업데이트

### WebSocket
- `WS /ws` - 실시간 로그 스트리밍 및 검색 진행 상황 업데이트

## 🧪 테스트

```bash
# 전체 테스트 실행
python -m pytest

# 특정 모듈 테스트
python -m pytest tests/unit/
python -m pytest tests/integration/

# 커버리지 포함 테스트
python -m pytest --cov=.
```

## 🔄 개발 가이드

### 새로운 도매상 추가하기
1. `scrapers/` 디렉터리에 새 스크래퍼 클래스 생성
2. `BaseScraper`를 상속하고 `login()`, `search_drug()` 메서드 구현
3. `models/drug_data.py`의 `DistributorType` enum에 새 도매상 추가
4. `web_server.py`에서 새 스크래퍼 통합

### 프론트엔드 수정하기
- CSS: `static/css/` 디렉터리의 기능별 파일 수정
- JavaScript: `static/js/` 디렉터리의 모듈별 파일 수정
- HTML: `templates/index.html` 수정

## 🐛 문제 해결

### 브라우저 설치 문제

```bash
# Playwright 브라우저 재설치
python -m playwright install chromium --force

# 시스템 의존성 설치 (Ubuntu/Debian)
sudo python -m playwright install-deps chromium
```

**⚠️ 주의사항**: 이 시스템은 교육 및 약국 업무 효율성 향상 목적으로 개발되었습니다. 도매상 이용 약관을 준수하여 사용하시기 바랍니다.
