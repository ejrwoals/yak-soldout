// 약품 재고 자동 검색 - 모던 대시보드 JavaScript

// 도매상 메타데이터 맵 (name → {id, color})
// /api/status 응답의 config.distributors 배열로 초기화됩니다.
let DISTRIBUTOR_MAP = {};

function buildDistributorMap(distributors) {
    DISTRIBUTOR_MAP = Object.fromEntries(
        (distributors || []).map(d => [d.name, { id: d.id, color: d.color }])
    );
}

function getDistributorInfo(distributorName) {
    return DISTRIBUTOR_MAP[distributorName] || { id: 'unknown', color: '#475569' };
}

class ModernDrugSearchApp {
    constructor() {
        // 상태
        this.isSearching = false;
        
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
        this.setupWebSocketManager();
        this.loadStatus();
        
        // 주기적 상태 업데이트
        setInterval(() => this.loadStatus(), 15000);
        
        console.log('🚀 품절 약품 체커가 시작되었습니다');
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
    
    // =================== WebSocket 설정 ===================
    setupWebSocketManager() {
        // UI 요소 설정
        window.webSocketManager.setUIElements({
            connectionDot: this.elements.connectionDot,
            connectionText: this.elements.connectionText
        });
        
        // 이벤트 리스너 등록
        window.webSocketManager.addEventListener('connected', () => {
            console.log('✅ WebSocket 연결됨');
        });
        
        window.webSocketManager.addEventListener('disconnected', () => {
            console.log('⚠️ WebSocket 연결 해제됨');
        });
        
        window.webSocketManager.addEventListener('reconnect-failed', () => {
            this.addLogMessage('실시간 연결이 끊어졌습니다. 페이지를 새로고침해주세요.', 'error');
        });
        
        // 메시지 처리
        window.webSocketManager.addEventListener('message', (event) => {
            this.handleWebSocketMessage(event.detail.message);
        });
        
        // 연결 시작
        window.webSocketManager.connect();
    }
    
    // =================== WebSocket 메시지 처리 ===================
    handleWebSocketMessage(message) {
        try {
            
            switch (message.type) {
                case 'log':
                    this.addLogMessage(message.message, this.getLogType(message.message));
                    break;
                    
                case 'cycle_start':
                    this.onCycleStart(message);
                    this.addLogMessage(message.message, 'info');
                    break;
                    
                case 'cycle_countdown':
                    this.onCycleCountdown(message);
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
                
                case 'urgent_alert':
                    this.onUrgentAlert(message.drug);
                    break;
                    
                default:
                    console.log('🤔 알 수 없는 메시지:', message.type);
            }
        } catch (error) {
            console.error('❌ 메시지 파싱 오류:', error);
        }
    }
    
    getLogType(message) {
        if (message.includes('🚨') || message.includes('[긴급 알림]')) return 'urgent';
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
            const statusCard = this.elements.drugCount.closest('.status-card');
            window.tooltipManager.updateDrugListTooltip(statusCard, files.drug_list || [], files.drug_count || 0);
        }
        
        // 결과 표시 제외 수
        if (this.elements.exclusionCount) {
            this.elements.exclusionCount.textContent = files.exclusion_count || '-';
            const statusCard = this.elements.exclusionCount.closest('.status-card');
            window.tooltipManager.updateExclusionListTooltip(statusCard, files.exclusion_list || [], files.exclusion_count || 0);
        }
    }
    
    updateDistributorStatus(config) {
        if (!this.elements.distributorStatus) return;

        // API 응답의 distributors 배열 기반 (하드코딩 없음)
        const allDistributors = config?.distributors || [];

        // 레지스트리 맵 갱신
        buildDistributorMap(allDistributors);

        const configured = allDistributors.filter(d => d.configured);

        // 카드에는 숫자만 표시
        this.elements.distributorStatus.textContent = configured.length.toString();

        // 툴팁 업데이트
        const statusCard = this.elements.distributorStatus.closest('.status-card');
        window.tooltipManager.updateDistributorTooltip(statusCard, configured.map(d => d.name));
    }




    
    updateSearchStatus(searching) {
        this.isSearching = searching;
        
		// 단일 액션 버튼 상태/라벨/아이콘 업데이트
		this.updateActionButton(searching);
        
        // 연결 상태 업데이트
        if (searching) {
            window.webSocketManager.updateConnectionStatus('searching');
        } else if (window.webSocketManager.isConnected()) {
            window.webSocketManager.updateConnectionStatus('connected');
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
    onCycleStart(message) {
        // 새 사이클 시작 - 화면 완전 초기화
        this.clearResults();
        this.clearCounters();
        this.errorDrugs = []; // 오류 목록 초기화
        
        // 사이클 번호 표시 (있다면)
        if (message && message.cycle_number) {
            console.log(`🔄 사이클 #${message.cycle_number} 시작`);
            // UI에 사이클 번호 표시 (선택적)
            this.updateCycleInfo(message.cycle_number);
        }
    }
    
    onCycleCountdown(message) {
        // 카운트다운 메시지 처리
        if (message && message.remaining_minutes && message.next_cycle) {
            console.log(`⏰ 다음 사이클(#${message.next_cycle})까지 ${message.remaining_minutes}분 남음`);
            
            // 버튼 텍스트 업데이트 (카운트다운 표시)
            const btn = this.elements.actionBtn;
            if (btn && message.remaining_minutes <= 5) {
                const label = btn.querySelector('span');
                if (label) {
                    label.textContent = `다음 사이클까지 ${message.remaining_minutes}분`;
                }
            }
        }
    }
    
    updateCycleInfo(cycleNumber) {
        // 사이클 정보를 UI에 표시 (선택적)
        // 나중에 대시보드 헤더나 상태 표시에 활용 가능
        console.log(`현재 사이클: #${cycleNumber}`);
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
        
        // 사이클 정보 포함한 로그 메시지
        const cycleInfo = data.cycle_number ? ` (사이클 #${data.cycle_number})` : '';
        this.addLogMessage(`🎉 검색 완료${cycleInfo}! 재고: ${data.found_count}개, 품절: ${data.soldout_count}개`, 'success');
        
        // 최신 결과 다시 로드 (약간의 지연 후)
        setTimeout(() => this.loadStatus(), 1500);
        
        // 완료 애니메이션 및 버튼 전환
        this.elements.actionBtn?.classList.remove('searching');
        this.updateActionButton(false);
        
        // 버튼 텍스트를 원래대로 복구 (카운트다운 텍스트가 있었다면)
        const btn = this.elements.actionBtn;
        if (btn) {
            const label = btn.querySelector('span');
            if (label && label.textContent.includes('다음 사이클까지')) {
                label.textContent = '검색 중단';  // 계속 실행 중이므로 중단 버튼으로
            }
        }
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
                        <div class="col-header success"><i class="bi bi-check-circle"></i> 재고 있음</div>
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
        
        // exclusion 체크: 제외된 약품은 카드를 생성하지 않음
        if (drug.is_excluded_from_alert) {
            return;
        }
        
        // 컬럼 컨테이너가 없다면 초기화
        if (!this.elements.searchResults.querySelector('.results-columns')) {
            this.clearResults();
        }

        const col = drug.has_stock
            ? document.querySelector('#col-found .col-body')
            : document.querySelector('#col-soldout .col-body');
        if (!col) return;
        
        const drugCard = document.createElement('div');
        drugCard.className = 'drug-result-card fade-in';

        const statusIcon = drug.has_stock ?
            '<i class="bi bi-check-circle text-success"></i>' :
            '<i class="bi bi-x-circle text-warning"></i>';

        // 도매상 정보 추출 (distributor 필드 사용)
        const distributor = drug.distributor || '지오영';
        const distInfo = getDistributorInfo(distributor);
        const distributorName = distributor;
        const distributorClass = distInfo.id;
        drugCard.style.setProperty('--dist-color', distInfo.color);
        const distributorBadge = `<span class="distributor-badge">${distributor}</span>`;

        drugCard.innerHTML = `
            <div class="drug-header">
                <div class="drug-title">
                    ${statusIcon}
                    <h5>${drug.name}</h5>
                </div>
                <div class="drug-actions">
                    <button class="btn-exclusion" onclick="window.modernDrugApp.addToExclusion('${drug.name}', '${distributorName}', this)" title="결과 표시 제외 목록에 추가">
                        <i class="bi bi-eye-slash"></i>
                    </button>
                </div>
            </div>
            <div class="drug-stock">
                ${distributorBadge}
                <span class="stock-item">메인: ${drug.main_stock}</span>
                ${distributorClass === 'geoweb' && drug.incheon_stock !== '-' ?
                    `<span class="stock-item">타센터: ${drug.incheon_stock}</span>` : ''}
            </div>
        `;
        
        col.appendChild(drugCard);
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
        const statusCard = this.elements.errorCount?.closest('.summary-card.danger');
        window.tooltipManager.updateErrorTooltip(statusCard, this.errorDrugs);
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
                        <h4><i class="bi bi-check-circle"></i> 재고가 있는 약품 ${foundDrugs.length}건</h4>
                    </div>
                    <div class="drugs-grid">
                        ${foundDrugs.slice(0, 6).map(drug => {
                            const distributor = drug.distributor || '지오영';
                            const _di = getDistributorInfo(distributor);
                            const distributorName = distributor;
                            const distributorClass = _di.id;
                            
                            return `
                            <div class="drug-card" style="--dist-color: ${_di.color}">
                                <div class="drug-card-header">
                                    <h5>${drug.name}</h5>
                                    <span class="distributor-badge">${distributorName}</span>
                                </div>
                                <div class="drug-info">
                                    ${drug.main_stock ? `<span class="stock-badge">메인: ${drug.main_stock}</span>` : ''}
                                    ${distributorClass === 'geoweb' && drug.incheon_stock && drug.incheon_stock !== '-' ?
                                        `<span class="stock-badge">타센터: ${drug.incheon_stock}</span>` : ''}
                                </div>
                            </div>
                        `;
                        }).join('')}
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
        window.notificationManager.showSuccess(message);
    }
    
    showError(message) {
        window.notificationManager.showError(message);
    }
    
    // =================== 긴급 알림 처리 ===================
    onUrgentAlert(drug) {
        // 브라우저 알림 API 확인 및 요청
        if ('Notification' in window) {
            if (Notification.permission === 'default') {
                Notification.requestPermission().then(permission => {
                    if (permission === 'granted') {
                        this.showUrgentNotification(drug);
                    }
                });
            } else if (Notification.permission === 'granted') {
                this.showUrgentNotification(drug);
            }
        }
        
        // 페이지 내 팝업 알림도 표시
        this.showUrgentPopup(drug);
        
        // 로그에도 긴급 알림 메시지 추가
        const logDrugName = drug.name + (drug.unit ? ` [${drug.unit}]` : '');
        this.addLogMessage(`🚨 [긴급 알림] ${logDrugName} 재고 발견! (${drug.distributor})`, 'urgent');
    }
    
    showUrgentNotification(drug) {
        // 브라우저 알림 생성
        const drugDisplayName = drug.name + (drug.unit ? ` [${drug.unit}]` : '');
        const notification = new Notification('🚨 긴급 재고 알림', {
            body: `${drugDisplayName}\n재고: ${drug.main_stock}${drug.incheon_stock !== '-' ? ` / 타센터: ${drug.incheon_stock}` : ''}\n도매상: ${drug.distributor}`,
            icon: '/static/favicon.ico',
            tag: `urgent-${drug.name}`, // 중복 알림 방지
            requireInteraction: true // 사용자가 클릭할 때까지 유지
        });
        
        notification.onclick = () => {
            window.focus(); // 브라우저 창을 앞으로 가져오기
            notification.close();
        };
        
        // 10초 후 자동 닫기
        setTimeout(() => notification.close(), 10000);
    }
    
    showUrgentPopup(drug) {
        // 모달 형태의 팝업 생성
        const popup = document.createElement('div');
        popup.className = 'urgent-alert-popup';
        popup.innerHTML = `
            <div class="urgent-alert-content">
                <div class="urgent-alert-header">
                    <i class="bi bi-bell-fill urgent-icon"></i>
                    <h3>긴급 재고 알림</h3>
                    <button class="urgent-close-btn" onclick="this.closest('.urgent-alert-popup').remove()">
                        <i class="bi bi-x-lg"></i>
                    </button>
                </div>
                <div class="urgent-alert-body">
                    <div class="urgent-drug-info">
                        <h4>${drug.name}${drug.unit ? ` [${drug.unit}]` : ''}</h4>
                        <div class="urgent-stock-info">
                            ${drug.specifications && drug.specifications.length > 0 ? 
                                drug.specifications.map(spec => 
                                    `<div class="stock-item">${spec.unit_display}: ${spec.main_display}</div>`
                                ).join('') :
                                `<span class="stock-item">메인: ${drug.main_stock}</span>
                                ${drug.incheon_stock !== '-' ? `<span class="stock-item">타센터: ${drug.incheon_stock}</span>` : ''}`
                            }
                        </div>
                        <div class="urgent-distributor" style="--dist-color: ${getDistributorInfo(drug.distributor).color}">
                            <span class="distributor-badge">${drug.distributor}</span>
                        </div>
                    </div>
                </div>
                <div class="urgent-alert-footer">
                    <div class="auto-close-countdown">
                        <span class="countdown-text">30초 후 자동으로 닫힘</span>
                    </div>
                    <div class="urgent-question">
                        앞으로 해당 약품의 긴급 알림 설정을 해제하시겠습니까?
                    </div>
                    <div class="urgent-buttons">
                        <button class="btn-cancel">취소</button>
                        <button class="btn-confirm">확인</button>
                    </div>
                </div>
            </div>
        `;
        
        document.body.appendChild(popup);
        
        // 애니메이션 효과
        setTimeout(() => popup.classList.add('show'), 10);
        
        // 카운트다운 기능
        let countdownSeconds = 30;
        const countdownElement = popup.querySelector('.countdown-text');
        
        const updateCountdown = () => {
            if (countdownSeconds > 0) {
                countdownElement.textContent = `${countdownSeconds}초 후 자동으로 닫힘`;
                countdownSeconds--;
                setTimeout(updateCountdown, 1000);
            }
        };
        
        // 카운트다운 시작 (1초 후부터)
        setTimeout(updateCountdown, 1000);
        
        // 자동 제거 (30초 후)
        const autoCloseTimeout = setTimeout(() => {
            if (popup.parentNode) {
                popup.classList.remove('show');
                setTimeout(() => popup.remove(), 300);
            }
        }, 30000);
        
        // 버튼 이벤트 처리
        const confirmBtn = popup.querySelector('.btn-confirm');
        const cancelBtn = popup.querySelector('.btn-cancel');
        const closeBtn = popup.querySelector('.urgent-close-btn');
        
        const manualClose = () => {
            clearTimeout(autoCloseTimeout);
            popup.classList.remove('show');
            setTimeout(() => popup.remove(), 300);
        };
        
        // 취소 버튼 - 단순히 팝업 닫기
        cancelBtn.onclick = manualClose;
        if (closeBtn) closeBtn.onclick = manualClose;
        
        // 확인 버튼 - 긴급 알림 해제 API 호출
        confirmBtn.onclick = async () => {
            try {
                confirmBtn.disabled = true;
                confirmBtn.textContent = '해제 중...';
                
                const response = await fetch('/api/drug-urgent-toggle', {
                    method: 'PUT',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        drugName: drug.original_drug_name || drug.name  // 백제인 경우 원래 약품명 사용
                    })
                });
                
                if (response.ok) {
                    const result = await response.json();
                    console.log('긴급 알림 해제 성공:', result.message);
                    
                    // 성공 메시지 표시 후 팝업 닫기
                    confirmBtn.textContent = '해제됨';
                    setTimeout(() => {
                        manualClose();
                    }, 1000);
                } else {
                    const error = await response.json();
                    throw new Error(error.detail || '해제 실패');
                }
            } catch (error) {
                console.error('긴급 알림 해제 오류:', error);
                confirmBtn.disabled = false;
                confirmBtn.textContent = '확인';
                alert(`긴급 알림 해제 실패: ${error.message}`);
            }
        };
    }
    
    // =================== 결과 표시 제외 처리 ===================
    async addToExclusion(drugName, distributor, buttonElement) {
        try {
            // 버튼 상태 변경 (로딩)
            const originalHtml = buttonElement.innerHTML;
            buttonElement.innerHTML = '<i class="bi bi-hourglass-split"></i>';
            buttonElement.disabled = true;
            
            const response = await fetch('/api/exclusion-add', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    drugName: drugName,
                    distributor: distributor
                })
            });
            
            const result = await response.json();
            
            if (response.ok) {
                // 성공 시 버튼 상태 변경
                buttonElement.innerHTML = '<i class="bi bi-check-circle"></i>';
                buttonElement.classList.add('btn-exclusion-added');
                buttonElement.title = '제외 목록에 추가됨';
                
                // 성공 메시지 표시
                this.showSuccess(result.message);
                
                // exclusionCount 실시간 업데이트
                this.updateExclusionCount();
                
                // 카드를 심플하게 제거
                const card = buttonElement.closest('.drug-result-card');
                if (card) {
                    setTimeout(() => {
                        // 페이드아웃과 살짝 위로 이동
                        card.style.transition = 'opacity 0.3s ease, transform 0.3s ease';
                        card.style.opacity = '0';
                        card.style.transform = 'translateY(-10px)';
                        
                        // 페이드아웃 완료 후 높이 축소
                        setTimeout(() => {
                            card.style.transition = 'height 0.2s ease, margin 0.2s ease, padding 0.2s ease';
                            card.style.height = '0';
                            card.style.marginBottom = '0';
                            card.style.paddingTop = '0';
                            card.style.paddingBottom = '0';
                            card.style.overflow = 'hidden';
                            
                            // 완전 제거
                            setTimeout(() => {
                                card.remove();
                                this.updateFoundCount();
                            }, 200);
                        }, 300);
                    }, 100);
                }
                
            } else {
                // 실패 시 원래 상태로 복원
                buttonElement.innerHTML = originalHtml;
                buttonElement.disabled = false;
                this.showError(result.detail || '제외 목록 추가에 실패했습니다');
            }
            
        } catch (error) {
            // 오류 시 원래 상태로 복원
            buttonElement.innerHTML = '<i class="bi bi-eye-slash"></i>';
            buttonElement.disabled = false;
            this.showError('제외 목록 추가 중 오류가 발생했습니다');
            console.error('Exclusion add error:', error);
        }
    }
    
    // =================== 상태 실시간 업데이트 ===================
    async updateExclusionCount() {
        try {
            const response = await fetch('/api/exclusion-list');
            if (response.ok) {
                const data = await response.json();
                const exclusionCount = data.exclusions?.length || 0;
                
                // exclusionCount 업데이트
                if (this.elements.exclusionCount) {
                    this.elements.exclusionCount.textContent = exclusionCount;
                }
                
                // 툴팁도 업데이트 (처음 5개만)
                const statusCard = this.elements.exclusionCount?.closest('.summary-card.info');
                if (statusCard && window.tooltipManager) {
                    const excludedNames = data.exclusions.slice(0, 5).map(item => item.drugName || '');
                    window.tooltipManager.updateExclusionTooltip(statusCard, excludedNames);
                }
                
                // 현재 표시된 카드들 중 exclusion list에 있는 것들 실시간 제거
                this.filterExcludedCards(data.exclusions);
            }
        } catch (error) {
            console.error('Exclusion count update error:', error);
        }
    }
    
    filterExcludedCards(exclusions) {
        // exclusion list에 있는 약품명들 추출
        const excludedNames = exclusions.map(item => item.drugName);
        
        // 현재 표시된 모든 카드 확인
        const allCards = document.querySelectorAll('.drug-result-card');
        
        allCards.forEach(card => {
            const drugNameElement = card.querySelector('h5');
            if (drugNameElement) {
                const drugName = drugNameElement.textContent.trim();
                
                // exclusion list에 있는 약품이면 카드 제거
                if (excludedNames.includes(drugName)) {
                    card.style.transition = 'opacity 0.3s ease, transform 0.3s ease';
                    card.style.opacity = '0';
                    card.style.transform = 'translateY(-10px)';
                    
                    setTimeout(() => {
                        card.remove();
                        this.updateFoundCount();
                    }, 300);
                }
            }
        });
    }
    
    updateFoundCount() {
        // 현재 표시되고 있는 카드 수 카운트
        const foundCards = document.querySelectorAll('#col-found .drug-result-card');
        const soldoutCards = document.querySelectorAll('#col-soldout .drug-result-card');
        
        const foundCount = foundCards.length;
        const soldoutCount = soldoutCards.length;
        
        // 카운트 업데이트
        if (this.elements.foundCount) {
            this.elements.foundCount.textContent = foundCount;
        }
        if (this.elements.soldoutCount) {
            this.elements.soldoutCount.textContent = soldoutCount;
        }
        
        // 재고가 모두 사라진 경우 빈 상태 표시
        if (foundCount === 0) {
            const colFound = document.querySelector('#col-found .col-body');
            if (colFound) {
                colFound.innerHTML = `
                    <div class="empty-state-small">
                        <i class="bi bi-inbox"></i>
                        <p>표시할 재고가 없습니다</p>
                    </div>
                `;
            }
        }
        
        // 품절이 모두 사라진 경우 빈 상태 표시
        if (soldoutCount === 0) {
            const colSoldout = document.querySelector('#col-soldout .col-body');
            if (colSoldout) {
                colSoldout.innerHTML = `
                    <div class="empty-state-small">
                        <i class="bi bi-inbox"></i>
                        <p>표시할 품절이 없습니다</p>
                    </div>
                `;
            }
        }
    }
    
}


// DOM 로드 완료 시 앱 초기화
document.addEventListener('DOMContentLoaded', () => {
    window.modernDrugApp = new ModernDrugSearchApp();
    
    // 도매상 모달 초기화
    window.distributorModal = new DistributorModal(window.modernDrugApp);
    
    // 약품 목록 모달 초기화
    window.drugListModal = new DrugListModal(window.modernDrugApp);
    
    // 결과 표시 제외 목록 모달 초기화
    window.exclusionListModal = new ExclusionListModal(window.modernDrugApp);
    
    // 시스템 설정 모달 초기화
    window.systemSettingsModal = new SystemSettingsModal(window.modernDrugApp);
});