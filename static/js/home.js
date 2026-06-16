// 홈 화면 (앱 런처) 로직: 테마 토글, 약국명 표시, keep-alive WebSocket

(function () {
    'use strict';

    // =================== 테마 관리 ===================
    let currentTheme = localStorage.getItem('theme') || 'light';

    function applyTheme() {
        document.documentElement.setAttribute('data-theme', currentTheme);
        const icon = document.querySelector('#themeToggle i');
        if (icon) {
            icon.className = currentTheme === 'light' ? 'bi bi-moon' : 'bi bi-sun';
        }
    }

    function toggleTheme() {
        currentTheme = currentTheme === 'light' ? 'dark' : 'light';
        localStorage.setItem('theme', currentTheme);
        applyTheme();
    }

    // =================== 약국명 표시 ===================
    async function loadBuildInfo() {
        try {
            const resp = await fetch('/api/build-info');
            if (!resp.ok) return;
            const data = await resp.json();
            const el = document.getElementById('pharmacyLabel');
            if (el && data.pharmacy_name) {
                el.textContent = `for ${data.pharmacy_name}`;
            }
        } catch (e) {
            console.warn('빌드 정보 로드 실패:', e);
        }
    }

    // =================== 연결 상태 표시 ===================
    function setConnectionStatus(status) {
        const dot = document.getElementById('connectionDot');
        const text = document.getElementById('connectionText');
        if (dot) dot.className = `status-dot ${status}`;
        if (text) text.textContent = status === 'connected' ? '연결됨' : '연결 끊김';
    }

    // =================== 자동 검색 동작 표시 ===================
    let searchingState = false;

    function setSearching(searching) {
        searchingState = searching;
        const badge = document.getElementById('checkerLiveBadge');
        const card = document.getElementById('checkerCard');
        const btn = document.getElementById('homeSearchBtn');

        if (badge) badge.hidden = !searching;
        if (card) card.classList.toggle('is-running', searching);

        if (btn) {
            btn.classList.toggle('is-searching', searching);
            const icon = btn.querySelector('i');
            const label = btn.querySelector('span');
            if (icon) icon.className = searching ? 'bi bi-stop-circle' : 'bi bi-play-circle';
            if (label) label.textContent = searching ? '검색 중단' : '검색 시작';
        }
    }

    // 현재 검색 상태를 서버에서 조회 (최초 진입 / 재연결 시 동기화)
    async function syncSearchStatus() {
        try {
            const resp = await fetch('/api/status');
            if (!resp.ok) return;
            const data = await resp.json();
            setSearching(!!data.is_searching);
        } catch (e) {
            console.warn('검색 상태 조회 실패:', e);
        }
    }

    // =================== 홈 검색 버튼 ===================
    async function toggleSearch() {
        const btn = document.getElementById('homeSearchBtn');
        if (btn) btn.disabled = true;
        try {
            const url = searchingState ? '/api/search/stop' : '/api/search/start';
            const resp = await fetch(url, { method: 'POST' });
            if (resp.ok) {
                const msg = searchingState ? '검색을 중단했습니다' : '검색을 시작했습니다';
                window.notificationManager?.showSuccess(msg);
            } else {
                const data = await resp.json().catch(() => ({}));
                window.notificationManager?.showError(data.detail || '요청 실패');
            }
        } catch (e) {
            window.notificationManager?.showError('서버 연결 오류');
        } finally {
            if (btn) btn.disabled = false;
        }
    }

    // =================== WebSocket 메시지 처리 ===================
    function handleWsMessage(raw) {
        let msg;
        try {
            msg = JSON.parse(raw);
        } catch (e) {
            return;
        }
        // 검색 시작(사이클 시작) → 동작 중 표시, 중단 → 표시 해제
        if (msg.type === 'cycle_start') {
            setSearching(true);
        } else if (msg.type === 'search_stopped') {
            setSearching(false);
        } else if (msg.type === 'urgent_alert' && msg.drug) {
            onUrgentAlert(msg.drug);
        }
        // search_completed 는 반복 모드에서 사이클 사이 대기 상태로,
        // 검색은 계속 진행되므로 표시를 유지한다.
    }

    // =================== 긴급 알림 (홈 화면) ===================
    function onUrgentAlert(drug) {
        const name = drug.name + (drug.unit ? ` [${drug.unit}]` : '');

        // 윈도우(브라우저) 알림
        if ('Notification' in window) {
            if (Notification.permission === 'default') {
                Notification.requestPermission().then(p => {
                    if (p === 'granted') showBrowserNotification(drug, name);
                });
            } else if (Notification.permission === 'granted') {
                showBrowserNotification(drug, name);
            }
        }

        // 토스트 알림
        window.notificationManager?.showNotification(
            `🚨 긴급 재고 발견: ${name} (${drug.distributor})`,
            'warning',
            8000
        );
    }

    function showBrowserNotification(drug, name) {
        const stockInfo = drug.main_stock || '';
        const incheonInfo = drug.incheon_stock && drug.incheon_stock !== '-'
            ? ` / 타센터: ${drug.incheon_stock}` : '';
        const notification = new Notification('🚨 긴급 재고 알림', {
            body: `${name}\n재고: ${stockInfo}${incheonInfo}\n도매상: ${drug.distributor}`,
            icon: '/static/favicon.ico',
            tag: `urgent-${drug.name}`,
            requireInteraction: true
        });
        notification.onclick = () => {
            window.location.href = '/checker';
            notification.close();
        };
        setTimeout(() => notification.close(), 10000);
    }

    // =================== Keep-alive WebSocket ===================
    // 대시보드(/checker)에서 홈으로 돌아올 때 모든 WebSocket이 끊겨
    // 서버가 "브라우저 닫힘"으로 오인하고 종료되는 것을 방지한다.
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
            setConnectionStatus('disconnected');
            scheduleReconnect();
            return;
        }

        ws.onopen = () => {
            setConnectionStatus('connected');
            syncSearchStatus(); // 연결/재연결 시 검색 상태 재동기화
        };
        ws.onmessage = (event) => handleWsMessage(event.data);
        ws.onclose = () => {
            setConnectionStatus('disconnected');
            scheduleReconnect();
        };
        ws.onerror = () => setConnectionStatus('disconnected');
    }

    function scheduleReconnect() {
        if (reconnectTimer) return;
        reconnectTimer = setTimeout(() => {
            reconnectTimer = null;
            connectWebSocket();
        }, 1500);
    }

    // =================== 초기화 ===================
    document.addEventListener('DOMContentLoaded', () => {
        applyTheme();
        document.getElementById('themeToggle')?.addEventListener('click', toggleTheme);
        loadBuildInfo();
        syncSearchStatus(); // 첫 진입 시 즉시 반영
        connectWebSocket();

        // 홈 검색 버튼 - stopPropagation으로 카드 링크 이동 방지
        document.getElementById('homeSearchBtn')?.addEventListener('click', (e) => {
            e.stopPropagation();
            e.preventDefault();
            toggleSearch();
        });
    });
})();
