// 알림 제외 목록 편집 모달 관리 클래스

class ExclusionListModal {
    constructor(mainApp) {
        this.app = mainApp;
        this.modal = document.getElementById('exclusionListModal');
        this.exclusionListContainer = document.getElementById('exclusionListContainer');
        this.saveBtn = document.getElementById('saveExclusionListBtn');
        
        // 현재 알림 제외 목록 (로컬 상태)
        this.currentExclusions = [];
        // 원본 알림 제외 목록 (변경사항 추적용)
        this.originalExclusions = [];
        
        this.init();
    }
    
    init() {
        // 이벤트 리스너 등록
        document.getElementById('exclusionListCard')?.addEventListener('click', () => this.open());
        document.getElementById('closeExclusionListModal')?.addEventListener('click', () => this.close());
        document.getElementById('cancelExclusionListBtn')?.addEventListener('click', () => this.close());
        document.getElementById('saveExclusionListBtn')?.addEventListener('click', () => this.save());
        
        // 모달 외부 클릭 시 닫기
        this.modal?.addEventListener('click', (e) => {
            if (e.target === this.modal) {
                this.close();
            }
        });
        
        // ESC 키로 모달 닫기
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && this.modal?.classList.contains('show')) {
                this.close();
            }
        });
    }
    
    async open() {
        try {
            // 현재 알림 제외 목록 로드
            const response = await fetch('/api/exclusion-list');
            if (!response.ok) throw new Error('알림 제외 목록 로드 실패');
            
            const data = await response.json();
            this.currentExclusions = JSON.parse(JSON.stringify(data.exclusions)); // 깊은 복사
            this.originalExclusions = JSON.parse(JSON.stringify(data.exclusions)); // 원본도 깊은 복사
            
            // alert_exclusion_days 값으로 텍스트 업데이트
            await this.updateExclusionInfoText();
            
            this.renderExclusionList();
            this.updateSaveButtonState(); // 초기 저장 버튼 상태 설정
            
            // 모달 표시
            this.modal.classList.add('show');
            
        } catch (error) {
            console.error('알림 제외 목록 로드 오류:', error);
            this.app.showError('알림 제외 목록을 불러오는데 실패했습니다');
        }
    }
    
    close() {
        this.modal?.classList.remove('show');
    }
    
    async updateExclusionInfoText() {
        try {
            const response = await fetch('/api/status');
            if (!response.ok) throw new Error('설정 로드 실패');
            
            const data = await response.json();
            const alertExclusionDays = data.config?.alert_exclusion_days || 7;
            
            const infoTextElement = document.getElementById('exclusionInfoText');
            if (infoTextElement) {
                infoTextElement.textContent = `고정하지 않은 항목은 ${alertExclusionDays}일 후 다시 알림 대상이 됩니다`;
            }
        } catch (error) {
            console.error('설정 로드 오류:', error);
            // 오류 시 기본값 7일 사용
            const infoTextElement = document.getElementById('exclusionInfoText');
            if (infoTextElement) {
                infoTextElement.textContent = `고정하지 않은 항목은 7일 후 다시 알림 대상이 됩니다`;
            }
        }
    }
    
    removeExclusion(index) {
        if (index >= 0 && index < this.currentExclusions.length) {
            const exclusion = this.currentExclusions[index];
            this.currentExclusions.splice(index, 1);
            this.renderExclusionList();
            this.updateSaveButtonState();
            this.app.showSuccess(`'${exclusion.drugName}'이(가) 제거되었습니다`);
        }
    }
    
    togglePin(index) {
        if (index >= 0 && index < this.currentExclusions.length) {
            const exclusion = this.currentExclusions[index];
            exclusion.isPinned = !exclusion.isPinned;
            
            // 핀 상태 변경 시 현재 날짜로 업데이트 (한국 표준시간)
            const kstDate = new Date(Date.now() + (9 * 60 * 60 * 1000)); // UTC + 9시간
            exclusion.date = kstDate.toISOString().slice(0, 19); // YYYY-MM-DDTHH:mm:ss 형식
            
            // 핀 상태 변경 시 목록 다시 정렬
            this.sortExclusions();
            this.renderExclusionList();
            this.updateSaveButtonState();
            
            const status = exclusion.isPinned ? '고정 제외' : '기간 제외';
            this.app.showSuccess(`'${exclusion.drugName}'이(가) ${status}로 변경되었습니다`);
        }
    }
    
    sortExclusions() {
        // 비핀 항목(상단) -> 핀 항목(하단), 각각 날짜 최신순
        this.currentExclusions.sort((a, b) => {
            // 먼저 핀 상태로 분류
            if (a.isPinned !== b.isPinned) {
                return a.isPinned ? 1 : -1; // 핀되지 않은 항목이 먼저
            }
            
            // 같은 핀 상태 내에서는 날짜 최신순
            const dateA = new Date(a.date);
            const dateB = new Date(b.date);
            return dateB - dateA; // 최신 날짜가 먼저
        });
    }
    
    renderExclusionList() {
        if (!this.exclusionListContainer) return;
        
        if (this.currentExclusions.length === 0) {
            this.exclusionListContainer.innerHTML = `
                <div class="empty-exclusion-list">
                    <i class="bi bi-bell"></i>
                    <p>알림 제외된 약품이 없습니다</p>
                    <p class="text-muted">모든 약품에 대해 알림을 받고 있습니다</p>
                </div>
            `;
            return;
        }
        
        // 핀된 항목과 일반 항목 분리
        const unpinnedItems = this.currentExclusions.filter(item => !item.isPinned);
        const pinnedItems = this.currentExclusions.filter(item => item.isPinned);
        
        let html = `
            <div class="exclusion-list-header">
                <span class="exclusion-count">총 ${this.currentExclusions.length}개 제외</span>
            </div>
            <div class="exclusion-items">
                ${this.currentExclusions.map((exclusion, index) => {
                    return this.renderExclusionItem(exclusion, index);
                }).join('')}
            </div>
        `;
        
        this.exclusionListContainer.innerHTML = html;
    }
    
    renderExclusionItem(exclusion, index) {
        const date = new Date(exclusion.date);
        const formatDate = date.toLocaleDateString('ko-KR', {
            year: 'numeric',
            month: '2-digit',
            day: '2-digit'
        });
        
        const isPinned = exclusion.isPinned;
        const pinButtonClass = isPinned ? 'pinned' : '';
        const pinIcon = isPinned ? 'bi-pin-fill' : 'bi-pin';
        
        return `
            <div class="exclusion-item ${isPinned ? 'pinned' : ''}" data-index="${index}">
                <div class="exclusion-info">
                    <div class="exclusion-main">
                        ${isPinned ? '<i class="bi bi-pin-fill pin-indicator"></i>' : ''}
                        <span class="exclusion-drug-name">${exclusion.drugName}</span>
                    </div>
                    <div class="exclusion-meta">
                        <span class="exclusion-distributor">${exclusion.distributor}</span>
                        <span class="exclusion-separator">•</span>
                        <span class="exclusion-date">${formatDate}</span>
                    </div>
                </div>
                <div class="exclusion-actions">
                    <button class="exclusion-pin-btn ${pinButtonClass}" 
                            onclick="window.exclusionListModal.togglePin(${index})"
                            title="${isPinned ? '기간 제외로 변경' : '고정 제외로 변경'}">
                        <i class="bi ${pinIcon}"></i>
                    </button>
                    <button class="exclusion-remove-btn" 
                            onclick="window.exclusionListModal.removeExclusion(${index})"
                            title="제외 목록에서 제거">
                        <i class="bi bi-x-lg"></i>
                    </button>
                </div>
            </div>
        `;
    }
    
    // 변경사항 감지
    hasChanges() {
        // 길이가 다르면 변경됨
        if (this.currentExclusions.length !== this.originalExclusions.length) {
            return true;
        }
        
        // 순서에 상관없이 내용 기반으로 비교 (정렬로 인한 순서 변경 무시)
        // 현재 항목 중 하나라도 원본과 다르거나 없으면 변경됨
        const hasCurrentChanges = this.currentExclusions.some(current => {
            const original = this.originalExclusions.find(orig => 
                orig.drugName === current.drugName &&
                orig.distributor === current.distributor &&
                orig.date === current.date
            );
            
            // 원본이 없거나 핀 상태가 다르면 변경됨
            return !original || current.isPinned !== original.isPinned;
        });
        
        // 원본 항목 중 하나라도 현재에 없으면 변경됨 (삭제된 경우)
        const hasOriginalChanges = this.originalExclusions.some(original => {
            const current = this.currentExclusions.find(curr => 
                curr.drugName === original.drugName &&
                curr.distributor === original.distributor &&
                curr.date === original.date
            );
            
            return !current;
        });
        
        return hasCurrentChanges || hasOriginalChanges;
    }
    
    // 저장 버튼 상태 업데이트
    updateSaveButtonState() {
        if (!this.saveBtn) return;
        
        const hasChanges = this.hasChanges();
        this.saveBtn.disabled = !hasChanges;
        
        if (hasChanges) {
            this.saveBtn.classList.remove('disabled');
        } else {
            this.saveBtn.classList.add('disabled');
        }
    }
    
    async save() {
        try {
            // 서버로 업데이트된 알림 제외 목록 전송
            const response = await fetch('/api/exclusion-list', {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ exclusions: this.currentExclusions })
            });
            
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || '저장 실패');
            }
            
            this.app.showSuccess('알림 제외 목록이 저장되었습니다');
            
            // 저장 성공 시 원본 데이터 업데이트 (깊은 복사)
            this.originalExclusions = JSON.parse(JSON.stringify(this.currentExclusions));
            this.updateSaveButtonState();
            
            this.close();
            
            // 상태 새로고침
            setTimeout(() => this.app.loadStatus(), 1000);
            
        } catch (error) {
            console.error('알림 제외 목록 저장 오류:', error);
            this.app.showError(`저장 실패: ${error.message}`);
        }
    }
}

// 전역 변수로 인스턴스 저장 (HTML에서 참조하기 위해)
window.exclusionListModal = null;