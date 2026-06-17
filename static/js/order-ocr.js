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
    const uploadCard = document.getElementById('uploadCard');
    const reviewSection = document.getElementById('reviewSection');
    const reviewBody = document.getElementById('reviewBody');
    const addRowBtn = document.getElementById('addRowBtn');
    const orderDate = document.getElementById('orderDate');
    // 검수 화면 원본 사진(좌측) 패널
    const reviewImg = document.getElementById('reviewImg');
    const imageViewport = document.getElementById('imageViewport');
    const zoomLevel = document.getElementById('zoomLevel');

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
            enterReview(n);
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
        renderMatch(slot, nameInput, item.match, item.drug_name || '');  // 내부에서 slot 을 비우므로 먼저
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
                        markUserConfirmed(slot);    // 직접 검색으로 고름 → 확인 표시
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

    // 사용자가 드롭다운/직접 검색으로 약품을 직접 골랐을 때 배지를 '사용자 확인'으로 교체.
    // 어디까지 검토·확정했는지 한눈에 보이도록 한다.
    function markUserConfirmed(slot) {
        const badge = matchBadge('confirmed', '✓ 사용자 확인',
            '사용자가 직접 선택해 확인한 항목입니다');
        const old = slot.querySelector('.match-badge');
        if (old) old.replaceWith(badge);
        else slot.prepend(badge);
    }

    // 원본/후보 중 고르는 드롭다운. 적용 값은 마스터의 공식 전체명(c.name).
    function buildApplySelect(slot, nameInput, original, options, preselectName) {
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
        sel.addEventListener('change', () => {
            nameInput.value = sel.value;
            markUserConfirmed(slot);   // 사용자가 직접 고름 → 확인 표시
        });
        return sel;
    }

    // 약품 마스터 매칭 결과 표시
    function renderMatch(slot, nameInput, match, original) {
        slot.innerHTML = '';
        if (!match || match.status === 'skip') return;  // 마스터 미등록 → 표시 없음

        if (match.status === 'matched') {
            // 공식명을 자동 적용 (드롭다운에서 원본으로 되돌릴 수 있음)
            nameInput.value = match.best.name;
            slot.appendChild(matchBadge('matched', '✓ 약품명 일치', match.best.name));
            slot.appendChild(buildApplySelect(slot, nameInput, original, [match.best], match.best.name));
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
        slot.appendChild(buildApplySelect(slot, nameInput, original, match.candidates || [], null));
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

    // =================== 검수 모드 전환 ===================
    // 추출 성공 시: 업로드 카드를 감추고, 좌(원본 사진)·우(검수표) 2단으로 전환
    function enterReview(count) {
        reviewImg.src = previewUrl;
        resetZoom();
        const hint = document.getElementById('reviewHint');
        if (hint) {
            hint.textContent = (count != null)
                ? `${count}개 품목을 읽었습니다. 왼쪽 원본과 대조하며 누락·오기를 직접 고쳐주세요.`
                : '왼쪽 원본과 대조하며 누락·오기를 직접 고쳐주세요.';
        }
        document.body.classList.add('review-mode');
        uploadCard.hidden = true;
        reviewSection.hidden = false;
        window.scrollTo({ top: 0, behavior: 'smooth' });
    }

    // '다른 이미지 올리기' — 업로드 화면으로 복귀
    function exitReview() {
        document.body.classList.remove('review-mode');
        reviewSection.hidden = true;
        uploadCard.hidden = false;
        clearFile();
        window.scrollTo({ top: 0, behavior: 'smooth' });
    }

    // =================== 원본 사진 확대 / 이동 ===================
    const Z = { scale: 1, tx: 0, ty: 0, min: 1, max: 6 };
    function clamp(v, lo, hi) { return Math.min(hi, Math.max(lo, v)); }

    function applyTransform() {
        reviewImg.style.transform = `translate(${Z.tx}px, ${Z.ty}px) scale(${Z.scale})`;
        if (zoomLevel) zoomLevel.textContent = Math.round(Z.scale * 100) + '%';
    }
    function resetZoom() { Z.scale = 1; Z.tx = 0; Z.ty = 0; applyTransform(); }

    // 커서(또는 핀치 중심) 아래 지점을 고정한 채 배율 변경.
    // transform-origin 이 center 이므로 화면 오프셋 = 기준점*scale + translate.
    function zoomAt(factor, clientX, clientY) {
        const rect = imageViewport.getBoundingClientRect();
        const ox = (clientX == null ? 0 : clientX - (rect.left + rect.width / 2));
        const oy = (clientY == null ? 0 : clientY - (rect.top + rect.height / 2));
        const newScale = clamp(Z.scale * factor, Z.min, Z.max);
        const bx = (ox - Z.tx) / Z.scale;
        const by = (oy - Z.ty) / Z.scale;
        Z.tx = ox - bx * newScale;
        Z.ty = oy - by * newScale;
        Z.scale = newScale;
        if (Z.scale === 1) { Z.tx = 0; Z.ty = 0; }  // 원배율이면 항상 중앙 정렬
        applyTransform();
    }

    function bindImageViewer() {
        document.getElementById('zoomInBtn').addEventListener('click', () => zoomAt(1.25, null, null));
        document.getElementById('zoomOutBtn').addEventListener('click', () => zoomAt(1 / 1.25, null, null));
        document.getElementById('zoomResetBtn').addEventListener('click', resetZoom);
        document.getElementById('reuploadBtn').addEventListener('click', exitReview);
        imageViewport.addEventListener('dblclick', resetZoom);

        // 휠로 확대/축소 (커서 위치 기준)
        imageViewport.addEventListener('wheel', (e) => {
            e.preventDefault();
            zoomAt(e.deltaY < 0 ? 1.15 : 1 / 1.15, e.clientX, e.clientY);
        }, { passive: false });

        // 마우스 드래그로 이동
        let dragging = false, lastX = 0, lastY = 0;
        imageViewport.addEventListener('mousedown', (e) => {
            dragging = true; lastX = e.clientX; lastY = e.clientY;
            imageViewport.classList.add('panning');
            e.preventDefault();
        });
        window.addEventListener('mousemove', (e) => {
            if (!dragging) return;
            Z.tx += e.clientX - lastX; Z.ty += e.clientY - lastY;
            lastX = e.clientX; lastY = e.clientY;
            applyTransform();
        });
        window.addEventListener('mouseup', () => {
            dragging = false; imageViewport.classList.remove('panning');
        });

        // 터치(태블릿): 한 손가락 이동 / 두 손가락 핀치 확대
        let touchMode = null, tLastX = 0, tLastY = 0, startDist = 0, startScale = 1, pinchX = 0, pinchY = 0;
        const dist = (t) => Math.hypot(t[0].clientX - t[1].clientX, t[0].clientY - t[1].clientY);
        imageViewport.addEventListener('touchstart', (e) => {
            if (e.touches.length === 1) {
                touchMode = 'pan'; tLastX = e.touches[0].clientX; tLastY = e.touches[0].clientY;
            } else if (e.touches.length === 2) {
                touchMode = 'pinch';
                startDist = dist(e.touches); startScale = Z.scale;
                pinchX = (e.touches[0].clientX + e.touches[1].clientX) / 2;
                pinchY = (e.touches[0].clientY + e.touches[1].clientY) / 2;
            }
        }, { passive: false });
        imageViewport.addEventListener('touchmove', (e) => {
            e.preventDefault();
            if (touchMode === 'pan' && e.touches.length === 1) {
                Z.tx += e.touches[0].clientX - tLastX; Z.ty += e.touches[0].clientY - tLastY;
                tLastX = e.touches[0].clientX; tLastY = e.touches[0].clientY;
                applyTransform();
            } else if (touchMode === 'pinch' && e.touches.length === 2) {
                const target = startScale * (dist(e.touches) / startDist);
                zoomAt(clamp(target, Z.min, Z.max) / Z.scale, pinchX, pinchY);
            }
        }, { passive: false });
        imageViewport.addEventListener('touchend', (e) => {
            if (e.touches.length === 0) touchMode = null;
            else if (e.touches.length === 1) {
                touchMode = 'pan'; tLastX = e.touches[0].clientX; tLastY = e.touches[0].clientY;
            }
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
        bindImageViewer();
        loadMasterStatus();
        connectWebSocket(); // 서버 자동 종료 방지 (keep-alive)
    });
})();
