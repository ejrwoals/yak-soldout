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
            <td><input type="text" class="f-name" placeholder="약품명"></td>
            <td class="col-unit"><input type="text" class="f-unit" placeholder="포장단위"></td>
            <td class="col-qty"><input type="text" class="f-qty" placeholder="수량"></td>
            <td class="col-del"><button class="del-row-btn" title="행 삭제"><i class="bi bi-trash"></i></button></td>
        `;
        tr.querySelector('.f-name').value = item.drug_name || '';
        tr.querySelector('.f-unit').value = item.package_unit || '';
        tr.querySelector('.f-qty').value = item.quantity || '';
        tr.querySelector('.del-row-btn').addEventListener('click', () => {
            tr.remove();
            renumber();
        });
        return tr;
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
        connectWebSocket(); // 서버 자동 종료 방지 (keep-alive)
    });
})();
