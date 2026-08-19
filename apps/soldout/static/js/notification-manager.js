// 알림 및 토스트 메시지 관리 클래스

class NotificationManager {
    constructor() {
        this.toastCount = 0;
        this.maxToasts = 5; // 최대 토스트 개수
    }
    
    /**
     * 성공 메시지 표시
     * @param {string} message - 표시할 메시지
     */
    showSuccess(message) {
        this.showNotification(message, 'success');
    }
    
    /**
     * 오류 메시지 표시
     * @param {string} message - 표시할 메시지
     */
    showError(message) {
        this.showNotification(message, 'error');
    }
    
    /**
     * 경고 메시지 표시
     * @param {string} message - 표시할 메시지
     */
    showWarning(message) {
        this.showNotification(message, 'warning');
    }
    
    /**
     * 정보 메시지 표시
     * @param {string} message - 표시할 메시지
     */
    showInfo(message) {
        this.showNotification(message, 'info');
    }
    
    /**
     * 토스트 알림 표시
     * @param {string} message - 표시할 메시지
     * @param {string} type - 알림 타입 ('success', 'error', 'warning', 'info')
     * @param {number} duration - 표시 시간 (ms, 기본값: 3000)
     */
    showNotification(message, type = 'info', duration = 3000) {
        // 토스트 개수 제한
        if (this.toastCount >= this.maxToasts) {
            console.warn('너무 많은 토스트가 표시되고 있습니다.');
            return;
        }
        
        const toast = this.createToastElement(message, type);
        this.toastCount++;
        
        document.body.appendChild(toast);
        
        // 진입 애니메이션
        this.animateToastIn(toast);
        
        // 자동 제거
        setTimeout(() => {
            this.removeToast(toast);
        }, duration);
    }
    
    /**
     * 토스트 요소 생성
     * @param {string} message - 메시지
     * @param {string} type - 타입
     * @returns {HTMLElement} 토스트 요소
     */
    createToastElement(message, type) {
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        
        // 아이콘 추가
        const icon = this.getIcon(type);
        
        toast.innerHTML = `
            <div class="toast-content">
                <i class="${icon}"></i>
                <span class="toast-message">${message}</span>
            </div>
        `;
        
        // 스타일 적용
        this.applyToastStyles(toast, type);
        
        // 클릭으로 닫기
        toast.addEventListener('click', () => {
            this.removeToast(toast);
        });
        
        return toast;
    }
    
    /**
     * 타입에 따른 아이콘 반환
     * @param {string} type - 알림 타입
     * @returns {string} 아이콘 클래스
     */
    getIcon(type) {
        const icons = {
            success: 'bi bi-check-circle',
            error: 'bi bi-x-circle',
            warning: 'bi bi-exclamation-triangle',
            info: 'bi bi-info-circle'
        };
        return icons[type] || icons.info;
    }
    
    /**
     * 토스트에 스타일 적용
     * @param {HTMLElement} toast - 토스트 요소
     * @param {string} type - 알림 타입
     */
    applyToastStyles(toast, type) {
        const colors = {
            success: 'var(--success)',
            error: 'var(--danger)',
            warning: 'var(--warning)',
            info: 'var(--primary)'
        };
        
        Object.assign(toast.style, {
            position: 'fixed',
            top: `${20 + (this.toastCount * 70)}px`, // 기존 토스트 아래에 배치
            right: '20px',
            padding: '12px 20px',
            borderRadius: '8px',
            color: 'white',
            background: colors[type] || colors.info,
            boxShadow: 'var(--shadow-lg)',
            zIndex: '1000',
            minWidth: '300px',
            maxWidth: '400px',
            transform: 'translateX(100%)',
            transition: 'all 0.3s ease',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            fontWeight: '500'
        });
        
        // 토스트 내용 스타일
        const content = toast.querySelector('.toast-content');
        if (content) {
            Object.assign(content.style, {
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                width: '100%'
            });
        }
        
        // 아이콘 스타일
        const icon = toast.querySelector('i');
        if (icon) {
            Object.assign(icon.style, {
                fontSize: '16px',
                flexShrink: '0'
            });
        }
        
        // 메시지 스타일
        const message = toast.querySelector('.toast-message');
        if (message) {
            Object.assign(message.style, {
                flex: '1',
                wordBreak: 'break-word'
            });
        }
    }
    
    /**
     * 토스트 진입 애니메이션
     * @param {HTMLElement} toast - 토스트 요소
     */
    animateToastIn(toast) {
        setTimeout(() => {
            toast.style.transform = 'translateX(0)';
        }, 100);
    }
    
    /**
     * 토스트 제거
     * @param {HTMLElement} toast - 제거할 토스트 요소
     */
    removeToast(toast) {
        if (!toast || !toast.parentNode) return;
        
        // 퇴장 애니메이션
        toast.style.transform = 'translateX(100%)';
        toast.style.opacity = '0';
        
        setTimeout(() => {
            if (toast.parentNode) {
                document.body.removeChild(toast);
                this.toastCount = Math.max(0, this.toastCount - 1);
                this.repositionToasts();
            }
        }, 300);
    }
    
    /**
     * 남은 토스트들의 위치 재조정
     */
    repositionToasts() {
        const toasts = document.querySelectorAll('.toast');
        toasts.forEach((toast, index) => {
            toast.style.top = `${20 + (index * 70)}px`;
        });
    }
    
    /**
     * 모든 토스트 제거
     */
    clearAll() {
        const toasts = document.querySelectorAll('.toast');
        toasts.forEach(toast => this.removeToast(toast));
    }
}

// 전역 인스턴스 생성
window.notificationManager = new NotificationManager();
