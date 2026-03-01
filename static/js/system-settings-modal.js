// 시스템 설정 모달 관리 클래스
// 도매상 목록은 /api/system-settings 응답에서 동적으로 수신합니다.

class SystemSettingsModal {
    constructor(mainApp) {
        this.app = mainApp;
        this.modal = document.getElementById('systemSettingsModal');
        this.form = document.getElementById('systemSettingsForm');
        this.repeatIntervalInput = document.getElementById('repeatInterval');
        this.alertExclusionDaysInput = document.getElementById('alertExclusionDays');
        this.enablesList = document.getElementById('systemDistributorEnables');

        // 원본 설정값 (변경사항 추적용)
        this.originalSettings = null;

        this.init();
    }

    init() {
        // 이벤트 리스너 등록
        document.getElementById('systemSettingsBtn')?.addEventListener('click', () => this.open());
        document.getElementById('closeSystemSettingsModal')?.addEventListener('click', () => this.confirmClose());
        document.getElementById('cancelSystemSettingsBtn')?.addEventListener('click', () => this.confirmClose());
        this.form?.addEventListener('submit', (e) => this.handleSubmit(e));

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
    }

    async open() {
        try {
            // 현재 설정 로드
            const response = await fetch('/api/system-settings');
            if (!response.ok) throw new Error('설정 로드 실패');

            const data = await response.json();
            this.loadSettings(data);

            // 원본 설정 스냅샷 저장
            this.originalSettings = this.getCurrentSettings();

            // 모달 표시
            this.modal.classList.add('show');

        } catch (error) {
            console.error('시스템 설정 로드 오류:', error);
            this.app.showError('설정을 불러오는데 실패했습니다');
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
    }

    // 현재 폼 값을 객체로 수집
    getCurrentSettings() {
        const distributorEnables = {};
        this.enablesList?.querySelectorAll('input[type="checkbox"]').forEach(checkbox => {
            const id = checkbox.id.replace('sys_enabled_', '');
            distributorEnables[id] = checkbox.checked;
        });

        return {
            repeat_interval_minutes: this.repeatIntervalInput?.value || '',
            alert_exclusion_days: this.alertExclusionDaysInput?.value || '',
            distributor_enables: distributorEnables
        };
    }

    // 변경사항 감지
    hasChanges() {
        if (!this.originalSettings) return false;

        const current = this.getCurrentSettings();

        if (current.repeat_interval_minutes !== this.originalSettings.repeat_interval_minutes) return true;
        if (current.alert_exclusion_days !== this.originalSettings.alert_exclusion_days) return true;

        const origEnables = this.originalSettings.distributor_enables;
        const currEnables = current.distributor_enables;
        for (const key of Object.keys(origEnables)) {
            if (origEnables[key] !== currEnables[key]) return true;
        }

        return false;
    }

    loadSettings(settings) {
        if (!this.repeatIntervalInput || !this.alertExclusionDaysInput) return;

        // 모니터링 설정값 입력 필드에 로드
        this.repeatIntervalInput.value = settings.repeat_interval_minutes || '';
        this.alertExclusionDaysInput.value = settings.alert_exclusion_days || '';

        // 도매상 활성화 체크박스 렌더링 (API 응답 기반 — 하드코딩 없음)
        const enables = settings.distributor_enables || {};
        if (this.enablesList) {
            this.enablesList.innerHTML = Object.entries(enables).map(([id, enabled]) => {
                // 도매상 표시 이름은 distributor_names 맵 또는 id를 그대로 사용
                const name = (settings.distributor_names || {})[id] || id;
                return `
                    <label class="distributor-enable-item">
                        <input type="checkbox" id="sys_enabled_${id}" ${enabled ? 'checked' : ''}>
                        <span>${name}</span>
                    </label>
                `;
            }).join('');
        }
    }

    async handleSubmit(e) {
        e.preventDefault();

        try {
            // 모니터링 설정 수집
            const repeatInterval = parseInt(this.repeatIntervalInput.value);
            const alertExclusionDays = parseInt(this.alertExclusionDaysInput.value);

            // 유효성 검사
            if (!repeatInterval || repeatInterval < 1 || repeatInterval > 1440) {
                this.app.showError('반복 간격은 1분에서 1440분(24시간) 사이의 값이어야 합니다');
                this.repeatIntervalInput.focus();
                return;
            }

            if (!alertExclusionDays || alertExclusionDays < 1 || alertExclusionDays > 365) {
                this.app.showError('알림 제외 기간은 1일에서 365일 사이의 값이어야 합니다');
                this.alertExclusionDaysInput.focus();
                return;
            }

            // 도매상 활성화 상태 수집 (렌더링된 체크박스 기준 — 동적)
            const distributorEnables = {};
            this.enablesList.querySelectorAll('input[type="checkbox"]').forEach(checkbox => {
                const id = checkbox.id.replace('sys_enabled_', '');
                distributorEnables[id] = checkbox.checked;
            });

            // 설정 데이터 구성
            const settingsData = {
                repeat_interval_minutes: repeatInterval,
                alert_exclusion_days: alertExclusionDays,
                distributor_enables: distributorEnables
            };

            // 서버로 전송
            const response = await fetch('/api/system-settings', {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(settingsData)
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || '저장 실패');
            }

            this.app.showSuccess('시스템 설정이 저장되었습니다');
            this.close();

            // 상태 새로고침 (활성화 도매상 변경 반영)
            setTimeout(() => this.app.loadStatus(), 500);

        } catch (error) {
            console.error('시스템 설정 저장 오류:', error);
            this.app.showError(`저장 실패: ${error.message}`);
        }
    }
}

// 전역 변수로 인스턴스 저장 (HTML에서 참조하기 위해)
window.systemSettingsModal = null;
