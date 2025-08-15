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
        document.getElementById('closeDrugListModal')?.addEventListener('click', () => this.close());
        document.getElementById('cancelDrugListBtn')?.addEventListener('click', () => this.close());
        document.getElementById('saveDrugListBtn')?.addEventListener('click', () => this.save());
        
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
            this.currentDrugs = [...data.drugs]; // 복사본 생성
            this.originalDrugs = [...data.drugs]; // 원본 저장
            this.newlyAddedDrugs.clear(); // 새로 추가된 약품 목록 초기화
            this.renderDrugList();
            this.updateSaveButtonState(); // 초기 저장 버튼 상태 설정
            
            // 모달 표시
            this.modal.classList.add('show');
            
        } catch (error) {
            console.error('약품 목록 로드 오류:', error);
            this.app.showError('약품 목록을 불러오는데 실패했습니다');
        }
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
        
        // 중복 검사
        if (this.currentDrugs.includes(drugName)) {
            this.app.showError('이미 등록된 약품입니다');
            return;
        }
        
        // 약품 추가 (배열 맨 앞에 추가)
        this.currentDrugs.unshift(drugName);
        this.newlyAddedDrugs.add(drugName); // 새로 추가된 약품으로 표시
        this.renderDrugList();
        this.hideAddForm();
        this.clearAddForm();
        this.updateSaveButtonState(); // 저장 버튼 상태 업데이트
        
        this.app.showSuccess(`'${drugName}'이(가) 추가되었습니다`);
    }
    
    removeDrug(drugName) {
        const index = this.currentDrugs.indexOf(drugName);
        if (index > -1) {
            this.currentDrugs.splice(index, 1);
            this.newlyAddedDrugs.delete(drugName); // 새로 추가된 약품 목록에서도 제거
            this.renderDrugList();
            this.updateSaveButtonState(); // 저장 버튼 상태 업데이트
            this.app.showSuccess(`'${drugName}'이(가) 삭제되었습니다`);
        }
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
                    const isNewlyAdded = this.newlyAddedDrugs.has(drug);
                    const drugNumber = this.currentDrugs.length - index; // 내림차순 넘버링
                    return `
                    <div class="drug-item ${isNewlyAdded ? 'newly-added' : ''}" data-drug="${drug}">
                        <div class="drug-info">
                            <span class="drug-number">${drugNumber}</span>
                            <span class="drug-name">${drug}</span>
                        </div>
                        <button class="drug-remove-btn" onclick="window.drugListModal.removeDrug('${drug.replace(/'/g, "\\'")}')">
                            <i class="bi bi-x-lg"></i>
                        </button>
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
        
        // 정렬된 배열을 비교하여 내용이 다른지 확인
        const currentSorted = [...this.currentDrugs].sort();
        const originalSorted = [...this.originalDrugs].sort();
        
        return !currentSorted.every((drug, index) => drug === originalSorted[index]);
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