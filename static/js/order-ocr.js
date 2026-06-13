// 손글씨 주문지 OCR 페이지 로직 (1단계: 업로드 → 추출 → 검수)
// 저장은 다음 단계(Supabase 연동)에서 추가된다.

(function () {
    'use strict';

    // =================== 테마 (home.js 와 동일 동작) ===================
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
    const previewImg = document.getElementById('previewImg');
    const dropPrompt = document.getElementById('dropPrompt');
    const clearBtn = document.getElementById('clearBtn');
    const extractBtn = document.getElementById('extractBtn');
    const statusMsg = document.getElementById('statusMsg');
    const reviewSection = document.getElementById('reviewSection');
    const reviewBody = document.getElementById('reviewBody');
    const addRowBtn = document.getElementById('addRowBtn');
    const orderDate = document.getElementById('orderDate');

    let selectedFile = null;
    let previewUrl = null;
    let masterRegistered = false;  // 약품 마스터 등록 여부 (직접 검색 버튼 노출 판단)

    // =================== 파일 선택 / 미리보기 ===================
    function setFile(file) {
        if (!file) return;
        if (!file.type.startsWith('image/')) {
            showStatus('error', '이미지 파일만 올릴 수 있습니다.');
            return;
        }
        selectedFile = file;
        if (previewUrl) URL.revokeObjectURL(previewUrl);
        previewUrl = URL.createObjectURL(file);
        previewImg.src = previewUrl;
        previewImg.hidden = false;
        dropPrompt.hidden = true;
        clearBtn.hidden = false;
        extractBtn.disabled = false;
        hideStatus();
    }

    function clearFile() {
        selectedFile = null;
        if (previewUrl) { URL.revokeObjectURL(previewUrl); previewUrl = null; }
        previewImg.src = '';
        previewImg.hidden = true;
        dropPrompt.hidden = false;
        clearBtn.hidden = true;
        extractBtn.disabled = true;
        fileInput.value = '';
        hideStatus();
    }

    // =================== 상태 메시지 ===================
    function showStatus(kind, text, withSpinner) {
        statusMsg.hidden = false;
        statusMsg.className = `status-msg ${kind}`;
        statusMsg.innerHTML = '';
        if (withSpinner) {
            const sp = document.createElement('span');
            sp.className = 'spinner';
            statusMsg.appendChild(sp);
        }
        statusMsg.appendChild(document.createTextNode(text));
    }
    function hideStatus() { statusMsg.hidden = true; }

    // =================== 추출 요청 ===================
    async function extract() {
        if (!selectedFile) return;
        extractBtn.disabled = true;
        showStatus('loading', '주문지를 읽는 중입니다… (수 초 걸릴 수 있어요)', true);

        const form = new FormData();
        form.append('image', selectedFile);

        try {
            const resp = await fetch('/api/order-ocr/extract', { method: 'POST', body: form });
            const data = await resp.json().catch(() => ({}));
            if (!resp.ok) {
                throw new Error(data.detail || `요청 실패 (${resp.status})`);
            }
            renderRows(data.items || []);
            const n = data.count || 0;
            showStatus('success', `${n}개 품목을 읽었습니다. 아래에서 확인·수정해주세요.`);
            reviewSection.hidden = false;
            reviewSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
        } catch (e) {
            showStatus('error', `읽기 실패: ${e.message}`);
        } finally {
            extractBtn.disabled = !selectedFile;
        }
    }

    // =================== 검수 테이블 ===================
    function makeRow(item) {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td class="col-idx"></td>
            <td class="col-name"><input type="text" class="f-name" placeholder="약품명"><div class="match-slot"></div></td>
            <td class="col-unit"><input type="text" class="f-unit" placeholder="포장단위"></td>
            <td class="col-qty"><input type="text" class="f-qty" placeholder="수량"></td>
            <td class="col-del"><button class="del-row-btn" title="행 삭제"><i class="bi bi-trash"></i></button></td>
        `;
        const nameInput = tr.querySelector('.f-name');
        nameInput.value = item.drug_name || '';
        tr.querySelector('.f-unit').value = item.package_unit || '';
        tr.querySelector('.f-qty').value = item.quantity || '';
        const slot = tr.querySelector('.match-slot');
        renderMatch(slot, nameInput, item.match, item.drug_name || '');
        // 마스터가 등록돼 있으면 어느 행이든 '직접 검색' 가능
        if (masterRegistered) addSearchUI(tr.querySelector('.col-name'), slot, nameInput);
        tr.querySelector('.del-row-btn').addEventListener('click', () => {
            tr.remove();
            renumber();
        });
        return tr;
    }

    // 후보에 없을 때: 마스터 DB를 직접 검색해서 고르는 UI
    function addSearchUI(cell, slot, nameInput) {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'search-btn';
        btn.innerHTML = `<i class="bi bi-search"></i> 직접 검색`;
        slot.appendChild(btn);

        const panel = document.createElement('div');
        panel.className = 'dm-search';
        panel.hidden = true;
        panel.innerHTML = `
            <input type="text" class="dm-search-input" placeholder="약품명으로 검색…">
            <ul class="dm-search-results"></ul>
        `;
        cell.appendChild(panel);
        const input = panel.querySelector('.dm-search-input');
        const list = panel.querySelector('.dm-search-results');

        function close() { panel.hidden = true; }
        function open() {
            panel.hidden = false;
            input.value = nameInput.value;
            input.focus();
            input.select();
            runSearch();
        }

        const runSearch = debounce(async () => {
            const q = input.value.trim();
            if (!q) { list.innerHTML = '<li class="dm-empty">검색어를 입력하세요</li>'; return; }
            list.innerHTML = '<li class="dm-empty">검색 중…</li>';
            try {
                const resp = await fetch(`/api/drug-master/search?q=${encodeURIComponent(q)}`);
                const data = await resp.json();
                const results = data.results || [];
                if (!results.length) { list.innerHTML = '<li class="dm-empty">결과 없음</li>'; return; }
                list.innerHTML = '';
                results.forEach((r) => {
                    const li = document.createElement('li');
                    li.className = 'dm-result';
                    li.title = r.name;
                    li.innerHTML = `<span class="dm-r-name"></span>` +
                        (r.maker ? `<span class="dm-r-maker"></span>` : '');
                    li.querySelector('.dm-r-name').textContent = r.name;
                    if (r.maker) li.querySelector('.dm-r-maker').textContent = r.maker;
                    li.addEventListener('click', () => {
                        nameInput.value = r.name;   // 검색 선택은 정식 전체명으로
                        close();
                    });
                    list.appendChild(li);
                });
            } catch (e) {
                list.innerHTML = '<li class="dm-empty">검색 실패</li>';
            }
        }, 200);

        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            if (panel.hidden) open(); else close();
        });
        input.addEventListener('input', runSearch);
        input.addEventListener('keydown', (e) => { if (e.key === 'Escape') close(); });
        // 패널 밖 클릭 시 닫기
        document.addEventListener('mousedown', (e) => {
            if (!panel.hidden && !panel.contains(e.target) && e.target !== btn && !btn.contains(e.target)) {
                close();
            }
        });
    }

    function debounce(fn, ms) {
        let t;
        return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
    }

    function matchBadge(kind, text, title) {
        const b = document.createElement('span');
        b.className = `match-badge match-${kind}`;
        b.textContent = text;
        if (title) b.title = title;
        return b;
    }

    // 원본/후보 중 고르는 드롭다운. 적용 값은 마스터의 공식 전체명(c.name).
    function buildApplySelect(nameInput, original, options, preselectName) {
        const sel = document.createElement('select');
        sel.className = 'match-select';
        const keep = document.createElement('option');
        keep.value = original;
        keep.textContent = `원본: ${original}`;
        sel.appendChild(keep);
        options.forEach((c) => {
            const o = document.createElement('option');
            o.value = c.name;                          // 적용은 공식 전체명으로
            o.textContent = `${c.core} (${c.score}%)`; // 표시는 핵심명 + 점수
            o.title = c.name;
            sel.appendChild(o);
        });
        if (preselectName) sel.value = preselectName;
        sel.addEventListener('change', () => { nameInput.value = sel.value; });
        return sel;
    }

    // 약품 마스터 매칭 결과 표시
    function renderMatch(slot, nameInput, match, original) {
        slot.innerHTML = '';
        if (!match || match.status === 'skip') return;  // 마스터 미등록 → 표시 없음

        if (match.status === 'matched') {
            // 공식명을 자동 적용 (드롭다운에서 원본으로 되돌릴 수 있음)
            nameInput.value = match.best.name;
            slot.appendChild(matchBadge('matched', '✓ 마스터 일치 · 공식명 적용', match.best.name));
            slot.appendChild(buildApplySelect(nameInput, original, [match.best], match.best.name));
            return;
        }
        if (match.status === 'none') {
            slot.appendChild(matchBadge('none', '미등록',
                '마스터에서 비슷한 약품을 찾지 못했습니다'));
            return;
        }
        // candidate — 비슷한 약품이 있음. 사용자가 고르면 공식명으로 교체
        slot.appendChild(matchBadge('candidate', '확인 필요',
            '비슷한 약품이 있습니다. 맞는 것을 선택하면 약품명이 바뀝니다'));
        slot.appendChild(buildApplySelect(nameInput, original, match.candidates || [], null));
    }

    function renderRows(items) {
        reviewBody.innerHTML = '';
        if (!items.length) {
            // 빈 결과여도 검수 화면을 보여주고 수동 입력 가능하도록 한 행 제공
            reviewBody.appendChild(makeRow({}));
        } else {
            items.forEach((it) => reviewBody.appendChild(makeRow(it)));
        }
        renumber();
    }

    function renumber() {
        [...reviewBody.querySelectorAll('tr')].forEach((tr, i) => {
            tr.querySelector('.col-idx').textContent = i + 1;
        });
    }

    // =================== 이벤트 바인딩 ===================
    function bindUpload() {
        dropZone.addEventListener('click', () => fileInput.click());
        fileInput.addEventListener('change', (e) => setFile(e.target.files[0]));

        ['dragenter', 'dragover'].forEach((ev) =>
            dropZone.addEventListener(ev, (e) => {
                e.preventDefault();
                dropZone.classList.add('dragover');
            }));
        ['dragleave', 'drop'].forEach((ev) =>
            dropZone.addEventListener(ev, (e) => {
                e.preventDefault();
                dropZone.classList.remove('dragover');
            }));
        dropZone.addEventListener('drop', (e) => {
            const file = e.dataTransfer.files && e.dataTransfer.files[0];
            if (file) setFile(file);
        });

        clearBtn.addEventListener('click', (e) => { e.stopPropagation(); clearFile(); });
        extractBtn.addEventListener('click', extract);
        addRowBtn.addEventListener('click', () => {
            reviewBody.appendChild(makeRow({}));
            renumber();
        });
    }

    // =================== Keep-alive WebSocket ===================
    // 이 앱은 활성 WebSocket이 0개가 되면 "브라우저 닫힘"으로 보고 서버를 자동 종료한다
    // (utils/websocket_manager.py). 홈에서 이 페이지로 넘어오면 홈의 WS가 끊기므로,
    // 여기서도 WS를 유지해 서버가 꺼지지 않게 한다. (home.js 와 동일한 목적)
    let ws = null;
    let reconnectTimer = null;

    function connectWebSocket() {
        if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
            return;
        }
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws`;
        try {
            ws = new WebSocket(wsUrl);
        } catch (e) {
            scheduleReconnect();
            return;
        }
        ws.onclose = () => scheduleReconnect();
        ws.onerror = () => { /* onclose 에서 재연결 처리 */ };
    }

    function scheduleReconnect() {
        if (reconnectTimer) return;
        reconnectTimer = setTimeout(() => {
            reconnectTimer = null;
            connectWebSocket();
        }, 1500);
    }

    // 약품 마스터 등록 여부 확인 (직접 검색 버튼 노출 판단)
    async function loadMasterStatus() {
        try {
            const resp = await fetch('/api/drug-master');
            const data = await resp.json();
            masterRegistered = !!data.registered;
        } catch (e) { /* 무시 */ }
    }

    // =================== 초기화 ===================
    document.addEventListener('DOMContentLoaded', () => {
        applyTheme();
        document.getElementById('themeToggle')?.addEventListener('click', toggleTheme);
        // 주문 날짜 기본값 = 오늘 (로컬 기준)
        if (orderDate) {
            const d = new Date();
            const local = new Date(d.getTime() - d.getTimezoneOffset() * 60000);
            orderDate.value = local.toISOString().slice(0, 10);
        }
        bindUpload();
        loadMasterStatus();
        connectWebSocket(); // 서버 자동 종료 방지 (keep-alive)
    });
})();
