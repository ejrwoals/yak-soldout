// 주문지 OCR 웹 (스택 1) — 업로드 → OCR → 검수(매칭) → Supabase 저장.
// 기존 로컬 앱 order-ocr.js 의 검수/매칭/줌 인터랙션을 그대로 이식하고,
// Google 로그인 게이트 + 우리 엔드포인트(/api/ocr, /api/preview, /api/save)로 연결한다.

(function () {
    'use strict';

    // =================== 인증 + 멤버십 (멀티테넌트) ===================
    let sb = null, session = null, membership = null;

    async function initAuth() {
        // 초대링크(?invite=코드)를 OAuth 왕복 전에 보관 (redirect 후 URL 파라미터가 사라져도 유지)
        const inviteFromUrl = new URL(location.href).searchParams.get('invite');
        if (inviteFromUrl) {
            sessionStorage.setItem('pending_invite', inviteFromUrl);
            const u = new URL(location.href); u.searchParams.delete('invite'); history.replaceState({}, '', u);
        }
        const cfg = await fetch('/api/config').then((r) => r.json()).catch(() => ({}));
        if (!cfg.url || !cfg.anonKey) {
            showLoginStatus('error', '서버 설정(SUPABASE_URL/ANON_KEY)이 비어 있습니다.');
            return;
        }
        sb = supabase.createClient(cfg.url, cfg.anonKey);
        session = (await sb.auth.getSession()).data.session;
        await afterAuth();
        sb.auth.onAuthStateChange(async (_e, s) => { session = s; await afterAuth(); });
    }

    async function afterAuth() {
        if (!session) { membership = null; renderState('login'); return; }
        await refreshMe();
        // 초대링크로 들어왔으면(sessionStorage 보관) 아직 소속이 없을 때 자동 합류
        if (!membership) {
            const code = sessionStorage.getItem('pending_invite');
            if (code) {
                sessionStorage.removeItem('pending_invite');
                await doAccept(code);
            }
        }
    }

    async function refreshMe() {
        try {
            const me = await fetch('/api/me', { headers: authHeader() }).then((r) => r.json());
            membership = me.member ? me : null;
        } catch (e) { membership = null; }
        renderState(membership ? 'app' : 'join');
    }

    // state: 'login' | 'join' | 'app'
    function renderState(state) {
        document.getElementById('loginView').hidden = state !== 'login';
        document.getElementById('joinView').hidden = state !== 'join';
        document.getElementById('appView').hidden = state !== 'app';
        document.getElementById('navControls').hidden = state === 'login';
        if (session) document.getElementById('userEmail').textContent = session.user?.email || '';
        const isAdmin = state === 'app' && membership && membership.role === 'admin';
        document.getElementById('inviteBtn').hidden = !isAdmin;
        // 약국 이름 + 역할 배지
        const badge = document.getElementById('pharmacyBadge');
        if (state === 'app' && membership) {
            document.getElementById('pharmacyName').textContent = membership.pharmacy_name || '';
            const roleEl = document.getElementById('roleBadge');
            roleEl.textContent = membership.role === 'admin' ? '관리자' : '스탭';
            roleEl.className = 'role-badge ' + (membership.role === 'admin' ? 'role-admin' : 'role-staff');
            badge.hidden = false;
        } else {
            badge.hidden = true;
        }
    }

    async function doAccept(code) {
        if (!code || !code.trim()) { showJoinStatus('error', '초대코드를 입력하세요.'); return; }
        showJoinStatus('loading', '합류 처리 중…');
        try {
            const r = await fetch('/api/accept-invite', {
                method: 'POST',
                headers: { ...authHeader(), 'Content-Type': 'application/json' },
                body: JSON.stringify({ code: code.trim() }),
            });
            const d = await r.json().catch(() => ({}));
            if (!r.ok) throw new Error(d.detail || '합류 실패');
            await refreshMe();
        } catch (e) { showJoinStatus('error', e.message); }
    }

    // 관리자: 스탭 초대 링크 발행
    async function createInvite() {
        try {
            const r = await fetch('/api/invites', { method: 'POST', headers: authHeader() });
            const d = await r.json().catch(() => ({}));
            if (!r.ok) throw new Error(d.detail || '초대 발행 실패');
            document.getElementById('inviteLink').value = `${location.origin}/?invite=${encodeURIComponent(d.code)}`;
            document.getElementById('inviteModalStatus').hidden = true;
            document.getElementById('inviteModal').hidden = false;
        } catch (e) { alert(e.message); }
    }

    function showLoginStatus(kind, text) {
        const el = document.getElementById('loginStatus');
        el.hidden = false; el.className = `status-msg ${kind}`; el.textContent = text;
    }
    function showJoinStatus(kind, text) {
        const el = document.getElementById('joinStatus');
        el.hidden = false; el.className = `status-msg ${kind}`; el.textContent = text;
    }
    function showInviteModalStatus(kind, text) {
        const el = document.getElementById('inviteModalStatus');
        el.hidden = false; el.className = `status-msg ${kind}`; el.textContent = text;
    }
    function authHeader() {
        return session ? { Authorization: 'Bearer ' + session.access_token } : {};
    }

    // =================== 주문 기록 뷰 ===================
    function escapeHtml(s) {
        return String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    }
    // view: 'home'(런처) | 'form'(주문지 OCR) | 'history'(주문 기록) | 'drugs'(약 목록 조회)
    let currentView = 'home';
    function showView(v) {
        currentView = v;
        document.getElementById('homeView').hidden = v !== 'home';
        document.getElementById('formView').hidden = v !== 'form';
        document.getElementById('historyView').hidden = v !== 'history';
        document.getElementById('drugsView').hidden = v !== 'drugs';
        document.getElementById('homeBtn').hidden = v === 'home';
        document.body.classList.toggle('history-mode', v === 'history');  // 달력+목록 2단용 와이드 레이아웃
        document.body.classList.toggle('drugs-mode', v === 'drugs');      // 약 목록도 같은 와이드 레이아웃
        document.body.classList.toggle('home-mode', v === 'home');        // 홈 카드 3개 한 줄용 와이드 레이아웃
        if (v === 'history') loadHistory();
        if (v === 'drugs') loadDrugs(true);
        window.scrollTo({ top: 0 });
    }
    let histOrders = [];                       // 마지막으로 불러온 주문 목록 (달력 렌더용)
    let calCursor = null;                      // 달력이 보여주는 달 {y, m(0-11)}
    async function loadHistory() {
        const list = document.getElementById('historyList');
        list.innerHTML = '<div class="hist-empty">불러오는 중…</div>';
        try {
            const r = await fetch('/api/orders', { headers: authHeader() });
            const d = await r.json().catch(() => ({}));
            if (!r.ok) throw new Error(d.detail || '조회 실패');
            histOrders = d.orders || [];
            renderCalendar();
            if (!histOrders.length) { list.innerHTML = '<div class="hist-empty">저장된 주문이 없습니다.</div>'; return; }
            list.innerHTML = '';
            histOrders.forEach((o) => list.appendChild(histCard(o)));
        } catch (e) { list.innerHTML = `<div class="hist-empty">조회 실패: ${escapeHtml(e.message)}</div>`; }
    }
    function histCard(o) {
        const el = document.createElement('div'); el.className = 'hist-order';
        el.dataset.oid = o.id;
        const items = o.order_items || [];
        const rows = items.map((it) => `<tr><td>${escapeHtml(it.drug_name)}</td><td>${escapeHtml(it.package_unit || '')}</td><td style="text-align:center">${escapeHtml(it.quantity || '')}</td></tr>`).join('');
        el.innerHTML = `<div class="hist-head"><span class="date">${escapeHtml(o.order_date)} ${escapeHtml(String(o.order_round))}차</span><span class="cnt">${items.length}품목</span><span class="hist-badge ${escapeHtml(o.status)}">${o.status === 'ordered' ? '주문완료' : '크롤링 대기'}</span></div>
          <div class="hist-items"><table><thead><tr><th>약품명</th><th>포장단위</th><th style="text-align:center">수량</th></tr></thead><tbody>${rows}</tbody></table>
          <div class="hist-actions">
            ${o.has_image ? '<button class="hist-btn img-btn"><i class="bi bi-image"></i> 원본 이미지</button>' : ''}
            <button class="hist-btn danger del-btn"><i class="bi bi-trash"></i> 삭제</button>
          </div></div>`;
        el.querySelector('.hist-head').addEventListener('click', () => el.classList.toggle('open'));
        el.querySelector('.img-btn')?.addEventListener('click', () => viewOrderImage(o));
        el.querySelector('.del-btn').addEventListener('click', () => deleteOrder(o));
        return el;
    }

    // ---- 달력 보기 ----
    function ymd(d) { return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`; }
    function renderCalendar() {
        const cal = document.getElementById('histCal');
        cal.hidden = false;
        if (!calCursor) {
            const latest = histOrders.length ? new Date(histOrders[0].order_date + 'T00:00:00') : new Date();
            calCursor = { y: latest.getFullYear(), m: latest.getMonth() };
        }
        const { y, m } = calCursor;
        document.getElementById('calTitle').textContent = `${y}년 ${m + 1}월`;
        const byDate = {};
        histOrders.forEach((o) => { (byDate[o.order_date] = byDate[o.order_date] || []).push(o); });
        const grid = document.getElementById('calGrid');
        grid.innerHTML = ['일', '월', '화', '수', '목', '금', '토'].map((d) => `<div class="cal-dow">${d}</div>`).join('');
        const first = new Date(y, m, 1);
        const start = new Date(y, m, 1 - first.getDay());   // 그 주의 일요일부터
        const todayStr = ymd(new Date());
        for (let i = 0; i < 42; i++) {
            const d = new Date(start.getFullYear(), start.getMonth(), start.getDate() + i);
            if (i === 35 && d.getMonth() !== m) break;       // 6번째 줄이 통째로 다음 달이면 생략
            const dateStr = ymd(d);
            const cell = document.createElement('div');
            cell.className = 'cal-day' + (d.getMonth() !== m ? ' out' : '') + (dateStr === todayStr ? ' today' : '');
            cell.innerHTML = `<div>${d.getDate()}</div>`;
            (byDate[dateStr] || []).slice().sort((a, b) => a.order_round - b.order_round).forEach((o) => {
                const chip = document.createElement('button');
                chip.className = `cal-chip ${o.status === 'ordered' ? 'ordered' : 'pending'}`;
                chip.textContent = `${o.order_round}차 · ${(o.order_items || []).length}품목`;
                chip.title = `${o.order_date} ${o.order_round}차 — 클릭하면 오른쪽 목록에서 펼쳐집니다`;
                chip.addEventListener('click', () => {
                    const card = document.querySelector(`.hist-order[data-oid="${o.id}"]`);
                    if (!card) return;
                    // 다른 카드는 접고 해당 카드만 연 뒤, 오른쪽 패널 안에서만 스크롤 (페이지는 그대로)
                    document.querySelectorAll('.hist-order.open').forEach((c) => { if (c !== card) c.classList.remove('open'); });
                    card.classList.add('open');
                    const pane = document.getElementById('histListPane');
                    pane.scrollTo({ top: card.offsetTop, behavior: 'smooth' });
                });
                cell.appendChild(chip);
            });
            grid.appendChild(cell);
        }
    }
    function shiftCalendar(delta) {
        if (!calCursor) return;
        const d = new Date(calCursor.y, calCursor.m + delta, 1);
        calCursor = { y: d.getFullYear(), m: d.getMonth() };
        renderCalendar();
    }

    // ---- 원본 이미지 / 삭제 ----
    let histImgUrl = null;
    async function viewOrderImage(o) {
        try {
            const r = await fetch(`/api/orders/${o.id}/image`, { headers: authHeader() });
            if (!r.ok) { const d = await r.json().catch(() => ({})); throw new Error(d.detail || '불러오기 실패'); }
            if (histImgUrl) URL.revokeObjectURL(histImgUrl);
            histImgUrl = URL.createObjectURL(await r.blob());
            document.getElementById('histImg').src = histImgUrl;
            document.getElementById('histImgTitle').textContent = `원본 주문지 — ${o.order_date} ${o.order_round}차`;
            histZoom?.reset();
            document.getElementById('imageModal').hidden = false;
        } catch (e) { alert('이미지를 불러올 수 없습니다: ' + e.message); }
    }
    async function deleteOrder(o) {
        if (!confirm(`${o.order_date} ${o.order_round}차 주문을 삭제할까요?\n품목과 원본 이미지도 함께 삭제되며 되돌릴 수 없습니다.`)) return;
        try {
            const r = await fetch(`/api/orders/${o.id}`, { method: 'DELETE', headers: authHeader() });
            const d = await r.json().catch(() => ({}));
            if (!r.ok) throw new Error(d.detail || '삭제 실패');
            loadHistory();
        } catch (e) { alert('삭제 실패: ' + e.message); }
    }

    // =================== 약 목록 조회 (읽기 전용) ===================
    const DRUG_PAGE = 50;
    let drugQuery = '', drugFilter = '', drugOffset = 0, drugLoading = false;

    function showDrugStatus(text) {
        const el = document.getElementById('drugStatus');
        if (text) { el.hidden = false; el.textContent = text; }
        else el.hidden = true;
    }
    function fmtAvg(v) {
        if (v == null) return '';
        return Number(v).toLocaleString(undefined, { maximumFractionDigits: 1 });
    }
    // 규격 칩 — 천 단위 콤마('1,000정')는 구분자가 아니다 (기존 저장 데이터 호환)
    function unitChips(str, cls) {
        return String(str || '').replace(/(\d),(?=\d{3}(?!\d))/g, '$1')
            .split(',').map((s) => s.trim()).filter(Boolean)
            .map((u) => `<span class="unit-chip ${cls}">${escapeHtml(u)}</span>`).join('');
    }
    async function loadDrugs(reset) {
        if (drugLoading) return;
        drugLoading = true;
        const rowsEl = document.getElementById('drugRows');
        const moreBtn = document.getElementById('drugMoreBtn');
        if (reset) { drugOffset = 0; rowsEl.innerHTML = ''; moreBtn.hidden = true; showDrugStatus('불러오는 중…'); }
        try {
            const p = new URLSearchParams({ q: drugQuery, filter: drugFilter, limit: DRUG_PAGE, offset: drugOffset });
            const r = await fetch('/api/drug-master?' + p, { headers: authHeader() });
            const d = await r.json().catch(() => ({}));
            if (!r.ok) throw new Error(d.detail || `조회 실패 (${r.status})`);
            (d.rows || []).forEach((row, i) => {
                const tr = document.createElement('tr');
                const units = unitChips(row.unit, 'scraped') + unitChips(row.unit_manual, 'manual');
                tr.innerHTML = `<td class="col-idx">${drugOffset + i + 1}</td>
                    <td>${escapeHtml(row.name)}${row.source === 'manual' ? '<span class="manual-badge">자유입력</span>' : ''}</td>
                    <td class="cell-code">${escapeHtml(row.insurance_code || '') || '—'}</td>
                    <td>${escapeHtml(row.maker || '')}</td>
                    <td class="cell-avg">${row.monthly_avg != null ? fmtAvg(row.monthly_avg) : '<span style="color:var(--text-muted)">—</span>'}</td>
                    <td>${units || '<span style="color:var(--text-muted)">—</span>'}</td>`;
                tr.addEventListener('click', () => openUsageModal(row));
                rowsEl.appendChild(tr);
            });
            drugOffset += (d.rows || []).length;
            document.getElementById('drugCount').textContent = `총 ${d.total ?? 0}개`;
            moreBtn.hidden = drugOffset >= (d.total || 0);
            showDrugStatus(drugOffset === 0 ? (drugQuery ? '검색 결과가 없습니다.' : '등록된 약품이 없습니다.') : null);
        } catch (e) {
            showDrugStatus(`조회 실패: ${e.message}`);
        } finally {
            drugLoading = false;
        }
    }

    // ---- 약품 월별 사용량 이력 모달 (행 클릭 → line chart) ----
    function openUsageModal(row) {
        document.getElementById('usageName').textContent = row.name;
        document.getElementById('usageMeta').textContent = [
            row.insurance_code ? `보험코드 ${row.insurance_code}` : null,
            row.maker || null,
        ].filter(Boolean).join(' · ');
        document.getElementById('usageStat').innerHTML = '';
        document.getElementById('usageBody').innerHTML = '<div class="usage-empty">불러오는 중…</div>';
        const modal = document.getElementById('usageModal');
        modal.hidden = false;
        const onKey = (e) => { if (e.key === 'Escape') close(); };
        const close = () => {
            modal.hidden = true;
            document.getElementById('closeUsageBtn').onclick = modal.onclick = null;
            document.removeEventListener('keydown', onKey);
        };
        document.getElementById('closeUsageBtn').onclick = close;
        modal.onclick = (e) => { if (e.target === modal) close(); };
        document.addEventListener('keydown', onKey);
        if (!row.insurance_code) {
            document.getElementById('usageBody').innerHTML =
                '<div class="usage-empty">보험코드가 없는 약품이라<br>사용량 데이터를 연결할 수 없습니다.</div>';
            return;
        }
        fetch('/api/drug-usage-history?code=' + encodeURIComponent(row.insurance_code), { headers: authHeader() })
            .then(async (r) => {
                const d = await r.json().catch(() => ({}));
                if (!r.ok) throw new Error(d.detail || `조회 실패 (${r.status})`);
                renderUsageHistory(d);
            })
            .catch((e) => {
                document.getElementById('usageBody').innerHTML =
                    `<div class="usage-empty">조회 실패: ${escapeHtml(e.message)}</div>`;
            });
    }
    function renderUsageHistory(d) {
        const months = d.months || [], st = d.stats;
        document.getElementById('usageStat').innerHTML = st
            ? `<span class="usage-stat-label">직전 12개월 평균 사용량</span>
               <div class="usage-stat-value">${fmtAvg(st.monthly_avg)}</div>
               <div class="usage-stat-caption">${escapeHtml(st.window_start)} ~ ${escapeHtml(st.window_end)} · 완전월 ${st.months_used}개월 기준</div>`
            : `<span class="usage-stat-label">최근 12개 완전월 내 사용 기록이 없어 월평균이 계산되지 않았어요.</span>`;
        const body = document.getElementById('usageBody');
        if (!months.length) {
            body.innerHTML = '<div class="usage-empty">저장된 월별 사용량 데이터가 없습니다.<br>로컬 앱의 약품 DB 갱신에서 사용량 엑셀을 올리면 표시돼요.</div>';
            return;
        }
        body.innerHTML = '';
        body.appendChild(usageChart(months, st ? Number(st.monthly_avg) : null));
        // 표로 보기 — 연도 × 1~12월 피벗 (툴팁 없이도 모든 값에 접근 가능하게)
        const byYear = {};
        months.forEach((m) => {
            const [y, mo] = m.ym.split('-');
            (byYear[y] = byYear[y] || {})[Number(mo)] = m.qty;
        });
        const det = document.createElement('details');
        det.innerHTML = `<summary class="usage-toggle">표로 보기</summary>
            <div class="usage-table"><table>
            <thead><tr><th>연도</th>${Array.from({ length: 12 }, (_, i) => `<th>${i + 1}월</th>`).join('')}</tr></thead>
            <tbody>${Object.keys(byYear).sort().map((y) => `<tr><td style="font-weight:600">${escapeHtml(y)}년</td>
              ${Array.from({ length: 12 }, (_, i) => {
                  const v = byYear[y][i + 1];
                  return `<td>${v != null ? fmtAvg(v) : '<span style="color:var(--text-muted)">—</span>'}</td>`;
              }).join('')}</tr>`).join('')}</tbody></table></div>`;
        body.appendChild(det);
    }
    function niceStep(raw) {
        const p = Math.pow(10, Math.floor(Math.log10(Math.max(raw, 1e-9))));
        const f = raw / p;
        return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10) * p;
    }
    // 단일 시리즈 line chart (SVG 직접 생성) — 완전한 달 데이터만 들어온다.
    // 색은 테마 변수(style 속성)로 지정해 다크모드에서도 그대로 읽힌다.
    function usageChart(months, avg) {
        const W = 640, H = 246, ML = 48, MR = 16, MT = 26, MB = 26;
        const iw = W - ML - MR, ih = H - MT - MB, n = months.length;
        const maxV = Math.max(...months.map((m) => m.qty), avg || 0);
        const step = niceStep((maxV || 1) / 4);
        const yMax = Math.max(step, Math.ceil((maxV || 1) / step) * step);
        const X = (i) => ML + (n === 1 ? iw / 2 : (i * iw) / (n - 1));
        const Y = (v) => MT + ih * (1 - v / yMax);
        const GRID = 'style="stroke:var(--border-color)"';
        const MUTED = 'style="fill:var(--text-muted)"';
        let grid = '';
        for (let v = 0; v <= yMax + 1e-9; v += step)
            grid += `<line x1="${ML}" y1="${Y(v)}" x2="${W - MR}" y2="${Y(v)}" ${GRID} stroke-width="1"/>
                     <text x="${ML - 7}" y="${Y(v) + 3.5}" text-anchor="end" font-size="10" ${MUTED}>${v.toLocaleString()}</text>`;
        const k = Math.ceil(n / 8);
        let xticks = '';
        for (let i = 0; i < n; i += k)
            xticks += `<text x="${X(i)}" y="${H - 8}" text-anchor="middle" font-size="10" ${MUTED}>${escapeHtml(months[i].ym.slice(2).replace('-', '.'))}</text>`;
        // 평균 라벨은 플롯 밖 우측 상단에 점선 키와 함께 — 숫자는 강조색 (키 위치는 렌더 후 실측 배치)
        let ref = '';
        if (avg != null && avg <= yMax)
            ref = `<line x1="${ML}" y1="${Y(avg)}" x2="${W - MR}" y2="${Y(avg)}" style="stroke:var(--text-muted)" stroke-width="1" stroke-dasharray="4 3"/>
                   <line class="usage-avgkey" x1="0" x2="0" y1="9" y2="9" style="stroke:var(--text-muted)" stroke-width="1" stroke-dasharray="4 3"/>
                   <text class="usage-avgtext" x="${W - MR}" y="12.5" text-anchor="end" font-size="10" ${MUTED}>12개월 평균 <tspan style="fill:var(--primary)" font-weight="700" font-size="11">${fmtAvg(avg)}</tspan></text>`;
        const pts = months.map((m, i) => [X(i), Y(m.qty)]);
        const path = (arr) => arr.map((p, i) => `${i ? 'L' : 'M'}${p[0]},${p[1]}`).join(' ');
        let line = '';
        if (n > 1)
            line = `<path d="${path(pts)} L${pts[n - 1][0]},${Y(0)} L${pts[0][0]},${Y(0)} Z" style="fill:var(--primary)" opacity=".08"/>`
                + `<path d="${path(pts)}" fill="none" style="stroke:var(--primary)" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>`;
        const dotEvery = n > 30 ? n - 1 : 1;   // 점이 너무 많으면 끝점만
        let dots = '';
        pts.forEach((p, i) => {
            if (i % dotEvery && i !== n - 1) return;
            dots += `<circle cx="${p[0]}" cy="${p[1]}" r="4" style="fill:var(--primary); stroke:var(--bg-primary)" stroke-width="2"/>`;
        });
        const LABEL = 'style="fill:var(--text-primary)" font-size="11" font-weight="600"';
        // 끝점 라벨 — 직전월이 더 커서 선이 내려오며 겹치면 포인트 아래에 표시
        const endDown = n > 1 && months[n - 2].qty > months[n - 1].qty;
        const endY = endDown ? Math.min(pts[n - 1][1] + 17, H - MB + 14) : pts[n - 1][1] - 9;
        const endLabel = `<text x="${pts[n - 1][0] + 4}" y="${endY}" text-anchor="end" ${LABEL}>${fmtAvg(months[n - 1].qty)}</text>`;
        // 최대는 포인트 위·최소는 포인트 아래 직접 라벨 (끝점 라벨과 겹치면 생략, 가장자리 클램프)
        const vals = months.map((m) => m.qty);
        const iMax = vals.indexOf(Math.max(...vals)), iMin = vals.indexOf(Math.min(...vals));
        const clampX = (x) => Math.max(ML + 14, Math.min(x, W - MR - 14));
        let extremes = '';
        if (n > 1 && iMax !== n - 1)
            extremes += `<text x="${clampX(pts[iMax][0])}" y="${Math.max(pts[iMax][1] - 9, 20)}" text-anchor="middle" ${LABEL}>${fmtAvg(vals[iMax])}</text>`;
        if (n > 1 && iMin !== n - 1 && iMin !== iMax)
            extremes += `<text x="${clampX(pts[iMin][0])}" y="${Math.min(pts[iMin][1] + 17, H - MB + 14)}" text-anchor="middle" ${LABEL}>${fmtAvg(vals[iMin])}</text>`;
        const wrap = document.createElement('div');
        wrap.className = 'usage-chart';
        wrap.innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="월별 사용량 추이">
            ${grid}${xticks}<line class="usage-cross" y1="${MT}" y2="${MT + ih}" style="stroke:var(--border-color)" stroke-width="1" display="none"/>
            ${ref}${line}${dots}${endLabel}${extremes}</svg>`;
        const tip = document.createElement('div');
        tip.className = 'usage-tip';
        wrap.appendChild(tip);
        const svg = wrap.querySelector('svg'), cross = wrap.querySelector('.usage-cross');
        // 평균 라벨 텍스트 폭을 실측해 점선 키를 그 왼쪽에 붙인다 (DOM 삽입 후에만 측정 가능)
        const avgText = svg.querySelector('.usage-avgtext');
        if (avgText) requestAnimationFrame(() => {
            try {
                const bb = avgText.getBBox(), key = svg.querySelector('.usage-avgkey');
                key.setAttribute('x1', bb.x - 24); key.setAttribute('x2', bb.x - 6);
            } catch (e) { /* 미표시 상태면 측정 불가 — 키 생략 */ }
        });
        // 크로스헤어 + 툴팁 — 포인터 X에 가장 가까운 달로 스냅
        svg.addEventListener('pointermove', (e) => {
            const rect = svg.getBoundingClientRect();
            const sx = (e.clientX - rect.left) * (W / rect.width);
            const i = Math.max(0, Math.min(n - 1, Math.round((sx - ML) / (n === 1 ? iw : iw / (n - 1)))));
            cross.setAttribute('x1', X(i)); cross.setAttribute('x2', X(i)); cross.removeAttribute('display');
            tip.textContent = '';
            const b = document.createElement('b'); b.textContent = fmtAvg(months[i].qty);
            const s = document.createElement('span'); s.className = 'dim'; s.textContent = ` · ${months[i].ym}`;
            tip.append(b, s);
            tip.style.display = 'block';
            const px = X(i) * (rect.width / W);
            tip.style.left = Math.max(0, Math.min(px + 10, rect.width - tip.offsetWidth - 4)) + 'px';
            tip.style.top = Math.max(0, Y(months[i].qty) * (rect.height / H) - 36) + 'px';
        });
        svg.addEventListener('pointerleave', () => { cross.setAttribute('display', 'none'); tip.style.display = 'none'; });
        return wrap;
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
    const modeOcrBtn = document.getElementById('modeOcrBtn');
    const modeManualBtn = document.getElementById('modeManualBtn');
    const pageSubtitle = document.getElementById('pageSubtitle');

    let selectedFile = null;
    let previewUrl = null;
    let mode = 'ocr';  // 'ocr'(사진) | 'manual'(직접 작성)

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

    async function save(overwrite) {
        if (!session) { showSaveStatus('error', '로그인이 필요합니다.'); return; }
        const items = collectItems();
        if (!items.length) { showSaveStatus('error', '저장할 품목이 없습니다. 약품명을 입력해주세요.'); return; }
        const payload = { order_date: orderDate.value, order_round: orderRound.value, items, overwrite: !!overwrite };
        const form = new FormData();
        form.append('payload', JSON.stringify(payload));
        if (selectedFile) form.append('image', selectedFile);

        saveBtn.disabled = true;
        showSaveStatus('loading', overwrite ? '기존 주문을 덮어쓰는 중입니다…' : '저장 중입니다…');
        try {
            const resp = await fetch('/api/save', { method: 'POST', body: form, headers: authHeader() });
            const data = await resp.json().catch(() => ({}));
            if (resp.status === 409 && !overwrite) {
                // 같은 (날짜, 차수) 주문 존재 → 사용자 확인 후 덮어쓰기 재요청
                hideSaveStatus();
                if (confirm(`${data.detail || '같은 날짜·차수의 주문이 이미 있습니다.'}\n\n기존 주문을 삭제하고 지금 내용으로 덮어쓸까요?`)) {
                    saveBtn.disabled = false;
                    return save(true);
                }
                return;
            }
            if (!resp.ok) throw new Error(data.detail || `요청 실패 (${resp.status})`);
            let msg = `저장되었습니다 — ${payload.order_date} ${payload.order_round}차 · ${items.length}개 품목. 로컬 앱에서 크롤링 대기 상태로 넘어갑니다.`;
            if (data.registered_drugs) msg += ` 약품 DB에 없던 ${data.registered_drugs}개 약품은 자유입력으로 자동 등록했어요.`;
            showSaveStatus('success', msg);
        } catch (e) {
            showSaveStatus('error', `저장 실패: ${e.message}`);
        } finally {
            saveBtn.disabled = false;
        }
    }

    // =================== 검수 모드 전환 ===================
    function enterReview(count) {
        hideSaveStatus();
        const manual = mode === 'manual';
        imagePane.hidden = manual;
        document.body.classList.toggle('manual-mode', manual);
        if (!manual) {
            if (previewUrl) reviewImg.src = previewUrl;
            else reviewImg.removeAttribute('src');
            reviewZoom?.reset();
        }
        const hint = document.getElementById('reviewHint');
        if (hint) {
            hint.textContent = manual
                ? '약품명을 입력하면 약품 DB에서 자동완성됩니다. 포장단위·수량을 입력하세요.'
                : (count != null)
                    ? `${count}개 품목을 읽었습니다. 왼쪽 원본과 대조하며 누락·오기를 직접 고쳐주세요.`
                    : '왼쪽 원본과 대조하며 누락·오기를 직접 고쳐주세요.';
        }
        document.body.classList.add('review-mode');
        uploadCard.hidden = true;
        reviewSection.hidden = false;
        window.scrollTo({ top: 0, behavior: 'smooth' });
    }
    function exitReview() {
        document.body.classList.remove('review-mode', 'manual-mode');
        reviewSection.hidden = true;
        uploadCard.hidden = false;
        imagePane.hidden = false;
        clearFile();
        // 사진 모드로 복귀
        mode = 'ocr';
        modeOcrBtn.classList.add('active'); modeManualBtn.classList.remove('active');
        modeOcrBtn.setAttribute('aria-selected', 'true'); modeManualBtn.setAttribute('aria-selected', 'false');
        if (pageSubtitle) pageSubtitle.textContent = '주문지 사진을 올리면 약품명·포장단위·수량을 자동으로 읽어옵니다';
        window.scrollTo({ top: 0, behavior: 'smooth' });
    }

    // 입력 방식 전환 (사진 ↔ 직접 작성)
    function setMode(next) {
        if (next === mode) return;
        if (next === 'manual') {
            mode = 'manual';
            modeManualBtn.classList.add('active'); modeOcrBtn.classList.remove('active');
            modeManualBtn.setAttribute('aria-selected', 'true'); modeOcrBtn.setAttribute('aria-selected', 'false');
            if (pageSubtitle) pageSubtitle.textContent = '약품을 직접 입력해 주문서를 작성합니다';
            clearFile();
            renderRows([]);      // 빈 행 1개
            enterReview(null);
        } else {
            exitReview();        // 사진 모드로 복귀 (업로드 화면)
        }
    }

    // =================== 원본 사진 확대 / 이동 ===================
    function clamp(v, lo, hi) { return Math.min(hi, Math.max(lo, v)); }
    function createZoomViewer(viewport, img, levelEl) {
        const Z = { scale: 1, tx: 0, ty: 0, min: 1, max: 6 };
        function applyTransform() {
            img.style.transform = `translate(${Z.tx}px, ${Z.ty}px) scale(${Z.scale})`;
            if (levelEl) levelEl.textContent = Math.round(Z.scale * 100) + '%';
        }
        function reset() { Z.scale = 1; Z.tx = 0; Z.ty = 0; applyTransform(); }
        function zoomAt(factor, clientX, clientY) {
            const rect = viewport.getBoundingClientRect();
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
        viewport.addEventListener('dblclick', reset);
        viewport.addEventListener('wheel', (e) => {
            e.preventDefault();
            zoomAt(e.deltaY < 0 ? 1.15 : 1 / 1.15, e.clientX, e.clientY);
        }, { passive: false });
        let dragging = false, lastX = 0, lastY = 0;
        viewport.addEventListener('mousedown', (e) => {
            dragging = true; lastX = e.clientX; lastY = e.clientY;
            viewport.classList.add('panning'); e.preventDefault();
        });
        window.addEventListener('mousemove', (e) => {
            if (!dragging) return;
            Z.tx += e.clientX - lastX; Z.ty += e.clientY - lastY;
            lastX = e.clientX; lastY = e.clientY;
            applyTransform();
        });
        window.addEventListener('mouseup', () => { dragging = false; viewport.classList.remove('panning'); });
        let touchMode = null, tLastX = 0, tLastY = 0, startDist = 0, startScale = 1, pinchX = 0, pinchY = 0;
        const dist = (t) => Math.hypot(t[0].clientX - t[1].clientX, t[0].clientY - t[1].clientY);
        viewport.addEventListener('touchstart', (e) => {
            if (e.touches.length === 1) { touchMode = 'pan'; tLastX = e.touches[0].clientX; tLastY = e.touches[0].clientY; }
            else if (e.touches.length === 2) {
                touchMode = 'pinch'; startDist = dist(e.touches); startScale = Z.scale;
                pinchX = (e.touches[0].clientX + e.touches[1].clientX) / 2;
                pinchY = (e.touches[0].clientY + e.touches[1].clientY) / 2;
            }
        }, { passive: false });
        viewport.addEventListener('touchmove', (e) => {
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
        viewport.addEventListener('touchend', (e) => {
            if (e.touches.length === 0) touchMode = null;
            else if (e.touches.length === 1) { touchMode = 'pan'; tLastX = e.touches[0].clientX; tLastY = e.touches[0].clientY; }
        });
        return { reset, zoomAt };
    }
    let reviewZoom = null, histZoom = null;
    function bindImageViewer() {
        reviewZoom = createZoomViewer(imageViewport, reviewImg, zoomLevel);
        document.getElementById('zoomInBtn').addEventListener('click', () => reviewZoom.zoomAt(1.25, null, null));
        document.getElementById('zoomOutBtn').addEventListener('click', () => reviewZoom.zoomAt(1 / 1.25, null, null));
        document.getElementById('zoomResetBtn').addEventListener('click', () => reviewZoom.reset());
        document.getElementById('reuploadBtn').addEventListener('click', () => {
            if (window.confirm('지금까지 입력·검수한 내용이 모두 사라지고 처음부터 다시 시작합니다.\n\n계속할까요?')) {
                exitReview();
            }
        });
        histZoom = createZoomViewer(
            document.getElementById('histViewport'),
            document.getElementById('histImg'),
            document.getElementById('histZoomLevel'),
        );
        document.getElementById('histZoomInBtn').addEventListener('click', () => histZoom.zoomAt(1.25, null, null));
        document.getElementById('histZoomOutBtn').addEventListener('click', () => histZoom.zoomAt(1 / 1.25, null, null));
        document.getElementById('histZoomResetBtn').addEventListener('click', () => histZoom.reset());
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
        saveBtn.addEventListener('click', () => save(false));
        modeOcrBtn.addEventListener('click', () => setMode('ocr'));
        modeManualBtn.addEventListener('click', () => setMode('manual'));
    }

    // =================== 초기화 ===================
    document.addEventListener('DOMContentLoaded', () => {
        applyTheme();
        document.getElementById('themeToggle')?.addEventListener('click', toggleTheme);
        document.getElementById('googleBtn')?.addEventListener('click', async () => {
            showLoginStatus('loading', 'Google 로그인 창으로 이동 중…');
            // redirectTo 는 origin(known-working). 초대코드는 sessionStorage 로 보존한다.
            const { error } = await sb.auth.signInWithOAuth({ provider: 'google', options: { redirectTo: location.origin } });
            if (error) showLoginStatus('error', error.message);
        });
        document.getElementById('logoutBtn')?.addEventListener('click', async () => { showView('home'); await sb?.auth.signOut(); });
        document.getElementById('homeBtn')?.addEventListener('click', () => showView('home'));
        document.getElementById('navBrand')?.addEventListener('click', () => { if (session && membership) showView('home'); });
        // 홈 카드 → 기능 진입 (클릭 + 키보드)
        [['cardOcr', 'form'], ['cardHistory', 'history'], ['cardDrugs', 'drugs']].forEach(([id, view]) => {
            const card = document.getElementById(id);
            card?.addEventListener('click', () => showView(view));
            card?.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); showView(view); } });
        });
        // 약 목록 검색 (디바운스)
        document.querySelectorAll('#drugFilters .drug-filter').forEach((b) => b.addEventListener('click', () => {
            document.querySelectorAll('#drugFilters .drug-filter').forEach((x) => x.classList.remove('active'));
            b.classList.add('active');
            drugFilter = b.dataset.filter || '';
            loadDrugs(true);
        }));
        document.getElementById('drugSearchInput')?.addEventListener('input', debounce((e) => {
            drugQuery = e.target.value.trim();
            loadDrugs(true);
        }, 250));
        document.getElementById('drugMoreBtn')?.addEventListener('click', () => loadDrugs(false));
        document.getElementById('joinBtn')?.addEventListener('click', () => doAccept(document.getElementById('inviteCode').value));
        document.getElementById('inviteCode')?.addEventListener('keydown', (e) => { if (e.key === 'Enter') doAccept(e.target.value); });
        document.getElementById('inviteBtn')?.addEventListener('click', createInvite);
        document.getElementById('copyInviteBtn')?.addEventListener('click', async () => {
            const link = document.getElementById('inviteLink').value;
            try { await navigator.clipboard.writeText(link); showInviteModalStatus('success', '복사되었습니다.'); }
            catch { document.getElementById('inviteLink').select(); showInviteModalStatus('error', '수동으로 복사하세요 (Cmd/Ctrl+C).'); }
        });
        document.getElementById('closeInviteBtn')?.addEventListener('click', () => { document.getElementById('inviteModal').hidden = true; });
        document.getElementById('calPrev')?.addEventListener('click', () => shiftCalendar(-1));
        document.getElementById('calNext')?.addEventListener('click', () => shiftCalendar(1));
        document.getElementById('closeImageBtn')?.addEventListener('click', () => { document.getElementById('imageModal').hidden = true; });
        const imageModal = document.getElementById('imageModal');
        // 뷰포트에서 드래그하다 오버레이 위에서 놓아도 닫히지 않도록, 오버레이에서 시작한 클릭만 닫기 처리
        let imgOverlayDown = false;
        imageModal?.addEventListener('mousedown', (e) => { imgOverlayDown = (e.target === e.currentTarget); });
        imageModal?.addEventListener('click', (e) => { if (imgOverlayDown && e.target === e.currentTarget) e.currentTarget.hidden = true; });
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
