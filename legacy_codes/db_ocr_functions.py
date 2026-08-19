"""[아카이브] db.py 의 주문지 OCR 관련 함수 — drug_master / orders 데이터 계층.

OCR·주문·약품 마스터 기능이 약국 주문 Agent(cloud_web/ + local_app/, Supabase)로 이전되어
품절약 서치앱 db.py 에서 분리했다. 어디서도 임포트되지 않는 참조용 사본이다.

로컬 SQLite(data/yak_soldout.db)의 drug_master / orders / order_items 테이블과 과거 데이터는
그대로 남아 있다 (스키마에서 DDL 은 제거했지만 기존 DB 의 테이블·데이터는 삭제되지 않음).
"""

# ----------------------------------------------------------------------------
# drug_master 쓰기 유틸
# ----------------------------------------------------------------------------
def insert_drug_master(conn: sqlite3.Connection, drug: Dict[str, Any],
                       imported_at: str, source_file: str, source: str = "excel") -> None:
    """drug_master 행 1건 INSERT. insurance_code는 비어 있으면 NULL로 저장."""
    code = (drug.get("insurance_code") or "").strip()
    if code.lower() == "nan":  # pandas가 빈 셀을 'nan' 문자열로 주는 경우 정규화
        code = ""
    conn.execute(
        """INSERT INTO drug_master (name, insurance_code, maker, maker_norm, imported_at, source_file, source)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            drug.get("name", ""),
            code or None,
            drug.get("maker", ""),
            drug.get("maker_norm", "") or None,
            imported_at,
            source_file,
            source,
        ),
    )


def replace_drug_master(drugs: List[Dict[str, Any]], source_file: str, imported_at: str) -> int:
    """약품 마스터 전체 교체 (재임포트). 단일 트랜잭션으로 DELETE 후 INSERT.

    엑셀에는 포장단위(unit)가 없고 스크래핑으로 수집하므로, 재임포트로 기존에 모아둔
    unit이 사라지지 않도록 (약품명, 보험코드) 기준으로 보존해 복원한다.

    반환: 저장된 행 수.
    """
    with transaction() as conn:
        # 기존 규격 스냅샷 (name, code) → (수집 unit, 직접추가 unit_manual)
        prev_units: Dict[tuple, tuple] = {}
        for r in conn.execute(
            """SELECT name, insurance_code, unit, unit_manual FROM drug_master
               WHERE (unit IS NOT NULL AND unit != '')
                  OR (unit_manual IS NOT NULL AND unit_manual != '')"""
        ).fetchall():
            prev_units[(r["name"], r["insurance_code"] or "")] = (r["unit"], r["unit_manual"])

        conn.execute("DELETE FROM drug_master")
        for drug in drugs:
            insert_drug_master(conn, drug, imported_at, source_file)

        # 보존된 규격 복원 (동일 약품명+보험코드 행에만)
        for (name, code), (unit, unit_manual) in prev_units.items():
            conn.execute(
                """UPDATE drug_master SET unit = ?, unit_manual = ?
                   WHERE name = ? AND IFNULL(insurance_code, '') = ?""",
                (unit, unit_manual, name, code),
            )
        return conn.execute("SELECT COUNT(*) FROM drug_master").fetchone()[0]


def upsert_drug_master(drugs: List[Dict[str, Any]], source_file: str, imported_at: str) -> Dict[str, int]:
    """약품 마스터 병합(upsert). (약품명, 보험코드) 기준으로 있으면 갱신, 없으면 추가.

    전체 교체(replace)와 달리 새 파일에 없는 기존 약품은 삭제하지 않고 그대로 둔다.
    기존 행을 지우지 않으므로 수집/직접추가한 규격(unit, unit_manual)은 자연히 유지된다.
    (제약사 표기만 새 파일 값으로 갱신; 규격 컬럼은 건드리지 않는다.)

    반환: {"inserted": 신규, "updated": 갱신, "total": 전체 행 수}.
    """
    inserted = updated = 0
    with transaction() as conn:
        for drug in drugs:
            name = drug.get("name", "")
            code = (drug.get("insurance_code") or "").strip()
            if code.lower() == "nan":
                code = ""
            maker = drug.get("maker", "")
            maker_norm = drug.get("maker_norm", "") or None

            # (약품명 + 보험코드) 일치 행을 갱신; 없으면 INSERT.
            # 빈 보험코드는 NULL로 저장되므로 IFNULL로 비교를 맞춘다.
            cur = conn.execute(
                """UPDATE drug_master SET maker = ?, maker_norm = ?, imported_at = ?, source_file = ?
                   WHERE name = ? AND IFNULL(insurance_code, '') = ?""",
                (maker, maker_norm, imported_at, source_file, name, code),
            )
            if cur.rowcount and cur.rowcount > 0:
                updated += 1
            else:
                insert_drug_master(conn, drug, imported_at, source_file)
                inserted += 1

        total = conn.execute("SELECT COUNT(*) FROM drug_master").fetchone()[0]
    return {"inserted": inserted, "updated": updated, "total": total}


def load_drug_master() -> List[Dict[str, Any]]:
    """drug_master 전체를 매칭용 dict 리스트로 반환."""
    rows = query_all(
        "SELECT name, insurance_code, maker, maker_norm, unit, unit_manual FROM drug_master ORDER BY id"
    )
    return [
        {
            "name": r["name"],
            "insurance_code": r["insurance_code"] or "",
            "maker": r["maker"] or "",
            "maker_norm": r["maker_norm"] or "",
            "unit": r["unit"] or "",
            "unit_manual": r["unit_manual"] or "",
        }
        for r in rows
    ]


def drug_master_meta() -> Dict[str, Any]:
    """등록 현황 요약 (count/source_file/imported_at). 비어 있으면 count=0."""
    row = query_one("SELECT COUNT(*) AS c, MAX(imported_at) AS m FROM drug_master")
    count = row["c"] if row else 0
    if not count:
        return {"count": 0, "source_file": "", "imported_at": ""}
    latest = query_one(
        "SELECT source_file, imported_at FROM drug_master ORDER BY imported_at DESC, id DESC LIMIT 1"
    )
    return {
        "count": count,
        "source_file": (latest["source_file"] if latest else "") or "",
        "imported_at": (latest["imported_at"] if latest else "") or "",
    }


def drug_master_cache_key() -> tuple:
    """매처 캐시 무효화 신호. 임포트(전체교체)마다 MAX(id)/count/imported_at이 바뀜."""
    # unit/unit_manual 은 UPDATE 로만 바뀌어 count/id/imported_at 이 안 변하므로,
    # 규격 텍스트 총길이를 시그니처에 포함해 규격 수집·직접추가 시에도 매처 캐시가 갱신되게 한다.
    row = query_one(
        """SELECT COUNT(*) AS c, COALESCE(MAX(imported_at),'') AS m, COALESCE(MAX(id),0) AS x,
                  COALESCE(SUM(LENGTH(COALESCE(unit,'')) + LENGTH(COALESCE(unit_manual,''))), 0) AS u
           FROM drug_master"""
    )
    return (row["c"], row["m"], row["x"], row["u"]) if row else (0, "", 0, 0)


# ----------------------------------------------------------------------------
# drug_master 포장단위(unit) 수집
# ----------------------------------------------------------------------------
def drug_master_rows_missing_unit() -> List[Dict[str, Any]]:
    """포장단위(unit)가 비어 있고 보험코드가 있는 행만 반환 (스크래핑 수집 대상).

    보험코드가 없으면 코드로 검색할 수 없으므로 제외한다.
    """
    rows = query_all(
        """SELECT id, name, insurance_code FROM drug_master
           WHERE insurance_code IS NOT NULL AND TRIM(insurance_code) != ''
             AND (unit IS NULL OR TRIM(unit) = '')
           ORDER BY id"""
    )
    return [
        {"id": r["id"], "name": r["name"], "insurance_code": r["insurance_code"]}
        for r in rows
    ]


def update_drug_master_unit(row_id: int, unit: str) -> None:
    """drug_master 한 행의 포장단위(unit) 갱신. 빈 값은 NULL로 저장."""
    execute("UPDATE drug_master SET unit = ? WHERE id = ?", ((unit or "").strip() or None, row_id))


def drug_master_unit_stats() -> Dict[str, int]:
    """포장단위 수집 현황 요약.

    - total: 전체 행 수
    - filled: unit이 채워진 행 수
    - missing_with_code: unit이 비었지만 보험코드가 있어 수집 가능한 행 수
    """
    row = query_one(
        """SELECT
             COUNT(*) AS total,
             SUM(CASE WHEN unit IS NOT NULL AND TRIM(unit) != '' THEN 1 ELSE 0 END) AS filled,
             SUM(CASE WHEN (unit IS NULL OR TRIM(unit) = '')
                       AND insurance_code IS NOT NULL AND TRIM(insurance_code) != ''
                      THEN 1 ELSE 0 END) AS missing_with_code
           FROM drug_master"""
    )
    return {
        "total": (row["total"] if row else 0) or 0,
        "filled": (row["filled"] if row else 0) or 0,
        "missing_with_code": (row["missing_with_code"] if row else 0) or 0,
    }


# ----------------------------------------------------------------------------
# drug_master 테이블 뷰어 / 사용자 직접 규격 추가
# ----------------------------------------------------------------------------
def _split_units(s: str) -> List[str]:
    """", "로 합쳐 저장한 규격 문자열을 토큰 리스트로 분해(공백 정리·빈값 제거)."""
    return [u.strip() for u in (s or "").split(",") if u.strip()]


def list_drug_master_rows(offset: int = 0, limit: int = 50, q: str = "",
                          unit_filter: str = "") -> Dict[str, Any]:
    """마스터 테이블을 페이지 단위로 조회(뷰어용). q는 약품명/보험코드 부분일치 검색.

    unit_filter (규격 수집 현황 배지와 동일 분류, 비우면 전체):
      - 'filled'  : 규격수집됨 (unit 있음)
      - 'missing' : 규격미수집 (unit 없음 + 보험코드 있음)
      - 'nocode'  : 보험코드없음 (unit 없음 + 보험코드 없음)
      - 'manual'  : 자유입력 (주문서 자유입력으로 자동 등록된 행, source='manual')

    반환: {"total": 전체(필터 적용) 행 수, "rows": [...]}.
    """
    conds: List[str] = []
    params: List[Any] = []
    if q.strip():
        conds.append("(name LIKE ? OR insurance_code LIKE ?)")
        like = f"%{q.strip()}%"
        params += [like, like]

    uf = (unit_filter or "").strip()
    if uf == "filled":
        conds.append("(unit IS NOT NULL AND TRIM(unit) != '')")
    elif uf == "missing":
        conds.append("((unit IS NULL OR TRIM(unit) = '') "
                     "AND insurance_code IS NOT NULL AND TRIM(insurance_code) != '')")
    elif uf == "nocode":
        conds.append("((unit IS NULL OR TRIM(unit) = '') "
                     "AND (insurance_code IS NULL OR TRIM(insurance_code) = ''))")
    elif uf == "manual":
        conds.append("source = 'manual'")

    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    total = query_one(f"SELECT COUNT(*) AS c FROM drug_master {where}", params)["c"]
    rows = query_all(
        f"""SELECT id, name, insurance_code, maker, unit, unit_manual, source
            FROM drug_master {where} ORDER BY id LIMIT ? OFFSET ?""",
        params + [int(limit), int(offset)],
    )
    return {
        "total": total,
        "rows": [
            {
                "id": r["id"],
                "name": r["name"],
                "insurance_code": r["insurance_code"] or "",
                "maker": r["maker"] or "",
                "unit": r["unit"] or "",
                "unit_manual": r["unit_manual"] or "",
                "source": r["source"] or "excel",
            }
            for r in rows
        ],
    }


def add_drug_master_manual_unit(row_id: int, unit: str) -> Optional[Dict[str, Any]]:
    """사용자가 직접 입력한 규격 1건을 unit_manual에 append(append-only, 삭제 없음).

    이미 수집(unit)되었거나 이미 직접추가(unit_manual)된 규격이면 중복 추가하지 않는다.
    반환: 행이 없으면 None. 있으면 {"added": bool, "unit_manual": 갱신된 문자열}.
    """
    unit = (unit or "").strip()
    row = query_one("SELECT unit, unit_manual FROM drug_master WHERE id = ?", (row_id,))
    if row is None:
        return None
    manual = _split_units(row["unit_manual"])
    if not unit:
        return {"added": False, "unit_manual": ", ".join(manual)}

    existing = set(_split_units(row["unit"])) | set(manual)
    if unit in existing:
        return {"added": False, "unit_manual": ", ".join(manual)}

    manual.append(unit)
    new_manual = ", ".join(manual)
    execute("UPDATE drug_master SET unit_manual = ? WHERE id = ?", (new_manual, row_id))
    return {"added": True, "unit_manual": new_manual}


def delete_drug_master_row(row_id: int) -> bool:
    """자유입력(source='manual') 마스터 행 1건 삭제.

    엑셀 임포트분(source='excel' 또는 NULL)은 안전상 삭제하지 않는다(엑셀 재업로드로 관리).
    반환: 삭제 성공 True / 대상이 없거나 자유입력 행이 아니면 False.
    """
    row = query_one("SELECT source FROM drug_master WHERE id = ?", (row_id,))
    if row is None or (row["source"] or "excel") != "manual":
        return False
    execute("DELETE FROM drug_master WHERE id = ?", (row_id,))
    return True


def rename_drug_master_row(row_id: int, new_name: str) -> Optional[Dict[str, Any]]:
    """자유입력(source='manual') 마스터 행의 약품명을 수정한다(OCR 오타 정리용).

    같은(옛) 이름을 가진 order_items.drug_name 도 새 이름으로 함께 갱신해 주문 이력과 연결을 유지한다.
    반환:
      - None  : 대상 없음 / 자유입력 행 아님 / 빈 이름 / 다른 행과 이름 충돌
      - dict  : {"renamed": bool, "updated_items": 갱신된 주문 항목 수}
    """
    new_name = (new_name or "").strip()
    if not new_name:
        return None
    with transaction() as conn:
        row = conn.execute(
            "SELECT name, source FROM drug_master WHERE id = ?", (row_id,)
        ).fetchone()
        if row is None or (row["source"] or "excel") != "manual":
            return None
        old = row["name"]
        if new_name == old:
            return {"renamed": False, "updated_items": 0}
        dup = conn.execute(
            "SELECT 1 FROM drug_master WHERE name = ? AND id != ?", (new_name, row_id)
        ).fetchone()
        if dup:
            return None
        conn.execute("UPDATE drug_master SET name = ? WHERE id = ?", (new_name, row_id))
        cur = conn.execute(
            "UPDATE order_items SET drug_name = ? WHERE drug_name = ?", (new_name, old)
        )
        return {"renamed": True, "updated_items": cur.rowcount}


def list_manual_master_rows() -> List[Dict[str, Any]]:
    """자유입력(source='manual') 마스터 행 목록. 각 행의 주문 항목 수(item_count) 포함.

    엑셀 갱신 후 정식 약품으로 승격할 후보를 찾는 데 쓴다(order_reconcile).
    """
    rows = query_all(
        """SELECT dm.id, dm.name, dm.unit_manual,
                  (SELECT COUNT(*) FROM order_items oi WHERE oi.drug_name = dm.name) AS item_count
           FROM drug_master dm WHERE dm.source = 'manual' ORDER BY dm.id"""
    )
    return [
        {"id": r["id"], "name": r["name"], "unit_manual": r["unit_manual"] or "",
         "item_count": r["item_count"]}
        for r in rows
    ]


def excel_master_names() -> set:
    """정식(source='excel') 마스터 약품명 집합. 승격 후보를 엑셀 행으로 한정하는 데 쓴다."""
    rows = query_all("SELECT name FROM drug_master WHERE source = 'excel'")
    return {r["name"] for r in rows}


def promote_manual_drugs(promotions: List[Dict[str, Any]]) -> Dict[str, int]:
    """자유입력(manual) 약품을 정식(excel) 약품으로 승격(병합)한다.

    각 promotion = {manual_id, excel_name}. 정식명이 실제 excel 행으로 존재할 때만 적용한다:
      1) manual 행의 규격(unit_manual)을 정식 행의 unit_manual에 중복 없이 합친다.
      2) 그 manual 이름으로 저장된 order_items.drug_name 을 정식명으로 갱신한다(이름이 다를 때).
      3) manual 행을 삭제한다.
    반환: {"promoted": 승격한 약품 수, "updated_items": 갱신된 주문 항목 수}.
    """
    promoted = 0
    updated_items = 0
    with transaction() as conn:
        for p in promotions or []:
            try:
                mid = int(p.get("manual_id"))
            except (TypeError, ValueError):
                continue
            to = (p.get("excel_name") or "").strip()
            if not to:
                continue
            mrow = conn.execute(
                "SELECT name, unit_manual, source FROM drug_master WHERE id = ?", (mid,)
            ).fetchone()
            if mrow is None or (mrow["source"] or "excel") != "manual":
                continue
            trow = conn.execute(
                "SELECT id, unit, unit_manual FROM drug_master WHERE name = ? AND source = 'excel' ORDER BY id LIMIT 1",
                (to,),
            ).fetchone()
            if trow is None:
                continue
            old = mrow["name"]
            # 1) 규격 병합 (정식 행에 없던 규격만 추가)
            man_units = _split_units(mrow["unit_manual"])
            if man_units:
                existing = set(_split_units(trow["unit"])) | set(_split_units(trow["unit_manual"]))
                add = [u for u in man_units if u not in existing]
                if add:
                    merged = _split_units(trow["unit_manual"]) + add
                    conn.execute(
                        "UPDATE drug_master SET unit_manual = ? WHERE id = ?",
                        (", ".join(merged), trow["id"]),
                    )
            # 2) 주문 항목 약품명 정식명으로 갱신
            if old != to:
                cur = conn.execute(
                    "UPDATE order_items SET drug_name = ? WHERE drug_name = ?", (to, old)
                )
                updated_items += cur.rowcount
            # 3) manual 행 삭제
            conn.execute("DELETE FROM drug_master WHERE id = ?", (mid,))
            promoted += 1
    return {"promoted": promoted, "updated_items": updated_items}



# ----------------------------------------------------------------------------
# 주문지 OCR 저장 (orders / order_items)
# ----------------------------------------------------------------------------
def order_image_dir() -> Path:
    """원본 주문지 이미지를 보관할 디렉터리(없으면 생성). DB와 같은 data/ 아래에 둔다."""
    d = _db_path().parent / "order_images"
    d.mkdir(exist_ok=True)
    return d


def order_exists(order_date: str, order_round: int) -> bool:
    """같은 (날짜, 차수) 주문이 이미 저장돼 있는지 여부."""
    row = query_one(
        "SELECT 1 FROM orders WHERE order_date = ? AND order_round = ?",
        (order_date, order_round),
    )
    return row is not None


def save_order(order_date: str, order_round: int, items: List[Dict[str, Any]],
               image_path: Optional[str], created_at: str) -> int:
    """검수 완료된 주문 1건을 저장하고 order_id 반환.

    같은 (날짜, 차수) 주문이 이미 있으면 기존 주문을 삭제하고 새로 저장한다(덮어쓰기).
    order_items 는 orders FK의 ON DELETE CASCADE로 함께 정리되므로 별도 삭제가 필요 없다.
    호출 전에 덮어쓰기 동의는 라우트(409 → 사용자 확인)에서 받는다.
    """
    with transaction() as conn:
        existing = conn.execute(
            "SELECT id FROM orders WHERE order_date = ? AND order_round = ?",
            (order_date, order_round),
        ).fetchone()
        if existing:
            conn.execute("DELETE FROM orders WHERE id = ?", (existing["id"],))
        cur = conn.execute(
            "INSERT INTO orders (order_date, order_round, image_path, created_at) VALUES (?, ?, ?, ?)",
            (order_date, order_round, image_path, created_at),
        )
        order_id = cur.lastrowid
        rows = [
            (order_id, it.get("drug_name", ""), it.get("package_unit", "") or None,
             it.get("quantity", "") or None, it.get("distributor", "") or None, i)
            for i, it in enumerate(items)
        ]
        if rows:
            conn.executemany(
                """INSERT INTO order_items
                       (order_id, drug_name, package_unit, quantity, distributor, position)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                rows,
            )
        return order_id


def register_free_input_drugs(items: List[Dict[str, Any]], created_at: str) -> Dict[str, Any]:
    """주문 저장 시, 마스터에 없는 자유입력 약품을 마스터에 'manual' 행으로 자동 등록한다.

    자유입력 약품도 사용자가 확인한 신뢰도 높은 약품명이므로, 마스터에 추가해 두면
    이후 OCR 약품명 매칭·직접검색·규격추천에 함께 활용된다(매처는 drug_master만 인덱싱).
    - 이미 같은 이름의 마스터 행이 있으면 건너뛴다(중복 방지, 같은 배치 내 중복도 1건만).
    - 입력 규격(package_unit)이 있으면 unit_manual로 함께 저장한다.
    - 보험코드/제약사는 비워 두고 source='manual', source_file='자유입력'로 표시한다.
    반환: {"added": 추가된 약품 수, "names": [추가된 약품명, ...]}.
    """
    added: List[str] = []
    with transaction() as conn:
        for it in items:
            name = (it.get("drug_name") or "").strip()
            if not name:
                continue
            exists = conn.execute(
                "SELECT 1 FROM drug_master WHERE name = ?", (name,)
            ).fetchone()
            if exists:
                continue
            unit_manual = (it.get("package_unit") or "").strip() or None
            conn.execute(
                """INSERT INTO drug_master
                       (name, insurance_code, maker, maker_norm, unit, unit_manual,
                        imported_at, source_file, source)
                   VALUES (?, NULL, '', NULL, NULL, ?, ?, '자유입력', 'manual')""",
                (name, unit_manual, created_at),
            )
            added.append(name)
    return {"added": len(added), "names": added}


def list_orders() -> List[Dict[str, Any]]:
    """저장된 모든 주문 요약을 최신순으로 반환 (달력 표시용).

    각 주문의 품목 수(item_count)와 이미지 보유 여부(has_image)를 함께 준다.
    """
    rows = query_all(
        """SELECT o.id, o.order_date, o.order_round, o.image_path, o.created_at,
                  COUNT(oi.id) AS item_count
           FROM orders o
           LEFT JOIN order_items oi ON oi.order_id = o.id
           GROUP BY o.id
           ORDER BY o.order_date DESC, o.order_round ASC"""
    )
    return [
        {
            "id": r["id"],
            "order_date": r["order_date"],
            "order_round": r["order_round"],
            "item_count": r["item_count"],
            "has_image": bool(r["image_path"]),
            "created_at": r["created_at"],
        }
        for r in rows
    ]


def get_order(order_id: int) -> Optional[Dict[str, Any]]:
    """주문 1건의 상세(메타 + 품목 목록). 없으면 None."""
    o = query_one(
        "SELECT id, order_date, order_round, image_path, created_at FROM orders WHERE id = ?",
        (order_id,),
    )
    if o is None:
        return None
    items = query_all(
        """SELECT drug_name, package_unit, quantity, distributor
           FROM order_items WHERE order_id = ? ORDER BY position""",
        (order_id,),
    )
    return {
        "id": o["id"],
        "order_date": o["order_date"],
        "order_round": o["order_round"],
        "image_path": o["image_path"],
        "created_at": o["created_at"],
        "items": [
            {
                "drug_name": it["drug_name"],
                "package_unit": it["package_unit"] or "",
                "quantity": it["quantity"] or "",
                "distributor": it["distributor"] or "",
            }
            for it in items
        ],
    }


def get_order_context(drug_names: List[str]) -> Dict[str, Dict[str, Any]]:
    """도매상 선택 단계용 — 주어진 약품명들의 과거 주문 이력과 마지막 도매상을 모은다.

    각 약품명별로:
      - last_distributor: 도매상이 기록된 가장 최근 주문의 도매상 dist_key (없으면 None)
      - history: [{order_date, order_round, distributor, quantity, package_unit}, ...] 최신순
    약품명은 검수 후 확정된 order_items.drug_name 기준으로 정확히 매칭한다.
    """
    out: Dict[str, Dict[str, Any]] = {}
    for raw in drug_names:
        name = (raw or "").strip()
        if not name or name in out:
            continue
        rows = query_all(
            """SELECT o.order_date, o.order_round,
                      oi.distributor, oi.quantity, oi.package_unit
               FROM order_items oi
               JOIN orders o ON o.id = oi.order_id
               WHERE oi.drug_name = ?
               ORDER BY o.order_date DESC, o.order_round DESC""",
            (name,),
        )
        history = [
            {
                "order_date": r["order_date"],
                "order_round": r["order_round"],
                "distributor": r["distributor"] or "",
                "quantity": r["quantity"] or "",
                "package_unit": r["package_unit"] or "",
            }
            for r in rows
        ]
        last_distributor = next((h["distributor"] for h in history if h["distributor"]), None)
        out[name] = {"last_distributor": last_distributor, "history": history}
    return out


def delete_order(order_id: int) -> Optional[str]:
    """주문 1건 삭제(품목은 FK CASCADE).

    반환:
      - 주문이 없으면 None (호출 측 404 처리)
      - 삭제 성공 시 image_path 문자열. 이미지가 없던 주문이면 빈 문자열("").
    호출 측은 반환된 파일명으로 원본 이미지 파일도 함께 정리한다.
    """
    row = query_one("SELECT image_path FROM orders WHERE id = ?", (order_id,))
    if row is None:
        return None
    execute("DELETE FROM orders WHERE id = ?", (order_id,))
    return row["image_path"] or ""


