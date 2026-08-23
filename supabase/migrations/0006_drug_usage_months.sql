-- 0006: 월별 사용량 요약 (drug_usage_months)
--
-- 약품 DB 탭의 '월별 타일' 시각화용. 월마다 사용량이 있는 약품 수·총량과
-- 월평균 계산에서의 역할(status)을 저장한다. 원본(drug_usage)에서 매번 집계하면
-- 수만 행을 읽어야 해서, 임포트 시 월평균 재계산과 함께 갱신해 둔다.
--   status: 'window'  = 최근 12개 완전월 (월평균 계산에 사용)
--           'stored'  = 저장돼 있지만 계산 구간 밖 (과거 달)
--           'partial' = 진행 중인 달(부분 데이터)로 판정돼 계산에서 제외

create table if not exists drug_usage_months (
  id          uuid primary key default gen_random_uuid(),
  pharmacy_id uuid not null references pharmacies(id) on delete cascade,
  year        int  not null check (year between 2000 and 2100),
  month       int  not null check (month between 1 and 12),
  drugs       int  not null default 0,      -- 그 달 사용량이 있는 약품 수
  total       numeric not null default 0,   -- 그 달 사용량 총합
  status      text not null check (status in ('window', 'stored', 'partial')),
  unique (pharmacy_id, year, month)
);

create index if not exists idx_drug_usage_months_pharmacy on drug_usage_months (pharmacy_id);

alter table drug_usage_months enable row level security;

drop policy if exists drug_usage_months_member on drug_usage_months;
create policy drug_usage_months_member on drug_usage_months for all
  using (pharmacy_id in (select auth_pharmacy_ids()))
  with check (pharmacy_id in (select auth_pharmacy_ids()));

grant select, insert, update, delete on drug_usage_months to authenticated;
grant all on drug_usage_months to service_role;
