"""[아카이브] 레거시 주문지 OCR·주문 기록·약품 마스터 라우트 — web_server.py 에서 분리.

이 기능들은 클라우드 "약국 주문 Agent"(cloud_web/) + 로컬 관리자 앱(local_app/)으로
마이그레이션 완료되어 레거시 앱(품절약 서치앱)에서 제거됐다. 참조용 사본이며 임포트되지 않는다.
과거 주문 데이터는 로컬 SQLite(data/)에 그대로 남아 있다 (db.py의 orders/drug_master 함수 참조).
"""

@app.get("/order-ocr", response_class=HTMLResponse)
async def read_order_ocr(request: Request):
    """손글씨 주문지 OCR — 업로드 & 검수 화면 (1단계 로컬 검증)"""
    return templates.TemplateResponse(request, "order_ocr.html")

@app.get("/orders", response_class=HTMLResponse)
async def read_order_history(request: Request):
    """주문 기록 — 달력으로 과거 주문지 내역 조회"""
    return templates.TemplateResponse(request, "order_history.html")

# Pillow 가 HEIC/HEIF 를 열 수 있도록 등록 (미리보기 변환용). 미설치 시 미리보기만 비활성.
try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except Exception:
    pass

# 업로드 이미지 허용 형식
_OCR_ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}
# content_type 이 누락/비표준으로 올 때 파일 확장자로 형식을 보정하기 위한 역매핑
_EXT_TO_MIME = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
    ".webp": "image/webp", ".heic": "image/heic", ".heif": "image/heif",
}
_OCR_MAX_BYTES = 15 * 1024 * 1024  # 15MB

@app.post("/api/order-ocr/extract")
async def order_ocr_extract(image: UploadFile = File(...)):
    """주문지 이미지 → Gemini OCR → [{drug_name, package_unit, quantity}] 추출.

    1단계(로컬 검증): 저장 없이 추출 결과만 반환한다. 사용자는 프론트의 검수
    테이블에서 확인·수정한다.
    """
    if not ocr_service.is_configured():
        raise HTTPException(
            status_code=503,
            detail="GEMINI_API_KEY 가 설정되지 않았습니다. .env 파일을 확인해주세요.")

    mime = (image.content_type or "").lower()
    if mime not in _OCR_ALLOWED_MIME:
        # content_type 누락/비표준 → 파일 확장자로 형식 보정
        ext = os.path.splitext(image.filename or "")[1].lower()
        mime = _EXT_TO_MIME.get(ext, mime)
    if mime not in _OCR_ALLOWED_MIME:
        raise HTTPException(
            status_code=400,
            detail=f"지원하지 않는 이미지 형식입니다: {mime or '알 수 없음'}")

    data = await image.read()
    if not data:
        raise HTTPException(status_code=400, detail="빈 파일입니다.")
    if len(data) > _OCR_MAX_BYTES:
        raise HTTPException(status_code=413, detail="이미지가 너무 큽니다 (최대 15MB).")

    try:
        items = await asyncio.to_thread(ocr_service.extract_order_items, data, mime)
    except ocr_service.OcrConfigError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OCR 처리 실패: {str(e)}")

    # 약품 마스터가 등록돼 있으면 각 항목에 오타 보정 매칭 결과를 덧붙인다 (없으면 status='skip')
    items = await asyncio.to_thread(drug_matcher.attach_matches, items)
    return {"items": items, "count": len(items)}


def _to_preview_jpeg(data: bytes, max_side: int = 1600) -> bytes:
    """업로드 이미지를 브라우저 미리보기용 JPEG 로 변환한다.

    HEIC(아이폰)는 브라우저 <img> 가 렌더링하지 못하므로 서버에서 변환한다.
    EXIF 회전 보정 + 긴 변 기준 축소로 전송 용량도 줄인다. 원본은 그대로 OCR/저장에 쓰인다.
    """
    import io
    from PIL import Image, ImageOps
    im = Image.open(io.BytesIO(data))
    im = ImageOps.exif_transpose(im)          # 촬영 방향(EXIF) 보정
    im = im.convert("RGB")
    if max(im.size) > max_side:
        im.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=82)
    return buf.getvalue()


@app.post("/api/order-ocr/preview")
async def order_ocr_preview(image: UploadFile = File(...)):
    """HEIC 등 브라우저가 그리지 못하는 이미지를 미리보기용 JPEG 로 변환해 반환한다."""
    data = await image.read()
    if not data:
        raise HTTPException(status_code=400, detail="빈 파일입니다.")
    if len(data) > _OCR_MAX_BYTES:
        raise HTTPException(status_code=413, detail="이미지가 너무 큽니다 (최대 15MB).")
    try:
        jpeg = await asyncio.to_thread(_to_preview_jpeg, data)
    except Exception as e:
        raise HTTPException(status_code=415, detail=f"미리보기 변환 실패: {str(e)}")
    return Response(content=jpeg, media_type="image/jpeg")


# mime → 저장 확장자 (원본 이미지 보관용)
_OCR_MIME_EXT = {
    "image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp",
    "image/heic": ".heic", "image/heif": ".heif",
}

@app.post("/api/order-ocr/order-context")
async def order_ocr_context(body: dict):
    """도매상 선택 단계용 컨텍스트 — 드롭다운 도매상 목록 + 약품별 과거 이력/마지막 도매상.

    프론트는 검수 완료 후 약품명 목록을 보내고, 응답으로 각 약품의 기본 도매상
    (마지막 주문 도매상 ?? 기준 도매상)을 채우는 데 필요한 정보를 받는다.
    """
    drug_names = [str(n) for n in (body.get("drug_names") or []) if str(n).strip()]

    # 드롭다운 옵션 — 표시되는 전체 도매상 (기준 도매상이 맨 앞)
    distributors = [
        {"id": dist_id, "name": info["name"], "color": info["default_color"]}
        for dist_id, info in get_visible_registry().items()
    ]
    primary = get_primary_distributor()
    drugs = await asyncio.to_thread(db.get_order_context, drug_names)
    return {"primary": primary, "distributors": distributors, "drugs": drugs}


@app.post("/api/order-ocr/save")
async def order_ocr_save(payload: str = Form(...), image: UploadFile = File(None)):
    """검수 완료된 주문을 로컬 SQLite(orders/order_items)에 저장한다.

    - (날짜, 차수)가 이미 있으면 409(conflict)를 돌려주고, 프론트가 사용자 확인을 받아
      overwrite=true 로 재요청하면 기존 주문을 덮어쓴다.
    - 원본 이미지는 data/order_images 아래에 '(날짜_차수)' 이름으로 함께 보관한다.
    """
    try:
        body = json.loads(payload)
    except (json.JSONDecodeError, TypeError):
        raise HTTPException(status_code=400, detail="잘못된 요청 형식입니다.")

    order_date = (body.get("order_date") or "").strip()
    if not order_date:
        raise HTTPException(status_code=400, detail="주문 날짜가 없습니다.")
    try:
        order_round = int(body.get("order_round"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="주문 차수가 올바르지 않습니다.")
    if order_round not in (1, 2, 3):
        raise HTTPException(status_code=400, detail="주문 차수는 1~3 이어야 합니다.")

    # 약품명이 빈 행은 저장에서 제외
    items = []
    for it in (body.get("items") or []):
        if not isinstance(it, dict):
            continue
        name = (it.get("drug_name") or "").strip()
        if not name:
            continue
        items.append({
            "drug_name": name,
            "package_unit": (it.get("package_unit") or "").strip(),
            "quantity": (it.get("quantity") or "").strip(),
            "distributor": (it.get("distributor") or "").strip() or None,
        })
    if not items:
        raise HTTPException(status_code=400, detail="저장할 품목이 없습니다.")

    # 중복 주문 — 동의 없이는 덮어쓰지 않고 409로 사용자 확인을 요청
    overwrite = bool(body.get("overwrite"))
    exists = await asyncio.to_thread(db.order_exists, order_date, order_round)
    if exists and not overwrite:
        return JSONResponse(
            status_code=409,
            content={"conflict": True,
                     "detail": f"{order_date} {order_round}차 주문이 이미 저장돼 있습니다."})

    # 원본 이미지 저장 — '(날짜_차수)' 이름으로 보관, 덮어쓰기 시 이전 이미지 교체
    image_name = None
    if image is not None:
        raw = await image.read()
        if raw:
            if len(raw) > _OCR_MAX_BYTES:
                raise HTTPException(status_code=413, detail="이미지가 너무 큽니다 (최대 15MB).")
            ext = _OCR_MIME_EXT.get((image.content_type or "").lower(), ".img")
            stem = f"{order_date}_{order_round}차"
            img_dir = db.order_image_dir()
            for old in img_dir.glob(f"{stem}.*"):  # 확장자가 달라진 경우까지 정리
                try:
                    old.unlink()
                except OSError:
                    pass
            image_name = f"{stem}{ext}"
            (img_dir / image_name).write_bytes(raw)

    created_at = datetime.now().isoformat(timespec="seconds")
    try:
        order_id = await asyncio.to_thread(
            db.save_order, order_date, order_round, items, image_name, created_at)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"주문 저장 실패: {str(e)}")

    # 자유입력(마스터에 없는) 약품을 마스터에 자동 등록 → 이후 OCR 매칭에 활용.
    # 보강 단계이므로 실패해도 주문 저장 자체는 성공으로 처리한다.
    registered = 0
    try:
        result = await asyncio.to_thread(db.register_free_input_drugs, items, created_at)
        registered = result.get("added", 0)
    except Exception:
        pass

    return {"saved": True, "order_id": order_id, "count": len(items),
            "order_date": order_date, "order_round": order_round,
            "registered_drugs": registered}


@app.get("/api/orders")
async def order_list():
    """저장된 주문 요약 목록 (달력 표시용)."""
    orders = await asyncio.to_thread(db.list_orders)
    return {"orders": orders}

@app.get("/api/orders/{order_id}")
async def order_detail(order_id: int):
    """주문 1건의 상세(메타 + 품목 목록)."""
    order = await asyncio.to_thread(db.get_order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="주문을 찾을 수 없습니다.")
    return order

@app.get("/api/orders/{order_id}/image")
async def order_image(order_id: int):
    """주문에 저장된 원본 주문지 이미지 파일을 반환."""
    order = await asyncio.to_thread(db.get_order, order_id)
    if order is None or not order.get("image_path"):
        raise HTTPException(status_code=404, detail="이미지가 없습니다.")
    path = db.order_image_dir() / order["image_path"]
    if not path.exists():
        raise HTTPException(status_code=404, detail="이미지 파일이 없습니다.")
    return FileResponse(str(path))

@app.delete("/api/orders/{order_id}")
async def order_delete(order_id: int):
    """주문 1건 삭제 (품목은 CASCADE, 원본 이미지 파일도 함께 정리)."""
    image_path = await asyncio.to_thread(db.delete_order, order_id)
    if image_path is None:
        raise HTTPException(status_code=404, detail="주문을 찾을 수 없습니다.")
    if image_path:  # 빈 문자열이면 이미지가 없던 주문
        f = db.order_image_dir() / image_path
        try:
            f.unlink()
        except OSError:
            pass
    return {"deleted": True}

# ===================== 약품 마스터 (오타 보정용) =====================

_XLSX_EXTS = (".xlsx", ".xls")

@app.get("/drug-master", response_class=HTMLResponse)
async def read_drug_master(request: Request):
    """약품 마스터 관리 — 엑셀 업로드 & 컬럼 매핑 등록 화면"""
    return templates.TemplateResponse(request, "drug_master.html")

@app.get("/api/drug-master")
async def drug_master_status():
    """마스터 등록 현황 (개수/출처/매핑한 컬럼)"""
    return drug_master.status()

@app.get("/api/drug-master/search")
async def drug_master_search(q: str = ""):
    """약품 마스터 직접 검색 — OCR 검수 화면에서 후보에 없는 약을 찾을 때 사용"""
    results = await asyncio.to_thread(drug_matcher.search, q, 20)
    return {"results": results}

@app.post("/api/drug-master/preview")
async def drug_master_preview(
    file: UploadFile = File(...),
    header_row: Optional[int] = Form(None),
):
    """업로드한 엑셀의 컬럼 목록 + 샘플 행 반환 (등록 전 미리보기).

    header_row 미지정 시 머리글 행을 자동 추정한다. 사용자가 머리글 행을 바꾸면
    그 값으로 다시 호출한다.
    """
    if not (file.filename or "").lower().endswith(_XLSX_EXTS):
        raise HTTPException(status_code=400, detail="엑셀 파일(.xlsx/.xls)만 업로드할 수 있습니다.")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="빈 파일입니다.")
    try:
        return await asyncio.to_thread(drug_master.preview, data, file.filename, header_row)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"미리보기 실패: {str(e)}")

@app.post("/api/drug-master/import")
async def drug_master_import(
    file: UploadFile = File(...),
    name_col: str = Form(...),
    code_col: str = Form(""),
    maker_col: str = Form(""),
    header_row: int = Form(0),
):
    """선택한 컬럼 매핑으로 약품 마스터 등록(덮어쓰기)"""
    if not (file.filename or "").lower().endswith(_XLSX_EXTS):
        raise HTTPException(status_code=400, detail="엑셀 파일(.xlsx/.xls)만 업로드할 수 있습니다.")
    if not name_col.strip():
        raise HTTPException(status_code=400, detail="약품명 컬럼을 선택해주세요.")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="빈 파일입니다.")
    try:
        return await asyncio.to_thread(
            drug_master.import_master, data, file.filename,
            name_col.strip(), code_col.strip(), maker_col.strip(), header_row,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"등록 실패: {str(e)}")

@app.post("/api/drug-master/collect-units")
async def drug_master_collect_units():
    """포장단위(규격) 일괄 수집 — unit이 빈 마스터 행을 기준 도매상에 보험코드로 검색해 채운다.

    진행 상황은 WebSocket으로 스트리밍하고, 완료 시 요약을 반환한다.
    """
    if unit_collector.is_running:
        raise HTTPException(status_code=409, detail="이미 포장단위 수집이 진행 중입니다")

    # 기준 도매상 자격 증명 확인 (preview-search와 동일한 가드)
    primary_id = get_primary_distributor()
    try:
        creds = app_state.config.get_credentials(primary_id)
        if not creds.username or not creds.password:
            raise Exception()
    except Exception:
        raise HTTPException(status_code=400, detail="도매상 계정 정보가 설정되지 않았습니다")

    try:
        return await unit_collector.run(app_state, manager)
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"포장단위 수집 실패: {str(e)}")

@app.post("/api/drug-master/collect-units/stop")
async def drug_master_collect_units_stop():
    """진행 중인 포장단위 수집을 중단 요청 (다음 행 경계에서 멈춤)."""
    unit_collector.request_stop()
    return {"message": "중단을 요청했습니다"}

@app.get("/api/drug-master/rows")
async def drug_master_rows(offset: int = 0, limit: int = 50, q: str = "", unit_filter: str = ""):
    """마스터 DB 테이블 뷰어 — 페이지 단위 조회 (약품명/보험코드 검색 + 규격 수집 필터)."""
    limit = max(1, min(int(limit), 200))
    offset = max(0, int(offset))
    return await asyncio.to_thread(db.list_drug_master_rows, offset, limit, q, unit_filter)

@app.post("/api/drug-master/manual-unit")
async def drug_master_manual_unit(data: dict):
    """뷰어에서 사용자가 직접 규격을 추가 (append-only). 수집 규격은 건드리지 않는다."""
    try:
        row_id = int(data.get("id"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="유효한 행 id가 필요합니다")
    unit = (data.get("unit") or "").strip()
    if not unit:
        raise HTTPException(status_code=400, detail="추가할 규격을 입력해주세요")

    result = await asyncio.to_thread(db.add_drug_master_manual_unit, row_id, unit)
    if result is None:
        raise HTTPException(status_code=404, detail="해당 행을 찾을 수 없습니다")
    return result

@app.put("/api/drug-master/rows/{row_id}")
async def drug_master_rename_row(row_id: int, data: dict):
    """자유입력(manual) 마스터 행의 약품명 수정. 같은 이름의 주문 항목도 함께 갱신된다."""
    new_name = (data.get("name") or "").strip()
    if not new_name:
        raise HTTPException(status_code=400, detail="약품명을 입력해주세요")
    result = await asyncio.to_thread(db.rename_drug_master_row, row_id, new_name)
    if result is None:
        raise HTTPException(
            status_code=400,
            detail="수정할 수 없습니다 (자유입력 약품이 아니거나 같은 이름이 이미 있습니다)")
    return result

@app.delete("/api/drug-master/rows/{row_id}")
async def drug_master_delete_row(row_id: int):
    """자유입력(manual) 마스터 행 삭제. 엑셀 임포트분은 삭제할 수 없다."""
    ok = await asyncio.to_thread(db.delete_drug_master_row, row_id)
    if not ok:
        raise HTTPException(
            status_code=400, detail="삭제할 수 없습니다 (자유입력 약품만 삭제 가능합니다)")
    return {"deleted": True}

@app.get("/api/drug-master/promotion-candidates")
async def drug_master_promotion_candidates():
    """엑셀 갱신 후 — 자유입력(manual) 약품 중 정식(excel) 약품으로 승격 가능한 후보 목록."""
    candidates = await asyncio.to_thread(order_reconcile.find_promotion_candidates)
    return {"candidates": candidates}

@app.post("/api/drug-master/promote")
async def drug_master_promote(data: dict):
    """선택된 승격 적용 — 자유입력 약품을 정식 약품으로 병합(주문 항목·규격 이관 후 manual 행 삭제).

    body: {"promotions": [{"manual_id": ..., "excel_name": ...}, ...]}
    """
    promotions = data.get("promotions") or []
    if not isinstance(promotions, list) or not promotions:
        raise HTTPException(status_code=400, detail="승격할 항목이 없습니다")
    return await asyncio.to_thread(order_reconcile.apply_promotions, promotions)

