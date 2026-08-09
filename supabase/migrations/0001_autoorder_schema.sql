-- =============================================================================
-- 자동 주문 솔루션 — 초기 스키마 (데이터 계약)
-- =============================================================================
-- 대상: 자동주문 솔루션 전용 (품절약 서치앱의 로컬 SQLite와 무관 — 옮기지 않음).
-- 두 스택(Cloud Run 웹 UI / 로컬 PyWebView 앱)은 이 스키마를 통해서만 만난다.
--
-- 적용: Supabase 대시보드 SQL Editor에 붙여넣거나, `supabase db push` (CLI).
-- 참고 계획: 주문-자동화-워크플로우-구현-계획.md §3
--
-- 수명주기(status): reviewing(웹 검수 중) → pending(저장, 로컬 크롤링 대기)
--                   → ordered(로컬이 장바구니 담기 완료)
-- =============================================================================

-- gen_random_uuid() 제공 (Supabase 기본 활성화지만 방어적으로 명시)
create extension if not exists pgcrypto;

-- -----------------------------------------------------------------------------
-- updated_at 자동 갱신 트리거 함수
-- -----------------------------------------------------------------------------
create or replace function set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

-- -----------------------------------------------------------------------------
-- orders — 주문장 (날짜 + 차수 = 한 주문)
-- -----------------------------------------------------------------------------
create table if not exists orders (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null references auth.users(id) on delete cascade,
  order_date  date not null,
  order_round int  not null check (order_round between 1 and 3),
  status      text not null default 'reviewing'
              check (status in ('reviewing', 'pending', 'ordered')),
  image_path  text,                       -- Supabase Storage 경로 (order-images 버킷 기준)
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  unique (user_id, order_date, order_round)  -- (날짜,차수) = 한 주문
);

create index if not exists idx_orders_user_status on orders (user_id, status);

drop trigger if exists trg_orders_updated_at on orders;
create trigger trg_orders_updated_at
  before update on orders
  for each row execute function set_updated_at();

-- -----------------------------------------------------------------------------
-- order_items — 주문 품목 (검수 후 확정값)
-- -----------------------------------------------------------------------------
create table if not exists order_items (
  id            uuid primary key default gen_random_uuid(),
  order_id      uuid not null references orders(id) on delete cascade,
  drug_name     text not null,
  package_unit  text,
  quantity      text,                     -- OCR 안정성 위해 문자열 유지 (기존 로컬 스키마와 동일)
  distributor   text,                     -- 주문 도매상 dist_key (예: "geoweb"), 미선택 시 NULL
  cart_status   text not null default 'none'
                check (cart_status in ('none', 'added', 'failed')),  -- 로컬 크롤링 결과
  position      int                       -- OCR 추출 순서 보존 (왼쪽열→오른쪽열)
);

create index if not exists idx_order_items_order on order_items (order_id);
create index if not exists idx_order_items_drug  on order_items (drug_name);

-- -----------------------------------------------------------------------------
-- drug_master — 약품 마스터 DB (로컬 SQLite에서 이전)
-- -----------------------------------------------------------------------------
create table if not exists drug_master (
  id             uuid primary key default gen_random_uuid(),
  user_id        uuid not null references auth.users(id) on delete cascade,
  name           text not null,
  insurance_code text,                    -- nullable·비유니크 (기존 v2 완화 유지)
  maker          text,
  maker_norm     text,
  unit           text,                    -- 규격수집 크롤링(로컬)이 채우는 포장단위
  unit_manual    text,                    -- 뷰어에서 사용자가 직접 추가한 규격
  source         text not null default 'excel' check (source in ('excel', 'manual')),
  imported_at    timestamptz,
  source_file    text
);

create index if not exists idx_drug_master_user on drug_master (user_id);
create index if not exists idx_drug_master_code on drug_master (insurance_code);
create index if not exists idx_drug_master_name on drug_master (user_id, name);

-- =============================================================================
-- RLS (Row Level Security) — 약국(user)별 물리적 격리
-- =============================================================================
alter table orders      enable row level security;
alter table order_items enable row level security;
alter table drug_master enable row level security;

-- orders: 본인 행만
drop policy if exists orders_owner on orders;
create policy orders_owner on orders
  for all
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

-- order_items: 부모 order의 소유자만 (order_items에는 user_id가 없으므로 EXISTS로 검사)
drop policy if exists order_items_owner on order_items;
create policy order_items_owner on order_items
  for all
  using (
    exists (select 1 from orders o where o.id = order_items.order_id and o.user_id = auth.uid())
  )
  with check (
    exists (select 1 from orders o where o.id = order_items.order_id and o.user_id = auth.uid())
  );

-- drug_master: 본인 행만
drop policy if exists drug_master_owner on drug_master;
create policy drug_master_owner on drug_master
  for all
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

-- =============================================================================
-- Storage — 주문지 원본 이미지 버킷
-- =============================================================================
-- 비공개 버킷. 경로 규칙: '<user_id>/<파일명>' → 첫 폴더가 소유자 uid.
insert into storage.buckets (id, name, public)
values ('order-images', 'order-images', false)
on conflict (id) do nothing;

-- 본인 폴더(<uid>/...)의 객체만 접근 (storage.foldername(name)[1] = 최상위 폴더명)
drop policy if exists order_images_owner on storage.objects;
create policy order_images_owner on storage.objects
  for all
  using (
    bucket_id = 'order-images'
    and (storage.foldername(name))[1] = auth.uid()::text
  )
  with check (
    bucket_id = 'order-images'
    and (storage.foldername(name))[1] = auth.uid()::text
  );
