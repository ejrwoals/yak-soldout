// WebSocket 연결 및 메시지 처리 관리 클래스

class WebSocketManager extends EventTarget {
    constructor(options = {}) {
        super();
        
        // 설정
        this.maxReconnectAttempts = options.maxReconnectAttempts || 5;
        this.baseReconnectDelay = options.baseReconnectDelay || 1000;
        this.maxReconnectDelay = options.maxReconnectDelay || 30000;
        
        // 상태
        this.ws = null;
        this.reconnectAttempts = 0;
        this.isConnecting = false;
        this.connectionStatus = 'disconnected';
        
        // UI 요소들 (선택적)
        this.connectionDot = options.connectionDot || null;
        this.connectionText = options.connectionText || null;
    }
    
    /**
     * WebSocket 연결 시작
     */
    connect() {
        if (this.isConnecting || (this.ws && this.ws.readyState === WebSocket.OPEN)) {
            console.log('이미 연결되었거나 연결 중입니다.');
            return;
        }
        
        this.isConnecting = true;
        
        try {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const wsUrl = `${protocol}//${window.location.host}/ws`;
            
            console.log(`🔌 WebSocket 연결 시도: ${wsUrl}`);
            this.ws = new WebSocket(wsUrl);
            
            this.setupEventHandlers();
            
        } catch (error) {
            console.error('❌ WebSocket 연결 실패:', error);
            this.isConnecting = false;
            this.updateConnectionStatus('disconnected');
            this.dispatchCustomEvent('connection-error', { error });
        }
    }
    
    /**
     * WebSocket 이벤트 핸들러 설정
     */
    setupEventHandlers() {
        if (!this.ws) return;
        
        this.ws.onopen = () => {
            console.log('✅ WebSocket 연결 성공');
            this.isConnecting = false;
            this.reconnectAttempts = 0;
            this.updateConnectionStatus('connected');
            this.dispatchCustomEvent('connected');
        };
        
        this.ws.onmessage = (event) => {
            this.handleMessage(event.data);
        };
        
        this.ws.onclose = (event) => {
            console.log('⚠️ WebSocket 연결 종료:', event.code, event.reason);
            this.isConnecting = false;
            this.updateConnectionStatus('disconnected');
            this.dispatchCustomEvent('disconnected', { code: event.code, reason: event.reason });
            
            // 정상 종료가 아닌 경우에만 재연결 시도
            if (event.code !== 1000) {
                this.attemptReconnect();
            }
        };
        
        this.ws.onerror = (error) => {
            console.error('❌ WebSocket 오류:', error);
            this.isConnecting = false;
            this.updateConnectionStatus('disconnected');
            this.dispatchCustomEvent('error', { error });
        };
    }
    
    /**
     * 재연결 시도
     */
    attemptReconnect() {
        if (this.reconnectAttempts >= this.maxReconnectAttempts) {
            console.error('💥 WebSocket 재연결 포기');
            this.dispatchCustomEvent('reconnect-failed');
            return;
        }
        
        this.reconnectAttempts++;
        const delay = Math.min(
            this.baseReconnectDelay * Math.pow(2, this.reconnectAttempts - 1),
            this.maxReconnectDelay
        );
        
        console.log(`🔄 WebSocket 재연결 시도 ${this.reconnectAttempts}/${this.maxReconnectAttempts} (${delay}ms 후)`);
        
        this.dispatchCustomEvent('reconnecting', { 
            attempt: this.reconnectAttempts, 
            maxAttempts: this.maxReconnectAttempts,
            delay 
        });
        
        setTimeout(() => {
            this.connect();
        }, delay);
    }
    
    /**
     * 메시지 처리
     * @param {string} data - 수신된 메시지 데이터
     */
    handleMessage(data) {
        try {
            const message = JSON.parse(data);
            
            // 메시지 타입별 이벤트 발생
            this.dispatchCustomEvent('message', { message, rawData: data });
            this.dispatchCustomEvent(`message-${message.type}`, { message, rawData: data });
            
        } catch (error) {
            console.error('❌ 메시지 파싱 오류:', error);
            this.dispatchCustomEvent('message-error', { error, rawData: data });
        }
    }
    
    /**
     * 메시지 전송
     * @param {object} message - 전송할 메시지 객체
     */
    send(message) {
        if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
            console.warn('WebSocket이 연결되지 않았습니다.');
            return false;
        }
        
        try {
            const data = typeof message === 'string' ? message : JSON.stringify(message);
            this.ws.send(data);
            return true;
        } catch (error) {
            console.error('❌ 메시지 전송 실패:', error);
            this.dispatchCustomEvent('send-error', { error, message });
            return false;
        }
    }
    
    /**
     * 연결 상태 업데이트
     * @param {string} status - 연결 상태 ('connected', 'disconnected', 'searching')
     */
    updateConnectionStatus(status) {
        this.connectionStatus = status;
        
        // UI 업데이트 (요소가 제공된 경우)
        this.updateConnectionUI(status);
        
        // 상태 변경 이벤트 발생
        this.dispatchCustomEvent('status-changed', { status });
    }
    
    /**
     * 연결 상태 UI 업데이트
     * @param {string} status - 연결 상태
     */
    updateConnectionUI(status) {
        // 상태 점 업데이트
        if (this.connectionDot) {
            this.connectionDot.className = 'status-dot';
            this.connectionDot.classList.add(status);
        }
        
        // 상태 텍스트 업데이트
        if (this.connectionText) {
            const statusTexts = {
                connected: '연결됨',
                disconnected: '연결 끊김',
                searching: '검색 중',
                connecting: '연결 중'
            };
            
            this.connectionText.textContent = statusTexts[status] || '알 수 없음';
        }
    }
    
    /**
     * 커스텀 이벤트 발생
     * @param {string} eventName - 이벤트 이름
     * @param {object} detail - 이벤트 상세 정보
     */
    dispatchCustomEvent(eventName, detail = {}) {
        const event = new CustomEvent(eventName, {
            detail: {
                ...detail,
                timestamp: new Date(),
                connectionStatus: this.connectionStatus
            }
        });
        
        this.dispatchEvent(event);
    }
    
    /**
     * WebSocket 연결 해제
     */
    disconnect() {
        if (this.ws) {
            console.log('🔌 WebSocket 연결 해제');
            this.ws.close(1000, 'Manual disconnect');
            this.ws = null;
        }
        
        this.reconnectAttempts = this.maxReconnectAttempts; // 재연결 시도 중단
        this.updateConnectionStatus('disconnected');
    }
    
    /**
     * 연결 상태 확인
     * @returns {boolean} 연결 여부
     */
    isConnected() {
        return this.ws && this.ws.readyState === WebSocket.OPEN;
    }
    
    /**
     * 현재 상태 정보 반환
     * @returns {object} 상태 정보
     */
    getStatus() {
        return {
            connectionStatus: this.connectionStatus,
            isConnected: this.isConnected(),
            isConnecting: this.isConnecting,
            reconnectAttempts: this.reconnectAttempts,
            maxReconnectAttempts: this.maxReconnectAttempts,
            readyState: this.ws ? this.ws.readyState : null
        };
    }
    
    /**
     * UI 요소 설정
     * @param {object} elements - UI 요소들
     */
    setUIElements(elements) {
        this.connectionDot = elements.connectionDot || this.connectionDot;
        this.connectionText = elements.connectionText || this.connectionText;
        
        // 현재 상태로 UI 업데이트
        this.updateConnectionUI(this.connectionStatus);
    }
}

// 전역 인스턴스 생성
window.webSocketManager = new WebSocketManager();
