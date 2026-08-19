// 툴팁 관리 클래스

class TooltipManager {
    constructor() {
        this.tooltipTypes = {
            DISTRIBUTOR: 'distributor-tooltip',
            STATUS: 'status-tooltip', 
            ERROR: 'error-tooltip'
        };
    }
    
    /**
     * 도매상 툴팁 업데이트
     * @param {HTMLElement} statusCard - 상태 카드 요소
     * @param {Array} distributors - 도매상 목록
     */
    updateDistributorTooltip(statusCard, distributors) {
        if (!statusCard) return;
        
        // 기존 툴팁 제거
        this.removeExistingTooltip(statusCard);
        
        // 새 툴팁 생성
        const tooltip = this.createTooltip(this.tooltipTypes.DISTRIBUTOR);
        
        if (distributors.length === 0) {
            tooltip.innerHTML = this.createEmptyDistributorContent();
        } else {
            tooltip.innerHTML = this.createDistributorContent(distributors);
        }
        
        statusCard.appendChild(tooltip);
    }
    
    /**
     * 약품 목록 툴팁 업데이트
     * @param {HTMLElement} statusCard - 상태 카드 요소
     * @param {Array} drugList - 약품 목록
     * @param {number} totalCount - 전체 개수
     */
    updateDrugListTooltip(statusCard, drugList, totalCount) {
        if (!statusCard) return;
        
        // 기존 툴팁 제거
        this.removeExistingTooltip(statusCard);
        
        // 새 툴팁 생성
        const tooltip = this.createTooltip(this.tooltipTypes.STATUS);
        
        if (drugList.length === 0) {
            tooltip.innerHTML = this.createEmptyDrugListContent();
        } else {
            tooltip.innerHTML = this.createDrugListContent(drugList, totalCount);
        }
        
        statusCard.appendChild(tooltip);
    }
    
    /**
     * 결과 표시 제외 목록 툴팁 업데이트
     * @param {HTMLElement} statusCard - 상태 카드 요소
     * @param {Array} exclusionList - 제외 목록
     * @param {number} totalCount - 전체 개수
     */
    updateExclusionListTooltip(statusCard, exclusionList, totalCount) {
        if (!statusCard) return;
        
        // 기존 툴팁 제거
        this.removeExistingTooltip(statusCard);
        
        // 새 툴팁 생성
        const tooltip = this.createTooltip(this.tooltipTypes.STATUS);
        
        if (exclusionList.length === 0) {
            tooltip.innerHTML = this.createEmptyExclusionContent();
        } else {
            tooltip.innerHTML = this.createExclusionContent(exclusionList, totalCount);
        }
        
        statusCard.appendChild(tooltip);
    }
    
    /**
     * 오류 툴팁 업데이트
     * @param {HTMLElement} statusCard - 상태 카드 요소
     * @param {Array} errorDrugs - 오류 약품 목록
     */
    updateErrorTooltip(statusCard, errorDrugs) {
        if (!statusCard) return;
        
        // 기존 툴팁 제거
        this.removeExistingTooltip(statusCard);
        
        // 새 툴팁 생성
        const tooltip = this.createTooltip(this.tooltipTypes.ERROR);
        
        if (errorDrugs.length === 0) {
            tooltip.innerHTML = this.createEmptyErrorContent();
        } else {
            tooltip.innerHTML = this.createErrorContent(errorDrugs);
        }
        
        statusCard.appendChild(tooltip);
    }
    
    /**
     * 기존 툴팁 제거
     * @param {HTMLElement} statusCard - 상태 카드 요소
     */
    removeExistingTooltip(statusCard) {
        if (!statusCard) return;
        
        const selectors = Object.values(this.tooltipTypes).map(type => `.${type}`).join(', ');
        const existingTooltips = statusCard.querySelectorAll(selectors);
        existingTooltips.forEach(tooltip => tooltip.remove());
    }
    
    /**
     * 툴팁 요소 생성
     * @param {string} className - 툴팁 클래스명
     * @returns {HTMLElement} 툴팁 요소
     */
    createTooltip(className) {
        const tooltip = document.createElement('div');
        tooltip.className = className;
        return tooltip;
    }
    
    /**
     * 툴팁 아이템 생성
     * @param {string} icon - 아이콘 클래스
     * @param {string} text - 텍스트
     * @param {string} color - 아이콘 색상
     * @param {string} title - 툴팁 제목 (선택사항)
     * @returns {string} HTML 문자열
     */
    createTooltipItem(icon, text, color = 'var(--primary)', title = '') {
        const titleAttr = title ? `title="${title}"` : '';
        return `
            <div class="tooltip-item" ${titleAttr}>
                <i class="${icon}" style="color: ${color}"></i>
                <span>${text}</span>
            </div>
        `;
    }
    
    /**
     * 더보기 아이템 생성
     * @param {string} text - 더보기 텍스트
     * @returns {string} HTML 문자열
     */
    createMoreItem(text) {
        return `
            <div class="tooltip-more">
                <span>${text}</span>
            </div>
        `;
    }
    
    // =================== 콘텐츠 생성 메서드들 ===================
    
    createEmptyDistributorContent() {
        return this.createTooltipItem(
            'bi bi-x-circle',
            '설정된 도매상 없음',
            'var(--danger)'
        );
    }
    
    createDistributorContent(distributors) {
        return distributors.map(name => 
            this.createTooltipItem(
                'bi bi-check-circle',
                name,
                'var(--success)'
            )
        ).join('');
    }
    
    createEmptyDrugListContent() {
        return this.createTooltipItem(
            'bi bi-inbox',
            '검색 대상 약품이 없습니다',
            'var(--text-muted)'
        );
    }
    
    createDrugListContent(drugList, totalCount) {
        const maxShow = 5;
        
        // 1차: 긴급 알림 대상 우선, 2차: 최신 dateAdded 우선
        const sortedDrugs = [...drugList].sort((a, b) => {
            const aUrgent = typeof a === 'object' && a.isUrgent;
            const bUrgent = typeof b === 'object' && b.isUrgent;
            
            // 1차 정렬: 긴급 알림 대상이 먼저
            if (aUrgent && !bUrgent) return -1;
            if (!aUrgent && bUrgent) return 1;
            
            // 2차 정렬: 같은 그룹 내에서는 dateAdded가 최신인 것이 먼저
            if (typeof a === 'object' && typeof b === 'object' && a.dateAdded && b.dateAdded) {
                return new Date(b.dateAdded) - new Date(a.dateAdded);
            }
            
            return 0;
        });
        
        const items = sortedDrugs.slice(0, maxShow).map(drug => {
            const drugName = typeof drug === 'object' ? drug.drugName : drug;
            const isUrgent = typeof drug === 'object' && drug.isUrgent;
            
            const icon = isUrgent ? 'bi bi-bell-fill' : 'bi bi-capsule';
            const color = isUrgent ? '#dc3545' : 'var(--primary)'; // 빨간색 또는 기본색
            
            return this.createTooltipItem(icon, drugName, color);
        }).join('');
        
        const moreItems = totalCount > maxShow ? 
            this.createMoreItem(`...`) : '';
        
        return items + moreItems;
    }
    
    createEmptyExclusionContent() {
        return this.createTooltipItem(
            'bi bi-eye',
            '모든 약품이 결과에 표시됨',
            'var(--success)'
        );
    }
    
    createExclusionContent(exclusionList, totalCount) {
        const items = exclusionList.map(item => {
            // JSON 형식 처리
            if (typeof item === 'object' && item.drugName && item.distributor) {
                const displayText = `[${item.distributor}] ${item.drugName}`;
                return this.createTooltipItem(
                    'bi bi-eye-slash',
                    displayText,
                    'var(--warning)'
                );
            }
            // 예외 처리
            else {
                return this.createTooltipItem(
                    'bi bi-eye-slash',
                    '알 수 없음',
                    'var(--warning)'
                );
            }
        }).join('');
        
        const moreItems = totalCount > exclusionList.length ? 
            this.createMoreItem('...') : '';
        
        return items + moreItems;
    }
    
    createEmptyErrorContent() {
        return this.createTooltipItem(
            'bi bi-check-circle',
            '오류 없음',
            'var(--success)'
        );
    }
    
    createErrorContent(errorDrugs) {
        const maxShow = 5;
        const items = errorDrugs.slice(0, maxShow).map(error => 
            this.createTooltipItem(
                'bi bi-exclamation-triangle',
                error.name,
                'var(--danger)',
                error.error || '오류 발생'
            )
        ).join('');
        
        const moreItems = errorDrugs.length > maxShow ? 
            this.createMoreItem(`외 ${errorDrugs.length - maxShow}개...`) : '';
        
        return items + moreItems;
    }
    
    // =================== 유틸리티 메서드들 ===================
    
    /**
     * 상태 카드에서 특정 요소 찾기
     * @param {HTMLElement} element - 기준 요소
     * @param {string} selector - CSS 선택자
     * @returns {HTMLElement|null} 찾은 요소
     */
    findStatusCard(element, selector = '.status-card') {
        return element ? element.closest(selector) : null;
    }
    
    /**
     * 모든 툴팁 제거
     */
    removeAllTooltips() {
        const selectors = Object.values(this.tooltipTypes).map(type => `.${type}`).join(', ');
        const allTooltips = document.querySelectorAll(selectors);
        allTooltips.forEach(tooltip => tooltip.remove());
    }
    
    /**
     * 특정 타입의 툴팁만 제거
     * @param {string} type - 툴팁 타입
     */
    removeTooltipsByType(type) {
        if (!this.tooltipTypes[type.toUpperCase()]) {
            console.warn(`알 수 없는 툴팁 타입: ${type}`);
            return;
        }
        
        const className = this.tooltipTypes[type.toUpperCase()];
        const tooltips = document.querySelectorAll(`.${className}`);
        tooltips.forEach(tooltip => tooltip.remove());
    }
}

// 전역 인스턴스 생성
window.tooltipManager = new TooltipManager();
