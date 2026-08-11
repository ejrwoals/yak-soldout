-- =============================================================================
-- 0004 멤버십 조회 편의 뷰 — 대시보드에서 UUID 대신 약국 이름·유저 이메일로 보기
-- =============================================================================
-- memberships 를 pharmacies(약국명) + auth.users(이메일/이름) 와 조인.
-- ⚠️ 이메일을 노출하므로 클라이언트 롤(anon/authenticated)에는 권한을 주지 않는다.
--    대시보드(postgres) / service_role 에서만 조회 → 데이터 유출 방지.
-- 적용: SQL Editor 에 붙여넣고 Run. 이후 Table Editor 목록의 membership_details 뷰로 확인.
-- =============================================================================

create or replace view membership_details as
select
  m.id,
  p.name                                                        as pharmacy_name,
  u.email                                                       as user_email,
  coalesce(u.raw_user_meta_data ->> 'full_name',
           u.raw_user_meta_data ->> 'name')                     as user_name,
  m.role,
  m.created_at,
  m.pharmacy_id,
  m.user_id
from memberships m
join pharmacies p on p.id = m.pharmacy_id
join auth.users u on u.id = m.user_id
order by p.name, m.created_at;

-- 클라이언트 롤에는 노출 금지 (0002 기본 권한으로 부여됐을 수 있어 명시적 회수)
revoke all on membership_details from anon, authenticated;
grant select on membership_details to service_role;
