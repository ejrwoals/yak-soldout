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
            const regionField = dist.id === 'geopharm' ? `
                <div class="form-group">
                    <label for="region_${dist.id}">지역</label>
                    <select id="region_${dist.id}" ${!dist.enabled ? 'disabled' : ''}>
                        <option value="01" ${(dist.region || '01') === '01' ? 'selected' : ''}>대구</option>
                        <option value="02" ${dist.region === '02' ? 'selected' : ''}>대전</option>
                        <option value="03" ${dist.region === '03' ? 'selected' : ''}>광주</option>
                        <option value="04" ${dist.region === '04' ? 'selected' : ''}>서울</option>
                    </select>
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
        const regionField = document.getElementById(`region_${distributorId}`);

        if (enabled) {
            usernameField.disabled = false;
            passwordField.disabled = false;
            if (regionField) regionField.disabled = false;
            usernameField.focus();
        } else {
            usernameField.disabled = true;
            passwordField.disabled = true;
            if (regionField) regionField.disabled = true;
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
                const regionSelect = section.querySelector('select');

                const distributorId = checkbox.id.replace('enabled_', '');
                const enabled = checkbox.checked;

                const distData = {
                    id: distributorId,
                    name: nameElement.textContent,
                    enabled: enabled,
                    username: usernameInput.value.trim(),
                    password: passwordInput.value.trim()
                };

                if (regionSelect) {
                    distData.region = regionSelect.value;
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