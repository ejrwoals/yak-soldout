// 주문 기록 페이지 — 달력으로 저장된 주문지 내역을 조회/삭제한다.
// 저장 데이터는 로컬 SQLite(orders/order_items). 백엔드: /api/orders 계열.

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
    const calTitle = document.getElementById('calTitle');
    const calGrid = document.getElementById('calGrid');
    const prevMonthBtn = document.getElementById('prevMonth');
    const nextMonthBtn = document.getElementById('nextMonth');
    const todayBtn = document.getElementById('todayBtn');
    const detailEmpty = document.getElementById('detailEmpty');
    const detailContent = document.getElementById('detailContent');
    const detailDate = document.getElementById('detailDate');
    const orderList = document.getElementById('orderList');

    const WEEKDAY_KO = ['일', '월', '화', '수', '목', '금', '토'];

    // 상태
    let viewYear, viewMonth;            // 현재 보고 있는 달 (month: 0~11)
    let ordersByDate = new Map();       // "YYYY-MM-DD" → [주문 요약, ...]
    let selectedDate = null;            // 선택된 날짜 문자열

    // =================== 날짜 유틸 ===================
    function ymd(d) {
        const y = d.getFullYear();
        const m = String(d.getMonth() + 1).padStart(2, '0');
        const day = String(d.getDate()).padStart(2, '0');
        return `${y}-${m}-${day}`;
    }
    const todayStr = ymd(new Date());

    // =================== 데이터 로드 ===================
    async function loadOrders() {
        try {
            const resp = await fetch('/api/orders');
            const data = await resp.json();
            ordersByDate = new Map();
            (data.orders || []).forEach((o) => {
                if (!ordersByDate.has(o.order_date)) ordersByDate.set(o.order_date, []);
                ordersByDate.get(o.order_date).push(o);
            });
        } catch (e) {
            ordersByDate = new Map();
        }
        // 선택 유효성 먼저 정리(삭제로 그날 주문이 모두 사라졌을 수 있음) → 그 다음 렌더
        if (!(selectedDate && ordersByDate.has(selectedDate))) selectedDate = null;
        renderCalendar();
        if (selectedDate) selectDate(selectedDate);
        else showEmptyDetail();
    }

    // =================== 달력 렌더 ===================
    function renderCalendar() {
        calTitle.textContent = `${viewYear}년 ${viewMonth + 1}월`;
        calGrid.innerHTML = '';

        const firstWeekday = new Date(viewYear, viewMonth, 1).getDay();
        const daysInMonth = new Date(viewYear, viewMonth + 1, 0).getDate();
        const totalCells = Math.ceil((firstWeekday + daysInMonth) / 7) * 7;

        for (let i = 0; i < totalCells; i++) {
            const cellDate = new Date(viewYear, viewMonth, 1 - firstWeekday + i);
            const inMonth = cellDate.getMonth() === viewMonth;
            const dateStr = ymd(cellDate);
            const cell = document.createElement('div');
            cell.className = 'cal-cell';
            cell.textContent = cellDate.getDate();

            if (!inMonth) {
                cell.classList.add('is-other');
            } else {
                if (dateStr === todayStr) cell.classList.add('is-today');
                const orders = ordersByDate.get(dateStr);
                if (orders && orders.length) {
                    cell.classList.add('has-orders');
                    const marker = document.createElement('span');
                    marker.className = 'cal-marker';
                    marker.innerHTML = `<span class="cal-dot"></span>${orders.length}`;
                    cell.appendChild(marker);
                    cell.addEventListener('click', () => selectDate(dateStr));
                }
                if (dateStr === selectedDate) cell.classList.add('is-selected');
            }
            calGrid.appendChild(cell);
        }
    }

    // =================== 상세 패널 ===================
    function showEmptyDetail() {
        detailContent.hidden = true;
        detailEmpty.hidden = false;
    }

    async function selectDate(dateStr) {
        selectedDate = dateStr;
        renderCalendar();  // 선택 하이라이트 반영

        const orders = (ordersByDate.get(dateStr) || []).slice()
            .sort((a, b) => a.order_round - b.order_round);
        if (!orders.length) { showEmptyDetail(); return; }

        const d = new Date(dateStr + 'T00:00:00');
        detailDate.textContent = `${dateStr} (${WEEKDAY_KO[d.getDay()]}) · 주문 ${orders.length}건`;
        detailEmpty.hidden = true;
        detailContent.hidden = false;

        // 각 주문의 상세(품목)를 불러와 카드로 렌더
        orderList.innerHTML = '<p class="oh-status">불러오는 중…</p>';
        try {
            const details = await Promise.all(
                orders.map((o) => fetch(`/api/orders/${o.id}`).then((r) => r.json())));
            orderList.innerHTML = '';
            details.forEach((od) => orderList.appendChild(buildOrderCard(od)));
        } catch (e) {
            orderList.innerHTML = '<p class="oh-status error">주문을 불러오지 못했습니다.</p>';
        }
    }

    function buildOrderCard(order) {
        const card = document.createElement('div');
        card.className = 'order-card';

        // 헤더: 차수 배지 + 저장시각 + 삭제
        const head = document.createElement('div');
        head.className = 'order-card-head';
        const badge = document.createElement('span');
        badge.className = 'order-round-badge';
        badge.textContent = `${order.order_round}차`;
        const meta = document.createElement('span');
        meta.className = 'order-meta-text';
        meta.textContent = `${order.items.length}개 품목` +
            (order.created_at ? ` · ${order.created_at.replace('T', ' ')} 저장` : '');
        const delBtn = document.createElement('button');
        delBtn.className = 'order-del-btn';
        delBtn.title = '이 주문 삭제';
        delBtn.innerHTML = '<i class="bi bi-trash"></i>';
        delBtn.addEventListener('click', () => deleteOrder(order));
        head.append(badge, meta, delBtn);

        // 본문: 원본 이미지(있으면) + 품목 표
        const body = document.createElement('div');
        body.className = 'order-card-body';
        if (order.image_path) {
            const img = document.createElement('img');
            img.className = 'order-img-thumb';
            img.src = `/api/orders/${order.id}/image`;
            img.alt = '원본 주문지';
            img.title = '클릭하면 새 탭에서 원본 보기';
            img.addEventListener('click', () => window.open(img.src, '_blank'));
            body.appendChild(img);
        }
        body.appendChild(buildItemsTable(order.items));

        card.append(head, body);
        return card;
    }

    function buildItemsTable(items) {
        const table = document.createElement('table');
        table.className = 'order-items-table';
        table.innerHTML = `
            <thead><tr>
                <th class="col-idx">#</th><th>약품명</th>
                <th>포장단위</th><th class="col-qty">수량</th>
            </tr></thead>`;
        const tbody = document.createElement('tbody');
        items.forEach((it, i) => {
            const tr = document.createElement('tr');
            const cells = [String(i + 1), it.drug_name, it.package_unit || '', it.quantity || ''];
            ['col-idx', 'col-name', 'col-unit', 'col-qty'].forEach((cls, j) => {
                const td = document.createElement('td');
                td.className = cls;
                td.textContent = cells[j];
                tr.appendChild(td);
            });
            tbody.appendChild(tr);
        });
        table.appendChild(tbody);
        return table;
    }

    async function deleteOrder(order) {
        const ok = window.confirm(
            `${order.order_date} ${order.order_round}차 주문(${order.items.length}개 품목)을 삭제할까요?\n삭제하면 되돌릴 수 없습니다.`);
        if (!ok) return;
        try {
            const resp = await fetch(`/api/orders/${order.id}`, { method: 'DELETE' });
            if (!resp.ok) {
                const data = await resp.json().catch(() => ({}));
                throw new Error(data.detail || `삭제 실패 (${resp.status})`);
            }
            await loadOrders();  // 목록·달력·상세 갱신
        } catch (e) {
            alert(`삭제 실패: ${e.message}`);
        }
    }

    // =================== 월 이동 ===================
    function goMonth(delta) {
        viewMonth += delta;
        if (viewMonth < 0) { viewMonth = 11; viewYear--; }
        else if (viewMonth > 11) { viewMonth = 0; viewYear++; }
        renderCalendar();
    }
    function goToday() {
        const now = new Date();
        viewYear = now.getFullYear();
        viewMonth = now.getMonth();
        renderCalendar();
    }

    // =================== Keep-alive WebSocket ===================
    // 활성 WebSocket이 0개가 되면 서버가 자동 종료되므로(websocket_manager.py),
    // 이 페이지도 WS를 유지한다. (home.js / order-ocr.js 와 동일 목적)
    let ws = null;
    let reconnectTimer = null;
    function connectWebSocket() {
        if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return;
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        try {
            ws = new WebSocket(`${protocol}//${window.location.host}/ws`);
        } catch (e) {
            scheduleReconnect();
            return;
        }
        ws.onclose = () => scheduleReconnect();
        ws.onerror = () => { /* onclose 에서 재연결 */ };
    }
    function scheduleReconnect() {
        if (reconnectTimer) return;
        reconnectTimer = setTimeout(() => { reconnectTimer = null; connectWebSocket(); }, 1500);
    }

    // =================== 초기화 ===================
    document.addEventListener('DOMContentLoaded', () => {
        applyTheme();
        document.getElementById('themeToggle')?.addEventListener('click', toggleTheme);
        const now = new Date();
        viewYear = now.getFullYear();
        viewMonth = now.getMonth();
        prevMonthBtn.addEventListener('click', () => goMonth(-1));
        nextMonthBtn.addEventListener('click', () => goMonth(1));
        todayBtn.addEventListener('click', goToday);
        loadOrders();
        connectWebSocket();
    });
})();
