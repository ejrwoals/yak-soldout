// 약품 마스터 관리 — 엑셀 업로드 → 컬럼 매핑 → 등록

(function () {
    'use strict';

    // =================== 테마 ===================
    let currentTheme = localStorage.getItem('theme') || 'light';
    function applyTheme() {
        document.documentElement.setAttribute('data-theme', currentTheme);
        const icon = document.querySelector('#themeToggle i');
        if (icon) icon.className = currentTheme === 'light' ? 'bi bi-moon' : 'bi bi-sun';
    }
    function toggleTheme() {
        currentTheme = currentTheme === 'light' ? 'dark' : 'light';
        localStorage.setItem('theme', currentTheme);
        applyTheme();
    }

    // =================== 엘리먼트 ===================
    const fileInput = document.getElementById('fileInput');
    const updateMasterBtn = document.getElementById('updateMasterBtn');
    const cancelFileBtn = document.getElementById('cancelFileBtn');
    const fileChosen = document.getElementById('fileChosen');
    const fileNameEl = document.getElementById('fileName');
    const previewBtn = document.getElementById('previewBtn');
    const statusMsg = document.getElementById('statusMsg');
    const mapModal = document.getElementById('mapModal');
    const closeMapModal = document.getElementById('closeMapModal');
    const modalStatus = document.getElementById('modalStatus');
    const nameCol = document.getElementById('nameCol');
    const codeCol = document.getElementById('codeCol');
    const makerCol = document.getElementById('makerCol');
    const totalRowsEl = document.getElementById('totalRows');
    const previewHead = document.getElementById('previewHead');
    const previewBody = document.getElementById('previewBody');
    const importBtn = document.getElementById('importBtn');
    const masterStatus = document.getElementById('masterStatus');
    const rawBody = document.getElementById('rawBody');
    const headerHint = document.getElementById('headerHint');
    // 포장 단위 수집
    const unitCard = document.getElementById('unitCard');
    const unitStats = document.getElementById('unitStats');
    const unitProgress = document.getElementById('unitProgress');
    const unitBarFill = document.getElementById('unitBarFill');
    const unitProgressText = document.getElementById('unitProgressText');
    const collectUnitBtn = document.getElementById('collectUnitBtn');
    const stopUnitBtn = document.getElementById('stopUnitBtn');
    const unitStatusMsg = document.getElementById('unitStatusMsg');

    let selectedFile = null;
    let columns = [];
    let headerRow = 0;       // 현재 선택된 머리글 행 (0-based)

    // 컬럼 자동 추정 키워드
    const HINTS = {
        name: ['제품명', '약품명', '품명', '약품', '제품', '품목명'],
        code: ['보험코드', '보험', '코드', 'code'],
        maker: ['제약사', '제조사', '업체', '회사', '제약', '메이커', 'maker'],
    };
    function guessColumn(cols, keys) {
        for (const k of keys) {
            const hit = cols.find((c) => c && c.toLowerCase().includes(k.toLowerCase()));
            if (hit) return hit;
        }
        return '';
    }

    // =================== 상태 메시지 ===================
    function showStatusOn(el, kind, text, spin) {
        el.hidden = false;
        el.className = `status-msg ${kind}`;
        el.innerHTML = '';
        if (spin) { const s = document.createElement('span'); s.className = 'spinner'; el.appendChild(s); }
        el.appendChild(document.createTextNode(text));
    }
    function showStatus(kind, text, spin) { showStatusOn(statusMsg, kind, text, spin); }
    function hideStatus() { statusMsg.hidden = true; }

    // =================== 모달 ===================
    function openModal() { mapModal.classList.add('show'); }
    function closeModal() { mapModal.classList.remove('show'); modalStatus.hidden = true; }

    // FastAPI 에러 detail 을 사람이 읽을 수 있는 문자열로 (422 는 배열 형태)
    function detailText(data, status) {
        const d = data && data.detail;
        if (Array.isArray(d)) return d.map((e) => e.msg || JSON.stringify(e)).join('; ');
        if (typeof d === 'string') return d;
        return `요청 실패 (${status})`;
    }

    // =================== 파일 선택 ===================
    function setFile(file) {
        if (!file) return;
        const ok = /\.(xlsx|xls)$/i.test(file.name);
        if (!ok) { showStatus('error', '엑셀 파일(.xlsx/.xls)만 올릴 수 있습니다.'); return; }
        selectedFile = file;
        fileNameEl.textContent = file.name;
        updateMasterBtn.hidden = true;   // 업로드 버튼 자리를 미리보기/취소로 대체
        fileChosen.hidden = false;
        previewBtn.disabled = false;
        hideStatus();
        closeModal(); // 새 파일 선택 시 열려있던 매핑 모달 닫기
    }

    // 선택 취소 / 등록 후 초기화 — 미리보기/취소 자리를 다시 업로드 버튼으로
    function resetFile() {
        selectedFile = null;
        fileInput.value = '';
        fileChosen.hidden = true;
        updateMasterBtn.hidden = false;
        previewBtn.disabled = true;
        closeModal();
    }

    // =================== 미리보기 ===================
    // headerRowArg: null=자동추정, 숫자=그 행을 머리글로. isReselect=머리글 재선택(스크롤 생략)
    async function doPreview(headerRowArg = null, isReselect = false) {
        if (!selectedFile) return;
        previewBtn.disabled = true;
        if (!isReselect) showStatus('loading', '엑셀을 읽는 중…', true);
        const form = new FormData();
        form.append('file', selectedFile);
        if (headerRowArg !== null) form.append('header_row', String(headerRowArg));
        try {
            const resp = await fetch('/api/drug-master/preview', { method: 'POST', body: form });
            const data = await resp.json().catch(() => ({}));
            if (!resp.ok) throw new Error(detailText(data, resp.status));
            headerRow = data.used_header_row ?? 0;
            columns = data.columns || [];
            renderRawTable(data.raw_rows || [], headerRow);
            buildPreviewTable(data.sample_rows || []);  // 먼저 표를 만들고
            buildSelectors();                           // 그다음 셀렉터 + highlightMapped (셀이 존재해야 색칠됨)
            totalRowsEl.textContent = `— 머리글 ${headerRow + 1}행 기준, 데이터 ${data.total_rows ?? '?'}행`;
            openModal();   // 재선택 시에도 이미 열려있어 idempotent
            hideStatus();
        } catch (e) {
            showStatus('error', `미리보기 실패: ${e.message}`);
        } finally {
            previewBtn.disabled = !selectedFile;
        }
    }

    // 상단 원본 행 표 — 클릭으로 머리글 행을 선택
    function renderRawTable(rawRows, usedHeaderRow) {
        rawBody.innerHTML = '';
        rawRows.forEach((cells, i) => {
            const tr = document.createElement('tr');
            tr.className = 'raw-row' +
                (i === usedHeaderRow ? ' is-header' : (i < usedHeaderRow ? ' is-skipped' : ''));
            tr.title = i === usedHeaderRow ? '현재 머리글 행' : '이 행을 머리글로 선택';
            const idx = document.createElement('td');
            idx.className = 'raw-idx';
            idx.textContent = i + 1;
            tr.appendChild(idx);
            cells.forEach((c) => {
                const td = document.createElement('td');
                td.textContent = c;
                tr.appendChild(td);
            });
            tr.addEventListener('click', () => {
                if (i === headerRow) return;
                doPreview(i, true);
            });
            rawBody.appendChild(tr);
        });
        if (headerHint) headerHint.textContent = `(현재: ${usedHeaderRow + 1}행)`;
    }

    function fillSelect(sel, withNone, preselect) {
        sel.innerHTML = '';
        if (withNone) {
            const o = document.createElement('option');
            o.value = ''; o.textContent = '(선택 안 함)';
            sel.appendChild(o);
        }
        columns.forEach((c) => {
            const o = document.createElement('option');
            o.value = c; o.textContent = c;
            sel.appendChild(o);
        });
        sel.value = preselect || '';
    }

    function buildSelectors() {
        fillSelect(nameCol, false, guessColumn(columns, HINTS.name) || columns[0]);
        fillSelect(codeCol, true, guessColumn(columns, HINTS.code));
        fillSelect(makerCol, true, guessColumn(columns, HINTS.maker));
        [nameCol, codeCol, makerCol].forEach((s) => s.addEventListener('change', highlightMapped));
        highlightMapped();
    }

    function buildPreviewTable(rows) {
        previewHead.innerHTML = '';
        previewBody.innerHTML = '';
        const trh = document.createElement('tr');
        columns.forEach((c) => {
            const th = document.createElement('th');
            th.textContent = c; th.dataset.col = c;
            trh.appendChild(th);
        });
        previewHead.appendChild(trh);
        rows.forEach((row) => {
            const tr = document.createElement('tr');
            columns.forEach((c) => {
                const td = document.createElement('td');
                td.textContent = row[c] ?? ''; td.dataset.col = c;
                tr.appendChild(td);
            });
            previewBody.appendChild(tr);
        });
    }

    // 매핑된 컬럼을 미리보기 표에서 색으로 표시
    function highlightMapped() {
        const map = {
            [nameCol.value]: 'mapped-name',
            [codeCol.value]: 'mapped-code',
            [makerCol.value]: 'mapped-maker',
        };
        document.querySelectorAll('.preview-table [data-col]').forEach((cell) => {
            cell.classList.remove('mapped-name', 'mapped-code', 'mapped-maker');
            const cls = map[cell.dataset.col];
            if (cls && cell.dataset.col) cell.classList.add(cls);
        });
    }

    // =================== 등록 ===================
    async function doImport() {
        if (!selectedFile) return;
        if (!nameCol.value) { showStatusOn(modalStatus, 'error', '약품명 컬럼을 선택해주세요.'); return; }
        importBtn.disabled = true;
        showStatusOn(modalStatus, 'loading', '등록 중…', true);
        const form = new FormData();
        form.append('file', selectedFile);
        form.append('name_col', nameCol.value);
        form.append('code_col', codeCol.value);
        form.append('maker_col', makerCol.value);
        form.append('header_row', String(headerRow));
        try {
            const resp = await fetch('/api/drug-master/import', { method: 'POST', body: form });
            const data = await resp.json().catch(() => ({}));
            if (!resp.ok) throw new Error(detailText(data, resp.status));
            resetFile();  // 매핑 모달 닫고 갱신 UI 접기
            showStatus('success',
                `갱신 완료 — 신규 ${(data.inserted ?? 0).toLocaleString()}개 추가, ` +
                `${(data.updated ?? 0).toLocaleString()}개 갱신 (총 ${(data.count ?? 0).toLocaleString()}개)`);
            loadStatus();
            checkOrderLinks();  // 마스터에 없던 주문 약품 소급 연결 검토
        } catch (e) {
            showStatusOn(modalStatus, 'error', `등록 실패: ${e.message}`);
        } finally {
            importBtn.disabled = false;
        }
    }

    // =================== 현황 ===================
    async function loadStatus() {
        try {
            const resp = await fetch('/api/drug-master');
            const data = await resp.json();
            if (data.registered) {
                const when = (data.imported_at || '').replace('T', ' ');
                const orphan = data.orphan_order_count || 0;
                const orphanChip = orphan
                    ? ` <span class="orphan-count" title="주문서에만 있고 마스터엔 없는 자유입력 약품 수">주문 자유입력 ${orphan.toLocaleString()}</span>`
                    : '';
                masterStatus.className = 'master-status registered';
                masterStatus.innerHTML =
                    `<span class="ms-line">` +
                        `<i class="bi bi-check-circle-fill" style="color:var(--success)"></i>` +
                        ` 등록됨 <span class="count">${data.count.toLocaleString()}개</span>` +
                        orphanChip +
                    `</span>` +
                    `<span class="meta">${escapeHtml(data.source_filename || '')} · ${escapeHtml(when)}</span>`;
                renderUnitStats(data.unit_stats);
                if (tableCard.hidden) loadRows(); // 최초 1회만 자동 로드 (이후엔 직접 조작 유지)
            } else {
                masterStatus.className = 'master-status';
                masterStatus.innerHTML = `<i class="bi bi-info-circle"></i> 아직 등록된 약품 마스터가 없습니다. 엑셀을 업로드해 등록하세요.`;
                unitCard.hidden = true;
                tableCard.hidden = true;
            }
        } catch (e) {
            masterStatus.innerHTML = `<i class="bi bi-exclamation-triangle"></i> 현황을 불러오지 못했습니다.`;
        }
    }
    function escapeHtml(s) {
        return String(s).replace(/[&<>"']/g, (c) =>
            ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    }

    // =================== 포장 단위(규격) 수집 ===================
    let collecting = false;

    function renderUnitStats(stats) {
        unitCard.hidden = false;
        if (!stats) { unitStats.innerHTML = ''; return; }
        const { total = 0, filled = 0, missing_with_code = 0 } = stats;
        const noCode = Math.max(0, total - filled - missing_with_code);
        unitStats.innerHTML =
            `<span class="us-item"><i class="bi bi-check-circle" style="color:var(--success)"></i> 수집됨 <b>${filled.toLocaleString()}</b></span>` +
            `<span class="us-item"><i class="bi bi-hourglass" style="color:var(--warning,#d97706)"></i> 미수집 <b>${missing_with_code.toLocaleString()}</b></span>` +
            (noCode ? `<span class="us-item us-muted"><i class="bi bi-dash-circle"></i> 코드없음 ${noCode.toLocaleString()}</span>` : '');
        // 수집할 대상이 없으면 버튼 비활성화
        collectUnitBtn.disabled = collecting || missing_with_code === 0;
        if (!collecting && missing_with_code === 0) {
            collectUnitBtn.innerHTML = `<i class="bi bi-check2-all"></i> 모두 수집됨`;
        } else if (!collecting) {
            collectUnitBtn.innerHTML = `<i class="bi bi-download"></i> 빈 규격 수집 시작 (${missing_with_code.toLocaleString()}개)`;
        }
    }

    function setCollecting(on) {
        collecting = on;
        collectUnitBtn.hidden = on;
        stopUnitBtn.hidden = !on;
        stopUnitBtn.disabled = false;
        unitProgress.hidden = !on;
    }

    function updateUnitBar(done, total) {
        const pct = total ? Math.round((done / total) * 100) : 0;
        unitBarFill.style.width = `${pct}%`;
        unitProgressText.textContent = `${done.toLocaleString()} / ${total.toLocaleString()} (${pct}%)`;
    }

    async function startCollectUnits() {
        if (collecting) return;
        setCollecting(true);
        unitStatusMsg.hidden = true;
        updateUnitBar(0, 0);
        unitProgressText.textContent = '기준 도매상 로그인 중…';
        try {
            const resp = await fetch('/api/drug-master/collect-units', { method: 'POST' });
            const data = await resp.json().catch(() => ({}));
            if (!resp.ok) throw new Error(detailText(data, resp.status));
            // 완료 요약 (WS done 메시지와 동일 — 여기서 최종 처리)
            finishCollect(data);
        } catch (e) {
            setCollecting(false);
            showStatusOn(unitStatusMsg, 'error', `수집 실패: ${e.message}`);
        }
    }

    function finishCollect(summary) {
        setCollecting(false);
        const updated = summary.updated || 0;
        const notfound = summary.notfound || 0;
        const failed = summary.failed || 0;
        const stopped = summary.stopped;
        const kind = failed ? 'error' : 'success';
        const head = stopped ? '중단됨' : '수집 완료';
        showStatusOn(unitStatusMsg, kind,
            `${head} — 채움 ${updated}개 · 미발견 ${notfound}개` + (failed ? ` · 실패 ${failed}개` : ''));
        loadStatus(); // 통계 새로고침
    }

    async function stopCollectUnits() {
        stopUnitBtn.disabled = true;
        unitProgressText.textContent = '중단 요청 중… (현재 항목까지 마무리)';
        try { await fetch('/api/drug-master/collect-units/stop', { method: 'POST' }); }
        catch (e) { /* best-effort */ }
    }

    // WebSocket 진행 메시지 처리
    function handleWsMessage(raw) {
        let msg;
        try { msg = JSON.parse(raw); } catch (e) { return; }
        switch (msg.type) {
            case 'unit_collect_started':
                updateUnitBar(0, msg.total || 0);
                unitProgressText.textContent =
                    `${(msg.distributor || '기준 도매상')}에서 ${(msg.total || 0).toLocaleString()}개 검색 시작…`;
                break;
            case 'unit_collect_progress': {
                updateUnitBar(msg.done || 0, msg.total || 0);
                const tag = msg.result === 'ok' ? `→ ${escapeHtml(msg.unit || '')}`
                    : msg.result === 'notfound' ? '→ 규격 없음' : '→ 오류';
                unitProgressText.textContent =
                    `${(msg.done || 0)} / ${(msg.total || 0)} · ${escapeHtml(msg.name || '')} ${tag}`;
                break;
            }
            case 'unit_collect_error':
                showStatusOn(unitStatusMsg, 'error', `수집 오류: ${escapeHtml(msg.message || '')}`);
                break;
            case 'unit_collect_done':
                // HTTP 응답에서도 동일 요약을 처리하므로 여기서는 진행바만 100%로
                updateUnitBar(msg.total || 0, msg.total || 0);
                if (!tableCard.hidden) loadRows(); // 뷰어 열려 있으면 수집 결과 반영
                break;
        }
    }

    // =================== 마스터 DB 뷰어 ===================
    const tableCard = document.getElementById('tableCard');
    const dmSearch = document.getElementById('dmSearch');
    const dmCount = document.getElementById('dmCount');
    const dmBody = document.getElementById('dmBody');
    const dmPrev = document.getElementById('dmPrev');
    const dmNext = document.getElementById('dmNext');
    const dmPageInfo = document.getElementById('dmPageInfo');

    const DM_LIMIT = 50;
    let dmOffset = 0;
    let dmQuery = '';
    let dmTotal = 0;
    let dmSearchTimer = null;

    function unitChips(str, cls) {
        return (str || '').split(',').map((u) => u.trim()).filter(Boolean)
            .map((u) => `<span class="unit-chip ${cls}">${escapeHtml(u)}</span>`).join('');
    }

    function renderRows(rows) {
        dmBody.innerHTML = '';
        if (!rows.length) {
            dmBody.innerHTML = `<tr><td colspan="6" class="mdb-empty">결과가 없습니다.</td></tr>`;
            return;
        }
        rows.forEach((r) => {
            const tr = document.createElement('tr');
            tr.dataset.id = r.id;
            tr.innerHTML =
                `<td class="mdb-id">${r.id}</td>` +
                `<td class="mdb-name" title="${escapeHtml(r.name)}">${escapeHtml(r.name)}</td>` +
                `<td class="mdb-code">${escapeHtml(r.insurance_code)}</td>` +
                `<td class="mdb-maker" title="${escapeHtml(r.maker)}">${escapeHtml(r.maker)}</td>` +
                `<td class="mdb-scraped">${unitChips(r.unit, 'scraped') || '<span class="mdb-dash">—</span>'}</td>` +
                `<td class="mdb-manual-cell">` +
                  `<span class="mdb-manual-chips">${unitChips(r.unit_manual, 'manual')}</span>` +
                  `<span class="mdb-add">` +
                    `<input type="text" class="mdb-add-input" placeholder="추가" maxlength="40">` +
                    `<button class="mdb-add-btn" title="규격 추가"><i class="bi bi-plus-lg"></i></button>` +
                  `</span>` +
                `</td>`;
            dmBody.appendChild(tr);
        });
    }

    async function loadRows() {
        tableCard.hidden = false;
        const params = new URLSearchParams({ offset: dmOffset, limit: DM_LIMIT, q: dmQuery });
        try {
            const resp = await fetch(`/api/drug-master/rows?${params}`);
            const data = await resp.json();
            dmTotal = data.total || 0;
            renderRows(data.rows || []);
            updatePager();
        } catch (e) {
            dmBody.innerHTML = `<tr><td colspan="6" class="mdb-empty">목록을 불러오지 못했습니다.</td></tr>`;
        }
    }

    function updatePager() {
        const from = dmTotal ? dmOffset + 1 : 0;
        const to = Math.min(dmOffset + DM_LIMIT, dmTotal);
        dmCount.textContent = `총 ${dmTotal.toLocaleString()}건`;
        dmPageInfo.textContent = `${from.toLocaleString()}–${to.toLocaleString()} / ${dmTotal.toLocaleString()}`;
        dmPrev.disabled = dmOffset <= 0;
        dmNext.disabled = dmOffset + DM_LIMIT >= dmTotal;
    }

    async function addManualUnit(tr) {
        const input = tr.querySelector('.mdb-add-input');
        const chipsEl = tr.querySelector('.mdb-manual-chips');
        const value = input.value.trim();
        if (!value) return;
        const btn = tr.querySelector('.mdb-add-btn');
        btn.disabled = true;
        try {
            const resp = await fetch('/api/drug-master/manual-unit', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ id: Number(tr.dataset.id), unit: value }),
            });
            const data = await resp.json().catch(() => ({}));
            if (!resp.ok) throw new Error(detailText(data, resp.status));
            chipsEl.innerHTML = unitChips(data.unit_manual, 'manual');
            input.value = '';
            if (!data.added) {
                input.classList.add('dup');
                input.placeholder = '중복';
                setTimeout(() => { input.classList.remove('dup'); input.placeholder = '추가'; }, 1500);
            }
            input.focus();
        } catch (e) {
            input.classList.add('dup');
            setTimeout(() => input.classList.remove('dup'), 1500);
        } finally {
            btn.disabled = false;
        }
    }

    function bindViewer() {
        dmSearch.addEventListener('input', () => {
            clearTimeout(dmSearchTimer);
            dmSearchTimer = setTimeout(() => {
                dmQuery = dmSearch.value.trim();
                dmOffset = 0;
                loadRows();
            }, 300);
        });
        dmPrev.addEventListener('click', () => {
            if (dmOffset <= 0) return;
            dmOffset = Math.max(0, dmOffset - DM_LIMIT);
            loadRows();
        });
        dmNext.addEventListener('click', () => {
            if (dmOffset + DM_LIMIT >= dmTotal) return;
            dmOffset += DM_LIMIT;
            loadRows();
        });
        // 추가 버튼 / Enter (이벤트 위임)
        dmBody.addEventListener('click', (e) => {
            const btn = e.target.closest('.mdb-add-btn');
            if (btn) addManualUnit(btn.closest('tr'));
        });
        dmBody.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && e.target.classList.contains('mdb-add-input')) {
                e.preventDefault();
                addManualUnit(e.target.closest('tr'));
            }
        });
    }

    // =================== 주문서 약품 소급 연결 ===================
    const linkModal = document.getElementById('linkModal');
    function openLinkModal() { linkModal.classList.add('show'); }
    function closeLinkModalFn() { linkModal.classList.remove('show'); }

    // 마스터 업데이트 직후: 마스터에 없던 주문 약품 중 이번에 매칭된 후보가 있으면 확인 모달
    async function checkOrderLinks() {
        try {
            const resp = await fetch('/api/order-ocr/link-candidates');
            const data = await resp.json().catch(() => ({}));
            const cands = (data && data.candidates) || [];
            if (!cands.length) return;
            renderLinkList(cands);
            document.getElementById('linkStatus').hidden = true;
            openLinkModal();
        } catch (e) { /* 부가기능이라 실패해도 무시 */ }
    }

    function renderLinkList(cands) {
        const list = document.getElementById('linkList');
        list.innerHTML = '';
        cands.forEach((c) => {
            const item = document.createElement('div');
            item.className = 'link-item';
            const head = document.createElement('div');
            head.className = 'link-from';
            head.innerHTML = `${escapeHtml(c.orphan_name)} <span class="link-count">${c.item_count}건</span>`;

            const pick = document.createElement('div');
            pick.className = 'link-pick';
            pick.innerHTML = '<i class="bi bi-arrow-return-right"></i>';
            const sel = document.createElement('select');
            sel.className = 'link-select';
            sel.dataset.from = c.orphan_name;
            const none = document.createElement('option');
            none.value = '';
            none.textContent = '— 연결 안 함 —';
            sel.appendChild(none);
            (c.candidates || []).forEach((s) => {
                const o = document.createElement('option');
                o.value = s.name;
                o.textContent = `${s.core || s.name} (${s.score}%)`;
                o.title = s.name;
                sel.appendChild(o);
            });
            // 최상위가 확신(>=90)일 때만 기본 선택; 아니면 '연결 안 함'으로 두어 오매칭을 막는다
            if (c.auto && c.candidates && c.candidates[0]) sel.value = c.candidates[0].name;
            pick.appendChild(sel);

            const text = document.createElement('div');
            text.className = 'link-text';
            text.appendChild(head);
            text.appendChild(pick);
            item.appendChild(text);
            list.appendChild(item);
        });
    }

    async function applyLinks() {
        const list = document.getElementById('linkList');
        const links = [...list.querySelectorAll('.link-select')]
            .filter((sel) => sel.value)
            .map((sel) => ({ orphan_name: sel.dataset.from, master_name: sel.value }));
        const statusEl = document.getElementById('linkStatus');
        if (!links.length) { showStatusOn(statusEl, 'error', '연결할 항목을 선택하세요.'); return; }
        const applyBtn = document.getElementById('linkApplyBtn');
        applyBtn.disabled = true;
        showStatusOn(statusEl, 'loading', '연결 중…', true);
        try {
            const resp = await fetch('/api/order-ocr/link', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ links }),
            });
            const data = await resp.json().catch(() => ({}));
            if (!resp.ok) throw new Error(detailText(data, resp.status));
            closeLinkModalFn();
            showStatus('success', `${data.linked_names}개 약품 · ${data.linked_items}개 주문 항목을 연결했습니다.`);
        } catch (e) {
            showStatusOn(statusEl, 'error', `연결 실패: ${e.message}`);
        } finally {
            applyBtn.disabled = false;
        }
    }

    function bindLinkModal() {
        document.getElementById('closeLinkModal').addEventListener('click', closeLinkModalFn);
        document.getElementById('linkSkipBtn').addEventListener('click', closeLinkModalFn);
        document.getElementById('linkApplyBtn').addEventListener('click', applyLinks);
        linkModal.addEventListener('click', (e) => { if (e.target === linkModal) closeLinkModalFn(); });
    }

    // =================== 주문 자유입력 약품 목록 ===================
    const orphanModal = document.getElementById('orphanModal');

    async function openOrphanModal() {
        const listEl = document.getElementById('orphanList');
        listEl.innerHTML = '<div class="orphan-empty">불러오는 중…</div>';
        orphanModal.classList.add('show');
        try {
            const resp = await fetch('/api/drug-master/orphan-drugs');
            const data = await resp.json().catch(() => ({}));
            const orphans = (data && data.orphans) || [];
            if (!orphans.length) {
                listEl.innerHTML = '<div class="orphan-empty">자유입력 약품이 없습니다.</div>';
                return;
            }
            listEl.innerHTML = '';
            orphans.forEach((o) => {
                const row = document.createElement('div');
                row.className = 'orphan-row';
                const date = (o.last_order_date || '').slice(0, 10);
                row.innerHTML =
                    `<span class="orphan-name"></span>` +
                    `<span class="orphan-meta">` +
                      (date ? `<span class="orphan-date"><i class="bi bi-calendar3"></i> ${escapeHtml(date)}</span>` : '') +
                      `<span class="orphan-rowcount">${o.item_count}건</span>` +
                    `</span>`;
                row.querySelector('.orphan-name').textContent = o.name;
                listEl.appendChild(row);
            });
        } catch (e) {
            listEl.innerHTML = '<div class="orphan-empty">불러오지 못했습니다.</div>';
        }
    }

    function bindOrphanModal() {
        document.getElementById('closeOrphanModal').addEventListener('click', () => orphanModal.classList.remove('show'));
        orphanModal.addEventListener('click', (e) => { if (e.target === orphanModal) orphanModal.classList.remove('show'); });
        // 현황 카드의 '주문 자유입력 N' 칩 클릭 → 목록 모달 (칩은 매번 새로 그려지므로 위임)
        masterStatus.addEventListener('click', (e) => {
            if (e.target.closest('.orphan-count')) openOrphanModal();
        });
    }

    // =================== Keep-alive WebSocket (서버 자동 종료 방지) ===================
    let ws = null, reconnectTimer = null;
    function connectWebSocket() {
        if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return;
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        try { ws = new WebSocket(`${protocol}//${window.location.host}/ws`); }
        catch (e) { scheduleReconnect(); return; }
        ws.onclose = () => scheduleReconnect();
        ws.onerror = () => {};
        ws.onmessage = (e) => handleWsMessage(e.data);
    }
    function scheduleReconnect() {
        if (reconnectTimer) return;
        reconnectTimer = setTimeout(() => { reconnectTimer = null; connectWebSocket(); }, 1500);
    }

    // =================== 이벤트 / 초기화 ===================
    function bind() {
        updateMasterBtn.addEventListener('click', () => fileInput.click());
        cancelFileBtn.addEventListener('click', resetFile);
        fileInput.addEventListener('change', (e) => setFile(e.target.files[0]));
        // 화살표로 감싸지 않으면 click Event 가 doPreview 의 첫 인자로 들어가 header_row 가 깨진다
        previewBtn.addEventListener('click', () => doPreview());
        importBtn.addEventListener('click', () => doImport());
        collectUnitBtn.addEventListener('click', startCollectUnits);
        stopUnitBtn.addEventListener('click', stopCollectUnits);
        bindViewer();
        bindLinkModal();
        bindOrphanModal();
        // 모달 닫기: X 버튼 / 배경 클릭 / ESC
        closeMapModal.addEventListener('click', closeModal);
        mapModal.addEventListener('click', (e) => { if (e.target === mapModal) closeModal(); });
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && mapModal.classList.contains('show')) closeModal();
        });
    }

    document.addEventListener('DOMContentLoaded', () => {
        applyTheme();
        document.getElementById('themeToggle')?.addEventListener('click', toggleTheme);
        bind();
        loadStatus();
        connectWebSocket();
    });
})();
