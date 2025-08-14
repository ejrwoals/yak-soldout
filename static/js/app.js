// 약품 재고 자동 검색 - 모던 대시보드 JavaScript

class ModernDrugSearchApp {
    constructor() {
        // WebSocket 관련
        this.ws = null;
        this.isSearching = false;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        
        // DOM 요소들
        this.elements = this.initializeElements();
        
        // 상태
        this.currentTheme = localStorage.getItem('theme') || 'light';
        this.errorDrugs = []; // 오류 발생한 약품 목록
        
        // 초기화
        this.init();
    }
    
    initializeElements() {
        return {
            // 네비게이션
            themeToggle: document.getElementById('themeToggle'),
            connectionDot: document.getElementById('connectionDot'),
            connectionText: document.getElementById('connectionText'),
            
			// 컨트롤 (토글 버튼)
			actionBtn: document.getElementById('actionBtn'),
            
            // 상태 카드
            drugCount: document.getElementById('drugCount'),
            distributorStatus: document.getElementById('distributorStatus'),
            exclusionCount: document.getElementById('exclusionCount'),
            
            // 로그
            logContainer: document.getElementById('logContainer'),
            clearLogBtn: document.getElementById('clearLogBtn'),
            
            // 결과
            foundCount: document.getElementById('foundCount'),
            soldoutCount: document.getElementById('soldoutCount'),
            errorCount: document.getElementById('errorCount'),
            lastUpdate: document.getElementById('lastUpdate'),
            searchResults: document.getElementById('searchResults')
        };
    }
    
    init() {
        this.applyTheme();
        this.setupEventListeners();
        this.connectWebSocket();
        this.loadStatus();
        
        // 주기적 상태 업데이트
        setInterval(() => this.loadStatus(), 15000);
        
        console.log('🚀 모던 약품 재고 체커가 시작되었습니다');
    }
    
    setupEventListeners() {
        // 테마 토글
        this.elements.themeToggle?.addEventListener('click', () => this.toggleTheme());
        
		// 검색 컨트롤 (토글)
		this.elements.actionBtn?.addEventListener('click', () => this.toggleSearch());
        
        // 로그 클리어
        this.elements.clearLogBtn?.addEventListener('click', () => this.clearLogs());
        
        // 키보드 단축키
        document.addEventListener('keydown', (e) => {
            if (e.ctrlKey || e.metaKey) {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    if (!this.isSearching) {
                        this.startSearch();
                    }
                } else if (e.key === 'Escape') {
                    e.preventDefault();
                    if (this.isSearching) {
                        this.stopSearch();
                    }
                }
            }
        });
    }
    
    // =================== 테마 관리 ===================
    toggleTheme() {
        this.currentTheme = this.currentTheme === 'light' ? 'dark' : 'light';
        this.applyTheme();
        localStorage.setItem('theme', this.currentTheme);
    }
    
    applyTheme() {
        document.documentElement.setAttribute('data-theme', this.currentTheme);
        
        if (this.elements.themeToggle) {
            const icon = this.elements.themeToggle.querySelector('i');
            if (icon) {
                icon.className = this.currentTheme === 'light' ? 'bi bi-moon' : 'bi bi-sun';
            }
        }
    }
    
    // =================== WebSocket 연결 ===================
    connectWebSocket() {
        try {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const wsUrl = `${protocol}//${window.location.host}/ws`;
            
            this.ws = new WebSocket(wsUrl);
            
            this.ws.onopen = () => {
                console.log('✅ WebSocket 연결 성공');
                this.reconnectAttempts = 0;
                this.updateConnectionStatus('connected');
            };
            
            this.ws.onmessage = (event) => {
                this.handleWebSocketMessage(event.data);
            };
            
            this.ws.onclose = (event) => {
                console.log('⚠️ WebSocket 연결 종료:', event.code);
                this.updateConnectionStatus('disconnected');
                this.attemptReconnect();
            };
            
            this.ws.onerror = (error) => {
                console.error('❌ WebSocket 오류:', error);
                this.updateConnectionStatus('disconnected');
            };
            
        } catch (error) {
            console.error('❌ WebSocket 연결 실패:', error);
            this.updateConnectionStatus('disconnected');
        }
    }
    
    attemptReconnect() {
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), 30000);
            
            console.log(`🔄 WebSocket 재연결 시도 ${this.reconnectAttempts}/${this.maxReconnectAttempts} (${delay}ms 후)`);
            
            setTimeout(() => {
                this.connectWebSocket();
            }, delay);
        } else {
            console.error('💥 WebSocket 재연결 포기');
            this.addLogMessage('실시간 연결이 끊어졌습니다. 페이지를 새로고침해주세요.', 'error');
        }
    }
    
    updateConnectionStatus(status) {
        if (!this.elements.connectionDot || !this.elements.connectionText) return;
        
        // 상태 점 업데이트
        this.elements.connectionDot.className = 'status-dot';
        this.elements.connectionDot.classList.add(status);
        
        // 상태 텍스트 업데이트
        const statusTexts = {
            connected: '연결됨',
            disconnected: '연결 끊김',
            searching: '검색 중'
        };
        
        this.elements.connectionText.textContent = statusTexts[status] || '알 수 없음';
    }
    
    // =================== WebSocket 메시지 처리 ===================
    handleWebSocketMessage(data) {
        try {
            const message = JSON.parse(data);
            
            switch (message.type) {
                case 'log':
                    this.addLogMessage(message.message, this.getLogType(message.message));
                    break;
                    
                case 'cycle_start':
                    this.onCycleStart();
                    this.addLogMessage(message.message, 'info');
                    break;
                    
                case 'search_started':
                    this.onSearchStarted();
                    this.addLogMessage(message.message, 'info');
                    break;
                    
                case 'drug_found':
                    this.onDrugFound(message.drug, message.progress);
                    break;
                case 'drug_soldout':
                    this.onDrugFound(message.drug, message.progress);
                    break;
                case 'drug_error':
                    this.onDrugError(message.drug, message.progress);
                    break;
                    
                case 'search_completed':
                    this.onSearchCompleted(message.data);
                    break;
                    
                case 'search_stopped':
                    this.onSearchStopped();
                    this.addLogMessage(message.message, 'warning');
                    break;
                    
                case 'search_error':
                    this.onSearchError(message.message);
                    break;
                    
                default:
                    console.log('🤔 알 수 없는 메시지:', message.type);
            }
        } catch (error) {
            console.error('❌ 메시지 파싱 오류:', error);
        }
    }
    
    getLogType(message) {
        if (message.includes('✅') || message.includes('완료')) return 'success';
        if (message.includes('❌') || message.includes('오류') || message.includes('실패')) return 'error';
        if (message.includes('⚠️') || message.includes('경고')) return 'warning';
        if (message.includes('🔍') || message.includes('검색')) return 'search';
        return 'info';
    }
    
    // =================== 로그 관리 ===================
    addLogMessage(message, type = 'info') {
        if (!this.elements.logContainer) return;
        
        // 첫 번째 로그 메시지일 때 placeholder 제거
        const placeholder = this.elements.logContainer.querySelector('.log-placeholder');
        if (placeholder) {
            placeholder.remove();
        }
        
        const logLine = document.createElement('div');
        logLine.className = `log-line log-${type}`;
        
        const timestamp = new Date().toLocaleTimeString('ko-KR', {
            hour12: false,
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit'
        });
        
        logLine.textContent = `[${timestamp}] ${message}`;
        
        this.elements.logContainer.appendChild(logLine);
        
        // 자동 스크롤
        this.elements.logContainer.scrollTop = this.elements.logContainer.scrollHeight;
        
        // 로그 개수 제한 (성능 최적화)
        const logLines = this.elements.logContainer.querySelectorAll('.log-line');
        if (logLines.length > 150) {
            for (let i = 0; i < 50; i++) {
                logLines[i].remove();
            }
        }
    }
    
    clearLogs() {
        if (!this.elements.logContainer) return;
        
        this.elements.logContainer.innerHTML = `
            <div class="log-placeholder">
                <i class="bi bi-clock"></i>
                <span>로그가 정리되었습니다</span>
            </div>
        `;
    }
    
    // =================== 상태 로드 ===================
    async loadStatus() {
        try {
            const response = await fetch('/api/status');
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            
            const data = await response.json();
            
            this.updateFileInfo(data.files);
            this.updateDistributorStatus(data.config);
            this.updateSearchStatus(data.is_searching);
            
            // 최근 검색 결과 표시
            if (data.last_search) {
                this.displaySearchResults(data.last_search);
            }
            
        } catch (error) {
            console.error('❌ 상태 로드 실패:', error);
            this.showError('서버 연결에 문제가 있습니다');
        }
    }
    
    updateFileInfo(files) {
        // 약품 목록 수
        if (this.elements.drugCount) {
            this.elements.drugCount.textContent = files.drug_count || '-';
            this.updateDrugListTooltip(files.drug_list || [], files.drug_count || 0);
        }
        
        // 알림 제외 수
        if (this.elements.exclusionCount) {
            this.elements.exclusionCount.textContent = files.exclusion_count || '-';
            this.updateExclusionListTooltip(files.exclusion_list || [], files.exclusion_count || 0);
        }
    }
    
    updateDistributorStatus(config) {
        if (!this.elements.distributorStatus) return;
        
        const geoweb = config?.geoweb_configured || false;
        const baekje = config?.baekje_configured || false;
        
        // 설정된 도매상 수 계산
        let configuredCount = 0;
        const distributors = [];
        
        if (geoweb) {
            configuredCount++;
            distributors.push('지오영');
        }
        if (baekje) {
            configuredCount++;
            distributors.push('백제약품');
        }
        
        // 카드에는 숫자만 표시
        this.elements.distributorStatus.textContent = configuredCount.toString();
        
        // 툴팁 업데이트
        this.updateDistributorTooltip(distributors);
    }
    
    updateDistributorTooltip(distributors) {
        const statusCard = this.elements.distributorStatus.closest('.status-card');
        if (!statusCard) return;
        
        // 기존 툴팁 제거
        this.removeExistingTooltip(statusCard);
        
        // 새 툴팁 생성
        const tooltip = document.createElement('div');
        tooltip.className = 'distributor-tooltip';
        
        if (distributors.length === 0) {
            tooltip.innerHTML = `
                <div class="tooltip-item">
                    <i class="bi bi-x-circle" style="color: var(--danger)"></i>
                    <span>설정된 도매상 없음</span>
                </div>
            `;
        } else {
            tooltip.innerHTML = distributors.map(name => `
                <div class="tooltip-item">
                    <i class="bi bi-check-circle" style="color: var(--success)"></i>
                    <span>${name}</span>
                </div>
            `).join('');
        }
        
        statusCard.appendChild(tooltip);
    }
    
    updateDrugListTooltip(drugList, totalCount) {
        const statusCard = this.elements.drugCount.closest('.status-card');
        if (!statusCard) return;
        
        // 기존 툴팁 제거
        this.removeExistingTooltip(statusCard);
        
        // 새 툴팁 생성
        const tooltip = document.createElement('div');
        tooltip.className = 'status-tooltip';
        
        if (drugList.length === 0) {
            tooltip.innerHTML = `
                <div class="tooltip-item">
                    <i class="bi bi-inbox" style="color: var(--text-muted)"></i>
                    <span>검색 대상 약품이 없습니다</span>
                </div>
            `;
        } else {
            const items = drugList.map(drug => `
                <div class="tooltip-item">
                    <i class="bi bi-capsule" style="color: var(--primary)"></i>
                    <span>${drug}</span>
                </div>
            `).join('');
            
            const moreItems = totalCount > drugList.length ? `
                <div class="tooltip-more">
                    <span>...</span>
                </div>
            ` : '';
            
            tooltip.innerHTML = items + moreItems;
        }
        
        statusCard.appendChild(tooltip);
    }
    
    updateExclusionListTooltip(exclusionList, totalCount) {
        const statusCard = this.elements.exclusionCount.closest('.status-card');
        if (!statusCard) return;
        
        // 기존 툴팁 제거
        this.removeExistingTooltip(statusCard);
        
        // 새 툴팁 생성
        const tooltip = document.createElement('div');
        tooltip.className = 'status-tooltip';
        
        if (exclusionList.length === 0) {
            tooltip.innerHTML = `
                <div class="tooltip-item">
                    <i class="bi bi-bell" style="color: var(--success)"></i>
                    <span>모든 약품에 알림 활성화</span>
                </div>
            `;
        } else {
            const items = exclusionList.map(item => {
                // 날짜@약품명 형식 파싱
                const parts = item.split('@');
                const displayText = parts.length > 1 ? parts[1].trim() : item;
                
                return `
                    <div class="tooltip-item">
                        <i class="bi bi-bell-slash" style="color: var(--warning)"></i>
                        <span>${displayText}</span>
                    </div>
                `;
            }).join('');
            
            const moreItems = totalCount > exclusionList.length ? `
                <div class="tooltip-more">
                    <span>...</span>
                </div>
            ` : '';
            
            tooltip.innerHTML = items + moreItems;
        }
        
        statusCard.appendChild(tooltip);
    }
    
    updateErrorTooltip() {
        const statusCard = this.elements.errorCount?.closest('.summary-card.danger');
        if (!statusCard) return;
        
        // 기존 툴팁 제거
        this.removeExistingTooltip(statusCard);
        
        // 새 툴팁 생성
        const tooltip = document.createElement('div');
        tooltip.className = 'error-tooltip';
        
        if (this.errorDrugs.length === 0) {
            tooltip.innerHTML = `
                <div class="tooltip-item">
                    <i class="bi bi-check-circle" style="color: var(--success)"></i>
                    <span>오류 없음</span>
                </div>
            `;
        } else {
            const items = this.errorDrugs.slice(0, 5).map(error => `
                <div class="tooltip-item">
                    <i class="bi bi-exclamation-triangle" style="color: var(--danger)"></i>
                    <span title="${error.error}">${error.name}</span>
                </div>
            `).join('');
            
            const moreItems = this.errorDrugs.length > 5 ? `
                <div class="tooltip-more">
                    <span>외 ${this.errorDrugs.length - 5}개 더...</span>
                </div>
            ` : '';
            
            tooltip.innerHTML = items + moreItems;
        }
        
        statusCard.appendChild(tooltip);
    }
    
    removeExistingTooltip(statusCard) {
        const existingTooltips = statusCard.querySelectorAll('.distributor-tooltip, .status-tooltip, .error-tooltip');
        existingTooltips.forEach(tooltip => tooltip.remove());
    }
    
    updateSearchStatus(searching) {
        this.isSearching = searching;
        
		// 단일 액션 버튼 상태/라벨/아이콘 업데이트
		this.updateActionButton(searching);
        
        // 연결 상태 업데이트
        if (searching) {
            this.updateConnectionStatus('searching');
        } else if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.updateConnectionStatus('connected');
        }
    }
    
    // =================== 검색 제어 ===================
    async startSearch() {
        try {
            const response = await fetch('/api/search/start', { method: 'POST' });
            const data = await response.json();
            
			if (response.ok) {
				this.onSearchStarted();
                this.showSuccess('검색을 시작했습니다');
            } else {
                throw new Error(data.detail || '검색 시작 실패');
            }
        } catch (error) {
            console.error('❌ 검색 시작 오류:', error);
            this.showError(`검색 시작 실패: ${error.message}`);
        }
    }
    
    async stopSearch() {
        try {
            const response = await fetch('/api/search/stop', { method: 'POST' });
            const data = await response.json();
            
			if (response.ok) {
				this.onSearchStopped();
                this.showSuccess('검색을 중단했습니다');
            } else {
                throw new Error(data.detail || '검색 중단 실패');
            }
        } catch (error) {
            console.error('❌ 검색 중단 오류:', error);
            this.showError(`검색 중단 실패: ${error.message}`);
        }
    }
    
	// 단일 토글 동작
	async toggleSearch() {
		if (this.isSearching) {
			return this.stopSearch();
		}
		return this.startSearch();
	}

    // =================== 검색 이벤트 핸들러 ===================
    onCycleStart() {
        // 새 사이클 시작 - 화면 완전 초기화
        this.clearResults();
        this.clearCounters();
        this.errorDrugs = []; // 오류 목록 초기화
    }
    
    onSearchStarted() {
        this.isSearching = true;
        this.updateSearchStatus(true);
        
		// 시작 애니메이션 및 버튼 전환
		this.elements.actionBtn?.classList.add('searching');
		this.updateActionButton(true);
    }
    
    onDrugFound(drug, progress) {
        // 개별 약품 검색 완료 시 실시간 업데이트
        this.updateProgress(progress);
        if (!this.elements.searchResults.querySelector('.results-columns')) {
            this.clearResults();
        }
        this.addDrugToResults(drug);
        
        // 카운터 실시간 업데이트
        if (drug.has_stock) {
            const currentFound = parseInt(this.elements.foundCount?.textContent || '0');
            this.elements.foundCount.textContent = currentFound + 1;
        } else {
            const currentSoldout = parseInt(this.elements.soldoutCount?.textContent || '0');
            this.elements.soldoutCount.textContent = currentSoldout + 1;
        }
    }
    
    onSearchCompleted(data) {
        this.isSearching = false;
        this.updateSearchStatus(false);
        
        // 결과 애니메이션과 함께 업데이트
        this.animateCounter(this.elements.foundCount, data.found_count, 'success');
        this.animateCounter(this.elements.soldoutCount, data.soldout_count, 'warning');
        this.animateCounter(this.elements.errorCount, data.error_count, 'danger');
        
        // 마지막 업데이트 시간
        if (this.elements.lastUpdate) {
            this.elements.lastUpdate.textContent = new Date().toLocaleString('ko-KR');
        }
        
        this.addLogMessage(`🎉 검색 완료! 재고: ${data.found_count}개, 품절: ${data.soldout_count}개`, 'success');
        
        // 최신 결과 다시 로드 (약간의 지연 후)
        setTimeout(() => this.loadStatus(), 1500);
        
		// 완료 애니메이션 및 버튼 전환
		this.elements.actionBtn?.classList.remove('searching');
		this.updateActionButton(false);
    }
    
	onSearchStopped() {
        this.isSearching = false;
        this.updateSearchStatus(false);
		this.elements.actionBtn?.classList.remove('searching');
		this.updateActionButton(false);
    }
    
	onSearchError(message) {
        this.isSearching = false;
        this.updateSearchStatus(false);
        this.addLogMessage(`검색 중 오류가 발생했습니다: ${message}`, 'error');
		this.elements.actionBtn?.classList.remove('searching');
		this.updateActionButton(false);
    }
    
    // =================== UI 업데이트 유틸리티 ===================
    animateCounter(element, targetValue, type) {
        if (!element) return;
        
        const startValue = parseInt(element.textContent) || 0;
        const duration = 1000;
        const steps = 30;
        const increment = (targetValue - startValue) / steps;
        
        let currentStep = 0;
        const timer = setInterval(() => {
            currentStep++;
            const currentValue = Math.round(startValue + (increment * currentStep));
            element.textContent = currentValue;
            
            if (currentStep >= steps) {
                clearInterval(timer);
                element.textContent = targetValue;
                
                // 완료 시 강조 효과
                if (targetValue > 0 && type === 'success') {
                    element.parentElement?.classList.add('highlight');
                    setTimeout(() => {
                        element.parentElement?.classList.remove('highlight');
                    }, 2000);
                }
            }
        }, duration / steps);
    }
    
    clearCounters() {
        const counters = [this.elements.foundCount, this.elements.soldoutCount, this.elements.errorCount];
        counters.forEach(counter => {
            if (counter) counter.textContent = '0';
        });
    }
    
    clearResults() {

        if (this.elements.searchResults) {
            this.elements.searchResults.innerHTML = `
                <div class="results-columns">
                    <div class="results-col" id="col-found">
                        <div class="col-header success"><i class="bi bi-check-circle"></i> 재고 발견</div>
                        <div class="col-body"></div>
                    </div>
                    <div class="results-col" id="col-soldout">
                        <div class="col-header warning"><i class="bi bi-x-circle"></i> 품절</div>
                        <div class="col-body"></div>
                    </div>
                </div>
            `;
        }

        // 메서드 종료 (clearResults)
    }

	// 액션 버튼 상태 갱신
	updateActionButton(searching) {
		const btn = this.elements.actionBtn;
		if (!btn) return;
		const icon = btn.querySelector('i');
		const label = btn.querySelector('span');
		if (searching) {
			btn.classList.remove('primary');
			btn.classList.add('danger');
			if (icon) icon.className = 'bi bi-stop-circle';
			if (label) label.textContent = '검색 중단';
		} else {
			btn.classList.remove('danger');
			btn.classList.add('primary');
			if (icon) icon.className = 'bi bi-play-circle';
			if (label) label.textContent = '검색 시작';
		}
		btn.disabled = false; // 토글 버튼은 항상 활성화
	}
    
    updateProgress(progress) {
        // 진행률 표시 (필요 시 추가)
        const percentage = Math.round((progress.current / progress.total) * 100);
        console.log(`검색 진행률: ${percentage}% (${progress.current}/${progress.total})`);
    }
    
    addDrugToResults(drug) {
        // 실시간으로 개별 약품을 결과에 추가
        if (!this.elements.searchResults) return;
        
        // 컬럼 컨테이너가 없다면 초기화
        if (!this.elements.searchResults.querySelector('.results-columns')) {
            this.clearResults();
        }

        const col = drug.has_stock
            ? document.querySelector('#col-found .col-body')
            : document.querySelector('#col-soldout .col-body');
        if (!col) return;
        
        const drugCard = document.createElement('div');
        drugCard.className = `drug-result-card ${drug.has_stock ? 'has-stock' : 'soldout'} fade-in`;
        
        const statusIcon = drug.has_stock ? 
            '<i class="bi bi-check-circle text-success"></i>' : 
            '<i class="bi bi-x-circle text-warning"></i>';
            
        drugCard.innerHTML = `
            <div class="drug-header">
                ${statusIcon}
                <h5>${drug.name}</h5>
            </div>
            <div class="drug-stock">
                <span class="stock-item">메인: ${drug.main_stock}</span>
                <span class="stock-item">인천: ${drug.incheon_stock}</span>
            </div>
        `;
        
        col.appendChild(drugCard);
        
        // 스크롤을 최신 결과로 이동
        drugCard.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }

    onDrugError(drug, progress) {
        // 진행률 갱신
        this.updateProgress(progress);
        
        // 오류 약품을 목록에 추가
        this.errorDrugs.push({
            name: drug.name,
            error: drug.error || '오류 발생'
        });

        // 에러 카운터 증가
        const currentErr = parseInt(this.elements.errorCount?.textContent || '0');
        this.elements.errorCount.textContent = currentErr + 1;
        
        // 오류 툴팁 업데이트
        this.updateErrorTooltip();
    }
    
    displaySearchResults(searchData) {
        if (!this.elements.searchResults) return;
        
        const foundDrugs = searchData.found_drugs || [];
        const soldoutDrugs = searchData.soldout_drugs || [];
        
        if (foundDrugs.length > 0) {
            // 재고가 있는 약품들을 표시
            const resultsHtml = `
                <div class="results-content-active">
                    <div class="alert-success">
                        <h4><i class="bi bi-check-circle"></i> 재고 발견된 약품 ${foundDrugs.length}개</h4>
                    </div>
                    <div class="drugs-grid">
                        ${foundDrugs.slice(0, 6).map(drug => `
                            <div class="drug-card">
                                <h5>${drug.name}</h5>
                                <div class="drug-info">
                                    <span class="stock-info">${drug.wholesale || '지오영'}</span>
                                    ${drug.main_stock ? `<span class="stock-badge">메인: ${drug.main_stock}</span>` : ''}
                                    ${drug.incheon_stock ? `<span class="stock-badge">인천: ${drug.incheon_stock}</span>` : ''}
                                </div>
                            </div>
                        `).join('')}
                        ${foundDrugs.length > 6 ? `
                            <div class="more-drugs">
                                <span>외 ${foundDrugs.length - 6}개 더...</span>
                            </div>
                        ` : ''}
                    </div>
                </div>
            `;
            this.elements.searchResults.innerHTML = resultsHtml;
        } else {
            // 재고가 없는 경우
            this.elements.searchResults.innerHTML = `
                <div class="empty-state">
                    <i class="bi bi-inbox"></i>
                    <h4>현재 재고가 있는 약품이 없습니다</h4>
                    <p>모든 약품이 품절 상태입니다. 나중에 다시 확인해보세요.</p>
                </div>
            `;
        }
        
        // 카운터 업데이트
        this.elements.foundCount.textContent = foundDrugs.length;
        this.elements.soldoutCount.textContent = soldoutDrugs.length;
        this.elements.errorCount.textContent = searchData.errors?.length || 0;
    }
    
    // =================== 알림 및 피드백 ===================
    showSuccess(message) {
        this.showNotification(message, 'success');
    }
    
    showError(message) {
        this.showNotification(message, 'error');
    }
    
    showNotification(message, type) {
        // 간단한 토스트 알림 구현
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.textContent = message;
        
        // 스타일 적용
        Object.assign(toast.style, {
            position: 'fixed',
            top: '20px',
            right: '20px',
            padding: '12px 20px',
            borderRadius: '8px',
            color: 'white',
            background: type === 'success' ? 'var(--success)' : 'var(--danger)',
            boxShadow: 'var(--shadow-lg)',
            zIndex: '1000',
            transform: 'translateX(100%)',
            transition: 'transform 0.3s ease'
        });
        
        document.body.appendChild(toast);
        
        // 애니메이션
        setTimeout(() => {
            toast.style.transform = 'translateX(0)';
        }, 100);
        
        // 자동 제거
        setTimeout(() => {
            toast.style.transform = 'translateX(100%)';
            setTimeout(() => {
                document.body.removeChild(toast);
            }, 300);
        }, 3000);
    }
    
}


// DOM 로드 완료 시 앱 초기화
document.addEventListener('DOMContentLoaded', () => {
    window.modernDrugApp = new ModernDrugSearchApp();
    
    // 도매상 모달 초기화
    window.distributorModal = new DistributorModal(window.modernDrugApp);
});