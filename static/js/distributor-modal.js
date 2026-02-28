// 도매상 설정 모달 관리 클래스

class DistributorModal {
    constructor(mainApp) {
        this.app = mainApp;
        this.modal = document.getElementById('distributorModal');
        this.form = document.getElementById('distributorForm');
        this.distributorList = document.getElementById('distributorList');
        
        this.init();
    }
    
    init() {
        // 이벤트 리스너 등록
        document.getElementById('distributorCard')?.addEventListener('click', () => this.open());
        document.getElementById('closeModal')?.addEventListener('click', () => this.close());
        document.getElementById('cancelBtn')?.addEventListener('click', () => this.close());
        this.form?.addEventListener('submit', (e) => this.handleSubmit(e));

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

        // 커스텀 드롭다운 이벤트 (이벤트 위임)
        document.addEventListener('click', (e) => {
            const trigger = e.target.closest('.custom-select-trigger');
            const option = e.target.closest('.custom-select-option');

            if (trigger) {
                const selectEl = trigger.closest('.custom-select');
                if (selectEl.classList.contains('disabled')) return;
                const isOpen = selectEl.classList.contains('open');
                document.querySelectorAll('.custom-select.open').forEach(s => s.classList.remove('open'));
                if (!isOpen) selectEl.classList.add('open');
            } else if (option) {
                const selectEl = option.closest('.custom-select');
                selectEl.dataset.value = option.dataset.value;
                selectEl.querySelector('.custom-select-value').textContent = option.textContent;
                selectEl.querySelectorAll('.custom-select-option').forEach(o => o.classList.remove('selected'));
                option.classList.add('selected');
                selectEl.classList.remove('open');
            } else {
                document.querySelectorAll('.custom-select.open').forEach(s => s.classList.remove('open'));
            }
        });
    }
    
    async open() {
        try {
            // 현재 설정 로드
            const response = await fetch('/api/distributor-settings');
            if (!response.ok) throw new Error('설정 로드 실패');
            
            const data = await response.json();
            this.render(data.distributors);
            
            // 모달 표시
            this.modal.classList.add('show');
            
        } catch (error) {
            console.error('도매상 설정 로드 오류:', error);
            this.app.showError('설정을 불러오는데 실패했습니다');
        }
    }
    
    close() {
        this.modal?.classList.remove('show');
    }
    
    render(distributors) {
        if (!this.distributorList) return;

        this.distributorList.innerHTML = distributors.map(dist => {
            const regions = [
                { value: '01', label: '대구' },
                { value: '02', label: '대전' },
                { value: '03', label: '광주' },
                { value: '04', label: '서울' },
            ];
            const selectedRegion = dist.region || '01';
            const selectedLabel = regions.find(r => r.value === selectedRegion)?.label || '대구';
            const chevron = `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"></polyline></svg>`;

            const regionField = dist.id === 'geopharm' ? `
                <div class="form-group">
                    <label>지역</label>
                    <div class="custom-select ${!dist.enabled ? 'disabled' : ''}" id="region_${dist.id}" data-value="${selectedRegion}">
                        <button class="custom-select-trigger" type="button">
                            <span class="custom-select-value">${selectedLabel}</span>
                            ${chevron}
                        </button>
                        <div class="custom-select-options">
                            ${regions.map(r => `
                                <div class="custom-select-option ${r.value === selectedRegion ? 'selected' : ''}" data-value="${r.value}">${r.label}</div>
                            `).join('')}
                        </div>
                    </div>
                </div>
            ` : '';

            return `
                <div class="distributor-section">
                    <div class="distributor-header">
                        <div class="distributor-checkbox">
                            <input type="checkbox" id="enabled_${dist.id}" ${dist.enabled ? 'checked' : ''}
                                   onchange="window.distributorModal.toggleFields('${dist.id}', this.checked)">
                            <label for="enabled_${dist.id}">활성화</label>
                        </div>
                        <h3 class="distributor-name">${dist.name}</h3>
                    </div>
                    <div class="distributor-form">
                        <div class="form-group">
                            <label for="username_${dist.id}">아이디</label>
                            <input type="text" id="username_${dist.id}"
                                   value="${dist.username}"
                                   ${!dist.enabled ? 'disabled' : ''}>
                        </div>
                        <div class="form-group">
                            <label for="password_${dist.id}">비밀번호</label>
                            <input type="password" id="password_${dist.id}"
                                   value="${dist.password}"
                                   ${!dist.enabled ? 'disabled' : ''}>
                        </div>
                        ${regionField}
                    </div>
                </div>
            `;
        }).join('');
    }
    
    toggleFields(distributorId, enabled) {
        const usernameField = document.getElementById(`username_${distributorId}`);
        const passwordField = document.getElementById(`password_${distributorId}`);
        const regionEl = document.getElementById(`region_${distributorId}`);

        if (enabled) {
            usernameField.disabled = false;
            passwordField.disabled = false;
            if (regionEl) regionEl.classList.remove('disabled');
            usernameField.focus();
        } else {
            usernameField.disabled = true;
            passwordField.disabled = true;
            if (regionEl) regionEl.classList.add('disabled');
        }
    }
    
    async handleSubmit(e) {
        e.preventDefault();
        
        try {
            // 폼 데이터 수집
            const distributors = [];
            
            this.distributorList.querySelectorAll('.distributor-section').forEach(section => {
                const checkbox = section.querySelector('input[type="checkbox"]');
                const nameElement = section.querySelector('.distributor-name');
                const usernameInput = section.querySelector('input[type="text"]');
                const passwordInput = section.querySelector('input[type="password"]');
                const regionEl = section.querySelector('.custom-select');

                const distributorId = checkbox.id.replace('enabled_', '');
                const enabled = checkbox.checked;

                const distData = {
                    id: distributorId,
                    name: nameElement.textContent,
                    enabled: enabled,
                    username: usernameInput.value.trim(),
                    password: passwordInput.value.trim()
                };

                if (regionEl) {
                    distData.region = regionEl.dataset.value;
                }

                distributors.push(distData);
            });
            
            // 유효성 검사
            for (const dist of distributors) {
                if (dist.enabled && (!dist.username || !dist.password)) {
                    this.app.showError(`${dist.name}의 아이디와 비밀번호를 모두 입력해주세요`);
                    return;
                }
            }
            
            // 서버로 전송
            const response = await fetch('/api/distributor-settings', {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ distributors: distributors })
            });
            
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || '저장 실패');
            }
            
            this.app.showSuccess('설정이 저장되었습니다');
            this.close();
            
            // 상태 새로고침
            setTimeout(() => this.app.loadStatus(), 1000);
            
        } catch (error) {
            console.error('도매상 설정 저장 오류:', error);
            this.app.showError(`저장 실패: ${error.message}`);
        }
    }
}

// 전역 변수로 인스턴스 저장 (HTML에서 참조하기 위해)
window.distributorModal = null;