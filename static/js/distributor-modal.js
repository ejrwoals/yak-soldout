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
            // 활성화된 도매상만 표시
            const enabledDistributors = data.distributors.filter(d => d.enabled);
            this.render(enabledDistributors);

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

        // 활성화된 도매상이 없을 경우 빈 상태 메시지
        if (distributors.length === 0) {
            this.distributorList.innerHTML = `
                <div class="empty-distributor-settings">
                    <i class="bi bi-shop"></i>
                    <p>활성화된 도매상이 없습니다</p>
                    <small>시스템 설정에서 먼저 활성화할 도매상을 선택해주세요</small>
                </div>
            `;
            return;
        }

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
                    <div class="custom-select" id="region_${dist.id}" data-value="${selectedRegion}">
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
                <div class="distributor-section" data-id="${dist.id}" data-name="${dist.name}">
                    <div class="distributor-header">
                        <h3 class="distributor-name">${dist.name}</h3>
                    </div>
                    <div class="distributor-form">
                        <div class="form-group">
                            <label for="username_${dist.id}">아이디</label>
                            <input type="text" id="username_${dist.id}" value="${dist.username}">
                        </div>
                        <div class="form-group">
                            <label for="password_${dist.id}">비밀번호</label>
                            <input type="password" id="password_${dist.id}" value="${dist.password}">
                        </div>
                        ${regionField}
                    </div>
                </div>
            `;
        }).join('');
    }

    async handleSubmit(e) {
        e.preventDefault();

        try {
            // 폼 데이터 수집 (활성화된 도매상만 표시되므로 모두 enabled: true)
            const distributors = [];

            this.distributorList.querySelectorAll('.distributor-section').forEach(section => {
                const distributorId = section.dataset.id;
                const distributorName = section.dataset.name;
                const usernameInput = section.querySelector('input[type="text"]');
                const passwordInput = section.querySelector('input[type="password"]');
                const regionEl = section.querySelector('.custom-select');

                const distData = {
                    id: distributorId,
                    name: distributorName,
                    enabled: true,
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
                if (!dist.username || !dist.password) {
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
