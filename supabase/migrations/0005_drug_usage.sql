-- 0005: 월별 약품 사용량 (drug_usage) + 월평균 통계 (drug_usage_stats)
--
-- 약국 조제 프로그램의 '월별 약품사용량' 엑셀을 로컬 앱에서 업로드하면
-- (청구코드, 연, 월) 단위 원본이 drug_usage 에 저장되고(연도 파일 재업로드 = 그 연도 교체),
-- '최근 12개 완전월' 기준 월평균이 drug_usage_stats 로 재계산된다.
-- 마지막 달의 부분 데이터 여부는 robust z-score(중앙값·MAD)로 판정한다.
-- 주문 검수 화면과 약품 DB 뷰어에서 참고 자료(월평균 사용량)로 표시한다.

-- ---- 1) 테이블 ----
create table if not exists drug_usage (
  id             uuid primary key default gen_random_uuid(),
  pharmacy_id    uuid not null references pharmacies(id) on delete cascade,
  insurance_code text not null,              -- 엑셀 청구코드 (조인 키)
  name           text,                       -- 표시/디버깅용 (엑셀 약품명)
  year           int  not null check (year between 2000 and 2100),
  month          int  not null check (month between 1 and 12),
  qty            numeric not null default 0, -- 그 달 사용량 (0인 달은 저장하지 않음)
  source_file    text,
  imported_at    timestamptz,
  unique (pharmacy_id, insurance_code, year, month)
);

create index if not exists idx_drug_usage_pharmacy on drug_usage (pharmacy_id, year, month);

create table if not exists drug_usage_stats (
  id             uuid primary key default gen_random_uuid(),
  pharmacy_id    uuid not null references pharmacies(id) on delete cascade,
  insurance_code text not null,
  name           text,
  monthly_avg    numeric not null default 0,
  months_used    int not null default 0,     -- 평균 분모 (취급 시작월부터 센 완전월 수)
  window_start   text,                       -- 'YYYY-MM' (계산에 쓴 완전월 구간)
  window_end     text,
  computed_at    timestamptz,
  unique (pharmacy_id, insurance_code)
);

create index if not exists idx_drug_usage_stats_pharmacy on drug_usage_stats (pharmacy_id);

-- ---- 2) RLS — 소속 멤버면 CRUD (drug_master 와 동일 기준) ----
alter table drug_usage       enable row level security;
alter table drug_usage_stats enable row level security;

drop policy if exists drug_usage_member on drug_usage;
create policy drug_usage_member on drug_usage for all
  using (pharmacy_id in (select auth_pharmacy_ids()))
  with check (pharmacy_id in (select auth_pharmacy_ids()));

drop policy if exists drug_usage_stats_member on drug_usage_stats;
create policy drug_usage_stats_member on drug_usage_stats for all
  using (pharmacy_id in (select auth_pharmacy_ids()))
  with check (pharmacy_id in (select auth_pharmacy_ids()));

-- ---- 3) 권한 (RLS 와 별개로 GRANT 필요) ----
grant select, insert, update, delete on drug_usage, drug_usage_stats to authenticated;
grant all on drug_usage, drug_usage_stats to service_role;
