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
    function setSearching(isSearching) {
        const badge = document.getElementById('checkerLiveBadge');
        const card = document.getElementById('checkerCard');
        if (badge) badge.hidden = !isSearching;
        if (card) card.classList.toggle('is-running', isSearching);
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

    // WebSocket 메시지로 실시간 상태 갱신
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
        }
        // search_completed 는 반복 모드에서 사이클 사이 대기 상태로,
        // 검색은 계속 진행되므로 표시를 유지한다.
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
    });
})();
