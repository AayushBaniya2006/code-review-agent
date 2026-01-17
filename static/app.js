// Change-Aware Auditor - Frontend JavaScript
let auditData = null;
let currentTab = null;

// ===== AUDIT FUNCTIONALITY =====

async function runAudit() {
    const diffInput = document.getElementById('diff-input');
    const depth = document.getElementById('depth').value;
    const checkboxes = document.querySelectorAll('input[name="audit"]:checked');
    const audits = Array.from(checkboxes).map(cb => cb.value);

    if (!diffInput.value.trim()) {
        showNotification('Please enter a git diff to analyze', 'error');
        return;
    }

    if (audits.length === 0) {
        showNotification('Please select at least one audit type', 'error');
        return;
    }

    // Show loading
    setLoading(true);

    try {
        const response = await fetch('/api/v1/audit/diff', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                diff: diffInput.value,
                audits: audits,
                depth: depth
            })
        });

        const responseText = await response.text();
        if (!response.ok) {
            const contentType = response.headers.get('content-type') || '';
            let message = `Audit failed (${response.status})`;
            if (responseText) {
                if (contentType.includes('application/json')) {
                    try {
                        const error = JSON.parse(responseText);
                        message = error.detail || error.error || message;
                    } catch (parseError) {
                        message = responseText.trim();
                    }
                } else {
                    message = responseText.trim();
                }
            }
            throw new Error(message);
        }

        try {
            auditData = JSON.parse(responseText);
        } catch (parseError) {
            throw new Error('Audit failed: server returned invalid JSON');
        }
        displayResults();
    } catch (error) {
        console.error('Audit error:', error);
        showNotification('Audit failed: ' + error.message, 'error');
    } finally {
        setLoading(false);
    }
}

function setLoading(isLoading) {
    const loading = document.getElementById('loading');
    const results = document.getElementById('results');
    const btn = document.getElementById('audit-btn');
    const btnText = document.getElementById('btn-text');

    if (isLoading) {
        loading.classList.add('is-visible');
        results.classList.remove('is-visible');
        btn.disabled = true;
        btnText.textContent = 'Analyzing...';
    } else {
        loading.classList.remove('is-visible');
        btn.disabled = false;
        btnText.textContent = 'Run Audit';
    }
}

function displayResults() {
    const results = document.getElementById('results');
    results.classList.add('is-visible');

    // Scroll to results
    setTimeout(() => {
        results.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 100);

    // Update score cards
    const score = auditData.summary.overall_score;
    const scoreEl = document.getElementById('overall-score');
    scoreEl.textContent = score;
    scoreEl.className = `summary-card__value ${getScoreColorClass(score)}`;

    const riskEl = document.getElementById('risk-level');
    riskEl.textContent = auditData.summary.risk_level.toUpperCase();
    riskEl.className = `summary-card__value ${getRiskColorClass(auditData.summary.risk_level)}`;

    document.getElementById('total-findings').textContent = auditData.summary.total_findings;
    document.getElementById('critical-count').textContent = auditData.summary.critical_findings;

    // Update executive summary
    const synthesis = auditData.synthesis || {};
    document.getElementById('summary-text').textContent =
        synthesis.executive_summary || 'Analysis complete. Review findings below.';

    const verdict = synthesis.verdict || 'APPROVE_WITH_CHANGES';
    const verdictBox = document.getElementById('verdict-box');
    verdictBox.textContent = verdict.replace(/_/g, ' ');
    verdictBox.className = `audit-results__verdict ${getVerdictClass(verdict)}`;

    buildAuditTabs();
}

function buildAuditTabs() {
    const tabsContainer = document.getElementById('audit-tabs');
    const audits = auditData.audits;

    if (!audits) {
        tabsContainer.innerHTML = '<p class="no-data">No audit data available</p>';
        return;
    }

    tabsContainer.innerHTML = '';

    const auditNames = {
        security: 'Security',
        quality: 'Quality',
        performance: 'Performance',
        best_practices: 'Best Practices'
    };

    let first = true;
    for (const [key, data] of Object.entries(audits)) {
        const tab = document.createElement('button');
        tab.className = `audit-tabs__btn ${first ? 'is-active' : ''}`;
        tab.textContent = `${auditNames[key] || key} (${data.score || '--'})`;
        tab.onclick = () => showAudit(key, tab);
        tabsContainer.appendChild(tab);

        if (first) {
            showAudit(key, tab);
            first = false;
        }
    }
}

function showAudit(auditKey, tabElement) {
    // Update tab styles
    document.querySelectorAll('.audit-tabs__btn').forEach(btn => {
        btn.classList.remove('is-active');
    });
    tabElement.classList.add('is-active');

    currentTab = auditKey;
    const data = auditData.audits[auditKey];
    const container = document.getElementById('audit-content');

    if (!data) {
        container.innerHTML = '<p style="color: var(--text-muted);">No data available</p>';
        return;
    }

    const scoreValue = data.score;
    const scoreDisplay = scoreValue === null || scoreValue === undefined ? '--' : scoreValue;
    const scoreClass = scoreValue === null || scoreValue === undefined
        ? 'summary-card__value--muted'
        : getScoreColorClass(scoreValue);

    let html = `
        <div class="audit-tabs__score">
            <div class="audit-tabs__score-value ${scoreClass}">${scoreDisplay}</div>
            <div class="audit-tabs__score-max">/ 100</div>
        </div>
    `;

    if (data.error) {
        html += `
            <div class="audit-warning">
                Audit failed for this category.
                <span class="audit-warning__detail">${escapeHtml(data.error)}</span>
            </div>
        `;
    } else if (data.parse_success === false) {
        html += `
            <div class="audit-warning">
                Parsing failed. Showing best-effort output.
                <span class="audit-warning__detail">${escapeHtml(data.parse_error || 'Invalid JSON from model')}</span>
            </div>
        `;
    }

    // Findings
    const findings = data.findings || [];
    if (findings.length > 0) {
        html += '<h4 style="font-size: 14px; font-weight: 600; letter-spacing: 0.05em; text-transform: uppercase; color: var(--text-muted); margin-bottom: 16px;">Findings</h4>';
        html += '<div class="findings-list">';
        findings.forEach(finding => {
            html += renderFinding(finding);
        });
        html += '</div>';
    } else {
        html += `
            <div class="no-findings">
                <svg class="no-findings__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/>
                </svg>
                <p class="no-findings__text">No issues found in this category</p>
            </div>
        `;
    }

    container.innerHTML = html;
}

function renderFinding(finding) {
    const severity = finding.severity || 'info';

    return `
        <div class="finding finding--${severity}">
            <div class="finding__header">
                <span class="finding__severity severity--${severity}">${escapeHtml(severity)}</span>
                <span class="finding__title">${escapeHtml(finding.title || finding.type || 'Issue')}</span>
                ${finding.line ? `<span class="finding__line">Line ${parseInt(finding.line, 10) || ''}</span>` : ''}
            </div>

            <p class="finding__description">${escapeHtml(finding.description || '')}</p>

            ${renderEvidence(finding.evidence)}

            ${finding.scenario ? `
                <div class="finding__detail">
                    <div class="finding__detail-label">Scenario</div>
                    <div class="finding__detail-text">${escapeHtml(finding.scenario)}</div>
                </div>
            ` : ''}

            ${finding.impact ? `
                <div class="finding__detail">
                    <div class="finding__detail-label">Impact</div>
                    <div class="finding__detail-text">${escapeHtml(finding.impact)}</div>
                </div>
            ` : ''}

            ${finding.code_snippet ? `
                <pre class="finding__code"><code>${escapeHtml(finding.code_snippet)}</code></pre>
            ` : ''}

            ${finding.suggestion ? `
                <div class="finding__suggestion">
                    <div class="finding__suggestion-label">Suggestion</div>
                    <div class="finding__suggestion-text">${escapeHtml(finding.suggestion)}</div>
                </div>
            ` : ''}

            ${finding.patch ? `
                <div class="finding__detail">
                    <div class="finding__detail-label">Patch</div>
                    <pre class="finding__code"><code>${escapeHtml(finding.patch)}</code></pre>
                </div>
            ` : ''}

            ${renderTests(finding.tests)}
        </div>
    `;
}

// ===== UTILITY FUNCTIONS =====

function getScoreColorClass(score) {
    if (score >= 80) return 'summary-card__value--green';
    if (score >= 60) return 'summary-card__value--yellow';
    if (score >= 40) return 'summary-card__value--orange';
    return 'summary-card__value--red';
}

function getRiskColorClass(risk) {
    const colors = {
        critical: 'summary-card__value--red',
        high: 'summary-card__value--orange',
        medium: 'summary-card__value--yellow',
        low: 'summary-card__value--green'
    };
    return colors[risk] || '';
}

function getVerdictClass(verdict) {
    const classes = {
        'APPROVE': 'verdict--approve',
        'APPROVE_WITH_CHANGES': 'verdict--changes',
        'REQUEST_CHANGES': 'verdict--request',
        'BLOCK': 'verdict--block'
    };
    return classes[verdict] || 'verdict--changes';
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function normalizeList(value) {
    if (!value) return [];
    if (Array.isArray(value)) return value.filter(Boolean);
    if (typeof value === 'string') return [value];
    return [];
}

function renderEvidence(evidence) {
    const items = normalizeList(evidence);
    if (items.length === 0) return '';
    const listItems = items.map(item => {
        if (typeof item === 'object') {
            return `<li>${escapeHtml(item.snippet || item.file_path || JSON.stringify(item))}</li>`;
        }
        return `<li>${escapeHtml(item)}</li>`;
    }).join('');
    return `
        <div class="finding__detail">
            <div class="finding__detail-label">Evidence</div>
            <ul class="finding__detail-list">${listItems}</ul>
        </div>
    `;
}

function renderTests(tests) {
    const items = normalizeList(tests);
    if (items.length === 0) return '';
    const content = items.map(item => escapeHtml(item)).join('\n\n');
    return `
        <div class="finding__detail">
            <div class="finding__detail-label">Tests</div>
            <pre class="finding__code"><code>${content}</code></pre>
        </div>
    `;
}

function showNotification(message, type = 'info') {
    // Create notification element
    const notification = document.createElement('div');
    notification.style.cssText = `
        position: fixed;
        top: 100px;
        left: 50%;
        transform: translateX(-50%);
        padding: 16px 24px;
        background: ${type === 'error' ? '#ef4444' : '#1a1a1a'};
        color: white;
        border-radius: 4px;
        font-size: 14px;
        z-index: 10000;
        box-shadow: 0 4px 20px rgba(0,0,0,0.15);
    `;
    notification.textContent = message;
    document.body.appendChild(notification);

    // Auto-remove after 5 seconds
    setTimeout(() => {
        notification.remove();
    }, 5000);
}

// ===== REVEAL ANIMATIONS =====

function initRevealAnimations() {
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('is-visible');
            }
        });
    }, {
        threshold: 0.1,
        rootMargin: '0px 0px -50px 0px'
    });

    document.querySelectorAll('.reveal').forEach(el => {
        observer.observe(el);
    });
}

// ===== SMOOTH SCROLL =====

function initSmoothScroll() {
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function(e) {
            e.preventDefault();
            const targetId = this.getAttribute('href');
            if (targetId === '#') return;

            const target = document.querySelector(targetId);
            if (target) {
                const nav = document.querySelector('.nav');
                const navHeight = nav ? nav.offsetHeight : 0;
                const targetPosition = target.getBoundingClientRect().top + window.pageYOffset - navHeight - 20;
                window.scrollTo({
                    top: targetPosition,
                    behavior: 'smooth'
                });
            }
        });
    });
}

// ===== MOBILE MENU =====

function initMobileMenu() {
    const toggle = document.querySelector('.nav__mobile-toggle');
    const links = document.querySelector('.nav__links');

    if (toggle && links) {
        toggle.addEventListener('click', () => {
            links.classList.toggle('is-open');
            toggle.classList.toggle('is-open');
        });
    }
}

// ===== NAVIGATION SCROLL EFFECT =====

function initNavScroll() {
    const nav = document.querySelector('.nav');
    if (!nav) return;

    window.addEventListener('scroll', () => {
        const currentScroll = window.pageYOffset;

        if (currentScroll > 100) {
            nav.style.borderBottomColor = 'var(--border-light)';
        } else {
            nav.style.borderBottomColor = 'transparent';
        }
    });
}

// ===== INITIALIZE =====

document.addEventListener('DOMContentLoaded', () => {
    console.log('Change-Aware Auditor loaded');

    initRevealAnimations();
    initSmoothScroll();
    initMobileMenu();
    initNavScroll();
});
