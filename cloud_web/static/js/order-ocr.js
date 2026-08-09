// 주문지 OCR 웹 (스택 1) — 업로드 → OCR → 검수(매칭) → Supabase 저장.
// 기존 로컬 앱 order-ocr.js 의 검수/매칭/줌 인터랙션을 그대로 이식하고,
// Google 로그인 게이트 + 우리 엔드포인트(/api/ocr, /api/preview, /api/save)로 연결한다.

(function () {
    'use strict';

    // =================== 인증 (Supabase Google 로그인) ===================
    let sb = null;
    let session = null;

    async function initAuth() {
        const cfg = await fetch('/api/config').then((r) => r.json()).catch(() => ({}));
        if (!cfg.url || !cfg.anonKey) {
            showLoginStatus('error', '서버 설정(SUPABASE_URL/ANON_KEY)이 비어 있습니다.');
            return;
        }
        sb = supabase.createClient(cfg.url, cfg.anonKey);
        session = (await sb.auth.getSession()).data.session;
        renderGate();
        sb.auth.onAuthStateChange((_e, s) => { session = s; renderGate(); });
    }
    function renderGate() {
        const authed = !!session;
        document.getElementById('loginView').hidden = authed;
        document.getElementById('appView').hidden = !authed;
        document.getElementById('navControls').hidden = !authed;
        if (authed) document.getElementById('userEmail').textContent = session.user?.email || '';
    }
    function showLoginStatus(kind, text) {
        const el = document.getElementById('loginStatus');
        el.hidden = false; el.className = `status-msg ${kind}`; el.textContent = text;
    }
    function authHeader() {
        return session ? { Authorization: 'Bearer ' + session.access_token } : {};
    }

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
    const previewImg = document.getElementById('previewImg');
    const dropPrompt = document.getElementById('dropPrompt');
    const clearBtn = document.getElementById('clearBtn');
    const extractBtn = document.getElementById('extractBtn');
    const statusMsg = document.getElementById('statusMsg');
    const uploadCard = document.getElementById('uploadCard');
    const reviewSection = document.getElementById('reviewSection');
    const reviewBody = document.getElementById('reviewBody');
    const addRowBtn = document.getElementById('addRowBtn');
    const saveBtn = document.getElementById('saveBtn');
    const saveStatus = document.getElementById('saveStatus');
    const orderDate = document.getElementById('orderDate');
    const orderRound = document.getElementById('orderRound');
    const reviewImg = document.getElementById('reviewImg');
    const imageViewport = document.getElementById('imageViewport');
    const zoomLevel = document.getElementById('zoomLevel');
    const imagePane = document.getElementById('imagePane');

    let selectedFile = null;
    let previewUrl = null;

    // =================== 파일 선택 / 미리보기 ===================
    const IMAGE_EXT_RE = /\.(jpe?g|png|webp|heic|heif|gif|bmp)$/i;
    function isImageFile(file) {
        if (file.type && file.type.startsWith('image/')) return true;
        return IMAGE_EXT_RE.test(file.name || '');
    }
    function isHeic(file) {
        const t = (file.type || '').toLowerCase();
        if (t.includes('heic') || t.includes('heif')) return true;
        return /\.(heic|heif)$/i.test(file.name || '');
    }
    async function buildPreviewUrl(file) {
        if (!isHeic(file)) return URL.createObjectURL(file);
        const form = new FormData();
        form.append('image', file);
        const resp = await fetch('/api/preview', { method: 'POST', body: form });
        if (!resp.ok) {
            const d = await resp.json().catch(() => ({}));
            throw new Error(d.detail || `변환 실패 (${resp.status})`);
        }
        return URL.createObjectURL(await resp.blob());
    }
    async function setFile(file) {
        if (!file) return;
        if (!isImageFile(file)) { showStatus('error', '이미지 파일만 올릴 수 있습니다.'); return; }
        selectedFile = file;
        if (previewUrl) { URL.revokeObjectURL(previewUrl); previewUrl = null; }
        previewImg.hidden = true;
        dropPrompt.hidden = true;
        clearBtn.hidden = false;
        extractBtn.disabled = false;
        hideStatus();
        if (isHeic(file)) showStatus('loading', 'HEIC 사진 미리보기를 준비하는 중…', true);
        try {
            const url = await buildPreviewUrl(file);
            if (selectedFile !== file) { URL.revokeObjectURL(url); return; }
            previewUrl = url;
            previewImg.src = previewUrl;
            previewImg.hidden = false;
            if (document.body.classList.contains('review-mode')) reviewImg.src = previewUrl;
            hideStatus();
        } catch (e) {
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
        if (!session) { showStatus('error', '로그인이 필요합니다.'); return; }
        extractBtn.disabled = true;
        showStatus('loading', '주문지를 읽는 중입니다… (수 초 걸릴 수 있어요)', true);
        const form = new FormData();
        form.append('image', selectedFile);
        try {
            const resp = await fetch('/api/ocr', { method: 'POST', body: form, headers: authHeader() });
            const data = await resp.json().catch(() => ({}));
            if (!resp.ok) throw new Error(data.detail || `요청 실패 (${resp.status})`);
            renderRows(data.items || []);
            enterReview(data.count || 0);
        } catch (e) {
            showStatus('error', `읽기 실패: ${e.message}`);
        } finally {
            extractBtn.disabled = !selectedFile;
        }
    }

    // =================== 약품명 자동완성 (DB 검색) ===================
    function debounce(fn, ms) {
        let t;
        return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
    }

    // 모든 행이 공유하는 단일 드롭다운 (position:fixed 로 표 overflow 밖에 표시)
    let acEl = null, acInput = null;
    function ensureAcEl() {
        if (acEl) return;
        acEl = document.createElement('ul');
        // .dm-search: 배경·테두리·그림자(불투명) / .dm-search-results: 리스트·스크롤
        acEl.className = 'dm-search dm-search-results';
        acEl.style.position = 'fixed';
        acEl.style.zIndex = '9999';
        acEl.style.margin = '0';
        acEl.hidden = true;
        document.body.appendChild(acEl);
    }
    function positionAc() {
        if (!acInput || acEl.hidden) return;
        const r = acInput.getBoundingClientRect();
        acEl.style.left = r.left + 'px';
        acEl.style.top = (r.bottom + 4) + 'px';
        acEl.style.width = r.width + 'px';
    }
    function closeAc() {
        if (acEl) acEl.hidden = true;
        acInput = null;
        window.removeEventListener('scroll', positionAc, true);
        window.removeEventListener('resize', positionAc);
    }
    function renderAc(input, tr, slot, results) {
        ensureAcEl();
        if (!results.length) { if (acInput === input) closeAc(); return; }
        acInput = input;
        acEl.innerHTML = '';
        results.forEach((r) => {
            const li = document.createElement('li');
            li.className = 'dm-result';
            li.title = r.name;
            li.innerHTML = `<span class="dm-r-name"></span>` + (r.maker ? `<span class="dm-r-maker"></span>` : '');
            li.querySelector('.dm-r-name').textContent = r.core || r.name;
            if (r.maker) li.querySelector('.dm-r-maker').textContent = r.maker;
            // mousedown + preventDefault: input blur 로 닫히기 전에 선택 처리
            li.addEventListener('mousedown', (e) => {
                e.preventDefault();
                input.value = r.name;               // 적용은 공식 전체명
                markUserConfirmed(slot);
                applyUnitFix(tr, r.known_units, { autoCorrect: true });
                closeAc();
            });
            acEl.appendChild(li);
        });
        acEl.hidden = false;
        positionAc();
        window.addEventListener('scroll', positionAc, true);
        window.addEventListener('resize', positionAc);
    }
    function attachAutocomplete(nameInput, slot) {
        const tr = nameInput.closest('tr');
        const run = debounce(async () => {
            const q = nameInput.value.trim();
            if (!q || document.activeElement !== nameInput) { if (acInput === nameInput) closeAc(); return; }
            try {
                const resp = await fetch('/api/drug-search?q=' + encodeURIComponent(q), { headers: authHeader() });
                const data = await resp.json().catch(() => ({}));
                if (document.activeElement === nameInput) renderAc(nameInput, tr, slot, data.results || []);
            } catch (e) { /* 무시 */ }
        }, 180);
        nameInput.addEventListener('input', run);
        nameInput.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeAc(); });
        nameInput.addEventListener('blur', () => setTimeout(() => { if (acInput === nameInput) closeAc(); }, 150));
    }
    // 드롭다운 밖 클릭 시 닫기
    document.addEventListener('mousedown', (e) => {
        if (acEl && !acEl.hidden && e.target !== acInput && !acEl.contains(e.target)) closeAc();
    });

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
        tr.querySelector('.f-unit').addEventListener('input', () => applyUnitFix(tr, tr._knownUnits, { autoCorrect: false }));
        const slot = tr.querySelector('.match-slot');
        renderMatch(slot, nameInput, item.match, item.drug_name || '');
        attachAutocomplete(nameInput, slot);  // 타이핑 시 DB 자동완성
        tr.querySelector('.del-row-btn').addEventListener('click', () => { tr.remove(); renumber(); });
        return tr;
    }

    function matchBadge(kind, text, title) {
        const b = document.createElement('span');
        b.className = `match-badge match-${kind}`;
        b.textContent = text;
        if (title) b.title = title;
        return b;
    }
    function markUserConfirmed(slot) {
        const badge = matchBadge('confirmed', '✓ 사용자 확인', '사용자가 직접 선택해 확인한 항목입니다');
        const old = slot.querySelector('.match-badge');
        if (old) old.replaceWith(badge);
        else slot.prepend(badge);
    }
    function buildApplySelect(slot, nameInput, original, options, preselectName) {
        const sel = document.createElement('select');
        sel.className = 'match-select';
        const keep = document.createElement('option');
        keep.value = original;
        keep.textContent = `원본: ${original}`;
        sel.appendChild(keep);
        options.forEach((c) => {
            const o = document.createElement('option');
            o.value = c.name;
            o.textContent = `${c.core} (${c.score}%)`;
            o.title = c.name;
            sel.appendChild(o);
        });
        if (preselectName) sel.value = preselectName;
        sel.addEventListener('change', () => {
            nameInput.value = sel.value;
            markUserConfirmed(slot);
            const picked = options.find((c) => c.name === sel.value);
            applyUnitFix(nameInput.closest('tr'), picked ? picked.known_units : [], { autoCorrect: true });
        });
        return sel;
    }

    // =================== 규격(포장단위) 자동 보정 ===================
    function normalizeUnit(s) {
        s = (s || '').trim();
        const m = s.match(/^\s*(\d+(?:\.\d+)?)\s*(.*)$/);
        if (!m) return { count: null, form: s.replace(/\(.*?\)/g, '').trim(), raw: s };
        return { count: parseFloat(m[1]), form: m[2].replace(/\(.*?\)/g, '').trim(), raw: s };
    }
    function applyUnitFix(tr, knownUnits, opts) {
        opts = opts || {};
        const input = tr.querySelector('.f-unit');
        const sug = tr.querySelector('.unit-suggest');
        tr._knownUnits = knownUnits || [];
        input.classList.remove('u-ok', 'u-auto', 'u-warn');
        sug.innerHTML = '';
        const known = (knownUnits || []).filter(Boolean);
        if (!known.length) return;
        const kp = known.map((u) => normalizeUnit(u)).sort((a, b) => (a.count ?? 1e9) - (b.count ?? 1e9));
        const cur = normalizeUnit(input.value);
        let state = null;
        if (cur.count == null) {
            if (opts.autoCorrect && kp.length === 1) { input.value = kp[0].raw; state = 'auto'; }
            else state = 'warn';
        } else {
            const matches = kp.filter((k) => k.count === cur.count);
            if (matches.length) {
                const exact = matches.some((k) => k.raw === input.value.trim());
                if (exact) state = 'ok';
                else if (opts.autoCorrect) { input.value = matches[0].raw; state = 'auto'; }
                else state = 'ok';
            } else {
                state = 'warn';
            }
        }
        if (state) input.classList.add('u-' + state);
        renderUnitChips(sug, tr, kp);
    }
    function renderUnitChips(sug, tr, kp) {
        sug.innerHTML = '';
        const input = tr.querySelector('.f-unit');
        const curRaw = input.value.trim();
        kp.forEach((k) => {
            const chip = document.createElement('button');
            chip.type = 'button';
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

    function renderMatch(slot, nameInput, match, original) {
        slot.innerHTML = '';
        if (!match || match.status === 'skip') return;
        if (match.status === 'matched') {
            nameInput.value = match.best.name;
            slot.appendChild(matchBadge('matched', '✓ 약품명 일치', match.best.name));
            slot.appendChild(buildApplySelect(slot, nameInput, original, [match.best], match.best.name));
            applyUnitFix(nameInput.closest('tr'), match.best.known_units, { autoCorrect: true });
            return;
        }
        if (match.status === 'none') {
            slot.appendChild(matchBadge('none', '미등록', '약품 DB에서 비슷한 약품을 찾지 못했습니다'));
            return;
        }
        slot.appendChild(matchBadge('candidate', '확인 필요', '비슷한 약품이 있습니다. 맞는 것을 선택하면 약품명이 바뀝니다'));
        slot.appendChild(buildApplySelect(slot, nameInput, original, match.candidates || [], null));
    }

    function renderRows(items) {
        reviewBody.innerHTML = '';
        if (!items.length) reviewBody.appendChild(makeRow({}));
        else items.forEach((it) => reviewBody.appendChild(makeRow(it)));
        renumber();
    }
    function renumber() {
        [...reviewBody.querySelectorAll('tr')].forEach((tr, i) => {
            tr.querySelector('.col-idx').textContent = i + 1;
        });
    }

    // =================== 저장 ===================
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

    async function save() {
        if (!session) { showSaveStatus('error', '로그인이 필요합니다.'); return; }
        const items = collectItems();
        if (!items.length) { showSaveStatus('error', '저장할 품목이 없습니다. 약품명을 입력해주세요.'); return; }
        const payload = { order_date: orderDate.value, order_round: orderRound.value, items };
        const form = new FormData();
        form.append('payload', JSON.stringify(payload));
        if (selectedFile) form.append('image', selectedFile);

        saveBtn.disabled = true;
        showSaveStatus('loading', '저장 중입니다…');
        try {
            const resp = await fetch('/api/save', { method: 'POST', body: form, headers: authHeader() });
            const data = await resp.json().catch(() => ({}));
            if (!resp.ok) throw new Error(data.detail || `요청 실패 (${resp.status})`);
            showSaveStatus('success', `저장되었습니다 — ${payload.order_date} ${payload.order_round}차 · ${items.length}개 품목. 로컬 앱에서 크롤링 대기 상태로 넘어갑니다.`);
        } catch (e) {
            showSaveStatus('error', `저장 실패: ${e.message}`);
        } finally {
            saveBtn.disabled = false;
        }
    }

    // =================== 검수 모드 전환 ===================
    function enterReview(count) {
        hideSaveStatus();
        if (previewUrl) reviewImg.src = previewUrl;
        else reviewImg.removeAttribute('src');
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
    function exitReview() {
        document.body.classList.remove('review-mode');
        reviewSection.hidden = true;
        uploadCard.hidden = false;
        imagePane.hidden = false;
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
        if (Z.scale === 1) { Z.tx = 0; Z.ty = 0; }
        applyTransform();
    }
    function bindImageViewer() {
        document.getElementById('zoomInBtn').addEventListener('click', () => zoomAt(1.25, null, null));
        document.getElementById('zoomOutBtn').addEventListener('click', () => zoomAt(1 / 1.25, null, null));
        document.getElementById('zoomResetBtn').addEventListener('click', resetZoom);
        document.getElementById('reuploadBtn').addEventListener('click', () => {
            if (window.confirm('지금까지 입력·검수한 내용이 모두 사라지고 처음부터 다시 시작합니다.\n\n계속할까요?')) {
                exitReview();
            }
        });
        imageViewport.addEventListener('dblclick', resetZoom);
        imageViewport.addEventListener('wheel', (e) => {
            e.preventDefault();
            zoomAt(e.deltaY < 0 ? 1.15 : 1 / 1.15, e.clientX, e.clientY);
        }, { passive: false });
        let dragging = false, lastX = 0, lastY = 0;
        imageViewport.addEventListener('mousedown', (e) => {
            dragging = true; lastX = e.clientX; lastY = e.clientY;
            imageViewport.classList.add('panning'); e.preventDefault();
        });
        window.addEventListener('mousemove', (e) => {
            if (!dragging) return;
            Z.tx += e.clientX - lastX; Z.ty += e.clientY - lastY;
            lastX = e.clientX; lastY = e.clientY;
            applyTransform();
        });
        window.addEventListener('mouseup', () => { dragging = false; imageViewport.classList.remove('panning'); });
        let touchMode = null, tLastX = 0, tLastY = 0, startDist = 0, startScale = 1, pinchX = 0, pinchY = 0;
        const dist = (t) => Math.hypot(t[0].clientX - t[1].clientX, t[0].clientY - t[1].clientY);
        imageViewport.addEventListener('touchstart', (e) => {
            if (e.touches.length === 1) { touchMode = 'pan'; tLastX = e.touches[0].clientX; tLastY = e.touches[0].clientY; }
            else if (e.touches.length === 2) {
                touchMode = 'pinch'; startDist = dist(e.touches); startScale = Z.scale;
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
            else if (e.touches.length === 1) { touchMode = 'pan'; tLastX = e.touches[0].clientX; tLastY = e.touches[0].clientY; }
        });
    }

    // =================== 이벤트 바인딩 ===================
    function bindUpload() {
        dropZone.addEventListener('click', () => fileInput.click());
        fileInput.addEventListener('change', (e) => setFile(e.target.files[0]));
        ['dragenter', 'dragover'].forEach((ev) =>
            dropZone.addEventListener(ev, (e) => { e.preventDefault(); dropZone.classList.add('dragover'); }));
        ['dragleave', 'drop'].forEach((ev) =>
            dropZone.addEventListener(ev, (e) => { e.preventDefault(); dropZone.classList.remove('dragover'); }));
        dropZone.addEventListener('drop', (e) => {
            const file = e.dataTransfer.files && e.dataTransfer.files[0];
            if (file) setFile(file);
        });
        clearBtn.addEventListener('click', (e) => { e.stopPropagation(); clearFile(); });
        extractBtn.addEventListener('click', extract);
        addRowBtn.addEventListener('click', () => { reviewBody.appendChild(makeRow({})); renumber(); });
        saveBtn.addEventListener('click', save);
    }

    // =================== 초기화 ===================
    document.addEventListener('DOMContentLoaded', () => {
        applyTheme();
        document.getElementById('themeToggle')?.addEventListener('click', toggleTheme);
        document.getElementById('googleBtn')?.addEventListener('click', async () => {
            showLoginStatus('loading', 'Google 로그인 창으로 이동 중…');
            const { error } = await sb.auth.signInWithOAuth({ provider: 'google', options: { redirectTo: location.origin } });
            if (error) showLoginStatus('error', error.message);
        });
        document.getElementById('logoutBtn')?.addEventListener('click', async () => { await sb?.auth.signOut(); });
        if (orderDate) {
            const d = new Date();
            const local = new Date(d.getTime() - d.getTimezoneOffset() * 60000);
            orderDate.value = local.toISOString().slice(0, 10);
        }
        bindUpload();
        bindImageViewer();
        initAuth();
    });
})();
