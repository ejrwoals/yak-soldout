# 🏥 약품 재고 자동 검색 시스템 (yak-soldout)

> 약국을 위한 도매상 품절 약품 자동 모니터링 시스템

주요 의약품 도매상(지오영, 백제약품, 인천약품, 지오팜, 복산)에서 품절된 약품의 재고 상황을 자동으로 모니터링하고 실시간으로 알림을 제공하는 시스템입니다.

FastAPI 기반의 웹 인터페이스와 Playwright를 활용한 안정적인 웹 자동화 기술을 사용하며, 레지스트리 패턴으로 도매상을 손쉽게 추가할 수 있는 확장형 아키텍처를 갖추고 있습니다.

## ✨ 주요 기능

- 🔍 **실시간 재고 검색**: 지오영, 백제약품 도매상 자동 로그인 및 재고 확인
- 📱 **웹 인터페이스**: 실시간 WebSocket 업데이트가 포함된 웹 대시보드
- 👁️ **결과 표시 제외 기능**: 도매상별로 독립적인 약품 결과 필터링 (검색은 계속 수행)
- 🔔 **스마트 알림**: 품절약 재고 발견시 알림 시스템 (날짜별 제외 관리)
- 📈 **진행 상황 추적**: 약품 검색 진행률 실시간 표시
- 🏗️ **모듈형 설계**: 확장 가능한 아키텍처와 포괄적인 테스트 커버리지
- ⚙️ **설정 관리**: 웹 UI를 통한 도매상 계정, 약품 목록, 결과 표시 제외 목록 관리
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

**⚠️ 주의사항**: 이 시스템은 교육 및 약국 업무 효율성 향상 목적으로 개발되었습니다. 도매상 이용 약관을 준수하여 사용하시기 바랍니다.

### 1. 환경 설정

```bash
# 저장소 클론
git clone https://github.com/your-username/yak-soldout.git
cd yak-soldout

# 가상환경 생성 (권장)
python -m venv venv
uv venv

# 가상환경 활성화
# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate

# 의존성 설치
pip install -r requirements.txt
uv pip install -r requirements.txt

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

# 결과 표시 제외 목록 (선택사항, JSON 형식으로 자동 생성됨)
# exclusion-list.json 파일이 웹 인터페이스를 통해 자동 관리됩니다

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
yak-soldout/
├── web_server.py              # FastAPI 웹 서버 (개발 실행: python web_server.py)
├── run_app.py                 # PyInstaller 배포 빌드용 진입점
├── info.txt                   # 도매상 로그인 정보 (직접 생성 필요)
├── geoweb-soldout-list.json   # 모니터링할 약품 목록
├── exclusion-list.json        # 결과 표시 제외 목록 (자동 생성)
│
├── scrapers/                  # Playwright 기반 도매상 스크래퍼
│   ├── registry.py            # 도매상 레지스트리 — Single Source of Truth
│   ├── base_scraper.py        # 기본 스크래퍼 공통 기능
│   ├── browser_manager.py     # 브라우저 인스턴스 중앙 관리
│   ├── geoweb_scraper.py      # 지오영 스크래퍼
│   ├── baekje_scraper.py      # 백제약품 스크래퍼
│   ├── incheon_scraper.py     # 인천약품 스크래퍼
│   ├── geopharm_scraper.py    # 지오팜 스크래퍼
│   └── boksan_scraper.py      # 복산 스크래퍼
│
├── models/                    # 데이터 구조 및 설정
│   ├── drug_data.py           # Drug, AppConfig, DistributorCredentials 데이터 클래스
│   └── config.py              # ConfigManager — registry 기반 동적 설정 파싱
│
├── utils/                     # 유틸리티
│   ├── search_engine.py       # 검색 실행 엔진 (registry 루프 기반)
│   ├── file_manager.py        # 약품 목록 / JSON 파일 I/O
│   ├── data_processor.py      # 데이터 처리 및 분류
│   └── notifications.py       # 크로스 플랫폼 알림
│
├── templates/
│   └── index.html             # 웹 프론트엔드 HTML 템플릿
│
├── static/
│   ├── css/                   # 기능별 CSS 파일
│   └── js/                    # 모듈별 JavaScript 파일
│
├── tests/                     # 테스트 (단위 + 통합)
│   ├── unit/
│   └── integration/
│
└── legacy_codes/              # 구 Selenium/Streamlit 구현 (참고용)
    └── g50.py
```

## 🏗️ 아키텍처: 도매상 레지스트리

`scrapers/registry.py`의 `DISTRIBUTOR_REGISTRY`가 모든 도매상 메타데이터의 **Single Source of Truth**입니다. 이 딕셔너리 하나에 도매상 ID, 이름, 한국어 키, 스크래퍼 클래스, 뱃지 심볼 등이 정의되어 있으며, 나머지 시스템(설정 파싱, 검색 엔진, API, 프론트엔드)은 모두 이 레지스트리를 참조해 동적으로 동작합니다.

```python
# scrapers/registry.py
DISTRIBUTOR_REGISTRY = {
    "geoweb": {
        "id": "geoweb",
        "name": "지오영",
        "korean_key": "지오영",       # info.txt 키 prefix
        "scraper_class": GeowebScraper,
        "default_enabled": True,
        "badge_symbol": "●",
        "extra_params": {},
    },
    # ... 나머지 도매상
}
```

## 🔧 고급 설정

### 검색 간격 및 결과 표시 제외 설정

설정은 `models/config.py`에서 수정할 수 있습니다:

- `repeat_interval_minutes`: 검색 반복 간격 (분)
- `alert_exclusion_days`: 결과 표시 제외 기간 (일) - 고정하지 않은 항목이 자동 삭제되는 기간

## 📊 데이터 파일

### 필수 파일

1. **info.txt**: 도매상 로그인 정보
2. **geoweb-soldout-list.json**: 모니터링할 약품 목록 (JSON 형식, 긴급 알림 설정 포함)

### 자동 생성 파일

1. **exclusion-list.json**: 결과 표시에서 제외할 약품 목록 (도매상별 독립 관리)
   - 웹 인터페이스에서 약품 카드의 눈 모양 아이콘(👁️‍🗨️)을 클릭하여 추가
   - 도매상별로 독립적으로 작동 (지오영/백제약품 별도 관리)
   - 백제약품의 경우 규격 정보까지 포함하여 정확한 매칭

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
- `GET /api/exclusion-list` - 결과 표시 제외 목록 조회
- `PUT /api/exclusion-list` - 결과 표시 제외 목록 업데이트
- `POST /api/exclusion-add` - 개별 약품을 결과 표시 제외 목록에 추가

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

레지스트리 패턴 덕분에 새 도매상 추가 시 수정해야 할 파일이 최소화되어 있습니다.

**1단계**: `DistributorType` enum에 추가 (`models/drug_data.py`)

```python
class DistributorType(Enum):
    # ... 기존 항목 ...
    NEWDIST = "신규도매상명"  # 추가
```

**2단계**: 레지스트리에 항목 추가 (`scrapers/registry.py`)

```python
"newdist": {
    "id": "newdist",
    "name": "신규도매상명",
    "korean_key": "신규도매상",    # info.txt 키 prefix
    "scraper_class": NewDistScraper,
    "default_enabled": False,
    "badge_symbol": "※",
    "extra_params": {},
},
```

**3단계**: 스크래퍼 파일 생성 (`scrapers/newdist_scraper.py`) — `BaseScraper` 상속 후 `login()`, `search_by_insurance_codes()` 등 구현

**4단계**: `info.txt`에 설정 키 추가

```
신규도매상아이디=
신규도매상비밀번호=
신규도매상활성화=false
```

이 4단계만으로 웹 UI, 검색 엔진, 설정 파싱, API 응답이 모두 자동으로 신규 도매상을 지원합니다.

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
