# 🏥 약품 재고 자동 검색 시스템 (yak-soldout)

> 약국을 위한 도매상 품절 약품 자동 모니터링 시스템

주요 의약품 도매상(지오영, 백제약품, 인천약품, 지오팜, 복산, 유팜몰, HMP몰, 티제이팜)에서 품절된 약품의 재고 상황을 자동으로 모니터링하고 실시간으로 알림을 제공하는 시스템입니다.

FastAPI 기반의 웹 인터페이스와 Playwright를 활용한 안정적인 웹 자동화 기술을 사용하며, 레지스트리 패턴으로 도매상을 손쉽게 추가할 수 있는 확장형 아키텍처를 갖추고 있습니다.

## ✨ 주요 기능

- 🔍 **실시간 재고 검색**: 지오영, 백제약품, 인천약품, 지오팜, 복산, 유팜몰, HMP몰, 티제이팜 도매상 자동 로그인 및 재고 확인
- 🔎 **약품 미리보기 검색**: 약품 목록에 약품을 추가할 때 기준 도매상에 실시간으로 질의하여 약품명, 보험코드, 제약사, 규격, 재고를 즉시 조회 (세션 기반 브라우저 재사용으로 로그인 비용 절감)
- 🪟 **도매상 사이트 바로가기**: 재고 카드의 바로가기 아이콘을 클릭하면 headed 브라우저가 해당 도매상을 자동 로그인하고 약품 검색까지 마친 상태로 사용자에게 노출 (지원 도매상 전체)
- 🏠 **홈 화면 (앱 런처)**: 루트(`/`)에 여러 약국 업무 자동화 기능의 진입점을 모은 런처 화면. 현재 "품절 약 서치앱"과 "주문지 OCR"이 활성화되어 있고 나머지는 "준비 중" 카드로 표시됩니다. 자동 검색이 진행 중이면 카드에 "검색 중" 배지가 실시간 표시됩니다.
- ✍️ **손글씨 주문지 OCR**: 손으로 작성한 약국 주문지를 사진으로 올리면 멀티모달 LLM(Google Gemini)이 약품명·포장단위·수량을 구조화 추출(`/order-ocr`). `AxB` 표기를 포장단위×주문수량으로, 함량/규격은 약품명에 포함하는 약국 도메인 프롬프트를 사용합니다. 한 줄도 빠뜨리지 않도록 흐린 글씨·취소선 줄까지 모두 추출하되 취소선 항목은 빼지 않고 "취소선" 배지로만 표시하며, 결과는 사용자가 직접 확인·수정하는 검수 테이블(Human-in-the-loop)로 제공됩니다. (1단계 로컬 검증 — 아직 저장은 하지 않음)
- 🔤 **OCR 약품명 오타 보정**: 약품 마스터가 등록돼 있으면, OCR로 읽은 약품명을 한글 자모(초/중/종성) 기반 fuzzy 매칭으로 마스터와 대조해 검수 테이블 각 행에 결과 배지를 표시합니다 — "약품명 일치"(공식 전체명 자동 적용, 원본으로 되돌리기 가능), "확인 필요"(후보 드롭다운에서 선택), "미등록". 용량(600mg≠300mg)·접두(짧은 손글씨명↔긴 공식명) 인식, 제형 접미·제약사 접두 제거를 반영하며, 후보에 없으면 행별 "직접 검색" 박스로 마스터 DB를 직접 조회할 수 있습니다.
- 💊 **약품 마스터 관리**: 약국이 취급하는 전체 약품 목록을 엑셀로 업로드해 로컬에 등록(`/drug-master`). 머리글 행 자동 추정 + 컬럼 매핑(약품명 필수, 보험코드·제약사 선택)을 거쳐 `data/drug_master.json`에 저장하며, 위의 OCR 약품명 오타 보정의 기준 데이터로 사용됩니다.
- 📱 **웹 인터페이스**: 실시간 WebSocket 업데이트가 포함된 웹 대시보드(`/checker`)
- 👁️ **결과 표시 제외 기능**: 도매상별로 독립적인 약품 결과 필터링 (검색은 계속 수행)
- 🔔 **스마트 알림**: 품절약 재고 발견시 알림 시스템 (날짜별 제외 관리)
- 📈 **진행 상황 추적**: 약품 검색 진행률 실시간 표시
- 🏗️ **모듈형 설계**: 확장 가능한 아키텍처와 포괄적인 테스트 커버리지
- 🎨 **도매상별 색상 구분**: 검색 결과 카드를 도매상별 색상으로 시각 구분, 색상 커스터마이징 지원
- ⚙️ **설정 관리**: 웹 UI를 통한 도매상 계정, 약품 목록, 결과 표시 제외 목록 관리
- 🔒 **안전한 스크래핑**: 팝업 자동 처리 및 안전한 요소 클릭 보장

## 🔗 지원 도매상 URL

각 도매상의 사이트 URL은 `scrapers/registry.py`의 `DISTRIBUTOR_REGISTRY`(`site_url` 필드)에서 관리됩니다.

| 도매상 | ID | URL |
|--------|----|-----|
| 지오영 | `geoweb` | https://order.geoweb.kr (지역별 상이, 아래 참고) |
| 백제약품 | `baekje` | https://www.ibjp.co.kr |
| 인천약품 | `incheon` | https://inchunpharm.com |
| 지오팜 | `geopharm` | https://orderpharm.geo-pharm.com |
| 복산 | `boksan` | https://wos.nicepharm.com |
| 유팜몰 | `upharmmall` | https://www.upharmmall.co.kr |
| HMP몰 | `hmpmall` | https://www.hmpmall.co.kr |
| 티제이팜 | `tjpharm` | https://tjp.co.kr |

위 URL은 `site_url` 필드(설정/약품목록 모달의 링크) 기준입니다. 일부 도매상은 지역별로 동작이 갈리는데, 그 방식이 서로 다릅니다.

- **지오영(geoweb)**: 지역마다 접속 도메인 자체가 다릅니다 (`REGION_URLS`, [scrapers/geoweb_scraper.py](scrapers/geoweb_scraper.py)).

  | 지역 | URL |
  |------|-----|
  | 서울·경기·인천 (`seoul`) | https://order.geoweb.kr |
  | 영남 (`yeongnam`) | https://bpm.geoweb.kr |
  | 대전 (`daejeon`) | https://djn.geoweb.kr |

- **지오팜(geopharm)**: URL은 동일하고, 로그인 시 지역코드만 선택합니다 (`daegu`/`daejeon`/`gwangju`/`seoul`).
- **HMP몰(hmpmall)**: URL은 동일하고, 검색 API의 `businessSidoCode` 파라미터로만 지역을 구분합니다 (`41`=경기, `47`=경북).

## 🛠️ 기술 스택

- **Backend**: FastAPI, Python 3.8+
- **Web Scraping**: Playwright (Chromium)
- **Frontend**: HTML5, CSS3, Vanilla JavaScript
- **Real-time Communication**: WebSocket
- **OCR / LLM**: Google Gemini (멀티모달, `google-genai` SDK), 키는 `.env`에서 로드(`python-dotenv`)
- **Fuzzy Matching**: rapidfuzz (한글 자모 분해 기반 약품명 오타 보정)
- **Data Processing**: pandas, numpy, openpyxl/xlrd (엑셀 파싱)
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

> **손글씨 주문지 OCR 사용 시(`.env`)**: OCR 기능은 Google Gemini API 키가 필요합니다. `.env.example`을 `.env`로 복사한 뒤 [Google AI Studio](https://aistudio.google.com/apikey)에서 발급한 키를 `GEMINI_API_KEY`에 입력하세요. (선택: `GEMINI_MODEL`, 기본값 `gemini-2.5-flash`) 키가 없으면 OCR 기능만 비활성화되고 나머지 기능은 정상 동작합니다.
>
> ```bash
> cp .env.example .env   # .env 를 열어 GEMINI_API_KEY 입력
> ```

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

개발 환경에서는 `./dev.sh` 한 줄로 실행하는 것을 권장합니다. 이 스크립트는 프로젝트 루트의 `.venv` 가상환경 파이썬을 사용하며, `PORT=8002`를 export한 뒤 해당 포트를 점유 중인 좀비 프로세스를 정리하고 `python web_server.py`를 실행합니다. (기본 포트는 **8002**입니다. 8000/8001은 다른 로컬 프로젝트와 충돌하기 때문입니다.)

```bash
# 개발 서버 시작 (권장)
./dev.sh

# 또는 직접 실행
python web_server.py

# 브라우저에서 접속
# http://localhost:8002

# 포트 변경이 필요한 경우 PORT 환경변수 사용
PORT=3000 python web_server.py
```

> `run_app.py`는 PyInstaller 패키지 빌드용 진입점이며, 개발 시에는 위의 `./dev.sh` 또는 `python web_server.py`를 사용하세요.

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
├── web_server.py              # FastAPI 웹 서버 (개발 실행: ./dev.sh 또는 python web_server.py)
├── dev.sh                     # 개발 실행 스크립트 (.venv 사용 + 포트 정리 + 서버 실행)
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
│   ├── ocr_service.py         # 손글씨 주문지 OCR — Gemini 호출 및 약품명·포장단위·수량 추출
│   ├── drug_master.py         # 약품 마스터 — 엑셀 업로드/머리글 추정/컬럼 매핑/제약사 정규화
│   ├── drug_matcher.py        # OCR 약품명 오타 보정 — 한글 자모 fuzzy 매칭(rapidfuzz) + 마스터 직접 검색
│   ├── file_manager.py        # 약품 목록 / JSON 파일 I/O
│   ├── data_processor.py      # 데이터 처리 및 분류
│   └── notifications.py       # 크로스 플랫폼 알림
│
├── templates/
│   ├── home.html              # 홈 화면(앱 런처) HTML 템플릿 (GET /)
│   ├── index.html             # 품절 약 서치앱 대시보드 HTML 템플릿 (GET /checker)
│   ├── order_ocr.html         # 손글씨 주문지 OCR 업로드·검수 화면 (GET /order-ocr)
│   └── drug_master.html       # 약품 마스터 등록 화면 (GET /drug-master)
│
├── static/
│   ├── css/                   # 기능별 CSS 파일 (home.css = 홈, order-ocr.css, drug-master.css 등)
│   └── js/                    # 모듈별 JavaScript 파일 (home.js = 홈, main.js = 대시보드, order-ocr.js, drug-master.js)
│
├── data/                      # 로컬 데이터 (자동 생성)
│   └── drug_master.json       # 등록된 약품 마스터 (약품명·보험코드·제약사)
│
├── .env                       # OCR용 Gemini API 키 (직접 생성, .env.example 참고, git 미커밋)
├── docs/                      # 기능 계획·설계 문서 (예: 손글씨-주문지-OCR-기능-계획.md)
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

### 홈 화면과 세션 복원

루트 경로 `/`는 앱 런처 역할의 **홈 화면**(`templates/home.html`, `static/js/home.js`, `static/css/home.css`)이며, 품절 약 서치앱 대시보드는 `/checker`(`templates/index.html`)로 분리되어 있습니다. 대시보드 상단 브랜드를 누르면 홈으로 돌아갑니다.

- **keep-alive WebSocket**: 대시보드에서 홈으로 이동하면 대시보드의 WebSocket이 끊깁니다. 서버는 모든 WebSocket이 끊기면 "브라우저가 닫힘"으로 판단해 종료하므로, 홈 화면도 `/ws`로 keep-alive WebSocket을 열어 이를 방지합니다. 홈은 이 연결로 받은 `cycle_start`/`search_stopped` 메시지와 `/api/status`로 카드의 "검색 중" 배지를 갱신합니다.
- **로그 히스토리 버퍼**: `ConnectionManager`는 모든 WebSocket 메시지의 단일 통로인 `broadcast_message`에서 로그성 메시지(로그·사이클·검색 완료·긴급 알림 등)를 텍스트로 정규화해 `log_history` 버퍼(최근 300줄)에 누적합니다. 연결 수와 무관하게 누적되며 `GET /api/logs`로 조회, `POST /api/logs/clear`로 비울 수 있습니다.
- **세션 복원**: 홈 → 대시보드로 다시 진입하면 `main.js`가 `/api/logs`로 진행상황 로그를, `/api/status`의 `current_search`로 직전 완료 사이클의 재고/품절 결과 카드를 복원합니다. 사용자가 대시보드에서 로그를 지우면 서버 버퍼(`/api/logs/clear`)도 함께 비워 재진입 시 되살아나지 않습니다.
- **no-cache 미들웨어**: `web_server.py`는 정적 파일과 페이지(`/`, `/checker`, `/order-ocr`, `/drug-master`)에 `Cache-Control: no-cache`를 강제하는 HTTP 미들웨어를 둡니다. `StaticFiles`가 `Cache-Control`을 생략해 브라우저가 옛 파일을 휴리스틱 캐싱하는 문제를 막기 위함이며, 변경이 없으면 304로 저렴하게 끝납니다.

반복 검색 모드에서는 한 사이클이 끝나도(`search_completed`) 검색이 계속 진행되므로, 대시보드의 액션 버튼은 명시적으로 중단하기 전까지 "검색 중단" 상태를 유지합니다.

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

### 손글씨 주문지 OCR (Order OCR)

손으로 작성한 약국 주문지를 사진으로 올리면 약품명·포장단위·주문수량을 구조화 추출하는 기능입니다(`/order-ocr`, `utils/ocr_service.py`).

- **멀티모달 LLM**: `google-genai` SDK로 Google Gemini(`gemini-2.5-flash`, `GEMINI_MODEL`로 변경 가능)를 호출합니다. 응답은 `response_schema`로 `[{drug_name, package_unit, quantity, crossed_out}]` 배열을 강제하고 `temperature=0`으로 안정성을 높입니다.
- **도메인 프롬프트**: 약국 주문지의 표기 규칙을 학습시킵니다 — 줄 오른쪽의 `AxB`는 'A정짜리 통을 B개 주문'으로 해석해 `package_unit`(예: `30정`)과 `quantity`(예: `2`)로 분리하고, 약품명 뒤 함량/규격(예: `600mg`)은 약품명에 포함하며, 머리글·날짜·메모 등 주문 품목이 아닌 줄은 제외합니다.
- **누락 방지(recall-first)**: 한 줄도 빠뜨리지 않도록 왼쪽 열을 위에서 아래로, 그다음 오른쪽 열을 전부 추출합니다. 글씨가 흐리거나 취소선이 그어졌거나 동그라미 등 주석이 있어도 모두 포함하며, **취소선 품목은 임의로 빼지 않고 `crossed_out=true`로 표시만** 합니다 — 주문에서 뺄지는 검수 화면에서 사용자가 결정합니다.
- **Human-in-the-loop 검수**: 추출이 끝나면 화면이 업로드 카드를 감추고 **좌우 2단 검수 레이아웃**으로 전환됩니다 — 왼쪽은 원본 사진을 sticky로 고정한 패널, 오른쪽은 편집 가능한 검수 테이블입니다. 왼쪽 사진은 원본과 대조하며 확인할 수 있도록 확대(휠/버튼, 커서·핀치 중심 고정)·이동(드래그/태블릿 터치)·원래대로(더블클릭/버튼) 및 '다른 이미지 올리기'(재업로드) 조작을 지원하고, 읽어온 품목 수는 검수 헤더로 옮겨 대조 중에도 보이게 했습니다. 화면이 좁으면(≤900px) 자동으로 위아래 세로 배치로 바뀝니다. **1단계(로컬 검증)에서는 저장하지 않습니다.** 키 유출 방지를 위해 배포 단계에서는 호출을 서버 측(Supabase Edge Function 등)으로 이전할 예정입니다(`docs/손글씨-주문지-OCR-기능-계획.md`).
- **키 미설정 처리**: SDK는 지연 임포트하며, `GEMINI_API_KEY`가 없으면 `/api/order-ocr/extract`가 503을 반환할 뿐 앱의 나머지 기능은 정상 동작합니다. 업로드는 JPEG/PNG/WebP/HEIC/HEIF, 최대 15MB로 제한됩니다.

### OCR 약품명 오타 보정 (Drug Matcher)

OCR로 읽은 약품명을 등록된 약품 마스터와 대조해 오타를 잡아내는 기능입니다(`utils/drug_matcher.py`, 의존성 `rapidfuzz`). 마스터가 등록돼 있을 때만 동작하며, 자동 교정 없이 검수 화면에 후보를 제시하는 Human-in-the-loop 방식입니다.

- **한글 자모 매칭**: 한글은 글자 단위 편집거리로는 부정확하므로 음절을 초/중/종성 자모로 분해한 뒤 유사도를 계산합니다. 마스터명은 길고 상세하므로(예: `가나칸정50밀리그램(이토프리드염산염)_(50mg/1정)`) 숫자·괄호 앞의 '핵심 이름'만 뽑아 비교하고, 제형 접미(`서방정`·`주`·`캡슐` 등)와 손글씨 약품명 앞의 제약사 접두(`일성)호이펜`→`호이펜`)는 떼어냅니다. 짧은 손글씨명이 긴 공식명의 접두인 경우는 부분일치로 보정합니다.
- **용량 인식**: 브랜드는 같아도 용량(규격) 숫자가 다르면(600mg≠300mg) 점수를 제한해 '일치'가 아닌 '확인 필요'로 처리합니다.
- **검수 화면 표시**: `/api/order-ocr/extract`가 각 항목에 매칭 결과(`match`)를 덧붙이며, 검수 테이블 각 행이 상태 배지를 보여줍니다 — `matched`(유사도 ≥90, "✓ 약품명 일치" 배지로 공식 전체명을 자동 적용하고 드롭다운으로 원본 복원 가능), `candidate`(70~90, 후보 드롭다운 제시), `none`(미등록), `skip`(마스터 미등록 → 표시 없음). 원본에 취소선이 있던 항목(`crossed_out`)은 빨간 "취소선" 배지를 추가로 달아 목록에 남겨두며, 사용자가 빼려면 직접 삭제합니다.
- **직접 검색**: 후보에 원하는 약이 없으면 행별 "직접 검색" 박스로 `GET /api/drug-master/search`를 호출해 마스터 DB를 이름 부분일치(우선) + 자모 fuzzy(보충)로 직접 조회·선택합니다.
- **인덱스 캐시**: 마스터 파일(`data/drug_master.json`)의 mtime을 기준으로 자모 인덱스를 캐싱하고, 파일이 바뀌면 자동 재구축합니다.

### 약품 마스터 관리 (Drug Master)

약국이 취급하는 전체 약품 목록을 엑셀로 등록하는 기능입니다(`/drug-master`, `utils/drug_master.py`). 위의 OCR 약품명 오타 보정(`drug_matcher`)의 기준 데이터로 사용됩니다.

- **머리글 행 자동 추정**: 실제 약국 엑셀 export는 제목·조회일시 등이 머리글 위에 깔리는 경우가 많습니다. `_guess_header_row`가 `약품명`·`보험코드`·`제약사` 등 키워드가 든 행(또는 비어있지 않은 칸이 가장 많은 행)을 머리글로 추정하며, `/api/drug-master/preview`로 원본 상단 행과 함께 반환합니다. 사용자는 모달에서 머리글 행을 직접 바꿀 수 있습니다.
- **컬럼 매핑**: 컬럼명이 약국마다 다르므로, 사용자가 약품명(필수)·보험코드(선택)·제약사(선택) 컬럼을 직접 지정해 `/api/drug-master/import`로 등록합니다. 빈 행은 건너뛰고 (약품명, 보험코드) 조합으로 중복을 제거합니다.
- **제약사 정규화**: `normalize_maker`가 `대웅제약(주)`→`대웅`, `(주)보령`→`보령`처럼 법인/접미 토큰을 제거한 정규화 형태(`maker_norm`)를 함께 저장해, 표기 편차에도 매칭이 가능하게 합니다.
- **저장**: 결과는 로컬 JSON `data/drug_master.json`에 등록(덮어쓰기)되며, `/api/drug-master`로 등록 현황(개수·출처 파일·매핑한 컬럼)을 조회합니다.

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
- `GET /` - 홈 화면 (앱 런처)
- `GET /checker` - 품절 약 서치앱 대시보드
- `GET /order-ocr` - 손글씨 주문지 OCR 업로드·검수 화면
- `POST /api/order-ocr/extract` - 주문지 이미지 → Gemini OCR → 약품명·포장단위·수량 추출 (마스터 등록 시 항목별 오타 보정 매칭 결과 포함)
- `GET /drug-master` - 약품 마스터 등록 화면
- `GET /api/drug-master` - 약품 마스터 등록 현황 조회
- `GET /api/drug-master/search` - 약품 마스터 직접 검색 (OCR 검수 화면의 "직접 검색"용, `q` 파라미터)
- `POST /api/drug-master/preview` - 업로드 엑셀 미리보기 (머리글 행 추정 + 컬럼·샘플 반환)
- `POST /api/drug-master/import` - 선택한 컬럼 매핑으로 약품 마스터 등록(덮어쓰기)
- `GET /api/status` - 현재 상태 조회
- `POST /api/search/start` - 검색 시작
- `POST /api/search/stop` - 검색 중단
- `GET /api/logs` - 진행상황 로그 히스토리 조회 (페이지 재진입 시 복원용)
- `POST /api/logs/clear` - 진행상황 로그 히스토리 비우기
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
- JavaScript: `static/js/` 디렉터리의 모듈별 파일 수정 (`home.js` = 홈 화면, `main.js` = 대시보드)
- HTML: 홈 화면은 `templates/home.html`, 대시보드는 `templates/index.html` 수정

## 🐛 문제 해결

### 브라우저 설치 문제

```bash
# Playwright 브라우저 재설치
python -m playwright install chromium --force

# 시스템 의존성 설치 (Ubuntu/Debian)
sudo python -m playwright install-deps chromium
```
