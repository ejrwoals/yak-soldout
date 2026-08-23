-- 0007: 규격 수집 미발견 보류 (drug_master.unit_notfound_at)
--
-- 규격 수집에서 기준 도매상에 규격 정보가 없던 약품(미발견)은 다음 수집 때도
-- 또 검색돼 시간을 낭비한다. 미발견 시각을 기록해 기본 수집 대상에서 제외하고,
-- 스탭이 수집 시작 모달에서 체크박스를 켠 경우에만 다시 포함한다.
-- 규격을 찾으면(또는 재검색에 성공하면) NULL 로 되돌린다.

alter table drug_master add column if not exists unit_notfound_at timestamptz;
