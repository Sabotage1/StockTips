const API = '';
let currentPanel = 'analyze';

const tickerInput = document.getElementById('tickerInput');
const analyzeBtn = document.getElementById('analyzeBtn');
const loadingEl = document.getElementById('loading');
const resultCard = document.getElementById('resultCard');
const historyBody = document.getElementById('historyBody');
const filterTicker = document.getElementById('filterTicker');
const filterSource = document.getElementById('filterSource');
const modalOverlay = document.getElementById('modalOverlay');
const modalContent = document.getElementById('modalContent');

// Nav
document.querySelectorAll('.nav-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        currentPanel = btn.dataset.panel;
        document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
        document.getElementById(`panel-${currentPanel}`).classList.add('active');
        if (currentPanel === 'history') loadHistory();
    });
});

// Quick analyze chips
function quickAnalyze(t) {
    tickerInput.value = t;
    analyze();
}

// Analyze
analyzeBtn.addEventListener('click', analyze);
tickerInput.addEventListener('keydown', e => { if (e.key === 'Enter') analyze(); });

async function analyze() {
    const ticker = tickerInput.value.trim().toUpperCase();
    if (!ticker) return;
    analyzeBtn.disabled = true;
    loadingEl.classList.add('active');
    resultCard.classList.remove('active');

    try {
        const resp = await fetch(`${API}/api/analyze`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ticker }),
        });
        if (!resp.ok) { const err = await resp.json(); throw new Error(err.error || 'Analysis failed'); }
        renderResult(await resp.json());
    } catch (err) {
        alert(`Error: ${err.message}`);
    } finally {
        analyzeBtn.disabled = false;
        loadingEl.classList.remove('active');
    }
}

function copyShareLink(token, btn) {
    const url = window.location.origin + '/share/' + token;
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(url).then(function() {
            btn.innerHTML = 'Link copied!';
            setTimeout(function() { btn.innerHTML = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M4 12v8a2 2 0 002 2h12a2 2 0 002-2v-8"/><polyline points="16 6 12 2 8 6"/><line x1="12" y1="2" x2="12" y2="15"/></svg> Share'; }, 2000);
        });
    } else {
        var ta = document.createElement('textarea');
        ta.value = url;
        ta.style.position = 'fixed';
        ta.style.opacity = '0';
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
        btn.innerHTML = 'Link copied!';
        setTimeout(function() { btn.innerHTML = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M4 12v8a2 2 0 002 2h12a2 2 0 002-2v-8"/><polyline points="16 6 12 2 8 6"/><line x1="12" y1="2" x2="12" y2="15"/></svg> Share'; }, 2000);
    }
}

function renderResult(data) {
    const rec = data.recommendation;
    const recClass = rec === 'BUY' ? 'badge-buy' : rec === 'SELL' ? 'badge-sell' : 'badge-hold';
    const confClass = data.confidence === 'HIGH' ? 'badge-high' : data.confidence === 'MEDIUM' ? 'badge-medium' : 'badge-low';
    const riskClass = data.risk_level === 'LOW' ? 'badge-high' : data.risk_level === 'HIGH' ? 'badge-low' : 'badge-medium';
    const priceStr = data.current_price ? `$${data.current_price.toFixed(2)}` : 'N/A';
    const priceColor = rec === 'BUY' ? 'var(--green)' : rec === 'SELL' ? 'var(--red)' : 'var(--yellow)';

    // Factors
    let factorsHtml = '';
    if (data.key_factors && data.key_factors.length) {
        factorsHtml = '<ul>' + data.key_factors.map(f => `<li>${f}</li>`).join('') + '</ul>';
    }

    // Metrics
    let metricsHtml = '';
    if (data.stock_data) {
        const sd = data.stock_data;
        const fmt = v => typeof v === 'number' ? `$${v.toFixed(2)}` : v;
        const rows = [
            ['P/E', sd.pe_ratio], ['Fwd P/E', sd.forward_pe], ['EPS', sd.eps],
            ['Mkt Cap', sd.market_cap],
            ['SMA 20', sd.sma_20 ? fmt(sd.sma_20) : null],
            ['SMA 150', sd.sma_150 ? fmt(sd.sma_150) : null],
            ['SMA 200', sd.sma_200 ? fmt(sd.sma_200) : null],
            ['ATR(14)', sd.atr_14], ['RSI(14)', sd.rsi_14],
            ['Beta', sd.beta], ['Div Yield', sd.dividend_yield],
            ['MA Setup', sd.ma_alignment],
        ].filter(([_, v]) => v != null && v !== '');
        metricsHtml = '<div class="metric-grid">' +
            rows.map(([l, v]) => `<div><span class="metric-label">${l}</span><span class="metric-val">${v}</span></div>`).join('') +
            '</div>';
    }

    // News
    let newsHtml = '<p style="color:var(--text3)">No news found.</p>';
    if (data.news_articles && data.news_articles.length) {
        newsHtml = '<ul class="news-list">' + data.news_articles.slice(0, 8).map(a =>
            `<li class="news-item"><a href="${a.link}" target="_blank">${a.title}</a><div class="news-source">${a.source} ${a.published ? '&mdash; ' + a.published : ''}</div></li>`
        ).join('') + '</ul>';
    }

    const patternHtml = data.chart_pattern && data.chart_pattern !== 'None detected' && data.chart_pattern !== 'N/A'
        ? `<div class="pattern-banner"><strong>Pattern Detected:</strong> ${data.chart_pattern}</div>` : '';

    // Trading Setup - Support & Resistance
    let supportHtml = '';
    if (data.support_levels && data.support_levels.length) {
        supportHtml = '<ul class="level-list">' + data.support_levels.map(s =>
            `<li class="level-item"><span class="level-dot support"></span>${s}</li>`
        ).join('') + '</ul>';
    } else {
        supportHtml = '<p style="color:var(--text3);font-size:13px">No key supports identified</p>';
    }

    let resistanceHtml = '';
    if (data.resistance_levels && data.resistance_levels.length) {
        resistanceHtml = '<ul class="level-list">' + data.resistance_levels.map(r =>
            `<li class="level-item"><span class="level-dot resistance"></span>${r}</li>`
        ).join('') + '</ul>';
    } else {
        resistanceHtml = '<p style="color:var(--text3);font-size:13px">No key resistances identified</p>';
    }

    const actionTrigger = data.action_trigger && data.action_trigger !== 'N/A' ? data.action_trigger : '';
    const breakoutLevel = data.breakout_level && data.breakout_level !== 'N/A' ? data.breakout_level : '';
    const breakoutDir = data.breakout_direction || '';
    const expGain = data.expected_gain_pct && data.expected_gain_pct !== 'N/A' ? data.expected_gain_pct : '';
    const expLoss = data.expected_loss_pct && data.expected_loss_pct !== 'N/A' ? data.expected_loss_pct : '';
    const rrRatio = data.risk_reward_ratio && data.risk_reward_ratio !== 'N/A' ? data.risk_reward_ratio : '';
    const timeframe = data.breakout_timeframe && data.breakout_timeframe !== 'N/A' ? data.breakout_timeframe : '';

    const hasTradingSetup = actionTrigger || breakoutLevel || expGain || data.support_levels?.length || data.resistance_levels?.length;

    const tradingSetupHtml = hasTradingSetup ? `
        <div class="trading-setup">
            <div class="card-title">Trading Setup</div>
            ${actionTrigger ? `
                <div class="action-trigger-box">
                    <div class="action-trigger-label">Action Trigger</div>
                    <div class="action-trigger-text">${actionTrigger}</div>
                </div>
            ` : ''}
            <div class="setup-grid">
                <div>
                    <div class="setup-section-title">Support Levels</div>
                    ${supportHtml}
                </div>
                <div>
                    <div class="setup-section-title">Resistance Levels</div>
                    ${resistanceHtml}
                </div>
            </div>
            <div class="breakout-box">
                ${breakoutLevel ? `
                    <div class="breakout-item">
                        <div class="breakout-item-label">Breakout Level</div>
                        <div class="breakout-item-value ${breakoutDir === 'BULLISH' ? 'green' : breakoutDir === 'BEARISH' ? 'red' : 'blue'}">${breakoutLevel}</div>
                    </div>
                ` : ''}
                ${expGain ? `
                    <div class="breakout-item">
                        <div class="breakout-item-label">Expected Gain</div>
                        <div class="breakout-item-value green">+${expGain.replace('+','')}</div>
                    </div>
                ` : ''}
                ${expLoss ? `
                    <div class="breakout-item">
                        <div class="breakout-item-label">Expected Loss</div>
                        <div class="breakout-item-value red">-${expLoss.replace('-','')}</div>
                    </div>
                ` : ''}
                ${rrRatio ? `
                    <div class="breakout-item">
                        <div class="breakout-item-label">Risk / Reward</div>
                        <div class="breakout-item-value accent">${rrRatio}</div>
                    </div>
                ` : ''}
            </div>
            ${timeframe ? `
                <div class="timeframe-row">
                    Expected timeframe: <strong>${timeframe}</strong>
                </div>
            ` : ''}
        </div>
    ` : '';

    resultCard.innerHTML = `
        <div class="result-hero">
            <div class="result-top">
                <div class="result-ticker-wrap">
                    <span class="result-ticker">${data.ticker}</span>
                    <span class="result-company">${data.company_name || ''}</span>
                </div>
                <span class="result-price" style="color:${priceColor}">${priceStr}</span>
            </div>
            <div class="badges">
                <span class="badge ${recClass}">${rec}</span>
                <span class="badge ${confClass}">${data.confidence} confidence</span>
                <span class="badge ${riskClass}">${data.risk_level || 'N/A'} risk</span>
                ${data.trend_status ? `<span class="badge badge-info">${data.trend_status}</span>` : ''}
                ${data.share_token ? `<button class="btn-share" onclick="copyShareLink('${data.share_token}', this)"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M4 12v8a2 2 0 002 2h12a2 2 0 002-2v-8"/><polyline points="16 6 12 2 8 6"/><line x1="12" y1="2" x2="12" y2="15"/></svg> Share</button>` : ''}
            </div>
            ${patternHtml}
            <div class="result-summary">${data.short_summary}</div>
        </div>

        ${tradingSetupHtml}

        <div class="cards-grid">
            <div class="card">
                <div class="card-title">Targets & Stop Loss</div>
                <div class="target-row"><span class="target-label">Short-term</span><span class="target-val">${data.price_target_short || 'N/A'}</span></div>
                <div class="target-row"><span class="target-label">Long-term</span><span class="target-val">${data.price_target_long || 'N/A'}</span></div>
                <div class="target-row"><span class="target-label">Stop Loss</span><span class="target-val red">${data.stop_loss || 'N/A'}</span></div>
            </div>
            <div class="card">
                <div class="card-title">Key Factors</div>
                ${factorsHtml || '<p style="color:var(--text3)">N/A</p>'}
            </div>
            <div class="card">
                <div class="card-title">Metrics</div>
                ${metricsHtml || '<p style="color:var(--text3)">N/A</p>'}
            </div>
        </div>

        <div class="chart-card">
            <div class="card-title">Candlestick Chart &mdash; SMA 20 / 150 / 200</div>
            <img src="${API}/api/chart/${data.ticker}" alt="Chart"
                 onerror="this.style.display='none'" />
        </div>

        <div class="analysis-card">
            <div class="card-title">Full Analysis</div>
            <div class="full-analysis">${data.full_analysis || 'N/A'}</div>
        </div>

        <div class="news-card">
            <div class="card-title">News (${data.news_count || 0})</div>
            ${newsHtml}
        </div>
    `;
    resultCard.classList.add('active');
}

// History
async function loadHistory() {
    const ticker = filterTicker.value.trim().toUpperCase();
    const source = filterSource.value;
    let url = `${API}/api/history?days=30`;
    if (ticker) url += `&ticker=${ticker}`;

    try {
        const resp = await fetch(url);
        let records = await resp.json();
        if (source) records = records.filter(r => r.source === source);

        document.getElementById('statTotal').textContent = records.length;
        document.getElementById('statBuys').textContent = records.filter(r => r.recommendation === 'BUY').length;
        document.getElementById('statSells').textContent = records.filter(r => r.recommendation === 'SELL').length;
        document.getElementById('statHolds').textContent = records.filter(r => r.recommendation === 'HOLD').length;

        if (!records.length) {
            historyBody.innerHTML = '<tr><td colspan="8" class="empty-row">No analysis history yet</td></tr>';
            return;
        }

        historyBody.innerHTML = records.map(r => {
            const cls = r.recommendation === 'BUY' ? 'badge-buy' : r.recommendation === 'SELL' ? 'badge-sell' : 'badge-hold';
            const src = r.source === 'telegram' ? 'telegram' : '';
            const d = r.created_at ? new Date(r.created_at).toLocaleString() : '';
            const p = r.current_price ? `$${r.current_price.toFixed(2)}` : 'N/A';
            return `<tr onclick="showDetail(${r.id})">
                <td><strong style="font-family:'JetBrains Mono',monospace">${r.ticker}</strong></td>
                <td>${r.company_name || ''}</td>
                <td style="font-family:'JetBrains Mono',monospace">${p}</td>
                <td><span class="badge ${cls}" style="font-size:10px;padding:3px 8px">${r.recommendation}</span></td>
                <td>${r.confidence}</td>
                <td><span class="source-badge ${src}">${r.source}</span></td>
                <td style="color:var(--text2);font-size:12px">${d}</td>
                <td style="display:flex;gap:6px;align-items:center">
                    ${r.share_token ? `<button class="btn-share btn-share-sm" onclick="event.stopPropagation();copyShareLink('${r.share_token}', this)"><svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M4 12v8a2 2 0 002 2h12a2 2 0 002-2v-8"/><polyline points="16 6 12 2 8 6"/><line x1="12" y1="2" x2="12" y2="15"/></svg> Share</button>` : ''}
                    <button class="btn-delete-row" onclick="event.stopPropagation();deleteAnalysis(${r.id})" title="Delete">&times;</button>
                </td>
            </tr>`;
        }).join('');
    } catch (err) { console.error('History error:', err); }
}

async function showDetail(id) {
    try {
        const resp = await fetch(`${API}/api/analysis/${id}`);
        const data = await resp.json();
        const cls = data.recommendation === 'BUY' ? 'badge-buy' : data.recommendation === 'SELL' ? 'badge-sell' : 'badge-hold';
        const price = data.current_price ? `$${data.current_price.toFixed(2)}` : 'N/A';
        const date = data.created_at ? new Date(data.created_at).toLocaleString() : '';

        let newsHtml = '';
        if (data.news_data && data.news_data.length) {
            newsHtml = '<ul class="news-list">' + data.news_data.map(a =>
                `<li class="news-item"><a href="${a.link}" target="_blank">${a.title}</a><div class="news-source">${a.source}</div></li>`
            ).join('') + '</ul>';
        }

        // Build user info section
        let userInfoHtml = '';
        const hasUserInfo = data.telegram_user || data.telegram_user_id || data.user_ip;
        if (hasUserInfo) {
            let rows = '';
            if (data.source === 'telegram') {
                if (data.telegram_user) rows += `<div class="user-info-row"><span class="user-info-label">Username</span><span class="user-info-val">${data.telegram_user}</span></div>`;
                if (data.telegram_user_id) rows += `<div class="user-info-row"><span class="user-info-label">Telegram ID</span><span class="user-info-val">${data.telegram_user_id}</span></div>`;
            }
            if (data.user_ip) rows += `<div class="user-info-row"><span class="user-info-label">IP Address</span><span class="user-info-val">${data.user_ip}</span></div>`;
            rows += `<div class="user-info-row"><span class="user-info-label">Source</span><span class="user-info-val"><span class="source-badge ${data.source === 'telegram' ? 'telegram' : ''}">${data.source}</span></span></div>`;

            userInfoHtml = `
                <div class="user-info-card">
                    <div class="card-title">User Info</div>
                    ${rows}
                </div>
            `;
        }

        // Block/unblock button for telegram users
        let blockBtnHtml = '';
        if (data.source === 'telegram' && data.telegram_user_id) {
            const isBlocked = data.is_blocked;
            blockBtnHtml = `
                <div class="block-user-section" style="margin-bottom:16px">
                    <button class="btn-block-user ${isBlocked ? 'blocked' : ''}"
                            id="blockBtn"
                            onclick="toggleBlockUser('${data.telegram_user_id}', '${(data.telegram_user || '').replace(/'/g, "\\'")}', ${isBlocked})">
                        ${isBlocked ? 'Unblock User' : 'Block User'}
                    </button>
                    ${isBlocked ? '<span class="block-status">This user is blocked from using the bot</span>' : ''}
                </div>
            `;
        }

        modalContent.innerHTML = `
            <div style="margin-bottom:20px">
                <span class="result-ticker">${data.ticker}</span>
                <span class="result-company" style="margin-left:8px">${data.company_name || ''}</span>
                <span style="float:right;font-family:'JetBrains Mono',monospace;font-size:22px;font-weight:700">${price}</span>
            </div>
            <div class="badges" style="margin-bottom:16px">
                <span class="badge ${cls}">${data.recommendation}</span>
                <span class="badge badge-info">${data.confidence}</span>
                <span class="source-badge ${data.source === 'telegram' ? 'telegram' : ''}">${data.source}</span>
                ${data.share_token ? `<button class="btn-share" onclick="copyShareLink('${data.share_token}', this)"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M4 12v8a2 2 0 002 2h12a2 2 0 002-2v-8"/><polyline points="16 6 12 2 8 6"/><line x1="12" y1="2" x2="12" y2="15"/></svg> Share</button>` : ''}
            </div>
            <p style="color:var(--text3);font-size:12px;margin-bottom:16px">${date}${data.telegram_user ? ' &mdash; ' + data.telegram_user : ''}</p>
            ${blockBtnHtml}
            ${userInfoHtml}
            <div class="result-summary">${data.short_summary}</div>
            <div class="chart-card" style="margin-top:16px">
                <img src="${API}/api/chart/${data.ticker}" alt="Chart" onerror="this.parentElement.style.display='none'" />
            </div>
            <div class="analysis-card" style="margin-top:16px;background:none;border:none;padding:0">
                <div class="card-title">Analysis</div>
                <div class="full-analysis">${data.full_analysis || 'N/A'}</div>
            </div>
            ${newsHtml ? `<div style="margin-top:16px"><div class="card-title">News</div>${newsHtml}</div>` : ''}
        `;
        modalOverlay.classList.add('active');
    } catch (err) { console.error('Detail error:', err); }
}

// Block / Unblock user
async function toggleBlockUser(userId, username, isCurrentlyBlocked) {
    const action = isCurrentlyBlocked ? 'unblock' : 'block';
    if (!confirm(`${isCurrentlyBlocked ? 'Unblock' : 'Block'} user ${username || userId}? ${isCurrentlyBlocked ? 'They will be able to use the bot again.' : 'They will no longer be able to use the bot.'}`)) return;
    try {
        const endpoint = isCurrentlyBlocked ? '/api/unblock-user' : '/api/block-user';
        const resp = await fetch(`${API}${endpoint}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ telegram_user_id: userId, telegram_username: username }),
        });
        if (!resp.ok) { const err = await resp.json(); throw new Error(err.error || `${action} failed`); }
        const btn = document.getElementById('blockBtn');
        const section = btn.parentElement;
        if (isCurrentlyBlocked) {
            btn.classList.remove('blocked');
            btn.textContent = 'Block User';
            btn.setAttribute('onclick', `toggleBlockUser('${userId}', '${username.replace(/'/g, "\\'")}', false)`);
            const status = section.querySelector('.block-status');
            if (status) status.remove();
        } else {
            btn.classList.add('blocked');
            btn.textContent = 'Unblock User';
            btn.setAttribute('onclick', `toggleBlockUser('${userId}', '${username.replace(/'/g, "\\'")}', true)`);
            const status = document.createElement('span');
            status.className = 'block-status';
            status.textContent = 'This user is blocked from using the bot';
            section.appendChild(status);
        }
    } catch (err) { alert(`Error: ${err.message}`); }
}

// Modal
document.querySelector('.modal-close').addEventListener('click', () => modalOverlay.classList.remove('active'));
modalOverlay.addEventListener('click', e => { if (e.target === modalOverlay) modalOverlay.classList.remove('active'); });

// Delete single analysis
async function deleteAnalysis(id) {
    if (!confirm('Delete this analysis?')) return;
    try {
        const resp = await fetch(`${API}/api/analysis/${id}`, { method: 'DELETE' });
        if (!resp.ok) { const err = await resp.json(); throw new Error(err.error || 'Delete failed'); }
        loadHistory();
    } catch (err) { alert(`Error: ${err.message}`); }
}

// Clear all history
async function clearAllHistory() {
    if (!confirm('Delete ALL history? This cannot be undone.')) return;
    try {
        const resp = await fetch(`${API}/api/history`, { method: 'DELETE' });
        if (!resp.ok) { const err = await resp.json(); throw new Error(err.error || 'Delete failed'); }
        loadHistory();
    } catch (err) { alert(`Error: ${err.message}`); }
}

// Filters
filterTicker.addEventListener('input', debounce(loadHistory, 500));
filterSource.addEventListener('change', loadHistory);

function debounce(fn, ms) { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; }

loadHistory();
