-- =============================================================================
-- 역할별 테이블 권한 (GRANT)
-- =============================================================================
-- RLS(행 수준 보안)는 "어떤 행"을 볼지 제어하고, GRANT는 "테이블 접근 자체"를 제어한다.
-- 둘은 별개다. SQL Editor로 직접 만든 테이블은 역할별 기본 GRANT가 누락될 수 있어
-- 여기서 명시적으로 부여한다.
--
-- 적용: Supabase SQL Editor에 붙여넣고 Run. (0001 다음에 실행)
--
-- 역할 정리:
--   service_role : RLS 우회 + 전체 권한 (서버/관리/개발 도구)
--   authenticated: 로그인 사용자. 전체 권한을 주되 RLS가 '본인 행'으로 제한
--   anon         : 미로그인. 권한 없음 → 로그인해야 데이터 접근 가능
-- =============================================================================

-- 로그인 사용자 (RLS가 본인 행으로 제한하므로 CRUD 부여해도 안전)
grant select, insert, update, delete on public.orders      to authenticated;
grant select, insert, update, delete on public.order_items to authenticated;
grant select, insert, update, delete on public.drug_master to authenticated;

-- 서버/관리/개발 도구 (RLS 우회)
grant all on public.orders      to service_role;
grant all on public.order_items to service_role;
grant all on public.drug_master to service_role;

-- 앞으로 public 스키마에 생기는 테이블도 자동으로 같은 권한을 받도록 기본 권한 설정
alter default privileges in schema public
  grant select, insert, update, delete on tables to authenticated;
alter default privileges in schema public
  grant all on tables to service_role;
