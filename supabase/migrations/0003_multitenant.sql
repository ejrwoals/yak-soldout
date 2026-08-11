-- =============================================================================
-- 0003 멀티테넌트 전환 — 데이터 주인을 개인(user_id) → 약국(pharmacy_id)으로
-- =============================================================================
-- 약국 1곳 = 테넌트. 사용자는 memberships 로 약국에 소속(admin|staff)되고,
-- 소속을 통해서만 그 약국 데이터에 접근한다(RLS). 다른 약국 데이터는 물리적 차단.
--
-- ⚠️ 개발 리셋: 기존 orders/order_items/drug_master 데이터를 비운다(폐기 가능 전제).
--    적용 후 약국(pharmacies) 1행과 관리자 멤버십(memberships, role='admin')을 만들고,
--    drug_master 는 로컬 앱의 관리자 엑셀 임포트로 채운다.
-- 적용: SQL Editor 에 붙여넣고 Run. (0001, 0002 다음)
-- =============================================================================

-- ---- 1) 테넌트 / 멤버십 / 초대 ----
create table if not exists pharmacies (
  id         uuid primary key default gen_random_uuid(),
  name       text not null,
  created_at timestamptz not null default now()
);

create table if not exists memberships (
  id          uuid primary key default gen_random_uuid(),
  pharmacy_id uuid not null references pharmacies(id) on delete cascade,
  user_id     uuid not null references auth.users(id) on delete cascade,
  role        text not null default 'staff' check (role in ('admin', 'staff')),
  created_at  timestamptz not null default now(),
  unique (pharmacy_id, user_id)
);
create index if not exists idx_memberships_user     on memberships(user_id);
create index if not exists idx_memberships_pharmacy on memberships(pharmacy_id);

create table if not exists invites (
  code        text primary key,                 -- 추측 불가능한 랜덤 코드
  pharmacy_id uuid not null references pharmacies(id) on delete cascade,
  created_by  uuid not null references auth.users(id),
  role        text not null default 'staff' check (role in ('admin', 'staff')),
  expires_at  timestamptz,
  max_uses    int,
  uses        int not null default 0,
  created_at  timestamptz not null default now()
);
create index if not exists idx_invites_pharmacy on invites(pharmacy_id);

-- ---- 2) 헬퍼 함수 (security definer — memberships RLS 재귀 방지) ----
create or replace function auth_pharmacy_ids()
returns setof uuid language sql security definer stable set search_path = public as $$
  select pharmacy_id from memberships where user_id = auth.uid()
$$;

create or replace function auth_is_admin(p uuid)
returns boolean language sql security definer stable set search_path = public as $$
  select exists (
    select 1 from memberships
    where user_id = auth.uid() and pharmacy_id = p and role = 'admin'
  )
$$;

grant execute on function auth_pharmacy_ids() to authenticated;
grant execute on function auth_is_admin(uuid) to authenticated;

-- ---- 3) 기존 데이터 테이블: user_id → pharmacy_id (개발 리셋) ----
truncate table orders cascade;   -- order_items 도 cascade 로 비워짐
truncate table drug_master;

-- orders
alter table orders drop column if exists user_id cascade;   -- 관련 unique/index 자동 제거
alter table orders add column if not exists pharmacy_id uuid not null
      references pharmacies(id) on delete cascade;
create index if not exists idx_orders_pharmacy_status on orders(pharmacy_id, status);
alter table orders drop constraint if exists orders_pharmacy_date_round_key;
alter table orders add constraint orders_pharmacy_date_round_key
      unique (pharmacy_id, order_date, order_round);

-- drug_master
alter table drug_master drop column if exists user_id cascade;
alter table drug_master add column if not exists pharmacy_id uuid not null
      references pharmacies(id) on delete cascade;
create index if not exists idx_drug_master_pharmacy on drug_master(pharmacy_id);

-- ---- 4) RLS ----
alter table pharmacies  enable row level security;
alter table memberships enable row level security;
alter table invites     enable row level security;
-- orders/order_items/drug_master 는 0001 에서 이미 RLS 활성화됨

-- pharmacies: 소속 약국만 조회. 생성은 service_role(엔드포인트)만.
drop policy if exists pharmacies_member on pharmacies;
create policy pharmacies_member on pharmacies for select
  using (id in (select auth_pharmacy_ids()));

-- memberships: 본인 멤버십 + 내가 admin 인 약국의 멤버 조회. 쓰기는 service_role.
drop policy if exists memberships_read on memberships;
create policy memberships_read on memberships for select
  using (user_id = auth.uid() or auth_is_admin(pharmacy_id));

-- invites: admin 이 자기 약국 초대 관리(조회/발행/폐기). redeem 은 service_role.
drop policy if exists invites_admin on invites;
create policy invites_admin on invites for all
  using (auth_is_admin(pharmacy_id))
  with check (auth_is_admin(pharmacy_id));

-- orders: 소속 멤버면 CRUD
drop policy if exists orders_owner  on orders;
drop policy if exists orders_member on orders;
create policy orders_member on orders for all
  using (pharmacy_id in (select auth_pharmacy_ids()))
  with check (pharmacy_id in (select auth_pharmacy_ids()));

-- order_items: 부모 order 의 약국 멤버면 CRUD
drop policy if exists order_items_owner  on order_items;
drop policy if exists order_items_member on order_items;
create policy order_items_member on order_items for all
  using (exists (select 1 from orders o
                 where o.id = order_items.order_id
                   and o.pharmacy_id in (select auth_pharmacy_ids())))
  with check (exists (select 1 from orders o
                 where o.id = order_items.order_id
                   and o.pharmacy_id in (select auth_pharmacy_ids())));

-- drug_master: 소속 멤버면 CRUD
drop policy if exists drug_master_owner  on drug_master;
drop policy if exists drug_master_member on drug_master;
create policy drug_master_member on drug_master for all
  using (pharmacy_id in (select auth_pharmacy_ids()))
  with check (pharmacy_id in (select auth_pharmacy_ids()));

-- Storage: order-images/<pharmacy_id>/... — 소속 멤버만 (경로는 text 비교, uuid 캐스팅 회피)
drop policy if exists order_images_owner  on storage.objects;
drop policy if exists order_images_member on storage.objects;
create policy order_images_member on storage.objects for all
  using (bucket_id = 'order-images'
         and (storage.foldername(name))[1] in (select auth_pharmacy_ids()::text))
  with check (bucket_id = 'order-images'
         and (storage.foldername(name))[1] in (select auth_pharmacy_ids()::text));

-- ---- 5) 새 테이블 권한 (RLS 와 별개로 GRANT 필요) ----
grant select, insert, update, delete on pharmacies, memberships, invites to authenticated;
grant all on pharmacies, memberships, invites to service_role;
