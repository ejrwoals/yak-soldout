# 🏥 약품 재고 자동 검색 시스템 (yak-soldout)

> 약국을 위한 도매상 품절 약품 자동 모니터링 시스템

주요 의약품 도매상(지오영, 백제약품, 인천약품, 지오팜, 복산, 유팜몰, HMP몰, 티제이팜)에서 품절된 약품의 재고 상황을 자동으로 모니터링하고 실시간으로 알림을 제공하는 시스템입니다.

FastAPI 기반의 웹 인터페이스와 Playwright를 활용한 안정적인 웹 자동화 기술을 사용하며, 레지스트리 패턴으로 도매상을 손쉽게 추가할 수 있는 확장형 아키텍처를 갖추고 있습니다.

## ✨ 주요 기능

- 🔍 **실시간 재고 검색**: 지오영, 백제약품, 인천약품, 지오팜, 복산, 유팜몰, HMP몰, 티제이팜 도매상 자동 로그인 및 재고 확인
- 🔎 **약품 미리보기 검색**: 약품 목록에 약품을 추가할 때 기준 도매상에 실시간으로 질의하여 약품명, 보험코드, 제약사, 규격, 재고를 즉시 조회 (세션 기반 브라우저 재사용으로 로그인 비용 절감)
- 🪟 **도매상 사이트 바로가기**: 재고 카드의 바로가기 아이콘을 클릭하면 headed 브라우저가 해당 도매상을 자동 로그인하고 약품 검색까지 마친 상태로 사용자에게 노출 (지원 도매상 전체)
- 📱 **웹 인터페이스**: 실시간 WebSocket 업데이트가 포함된 웹 대시보드
- 👁️ **결과 표시 제외 기능**: 도매상별로 독립적인 약품 결과 필터링 (검색은 계속 수행)
- 🔔 **스마트 알림**: 품절약 재고 발견시 알림 시스템 (날짜별 제외 관리)
- 📈 **진행 상황 추적**: 약품 검색 진행률 실시간 표시
- 🏗️ **모듈형 설계**: 확장 가능한 아키텍처와 포괄적인 테스트 커버리지
- 🎨 **도매상별 색상 구분**: 검색 결과 카드를 도매상별 색상으로 시각 구분, 색상 커스터마이징 지원
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
# 로그인 정보 설정 (config.example.json을 참고하여 생성)
cp config.example.json config.json
# config.json 파일을 열어 실제 도매상 계정 정보 입력
```

> **기존 info.txt 사용자**: 기존 `info.txt` 파일이 있으면 첫 실행 시 `config.json`으로 자동 마이그레이션됩니다. 원본은 `info.txt.bak`으로 백업됩니다.

`config.json` 파일 형식:
```json
{
  "distributors": {
    "geoweb": {
      "enabled": true,
      "username": "your_geoweb_username",
      "password": "your_geoweb_password",
      "color": "#0d9488",
      "region": "seoul"
    },
    "baekje": {
      "enabled": false,
      "username": "",
      "password": "",
      "color": "#3b82f6"
    },
    "upharmmall": {
      "enabled": false,
      "username": "",
      "password": "",
      "color": "#059669"
    },
    "hmpmall": {
      "enabled": false,
      "username": "",
      "password": "",
      "color": "#ea580c",
      "region": "41"
    },
    "tjpharm": {
      "enabled": false,
      "username": "",
      "password": "",
      "color": "#0891b2"
    }
  },
  "monitoring": {
    "repeat_interval_minutes": 30,
    "alert_exclusion_days": 7
  }
}
```

> **color 필드**: 도매상 구분 색상입니다. 웹 UI의 도매상 설정 모달에서 변경할 수 있으며, 생략 시 레지스트리의 `default_color` 값이 사용됩니다.

> **region 필드**: 일부 도매상(지오영, 지오팜, HMP몰)은 지역별로 다른 서버를 사용합니다. 웹 UI의 도매상 설정 모달에서 드롭다운으로 선택할 수 있으며, 생략 시 레지스트리의 `extra_params` 기본값이 사용됩니다. 지오영은 `"seoul"` (서울/경기/인천), `"yeongnam"` (영남), `"daejeon"` (대전) 중 선택하며, 영남/대전 지역은 타센터 재고가 표시되지 않습니다. 지오팜은 `"daegu"`, `"daejeon"`, `"gwangju"`, `"seoul"` 중 선택, HMP몰은 `"41"` (경기) 또는 `"47"` (경북)을 선택합니다.

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
# 웹 서버 시작 (기본 포트: 8000)
python web_server.py

# 브라우저에서 접속
# http://localhost:8000

# 포트 변경이 필요한 경우 PORT 환경변수 사용
PORT=3000 python web_server.py
```

#### 🔍 디버그 모드 (브라우저 화면 보기)

브라우저 창을 보면서 실행하고 싶다면:

```bash
# 웹 인터페이스 디버그 모드
HEADLESS=false python web_server.py

# Windows에서는
set HEADLESS=false && python web_server.py

# 환경변수 조합 사용 가능
PORT=3000 HEADLESS=false python web_server.py
```

## 📁 프로젝트 구조

```
yak-soldout/
├── web_server.py              # FastAPI 웹 서버 (개발 실행: python web_server.py)
├── run_app.py                 # PyInstaller 배포 빌드용 진입점
├── config.json                # 도매상 로그인 정보 (직접 생성 필요, JSON 형식)
├── build_config.json          # 약국별 빌드 설정 (선택사항, PyInstaller 배포 시 사용)
├── geoweb-soldout-list.json   # 모니터링할 약품 목록
├── exclusion-list.json        # 결과 표시 제외 목록 (자동 생성)
│
├── scrapers/                  # Playwright 기반 도매상 스크래퍼
│   ├── registry.py            # 도매상 레지스트리 — Single Source of Truth
│   ├── base_scraper.py        # 기본 스크래퍼 공통 기능
│   ├── browser_manager.py     # 브라우저 인스턴스 중앙 관리
│   ├── geoweb_scraper.py      # 지오영 스크래퍼
│   ├── baekje_scraper.py      # 백제약품 스크래퍼 (JWT 인증 + REST API 기반)
│   ├── incheon_scraper.py     # 인천약품 스크래퍼
│   ├── geopharm_scraper.py    # 지오팜 스크래퍼
│   ├── boksan_scraper.py      # 복산 스크래퍼
│   ├── upharmmall_scraper.py  # 유팜몰 스크래퍼
│   ├── hmpmall_scraper.py     # HMP몰 스크래퍼 (JSON API 기반 통합 플랫폼)
│   └── tjpharm_scraper.py    # 티제이팜 스크래퍼 (HTTP API 기반)
│
├── models/                    # 데이터 구조 및 설정
│   ├── drug_data.py           # Drug, AppConfig, DistributorCredentials 데이터 클래스
│   ├── config.py              # ConfigManager — config.json 기반 설정 관리 (자동 마이그레이션 포함)
│   └── build_config.py        # 빌드 설정 관리 — build_config.json 기반 약국별 커스터마이징 및 기준 도매상 설정
│
├── utils/                     # 유틸리티
│   ├── search_engine.py       # 검색 실행 엔진 (registry 루프 기반) + PreviewSearchSession
│   ├── open_site_session.py   # 바로가기 headed 브라우저 세션 관리 (OpenSiteSession)
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

`scrapers/registry.py`의 `DISTRIBUTOR_REGISTRY`가 모든 도매상 메타데이터의 **Single Source of Truth**입니다. 이 딕셔너리 하나에 도매상 ID, 이름, 한국어 키, 스크래퍼 클래스, 기본 색상, 사이트 URL, 지역 옵션 등이 정의되어 있으며, 나머지 시스템(설정 파싱, 검색 엔진, API, 프론트엔드)은 모두 이 레지스트리를 참조해 동적으로 동작합니다. `build_config.json`이 존재하면 `get_visible_registry()` 함수가 빌드 설정에 따라 필터링된 레지스트리를 반환하여, 특정 약국에 불필요한 도매상을 숨길 수 있습니다. 단, 기준 도매상은 `build_config.json`에서 `0`으로 설정해도 항상 표시됩니다.

검색 결과 카드는 도매상별 색상으로 시각적으로 구분됩니다. 각 도매상에 `default_color`가 지정되어 있으며, 사용자가 웹 UI의 도매상 설정 모달에서 색상을 변경하면 `config.json`에 저장되어 기본 색상을 덮어씁니다.

일부 도매상은 지역별로 다른 서버를 사용합니다. `region_options`가 정의된 도매상(지오영, 지오팜, HMP몰)은 설정 모달에 지역 선택 드롭다운이 표시되며, 선택한 지역에 따라 스크래퍼가 해당 지역의 서버에 접속합니다. 기본 지역은 `extra_params`의 `region` 값으로 설정됩니다.

### 기준 도매상 (Primary Distributor)

검색 엔진은 **기준 도매상**을 항상 먼저 검색하여 약품명 텍스트 검색을 수행하고, 그 결과에서 보험코드를 수집합니다. 나머지 도매상은 이 보험코드를 이용해 검색합니다. 기본적으로 지오영이 기준 도매상이며, `build_config.json`의 `primary_distributor` 설정으로 변경할 수 있습니다. 현재 텍스트 검색을 지원하는 도매상은 `geoweb`(지오영)과 `upharmmall`(유팜몰)이며, 이 외의 값이 설정되면 기본값인 `geoweb`으로 동작합니다.

개별 도매상 검색 중 오류가 발생하면 해당 도매상만 건너뛰고 나머지 도매상 검색을 계속 진행합니다.

### 약품 미리보기 검색 (Preview Search)

약품 목록 모달에서 약품을 추가할 때, 사용자가 입력한 키워드를 **기준 도매상**에 실시간으로 질의하여 후보 약품들의 약품명·보험코드·제약사·규격·현재 재고를 제공하는 기능입니다. 정확한 약품명으로 목록에 등록하도록 돕고, 실수로 잘못된 이름을 추가하는 것을 방지합니다.

`utils/search_engine.py`의 `PreviewSearchSession` 클래스가 이 기능을 담당하며, 브라우저/로그인 세션을 프로세스 수명 동안 유지하여 연속 질의에서 로그인 비용을 발생시키지 않습니다. 메인 검색, 미리보기, 바로가기는 각기 독립된 브라우저 세션을 사용하므로 서로 차단하지 않고 동시에 실행할 수 있습니다.

### 도매상 사이트 바로가기 (Open Site)

재고 카드 우측의 바로가기 아이콘을 누르면, 해당 도매상 사이트를 자동 로그인하고 약품 검색까지 마친 상태의 브라우저 창이 사용자에게 노출됩니다. 사용자는 그 창에서 실제 주문/상세 조회 등을 이어서 수행할 수 있습니다.

`utils/open_site_session.py`의 `OpenSiteSession` 클래스가 동시 1개의 headed 브라우저 세션을 관리합니다. 로그인·검색이 끝나기 전에는 창을 작은 크기(또는 Windows의 경우 minimized)로 띄워 사용자의 작업을 방해하지 않고, 준비가 끝나면 CDP `Browser.setWindowBounds`로 1280×800 중앙 위치로 창을 드러냅니다. 사용자가 창을 닫거나 `IDLE_TIMEOUT`(기본 10분)이 경과하면 워치독이 세션을 자동 정리합니다.

바로가기 지원 여부는 `scrapers/registry.py`의 각 도매상 항목의 `supports_open_site` 플래그로 결정됩니다. `True`면 카드에 바로가기 버튼이 표시됩니다. 현재 등록된 8개 도매상(지오영·백제약품·인천약품·지오팜·복산·유팜몰·HMP몰·티제이팜)은 모두 `True`입니다.

각 스크래퍼는 `BaseScraper.open_for_user_interaction(query, original_drug_name)`를 override하여 "검색 실행까지만" 수행하고 결과 파싱은 하지 않습니다. 공통 후처리 `_wait_search_settled(<결과 셀렉터>)`로 DOM 렌더링과 networkidle까지 대기해 UX 일관성을 확보합니다. 도매상별 검색창·결과 셀렉터는 스크래퍼 내부에 정의되어 있으며(예: 지오팜 `#item_name` + iframe 응답, 인천약품 `#tx_insucd`, 복산 `#tx_physic`, 백제 Quasar SPA 검색창 + Enter, 티제이팜 `#search_name_2` + `#table_id_1`), 플랫폼 구조에 맞게 각자 구현됩니다.

프론트엔드는 WebSocket으로 스트리밍되는 재고 카드의 `insurance_code`를 바로가기 쿼리로 사용합니다. 보험코드가 비어 있으면 약품명을 대신 사용합니다.

### HMP몰: 통합 플랫폼 스크래퍼

HMP몰(hmpmall.co.kr)은 ~20개 입점 도매상의 재고를 통합 검색하는 플랫폼으로, 기존 도매상 스크래퍼와는 동작 방식이 다릅니다.

- **JSON API 기반**: DOM 파싱 대신 `SearchProductSellerListJson.do` API를 호출하여 안정적으로 데이터를 조회합니다.
- **검색 흐름**: 보험코드 검색 -> HTML에서 `productMasterId` 추출 -> JSON API로 도매상별 재고 조회
- **재고 합산 로직**: 모든 입점 도매상의 `stockQuantity`를 합산하며, 전부 0일 때만 품절로 처리합니다. 검색 결과 카드에 "N/M 업체 재고 합산" 형태로 몇 개 도매상에 재고가 있는지 표시됩니다.
- **지역 필터링**: `businessSidoCode` 파라미터로 지역별 도매상을 필터링합니다 (`41`=경기, `47`=경북).

```python
# scrapers/registry.py
DISTRIBUTOR_REGISTRY = {
    "geoweb": {
        "id": "geoweb",
        "name": "지오영",
        "korean_key": "지오영",       # 한국어 표시명 prefix
        "scraper_class": GeowebScraper,
        "default_enabled": True,
        "default_color": "#0d9488",   # 도매상 구분 색상 (카드 보더, 배경 틴트, 배지에 적용)
        "site_url": "https://order.geoweb.kr",  # 도매상 사이트 URL (설정/약품목록 모달에서 링크로 표시)
        "extra_params": {"region": "seoul"},   # 기본 지역 설정
        "region_options": {                    # 도매상 설정 모달에 드롭다운으로 표시
            "seoul": "서울, 경기, 인천",
            "yeongnam": "영남",
            "daejeon": "대전",
        },
        "supports_open_site": True,            # 재고 카드 바로가기 지원 여부
    },
    # ... 나머지 도매상
}
```

## 🔧 고급 설정

### 검색 간격 및 결과 표시 제외 설정

설정은 `config.json`의 `monitoring` 섹션에서 수정할 수 있습니다:

- `repeat_interval_minutes`: 검색 반복 간격 (분)
- `alert_exclusion_days`: 결과 표시 제외 기간 (일) - 고정하지 않은 항목이 자동 삭제되는 기간

### 약국별 빌드 설정 (build_config.json)

특정 약국에 배포할 때 표시할 도매상을 제한하고 약국 이름을 설정할 수 있습니다. 이 파일은 **선택사항**이며, 파일이 없으면 전체 도매상이 표시됩니다 (개발 환경 호환).

```bash
# 예시 파일을 복사하여 생성
cp build_config.example.json build_config.json
```

```json
{
  "pharmacy_name": "가나안약국",
  "primary_distributor": "geoweb",
  "distributors": {
    "geoweb": 1,
    "baekje": 0,
    "incheon": 0,
    "boksan": 0,
    "geopharm": 1,
    "upharmmall": 1,
    "hmpmall": 1,
    "tjpharm": 1
  }
}
```

- **pharmacy_name**: 웹 인터페이스 헤더에 "for XXX약국" 형태로 표시됩니다. 생략하면 표시되지 않습니다.
- **primary_distributor**: 기준 도매상 ID (`"geoweb"` 또는 `"upharmmall"`). 생략하면 기본값 `"geoweb"`이 사용됩니다. 기준 도매상은 `distributors`에서 `0`으로 설정해도 항상 표시됩니다.
- **distributors**: 각 도매상의 표시 여부를 `1`(표시) 또는 `0`(숨김)으로 설정합니다. 누락된 도매상은 기본 표시(1)로 처리됩니다. `0`으로 설정된 도매상은 UI, 설정, 검색에서 완전히 제외됩니다.

PyInstaller로 빌드할 때 `build_config.json`이 번들에 포함되어, 약국별로 맞춤 배포가 가능합니다.

## 📊 데이터 파일

### 필수 파일

1. **config.json**: 도매상 로그인 정보 및 모니터링 설정 (JSON 형식)
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
- `GET /api/build-info` - 빌드 정보 조회 (약국명, 기준 도매상명 등)
- `POST /api/preview-search` - 약품 미리보기 검색 (기준 도매상에 실시간 질의)
- `POST /api/preview-search/close` - 미리보기 검색 세션 브라우저 종료
- `POST /api/open-distributor-site` - 도매상 사이트 바로가기 (headed 브라우저 자동 로그인+검색)
- `POST /api/open-distributor-site/close` - 바로가기 세션 수동 종료

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
    "korean_key": "신규도매상",    # 한국어 표시명 prefix
    "scraper_class": NewDistScraper,
    "default_enabled": False,
    "default_color": "#059669",    # 도매상 구분 색상
    "site_url": "https://example.com",  # 도매상 사이트 URL
    "extra_params": {},
    "supports_open_site": False,   # 바로가기 지원 시 True + scraper에 open_for_user_interaction 구현
},
```

**3단계**: 스크래퍼 파일 생성 (`scrapers/newdist_scraper.py`) — `BaseScraper` 상속 후 `login()`, `search_by_insurance_codes()` 등 구현

**4단계**: `config.json`에 도매상 설정 추가

```json
{
  "distributors": {
    "newdist": {
      "enabled": false,
      "username": "",
      "password": ""
    }
  }
}
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
