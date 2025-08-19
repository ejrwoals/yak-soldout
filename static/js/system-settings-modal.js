// 시스템 설정 모달 관리 클래스

class SystemSettingsModal {
    constructor(mainApp) {
        this.app = mainApp;
        this.modal = document.getElementById('systemSettingsModal');
        this.form = document.getElementById('systemSettingsForm');
        this.repeatIntervalInput = document.getElementById('repeatInterval');
        this.alertExclusionDaysInput = document.getElementById('alertExclusionDays');
        
        this.init();
    }
    
    init() {
        // 이벤트 리스너 등록
        document.getElementById('systemSettingsBtn')?.addEventListener('click', () => this.open());
        document.getElementById('closeSystemSettingsModal')?.addEventListener('click', () => this.close());
        document.getElementById('cancelSystemSettingsBtn')?.addEventListener('click', () => this.close());
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
            const response = await fetch('/api/system-settings');
            if (!response.ok) throw new Error('설정 로드 실패');
            
            const data = await response.json();
            this.loadSettings(data);
            
            // 모달 표시
            this.modal.classList.add('show');
            
            // 첫 번째 입력 필드에 포커스
            this.repeatIntervalInput?.focus();
            
        } catch (error) {
            console.error('시스템 설정 로드 오류:', error);
            this.app.showError('설정을 불러오는데 실패했습니다');
        }
    }
    
    close() {
        this.modal?.classList.remove('show');
    }
    
    loadSettings(settings) {
        if (!this.repeatIntervalInput || !this.alertExclusionDaysInput) return;
        
        // 설정값 입력 필드에 로드
        this.repeatIntervalInput.value = settings.repeat_interval_minutes || '';
        this.alertExclusionDaysInput.value = settings.alert_exclusion_days || '';
    }
    
    async handleSubmit(e) {
        e.preventDefault();
        
        try {
            // 폼 데이터 수집
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
            
            // 설정 데이터 구성
            const settingsData = {
                repeat_interval_minutes: repeatInterval,
                alert_exclusion_days: alertExclusionDays
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
            
        } catch (error) {
            console.error('시스템 설정 저장 오류:', error);
            this.app.showError(`저장 실패: ${error.message}`);
        }
    }
}

// 전역 변수로 인스턴스 저장 (HTML에서 참조하기 위해)
window.systemSettingsModal = null;