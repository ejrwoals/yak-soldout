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
    const dropZone = document.getElementById('dropZone');
    const fileInput = document.getElementById('fileInput');
    const dropPrompt = document.getElementById('dropPrompt');
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
        dropPrompt.hidden = true;
        fileChosen.hidden = false;
        previewBtn.disabled = false;
        hideStatus();
        closeModal(); // 새 파일 선택 시 열려있던 매핑 모달 닫기
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
            closeModal();
            showStatus('success', `${data.count}개 약품을 등록했습니다.`);  // 모달 닫힌 뒤 업로드 카드에 표시
            loadStatus();
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
                masterStatus.className = 'master-status registered';
                masterStatus.innerHTML =
                    `<i class="bi bi-check-circle-fill" style="color:var(--success)"></i>` +
                    ` 등록됨 <span class="count">${data.count.toLocaleString()}개</span>` +
                    `<span class="meta"> · ${escapeHtml(data.source_filename||'')} · ${escapeHtml(when)}</span>`;
            } else {
                masterStatus.className = 'master-status';
                masterStatus.innerHTML = `<i class="bi bi-info-circle"></i> 아직 등록된 약품 마스터가 없습니다. 엑셀을 업로드해 등록하세요.`;
            }
        } catch (e) {
            masterStatus.innerHTML = `<i class="bi bi-exclamation-triangle"></i> 현황을 불러오지 못했습니다.`;
        }
    }
    function escapeHtml(s) {
        return String(s).replace(/[&<>"']/g, (c) =>
            ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
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
    }
    function scheduleReconnect() {
        if (reconnectTimer) return;
        reconnectTimer = setTimeout(() => { reconnectTimer = null; connectWebSocket(); }, 1500);
    }

    // =================== 이벤트 / 초기화 ===================
    function bind() {
        dropZone.addEventListener('click', () => fileInput.click());
        fileInput.addEventListener('change', (e) => setFile(e.target.files[0]));
        ['dragenter', 'dragover'].forEach((ev) => dropZone.addEventListener(ev, (e) => {
            e.preventDefault(); dropZone.classList.add('dragover');
        }));
        ['dragleave', 'drop'].forEach((ev) => dropZone.addEventListener(ev, (e) => {
            e.preventDefault(); dropZone.classList.remove('dragover');
        }));
        dropZone.addEventListener('drop', (e) => {
            const f = e.dataTransfer.files && e.dataTransfer.files[0];
            if (f) setFile(f);
        });
        // 화살표로 감싸지 않으면 click Event 가 doPreview 의 첫 인자로 들어가 header_row 가 깨진다
        previewBtn.addEventListener('click', () => doPreview());
        importBtn.addEventListener('click', () => doImport());
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
