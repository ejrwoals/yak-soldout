# Supabase — 자동 주문 솔루션 백엔드

자동주문 솔루션(Cloud Run 웹 UI + 로컬 PyWebView 앱)이 공유하는 **유일한 접점**.
품절약 서치앱의 로컬 SQLite와는 무관하다.

전체 설계: [../주문-자동화-워크플로우-구현-계획.md](../주문-자동화-워크플로우-구현-계획.md)

```
supabase/
  migrations/
    0001_autoorder_schema.sql   # orders / order_items / drug_master + RLS + Storage
```

## 1. 프로젝트 생성 & 키 발급

1. https://supabase.com → 새 프로젝트 생성 (리전은 가까운 곳, 예: Seoul/Tokyo)
2. Project Settings → API 에서 아래 3개를 확보:
   - **Project URL** (`https://xxxx.supabase.co`)
   - **anon public key** — 클라이언트/로컬 앱용 (RLS로 보호됨)
   - **service_role key** — 서버 전용, **절대 클라이언트/이미지에 노출 금지**

## 2. 스키마 적용

**방법 A — 대시보드 (간단):**
SQL Editor → New query → [migrations/0001_autoorder_schema.sql](migrations/0001_autoorder_schema.sql) 내용
전체 붙여넣기 → Run.

**방법 B — CLI:**
```bash
supabase link --project-ref <프로젝트-ref>
supabase db push
```

적용 후 Table Editor에 `orders`·`order_items`·`drug_master`가, Storage에 `order-images`
버킷(비공개)이 생겼는지 확인.

## 3. Google 로그인(OAuth) 설정

Authentication → Providers → **Google** 활성화. Google Cloud Console에서 OAuth 클라이언트를
만들고, 승인된 리디렉션 URI에 Supabase가 안내하는 콜백 URL
(`https://xxxx.supabase.co/auth/v1/callback`)을 등록. 배포 후 Cloud Run 도메인을
Authentication → URL Configuration의 Redirect URLs에 추가.

## 4. 로컬/서버에서 쓸 환경변수

각 스택의 `.env` 에 (커밋 금지):

```
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_ANON_KEY=<anon key>         # 로컬 PyWebView 앱 (RLS 적용)
# SUPABASE_SERVICE_KEY=<service key> # Cloud Run 웹만, Secret Manager로 주입
```

## 데이터 계약 요약

| 테이블 | 키 | 용도 |
|--------|-----|------|
| `orders` | `(user_id, order_date, order_round)` | 주문장. `status`: reviewing→pending→ordered |
| `order_items` | `order_id` FK | 품목. `cart_status`: none/added/failed (크롤링 결과) |
| `drug_master` | `user_id` | 약품 마스터 (로컬 SQLite에서 이전) |

- 로컬 앱은 `status = 'pending'` 주문만 조회 → 크롤링 → 완료 시 `ordered`로 갱신 + 품목 `cart_status` 기록.
- 모든 테이블 RLS로 `user_id` 격리. Storage `order-images`는 `<user_id>/파일명` 경로 규칙.
