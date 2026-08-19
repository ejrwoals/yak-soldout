// 손글씨 주문지 OCR 페이지 로직 (업로드 → 추출 → 검수 → 저장)
// 검수 완료분은 로컬 SQLite(orders/order_items)에 (날짜, 차수) 단위로 저장한다.

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
    const nextBtn = document.getElementById('nextBtn');
    const nextStatus = document.getElementById('nextStatus');
    const saveBtn = document.getElementById('saveBtn');
    const saveStatus = document.getElementById('saveStatus');
    const orderDate = document.getElementById('orderDate');
    const orderRound = document.getElementById('orderRound');
    // 도매상 선택 단계 엘리먼트
    const supplierSection = document.getElementById('supplierSection');
    const supplierBody = document.getElementById('supplierBody');
    const histPanel = document.getElementById('histPanel');
    const backBtn = document.getElementById('backBtn');
    // 검수 화면 원본 사진(좌측) 패널
    const reviewImg = document.getElementById('reviewImg');
    const imageViewport = document.getElementById('imageViewport');
    const zoomLevel = document.getElementById('zoomLevel');
    const imagePane = document.getElementById('imagePane');
    // 입력 방식 토글 + 직접 작성 모드 좌측 이력 패널
    const modeOcrBtn = document.getElementById('modeOcrBtn');
    const modeManualBtn = document.getElementById('modeManualBtn');
    const reviewHistPane = document.getElementById('reviewHistPane');
    const reviewHistPanel = document.getElementById('reviewHistPanel');
    const pageSubtitle = document.getElementById('pageSubtitle');

    let selectedFile = null;
    let previewUrl = null;
    let masterRegistered = false;  // 약품 마스터 등록 여부 (직접 검색 버튼 노출 판단)
    let distNameMap = {};          // dist_key → 한글명 (도매상 이력 표시용)
    let mode = 'ocr';              // 'ocr'(사진) | 'manual'(직접 작성)
    const histCache = {};          // drugName → history[] (직접 작성 모드 이력 캐시)
    const HIST_EMPTY_MSG = '약품명을 입력하거나 검색해서 선택하면 과거에 어느 도매상에서 몇 개를 주문했는지 보여줍니다.';

    // =================== 파일 선택 / 미리보기 ===================
    // 일부 환경/파일은 file.type 이 빈 문자열이거나 비표준으로 와서, 확장자로도 판별한다
    const IMAGE_EXT_RE = /\.(jpe?g|png|webp|heic|heif|gif|bmp)$/i;
    function isImageFile(file) {
        if (file.type && file.type.startsWith('image/')) return true;
        return IMAGE_EXT_RE.test(file.name || '');
    }

    // HEIC/HEIF 판별 — 브라우저 <img> 로는 못 그리므로 미리보기 전에 변환이 필요
    function isHeic(file) {
        const t = (file.type || '').toLowerCase();
        if (t.includes('heic') || t.includes('heif')) return true;
        return /\.(heic|heif)$/i.test(file.name || '');
    }

    // 미리보기용 표시 URL 생성. HEIC 은 서버에서 JPEG 로 변환(원본은 그대로 OCR/저장에 사용).
    async function buildPreviewUrl(file) {
        if (!isHeic(file)) return URL.createObjectURL(file);
        const form = new FormData();
        form.append('image', file);
        const resp = await fetch('/api/order-ocr/preview', { method: 'POST', body: form });
        if (!resp.ok) {
            const d = await resp.json().catch(() => ({}));
            throw new Error(d.detail || `변환 실패 (${resp.status})`);
        }
        const blob = await resp.blob();
        return URL.createObjectURL(blob);
    }

    async function setFile(file) {
        if (!file) return;
        if (!isImageFile(file)) {
            showStatus('error', '이미지 파일만 올릴 수 있습니다.');
            return;
        }
        selectedFile = file;
        if (previewUrl) { URL.revokeObjectURL(previewUrl); previewUrl = null; }
        previewImg.hidden = true;
        dropPrompt.hidden = true;
        clearBtn.hidden = false;
        extractBtn.disabled = false;   // OCR 은 원본으로 진행하므로 미리보기 변환을 기다리지 않아도 됨
        hideStatus();

        // 미리보기 URL 생성 (HEIC 은 변환에 잠시 걸릴 수 있음)
        if (isHeic(file)) showStatus('loading', 'HEIC 사진 미리보기를 준비하는 중…', true);
        try {
            const url = await buildPreviewUrl(file);
            if (selectedFile !== file) { URL.revokeObjectURL(url); return; }  // 그새 다른 파일 선택됨
            previewUrl = url;
            previewImg.src = previewUrl;
            previewImg.hidden = false;
            // 이미 검수(사진 모드)에 들어와 있으면 좌측 원본 사진도 갱신
            if (mode !== 'manual' && document.body.classList.contains('review-mode')) {
                reviewImg.src = previewUrl;
            }
            hideStatus();
        } catch (e) {
            // 변환 실패해도 OCR 은 가능 — 미리보기만 생략
            previewImg.hidden = true;
            showStatus('error', `미리보기를 표시할 수 없습니다 (${e.message}). '글자 읽기'는 그대로 진행할 수 있어요.`);
        }
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
            <td class="col-unit"><input type="text" class="f-unit" placeholder="포장단위"><div class="unit-suggest"></div></td>
            <td class="col-qty"><input type="text" class="f-qty" placeholder="수량"></td>
            <td class="col-del"><button class="del-row-btn" title="행 삭제"><i class="bi bi-trash"></i></button></td>
        `;
        const nameInput = tr.querySelector('.f-name');
        nameInput.value = item.drug_name || '';
        tr.querySelector('.f-unit').value = item.package_unit || '';
        tr.querySelector('.f-qty').value = item.quantity || '';
        // 사용자가 규격을 직접 고치면 자동보정 없이 상태(일치/경고)만 다시 평가
        tr.querySelector('.f-unit').addEventListener('input', () => applyUnitFix(tr, tr._knownUnits, { autoCorrect: false }));
        const slot = tr.querySelector('.match-slot');
        renderMatch(slot, nameInput, item.match, item.drug_name || '');  // 내부에서 slot 을 비우므로 먼저
        // 마스터가 등록돼 있으면 어느 행이든 '직접 검색' 가능
        if (masterRegistered) addSearchUI(tr.querySelector('.col-name'), slot, nameInput);
        tr.querySelector('.del-row-btn').addEventListener('click', () => {
            tr.remove();
            renumber();
        });
        // 직접 작성 모드: 행을 클릭하거나 약품명을 바꾸면 좌측에 과거 이력 표시
        if (mode === 'manual') {
            tr.addEventListener('click', (e) => {
                if (e.target.closest('.del-row-btn')) return;  // 삭제 클릭은 제외
                selectReviewRow(tr);
            });
            nameInput.addEventListener('change', () => selectReviewRow(tr));
        }
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

        // 드롭다운은 position:fixed 로 띄워 표(overflow:auto) 밖으로 나오게 한다.
        // 좌표는 셀 위치에 맞춰 매번 계산하고, 스크롤/리사이즈 시 갱신한다.
        function positionPanel() {
            const r = cell.getBoundingClientRect();
            panel.style.left = `${r.left}px`;
            panel.style.top = `${r.bottom + 4}px`;
            panel.style.width = `${r.width}px`;
        }
        function close() {
            panel.hidden = true;
            window.removeEventListener('scroll', positionPanel, true);
            window.removeEventListener('resize', positionPanel);
        }
        function open() {
            panel.hidden = false;
            positionPanel();
            input.value = nameInput.value;
            input.focus();
            input.select();
            runSearch();
            window.addEventListener('scroll', positionPanel, true);
            window.addEventListener('resize', positionPanel);
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
                        applyUnitFix(nameInput.closest('tr'), r.known_units, { autoCorrect: true });
                        close();
                        if (mode === 'manual') selectReviewRow(nameInput.closest('tr'));
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
            // 선택한 약의 규격으로 보정 (원본으로 되돌리면 규격 데이터 없음)
            const picked = options.find((c) => c.name === sel.value);
            applyUnitFix(nameInput.closest('tr'), picked ? picked.known_units : [], { autoCorrect: true });
            if (mode === 'manual') selectReviewRow(nameInput.closest('tr'));
        });
        return sel;
    }

    // =================== 규격(포장단위) 자동 보정 ===================
    // 규격을 (개수, 제형)으로 정규화. 포장표기 괄호는 무시. 예: "30정(병)" → {count:30, form:"정"}
    function normalizeUnit(s) {
        s = (s || '').trim();
        const m = s.match(/^\s*(\d+(?:\.\d+)?)\s*(.*)$/);
        if (!m) return { count: null, form: s.replace(/\(.*?\)/g, '').trim(), raw: s };
        return { count: parseFloat(m[1]), form: m[2].replace(/\(.*?\)/g, '').trim(), raw: s };
    }

    // 매칭된 약의 알려진 규격(knownUnits)으로 규격칸을 검증/보정한다. (개수 위주 비교)
    // opts.autoCorrect=true 면 확신 케이스에서 값까지 바꾼다(약품 선택/칩 클릭 시).
    function applyUnitFix(tr, knownUnits, opts) {
        opts = opts || {};
        const input = tr.querySelector('.f-unit');
        const sug = tr.querySelector('.unit-suggest');
        tr._knownUnits = knownUnits || [];
        input.classList.remove('u-ok', 'u-auto', 'u-warn');
        sug.innerHTML = '';

        const known = (knownUnits || []).filter(Boolean);
        if (!known.length) return;  // 규격 데이터 없음 → 손대지 않음

        const kp = known.map((u) => normalizeUnit(u))
            .sort((a, b) => (a.count ?? 1e9) - (b.count ?? 1e9));
        const cur = normalizeUnit(input.value);
        let state = null;

        if (cur.count == null) {
            // 빈칸/숫자없음 — 유효 규격이 하나뿐이면 자동 채움, 아니면 선택 필요(경고)
            if (opts.autoCorrect && kp.length === 1) { input.value = kp[0].raw; state = 'auto'; }
            else state = 'warn';
        } else {
            const matches = kp.filter((k) => k.count === cur.count);
            if (matches.length) {
                // 이미 유효 규격과 '정확히' 일치하면 유지 (같은 개수의 다른 포장 선택을 덮지 않음)
                const exact = matches.some((k) => k.raw === input.value.trim());
                if (exact) state = 'ok';
                else if (opts.autoCorrect) { input.value = matches[0].raw; state = 'auto'; }  // 개수만 같음 → 정식 표기로(여러개면 임의 1개)
                else state = 'ok';
            } else {
                state = 'warn';  // 개수가 유효 규격 집합에 없음 → 오인식 의심
            }
        }
        if (state) input.classList.add('u-' + state);
        renderUnitChips(sug, tr, kp);
    }

    // 알려진 규격을 클릭 가능한 칩으로 표시. 현재 값과 개수가 같은 칩은 강조.
    function renderUnitChips(sug, tr, kp) {
        sug.innerHTML = '';
        const input = tr.querySelector('.f-unit');
        const curRaw = input.value.trim();
        kp.forEach((k) => {
            const chip = document.createElement('button');
            chip.type = 'button';
            // 정확히 일치하는 규격만 강조 (같은 개수라도 포장이 다르면 강조 안 함)
            chip.className = 'unit-chip-btn' + (k.raw === curRaw ? ' active' : '');
            chip.textContent = k.raw;
            chip.title = '이 규격으로 설정';
            chip.addEventListener('click', () => {
                input.value = k.raw;
                applyUnitFix(tr, tr._knownUnits, { autoCorrect: true });
            });
            sug.appendChild(chip);
        });
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
            // 매칭된 약의 알려진 규격으로 포장단위 자동 보정
            applyUnitFix(nameInput.closest('tr'), match.best.known_units, { autoCorrect: true });
            return;
        }
        if (match.status === 'none') {
            slot.appendChild(matchBadge('none', '미등록',
                '약품 DB에서 비슷한 약품을 찾지 못했습니다'));
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

    // =================== 저장 ===================
    // 검수표의 각 행을 {drug_name, package_unit, quantity} 로 수집 (약품명이 빈 행은 제외)
    function collectItems() {
        return [...reviewBody.querySelectorAll('tr')].map((tr) => ({
            drug_name: tr.querySelector('.f-name').value.trim(),
            package_unit: tr.querySelector('.f-unit').value.trim(),
            quantity: tr.querySelector('.f-qty').value.trim(),
        })).filter((it) => it.drug_name);
    }

    function showSaveStatus(kind, text) {
        saveStatus.hidden = false;
        saveStatus.className = `status-msg ${kind}`;
        saveStatus.textContent = text;
    }
    function hideSaveStatus() { saveStatus.hidden = true; }

    function showNextStatus(kind, text) {
        nextStatus.hidden = false;
        nextStatus.className = `status-msg ${kind}`;
        nextStatus.textContent = text;
    }
    function hideNextStatus() { nextStatus.hidden = true; }

    // =================== 도매상 선택 단계 ===================
    // 검수 → 다음: 품목을 모아 도매상 선택 컨텍스트(이력/기본 도매상)를 받아 단계 전환
    async function enterSupplierStep() {
        const items = collectItems();
        if (!items.length) {
            showNextStatus('error', '품목이 없습니다. 약품명을 입력해주세요.');
            return;
        }
        nextBtn.disabled = true;
        showNextStatus('loading', '주문 이력을 불러오는 중입니다…');
        try {
            const resp = await fetch('/api/order-ocr/order-context', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ drug_names: items.map((it) => it.drug_name) }),
            });
            const ctx = await resp.json().catch(() => ({}));
            if (!resp.ok) throw new Error(ctx.detail || `요청 실패 (${resp.status})`);
            renderSupplierRows(items, ctx);
            hideNextStatus();
            showSupplierStep();
        } catch (e) {
            showNextStatus('error', `불러오기 실패: ${e.message}`);
        } finally {
            nextBtn.disabled = false;
        }
    }

    // 도매상 선택 테이블 렌더. 기본 도매상 = 마지막 주문 도매상 ?? 기준 도매상.
    function renderSupplierRows(items, ctx) {
        const distributors = ctx.distributors || [];
        const primary = ctx.primary || (distributors[0] && distributors[0].id) || '';
        const drugs = ctx.drugs || {};
        distNameMap = {};
        distributors.forEach((d) => { distNameMap[d.id] = d.name; });

        supplierBody.innerHTML = '';
        items.forEach((it, i) => {
            const info = drugs[it.drug_name] || {};
            const def = info.last_distributor || primary;
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td class="col-idx">${i + 1}</td>
                <td class="col-name s-name"></td>
                <td class="col-unit s-unit"></td>
                <td class="col-qty s-qty"></td>
                <td class="col-dist"><select class="dist-select match-select"></select></td>
            `;
            tr.querySelector('.s-name').textContent = it.drug_name;
            tr.querySelector('.s-unit').textContent = it.package_unit || '';
            tr.querySelector('.s-qty').textContent = it.quantity || '';
            const sel = tr.querySelector('.dist-select');
            distributors.forEach((d) => {
                const o = document.createElement('option');
                o.value = d.id;
                o.textContent = d.name;
                sel.appendChild(o);
            });
            sel.value = def;
            // 행 클릭 시 좌측에 과거 이력 표시 (드롭다운 조작은 제외)
            tr.addEventListener('click', (e) => {
                if (e.target.closest('.dist-select')) return;
                selectSupplierRow(tr, it.drug_name, info.history || []);
            });
            supplierBody.appendChild(tr);
        });
    }

    // 선택 행 강조 + 좌측 이력 패널 렌더
    function selectSupplierRow(tr, drugName, history) {
        [...supplierBody.querySelectorAll('tr')].forEach((r) => r.classList.remove('row-selected'));
        tr.classList.add('row-selected');
        renderHistory(histPanel, drugName, history);
    }

    // =================== 직접 작성 모드: 검수 단계 좌측 이력 패널 ===================
    // 도매상 한글명 맵 확보 (이력 표시에 필요) — 비어 있을 때 1회만 로드
    async function ensureDistNames() {
        if (Object.keys(distNameMap).length) return;
        try {
            const resp = await fetch('/api/order-ocr/order-context', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ drug_names: [] }),
            });
            const ctx = await resp.json().catch(() => ({}));
            (ctx.distributors || []).forEach((d) => { distNameMap[d.id] = d.name; });
        } catch (e) { /* 무시 */ }
    }

    // 검수표의 한 행을 선택 강조하고, 그 약품의 과거 주문 이력을 좌측 패널에 표시
    async function selectReviewRow(tr) {
        [...reviewBody.querySelectorAll('tr')].forEach((r) => r.classList.remove('row-selected'));
        tr.classList.add('row-selected');
        const name = tr.querySelector('.f-name').value.trim();
        if (!name) {
            reviewHistPanel.innerHTML = `<p class="hist-empty">${HIST_EMPTY_MSG}</p>`;
            return;
        }
        if (name in histCache) { renderHistory(reviewHistPanel, name, histCache[name]); return; }
        try {
            const resp = await fetch('/api/order-ocr/order-context', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ drug_names: [name] }),
            });
            const ctx = await resp.json().catch(() => ({}));
            (ctx.distributors || []).forEach((d) => { distNameMap[d.id] = d.name; });
            const hist = (ctx.drugs && ctx.drugs[name] && ctx.drugs[name].history) || [];
            histCache[name] = hist;
            renderHistory(reviewHistPanel, name, hist);
        } catch (e) {
            reviewHistPanel.innerHTML = '<p class="hist-empty">이력을 불러오지 못했습니다.</p>';
        }
    }

    // 직접 작성 모드 시작: 빈 검수표로 바로 진입
    function startManualReview() {
        clearFile();
        renderRows([]);                 // 빈 행 1개
        ensureDistNames();
        reviewHistPanel.innerHTML = `<p class="hist-empty">${HIST_EMPTY_MSG}</p>`;
        enterReview(null);
    }

    // 입력 방식 전환 (사진 ↔ 직접 작성)
    function setMode(next) {
        if (next === mode) return;
        mode = next;
        const isManual = mode === 'manual';
        modeOcrBtn.classList.toggle('active', !isManual);
        modeManualBtn.classList.toggle('active', isManual);
        modeOcrBtn.setAttribute('aria-selected', String(!isManual));
        modeManualBtn.setAttribute('aria-selected', String(isManual));
        if (pageSubtitle) {
            pageSubtitle.textContent = isManual
                ? '약품을 직접 검색해 고르고 규격·수량을 입력해 주문서를 작성합니다'
                : '주문지 사진을 올리면 약품명·포장단위·수량을 자동으로 읽어옵니다';
        }
        if (isManual) startManualReview();
        else exitReview();
    }

    function renderHistory(panel, drugName, history) {
        panel.innerHTML = '';
        const title = document.createElement('div');
        title.className = 'hist-title';
        title.textContent = drugName;
        panel.appendChild(title);

        if (!history.length) {
            const empty = document.createElement('p');
            empty.className = 'hist-empty';
            empty.textContent = '과거 주문 이력이 없습니다.';
            panel.appendChild(empty);
            return;
        }

        // 규격(포장단위)별로 묶어 구분해서 보여준다.
        // history 는 최신순이라, 먼저 등장한 규격이 더 최근에 주문한 규격으로 위에 온다.
        const groups = new Map();   // package_unit → [items]
        history.forEach((h) => {
            const key = (h.package_unit || '').trim() || '(규격 미상)';
            if (!groups.has(key)) groups.set(key, []);
            groups.get(key).push(h);
        });

        const MAX_PER_GROUP = 3;   // 규격별 기본 표시 건수 (나머지는 접어둠)
        groups.forEach((items, unit) => {
            const group = document.createElement('div');
            group.className = 'hist-group';
            const head = document.createElement('div');
            head.className = 'hist-unit-head';
            head.textContent = unit;
            group.appendChild(head);

            const ul = document.createElement('ul');
            ul.className = 'hist-list';
            items.forEach((h, idx) => {
                const li = document.createElement('li');
                // 최근 MAX_PER_GROUP 건만 기본 노출, 나머지는 '더 보기' 전까지 숨김
                li.className = 'hist-item' + (idx >= MAX_PER_GROUP ? ' hist-extra' : '');
                const distName = distNameMap[h.distributor] || h.distributor || '—';
                const qty = h.quantity ? `${h.quantity}` : '';
                li.innerHTML = `
                    <span class="hist-date">${h.order_date} ${h.order_round}차</span>
                    <span class="hist-dist"></span>
                    <span class="hist-qty"></span>
                `;
                li.querySelector('.hist-dist').textContent = distName;
                li.querySelector('.hist-qty').textContent = qty;
                ul.appendChild(li);
            });
            group.appendChild(ul);

            if (items.length > MAX_PER_GROUP) {
                const extra = items.length - MAX_PER_GROUP;
                const more = document.createElement('button');
                more.type = 'button';
                more.className = 'hist-more';
                more.textContent = `+${extra}건 더 보기`;
                more.addEventListener('click', () => {
                    const open = ul.classList.toggle('expanded');
                    more.textContent = open ? '접기' : `+${extra}건 더 보기`;
                });
                group.appendChild(more);
            }
            panel.appendChild(group);
        });
    }

    // 도매상 선택 테이블의 각 행을 {drug_name, package_unit, quantity, distributor} 로 수집
    function collectSupplierItems() {
        return [...supplierBody.querySelectorAll('tr')].map((tr) => ({
            drug_name: tr.querySelector('.s-name').textContent.trim(),
            package_unit: tr.querySelector('.s-unit').textContent.trim(),
            quantity: tr.querySelector('.s-qty').textContent.trim(),
            distributor: tr.querySelector('.dist-select').value,
        })).filter((it) => it.drug_name);
    }

    // 검수 단계로 복귀 (검수 테이블은 보존)
    function backToReview() {
        supplierSection.hidden = true;
        reviewSection.hidden = false;
        hideSaveStatus();
        window.scrollTo({ top: 0, behavior: 'smooth' });
    }

    function showSupplierStep() {
        reviewSection.hidden = true;
        supplierSection.hidden = false;
        hideSaveStatus();
        window.scrollTo({ top: 0, behavior: 'smooth' });
    }

    // =================== 저장 ===================
    // 도매상 선택 완료분을 서버에 저장. (날짜,차수) 중복이면 409 → 사용자 확인 후 덮어쓰기 재요청.
    async function save() {
        const items = collectSupplierItems();
        if (!items.length) {
            showSaveStatus('error', '저장할 품목이 없습니다.');
            return;
        }
        await postSave(items, false);
    }

    async function postSave(items, overwrite) {
        const payload = {
            order_date: orderDate.value,
            order_round: orderRound.value,
            items,
            overwrite,
        };
        const form = new FormData();
        form.append('payload', JSON.stringify(payload));
        if (selectedFile) form.append('image', selectedFile);  // 원본 이미지 동봉

        saveBtn.disabled = true;
        showSaveStatus('loading', '저장 중입니다…');
        try {
            const resp = await fetch('/api/order-ocr/save', { method: 'POST', body: form });
            const data = await resp.json().catch(() => ({}));

            if (resp.status === 409 && data.conflict) {
                // 같은 (날짜,차수) 주문이 이미 있음 — 사용자 동의를 받아 덮어쓰기
                hideSaveStatus();
                const ok = window.confirm(
                    `${data.detail}\n\n기존 주문을 덮어쓰고 이 내용으로 저장할까요?`);
                if (ok) { await postSave(items, true); return; }
                showSaveStatus('error', '저장을 취소했습니다.');
                return;
            }
            if (!resp.ok) throw new Error(data.detail || `요청 실패 (${resp.status})`);

            showSaveStatus('success',
                `저장되었습니다 — ${data.order_date} ${data.order_round}차 · ${data.count}개 품목`);
        } catch (e) {
            showSaveStatus('error', `저장 실패: ${e.message}`);
        } finally {
            saveBtn.disabled = false;
        }
    }

    // =================== 검수 모드 전환 ===================
    // 추출 성공 시: 업로드 카드를 감추고, 좌(원본 사진)·우(검수표) 2단으로 전환
    function enterReview(count) {
        hideSaveStatus();
        const isManual = mode === 'manual';
        // 좌측 패널: 사진 모드 → 원본 사진 / 직접 작성 모드 → 과거 이력
        imagePane.hidden = isManual;
        reviewHistPane.hidden = !isManual;
        if (!isManual) {
            // 미리보기 변환이 아직이면 setFile 완료 시 갱신된다 (HEIC)
            if (previewUrl) reviewImg.src = previewUrl;
            else reviewImg.removeAttribute('src');
            resetZoom();
        }
        const hint = document.getElementById('reviewHint');
        if (hint) {
            hint.textContent = isManual
                ? '약품을 검색해 고르고 규격·수량을 입력하세요. 행을 클릭하면 왼쪽에 과거 주문 이력이 표시됩니다.'
                : (count != null)
                    ? `${count}개 품목을 읽었습니다. 왼쪽 원본과 대조하며 누락·오기를 직접 고쳐주세요.`
                    : '왼쪽 원본과 대조하며 누락·오기를 직접 고쳐주세요.';
        }
        document.body.classList.add('review-mode');
        uploadCard.hidden = true;
        supplierSection.hidden = true;
        reviewSection.hidden = false;
        window.scrollTo({ top: 0, behavior: 'smooth' });
    }

    // '다른 이미지 올리기' — 업로드 화면으로 복귀
    function exitReview() {
        document.body.classList.remove('review-mode');
        reviewSection.hidden = true;
        supplierSection.hidden = true;
        uploadCard.hidden = false;
        imagePane.hidden = false;
        reviewHistPane.hidden = true;
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
        nextBtn.addEventListener('click', enterSupplierStep);
        backBtn.addEventListener('click', backToReview);
        saveBtn.addEventListener('click', save);
        modeOcrBtn.addEventListener('click', () => setMode('ocr'));
        modeManualBtn.addEventListener('click', () => setMode('manual'));
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
