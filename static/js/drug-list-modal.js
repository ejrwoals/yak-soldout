// 약품 목록 편집 모달 관리 클래스

class DrugListModal {
    constructor(mainApp) {
        this.app = mainApp;
        this.modal = document.getElementById('drugListModal');
        this.drugListContainer = document.getElementById('drugListContainer');
        this.addDrugForm = document.getElementById('addDrugForm');
        this.newDrugNameInput = document.getElementById('newDrugName');
        this.saveBtn = document.getElementById('saveDrugListBtn');
        
        // 현재 약품 목록 (로컬 상태)
        this.currentDrugs = [];
        // 원본 약품 목록 (변경사항 추적용)
        this.originalDrugs = [];
        // 새로 추가된 약품 목록 (임시 스타일링용)
        this.newlyAddedDrugs = new Set();
        
        this.init();
    }
    
    init() {
        // 이벤트 리스너 등록
        document.getElementById('drugListCard')?.addEventListener('click', () => this.open());
        document.getElementById('addDrugBtn')?.addEventListener('click', () => this.showAddForm());
        document.getElementById('confirmAddBtn')?.addEventListener('click', () => this.addDrug());
        document.getElementById('cancelAddBtn')?.addEventListener('click', () => this.hideAddForm());
        document.getElementById('closeDrugListModal')?.addEventListener('click', () => this.confirmClose());
        document.getElementById('cancelDrugListBtn')?.addEventListener('click', () => this.confirmClose());
        document.getElementById('saveDrugListBtn')?.addEventListener('click', () => this.save());

        // 모달 외부 클릭 시 닫기
        this.modal?.addEventListener('click', (e) => {
            if (e.target === this.modal) {
                this.confirmClose();
            }
        });

        // ESC 키로 모달 닫기
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && this.modal?.classList.contains('show')) {
                this.confirmClose();
            }
        });
        
        // 입력 필드에서 Enter 키 처리
        this.newDrugNameInput?.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                this.addDrug();
            }
        });
    }
    
    async open() {
        try {
            // 현재 약품 목록 로드
            const response = await fetch('/api/drug-list');
            if (!response.ok) throw new Error('약품 목록 로드 실패');
            
            const data = await response.json();
            this.currentDrugs = JSON.parse(JSON.stringify(data.drugs)); // 깊은 복사
            this.originalDrugs = JSON.parse(JSON.stringify(data.drugs)); // 원본도 깊은 복사
            this.newlyAddedDrugs.clear(); // 새로 추가된 약품 목록 초기화
            this.sortDrugs(); // 로드 후 정렬
            this.renderDrugList();
            this.updateSaveButtonState(); // 초기 저장 버튼 상태 설정
            
            // 모달 표시
            this.modal.classList.add('show');
            
        } catch (error) {
            console.error('약품 목록 로드 오류:', error);
            this.app.showError('약품 목록을 불러오는데 실패했습니다');
        }
    }
    
    confirmClose() {
        if (this.hasChanges()) {
            if (!confirm('변경 사항이 저장되지 않았습니다. 그래도 닫으시겠습니까?')) {
                return;
            }
        }
        this.close();
    }

    close() {
        this.modal?.classList.remove('show');
        this.hideAddForm();
        this.clearAddForm();
    }
    
    showAddForm() {
        this.addDrugForm.style.display = 'block';
        this.newDrugNameInput.focus();
    }
    
    hideAddForm() {
        this.addDrugForm.style.display = 'none';
    }
    
    clearAddForm() {
        this.newDrugNameInput.value = '';
    }
    
    addDrug() {
        const drugName = this.newDrugNameInput.value.trim();
        
        if (!drugName) {
            this.app.showError('약품명을 입력해주세요');
            return;
        }
        
        // 중복 검사 (문자열과 객체 모두 처리)
        const isDuplicate = this.currentDrugs.some(drug => 
            typeof drug === 'string' ? drug === drugName : drug.drugName === drugName
        );
        if (isDuplicate) {
            this.app.showError('이미 등록된 약품입니다');
            return;
        }
        
        // 약품 추가 (배열 맨 앞에 추가) - 새 약품은 객체 형태로 추가
        const kstDate = new Date(Date.now() + (9 * 60 * 60 * 1000)); // UTC + 9시간
        const newDrug = {
            drugName: drugName,
            isUrgent: false,
            dateAdded: kstDate.toISOString().slice(0, 19)
        };
        this.currentDrugs.unshift(newDrug);
        this.newlyAddedDrugs.add(drugName); // 새로 추가된 약품으로 표시
        this.sortDrugs(); // 추가 후 정렬
        this.renderDrugList();
        this.hideAddForm();
        this.clearAddForm();
        this.updateSaveButtonState(); // 저장 버튼 상태 업데이트
        
        this.app.showSuccess(`'${drugName}'이(가) 추가되었습니다`);
    }
    
    removeDrug(drugName) {
        const index = this.currentDrugs.findIndex(drug => 
            typeof drug === 'string' ? drug === drugName : drug.drugName === drugName
        );
        if (index > -1) {
            this.currentDrugs.splice(index, 1);
            this.newlyAddedDrugs.delete(drugName); // 새로 추가된 약품 목록에서도 제거
            this.sortDrugs(); // 삭제 후 정렬
            this.renderDrugList();
            this.updateSaveButtonState(); // 저장 버튼 상태 업데이트
            this.app.showSuccess(`'${drugName}'이(가) 삭제되었습니다`);
        }
    }
    
    toggleUrgent(drugName) {
        const index = this.currentDrugs.findIndex(drug => 
            typeof drug === 'string' ? drug === drugName : drug.drugName === drugName
        );
        if (index > -1) {
            // 문자열인 경우 객체로 변환
            if (typeof this.currentDrugs[index] === 'string') {
                const kstDate = new Date(Date.now() + (9 * 60 * 60 * 1000)); // UTC + 9시간
                this.currentDrugs[index] = {
                    drugName: this.currentDrugs[index],
                    isUrgent: false,
                    dateAdded: kstDate.toISOString().slice(0, 19)
                };
            }
            
            const drug = this.currentDrugs[index];
            drug.isUrgent = !drug.isUrgent;
            
            // 긴급 상태 변경 시 현재 날짜로 업데이트 (한국 표준시간)
            const kstDate = new Date(Date.now() + (9 * 60 * 60 * 1000)); // UTC + 9시간
            drug.dateAdded = kstDate.toISOString().slice(0, 19); // YYYY-MM-DDTHH:mm:ss 형식
            
            // 긴급 상태 변경 시 목록 다시 정렬
            this.sortDrugs();
            this.renderDrugList();
            this.updateSaveButtonState();
            
            const status = drug.isUrgent ? '긴급 알림' : '일반 알림';
            this.app.showSuccess(`'${drug.drugName}'이(가) ${status}으로 설정되었습니다`);
        }
    }
    
    sortDrugs() {
        // 긴급 항목(상단) -> 일반 항목(하단), 각각 dateAdded 최신순
        this.currentDrugs.sort((a, b) => {
            const aName = typeof a === 'string' ? a : a.drugName;
            const bName = typeof b === 'string' ? b : b.drugName;
            const aUrgent = typeof a === 'object' ? a.isUrgent : false;
            const bUrgent = typeof b === 'object' ? b.isUrgent : false;
            
            // 먼저 긴급 상태로 분류
            if (aUrgent !== bUrgent) {
                return aUrgent ? -1 : 1; // 긴급 항목이 먼저 (상단)
            }
            
            // 같은 긴급 상태 내에서는 dateAdded 최신순
            const aDate = typeof a === 'object' ? new Date(a.dateAdded) : new Date(0);
            const bDate = typeof b === 'object' ? new Date(b.dateAdded) : new Date(0);
            return bDate - aDate; // 최신 날짜가 먼저 (상단)
        });
    }
    
    renderDrugList() {
        if (!this.drugListContainer) return;
        
        if (this.currentDrugs.length === 0) {
            this.drugListContainer.innerHTML = `
                <div class="empty-drug-list">
                    <i class="bi bi-inbox"></i>
                    <p>등록된 약품이 없습니다</p>
                    <p class="text-muted">위의 '약품 추가하기' 버튼을 눌러 약품을 추가해보세요</p>
                </div>
            `;
            return;
        }
        
        this.drugListContainer.innerHTML = `
            <div class="drug-list-header">
                <span class="drug-count">총 ${this.currentDrugs.length}개 약품</span>
            </div>
            <div class="drug-items">
                ${this.currentDrugs.map((drug, index) => {
                    const drugName = typeof drug === 'string' ? drug : drug.drugName;
                    const isUrgent = typeof drug === 'object' ? drug.isUrgent : false;
                    const isNewlyAdded = this.newlyAddedDrugs.has(drugName);
                    const drugNumber = this.currentDrugs.length - index; // 내림차순 넘버링
                    
                    return `
                    <div class="drug-item ${isNewlyAdded ? 'newly-added' : ''} ${isUrgent ? 'urgent' : ''}" data-drug="${drugName}">
                        <div class="drug-info">
                            <span class="drug-number">${drugNumber}</span>
                            <span class="drug-name">${drugName}</span>
                            ${isUrgent ? '<i class="bi bi-bell-fill urgent-indicator" title="긴급 알림"></i>' : ''}
                        </div>
                        <div class="drug-actions">
                            <button class="drug-urgent-btn ${isUrgent ? 'urgent' : ''}" 
                                    onclick="window.drugListModal.toggleUrgent('${drugName.replace(/'/g, "\\'")}')"
                                    title="${isUrgent ? '일반 알림으로 변경' : '긴급 알림으로 변경'}">
                                <i class="bi ${isUrgent ? 'bi-bell-fill' : 'bi-bell'}"></i>
                            </button>
                            <button class="drug-remove-btn" onclick="window.drugListModal.removeDrug('${drugName.replace(/'/g, "\\'")}')">
                                <i class="bi bi-x-lg"></i>
                            </button>
                        </div>
                    </div>
                `;
                }).join('')}
            </div>
        `;
    }
    
    // 변경사항 감지
    hasChanges() {
        // 배열 길이가 다르면 변경됨
        if (this.currentDrugs.length !== this.originalDrugs.length) {
            return true;
        }
        
        // 현재 약품 중 하나라도 원본과 다르거나 없으면 변경됨
        const hasCurrentChanges = this.currentDrugs.some(current => {
            const currentName = typeof current === 'string' ? current : current.drugName;
            const currentUrgent = typeof current === 'object' ? current.isUrgent : false;
            
            const original = this.originalDrugs.find(orig => {
                const origName = typeof orig === 'string' ? orig : orig.drugName;
                return origName === currentName;
            });
            
            if (!original) return true; // 원본에 없는 새 항목
            
            const originalUrgent = typeof original === 'object' ? original.isUrgent : false;
            
            // 긴급 상태가 다르면 변경됨
            return currentUrgent !== originalUrgent;
        });
        
        // 원본 약품 중 하나라도 현재에 없으면 변경됨 (삭제된 경우)
        const hasOriginalChanges = this.originalDrugs.some(original => {
            const originalName = typeof original === 'string' ? original : original.drugName;
            
            const current = this.currentDrugs.find(curr => {
                const currentName = typeof curr === 'string' ? curr : curr.drugName;
                return currentName === originalName;
            });
            
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
            // 서버로 업데이트된 약품 목록 전송
            const response = await fetch('/api/drug-list', {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ drugs: this.currentDrugs })
            });
            
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || '저장 실패');
            }
            
            this.app.showSuccess('약품 목록이 저장되었습니다');
            
            // 저장 성공 시 원본 데이터 업데이트 및 임시 스타일 제거
            this.originalDrugs = [...this.currentDrugs];
            this.newlyAddedDrugs.clear(); // 새로 추가된 약품 목록 초기화
            this.renderDrugList(); // 스타일 업데이트를 위해 다시 렌더링
            this.updateSaveButtonState();
            
            this.close();
            
            // 상태 새로고침
            setTimeout(() => this.app.loadStatus(), 1000);
            
        } catch (error) {
            console.error('약품 목록 저장 오류:', error);
            this.app.showError(`저장 실패: ${error.message}`);
        }
    }
}

// 전역 변수로 인스턴스 저장 (HTML에서 참조하기 위해)
window.drugListModal = null;