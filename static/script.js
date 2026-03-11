const API = '';
let currentPanel = 'analyze';
let currentUserRole = 'viewer';

// Portfolio state
let portfolioRefreshTimer = null;
let portfolioRefreshCountdown = 60;
let portfolioData = null;

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
        // Stop portfolio refresh when leaving that tab
        if (currentPanel !== 'portfolio') stopPortfolioRefresh();
        if (currentPanel === 'history') loadHistory();
        if (currentPanel === 'usage') loadUsage();
        if (currentPanel === 'users') loadUsers();
        if (currentPanel === 'portfolio') loadPortfolio();
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

    const priceInput = document.getElementById('purchasePriceInput');
    const rawPrice = priceInput ? priceInput.value.trim().replace('$', '').replace(',', '') : '';
    const body = { ticker };
    if (rawPrice && !isNaN(parseFloat(rawPrice)) && parseFloat(rawPrice) > 0) {
        body.purchase_price = parseFloat(rawPrice);
    }

    try {
        const resp = await fetch(`${API}/api/analyze`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
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
    const recClass = rec.startsWith('BUY') ? 'badge-buy' : rec.startsWith('SELL') ? 'badge-sell' : 'badge-hold';
    const confClass = data.confidence === 'HIGH' ? 'badge-high' : data.confidence === 'MEDIUM' ? 'badge-medium' : 'badge-low';
    const riskClass = data.risk_level === 'LOW' ? 'badge-high' : data.risk_level === 'HIGH' ? 'badge-low' : 'badge-medium';
    const priceStr = data.current_price ? `$${data.current_price.toFixed(2)}` : 'N/A';
    const priceColor = rec.startsWith('BUY') ? 'var(--green)' : rec.startsWith('SELL') ? 'var(--red)' : 'var(--yellow)';

    // Entry price / P&L
    let entryHtml = '';
    if (data.purchase_price && data.current_price) {
        const pnl = data.current_price - data.purchase_price;
        const pnlPct = (pnl / data.purchase_price) * 100;
        const sign = pnl >= 0 ? '+' : '';
        const pnlColor = pnl >= 0 ? 'var(--green)' : 'var(--red)';
        entryHtml = `<div class="entry-price-row" style="margin-top:6px;font-size:13px;color:var(--text2)">Entry: $${data.purchase_price.toFixed(2)} <span style="color:${pnlColor};font-weight:600">(${sign}${pnlPct.toFixed(1)}%)</span></div>`;
    }

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
            ${entryHtml}
            <div class="badges">
                <span class="badge ${recClass}">${rec}</span>
                <span class="badge ${confClass}">${data.confidence} confidence</span>
                <span class="badge ${riskClass}">${data.risk_level || 'N/A'} risk</span>
                ${data.trend_status ? `<span class="badge badge-info">${data.trend_status}</span>` : ''}
                ${data.share_token ? `<button class="btn-share" onclick="copyShareLink('${data.share_token}', this)"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M4 12v8a2 2 0 002 2h12a2 2 0 002-2v-8"/><polyline points="16 6 12 2 8 6"/><line x1="12" y1="2" x2="12" y2="15"/></svg> Share</button>` : ''}
                <button class="btn-add-portfolio" onclick="showAddToPortfolioFromAnalysis('${data.ticker}', '${(data.company_name || '').replace(/'/g, "\\'")}', ${data.current_price || 0})">+ Portfolio</button>
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

        ${data.news_digest ? `
        <div class="news-digest-card">
            <div class="card-title">AI News Digest</div>
            <span class="sentiment-badge sentiment-${(data.news_digest.sentiment || '').toLowerCase()}">${data.news_digest.sentiment || 'N/A'}</span>
            <ul class="digest-bullets">
                ${(data.news_digest.summary_bullets || []).map(b => `<li>${b}</li>`).join('')}
            </ul>
        </div>
        ` : ''}

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
        document.getElementById('statBuys').textContent = records.filter(r => r.recommendation.startsWith('BUY')).length;
        document.getElementById('statSells').textContent = records.filter(r => r.recommendation.startsWith('SELL')).length;
        document.getElementById('statHolds').textContent = records.filter(r => r.recommendation === 'HOLD').length;

        const isAdmin = currentUserRole === 'admin';
        const colSpan = isAdmin ? 9 : 8;

        // Show/hide the User column header
        const userTh = document.getElementById('thUser');
        if (userTh) userTh.style.display = isAdmin ? '' : 'none';

        if (!records.length) {
            historyBody.innerHTML = `<tr><td colspan="${colSpan}" class="empty-row">No analysis history yet</td></tr>`;
            return;
        }

        historyBody.innerHTML = records.map(r => {
            const cls = r.recommendation.startsWith('BUY') ? 'badge-buy' : r.recommendation.startsWith('SELL') ? 'badge-sell' : 'badge-hold';
            const src = r.source === 'telegram' ? 'telegram' : '';
            const d = r.created_at ? new Date(r.created_at).toLocaleString() : '';
            const p = r.current_price ? `$${r.current_price.toFixed(2)}` : 'N/A';
            const requestedBy = r.source === 'telegram' ? (r.telegram_user || '') : (r.web_user || '');
            return `<tr onclick="showDetail(${r.id})">
                <td><strong style="font-family:'JetBrains Mono',monospace">${r.ticker}</strong></td>
                <td>${r.company_name || ''}</td>
                <td style="font-family:'JetBrains Mono',monospace">${p}</td>
                <td><span class="badge ${cls}" style="font-size:10px;padding:3px 8px">${r.recommendation}</span></td>
                <td>${r.confidence}</td>
                ${isAdmin ? `<td style="color:var(--text2);font-size:12px">${requestedBy}</td>` : ''}
                <td><span class="source-badge ${src}">${r.source}</span></td>
                <td style="color:var(--text2);font-size:12px">${d}</td>
                <td style="display:flex;gap:6px;align-items:center">
                    ${r.share_token ? `<button class="btn-share btn-share-sm" onclick="event.stopPropagation();copyShareLink('${r.share_token}', this)"><svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M4 12v8a2 2 0 002 2h12a2 2 0 002-2v-8"/><polyline points="16 6 12 2 8 6"/><line x1="12" y1="2" x2="12" y2="15"/></svg> Share</button>` : ''}
                    ${isAdmin ? `<button class="btn-delete-row" onclick="event.stopPropagation();deleteAnalysis(${r.id})" title="Delete">&times;</button>` : ''}
                </td>
            </tr>`;
        }).join('');
    } catch (err) { console.error('History error:', err); }
}

async function showDetail(id) {
    try {
        const resp = await fetch(`${API}/api/analysis/${id}`);
        const data = await resp.json();
        const rec = data.recommendation;
        const cls = rec.startsWith('BUY') ? 'badge-buy' : rec.startsWith('SELL') ? 'badge-sell' : 'badge-hold';
        const confClass = data.confidence === 'HIGH' ? 'badge-high' : data.confidence === 'MEDIUM' ? 'badge-medium' : 'badge-low';
        const riskClass = data.risk_level === 'LOW' ? 'badge-high' : data.risk_level === 'HIGH' ? 'badge-low' : 'badge-medium';
        const price = data.current_price ? `$${data.current_price.toFixed(2)}` : 'N/A';
        const priceColor = rec.startsWith('BUY') ? 'var(--green)' : rec.startsWith('SELL') ? 'var(--red)' : 'var(--yellow)';
        const date = data.created_at ? new Date(data.created_at).toLocaleString() : '';

        // Pattern banner
        const patternHtml = data.chart_pattern && data.chart_pattern !== 'None detected' && data.chart_pattern !== 'N/A'
            ? `<div class="pattern-banner"><strong>Pattern Detected:</strong> ${data.chart_pattern}</div>` : '';

        // Trading Setup
        const actionTrigger = data.action_trigger && data.action_trigger !== 'N/A' ? data.action_trigger : '';
        const breakoutLevel = data.breakout_level && data.breakout_level !== 'N/A' ? data.breakout_level : '';
        const breakoutDir = data.breakout_direction || '';
        const expGain = data.expected_gain_pct && data.expected_gain_pct !== 'N/A' ? data.expected_gain_pct : '';
        const expLoss = data.expected_loss_pct && data.expected_loss_pct !== 'N/A' ? data.expected_loss_pct : '';
        const rrRatio = data.risk_reward_ratio && data.risk_reward_ratio !== 'N/A' ? data.risk_reward_ratio : '';
        const timeframe = data.breakout_timeframe && data.breakout_timeframe !== 'N/A' ? data.breakout_timeframe : '';

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

        const hasTradingSetup = actionTrigger || breakoutLevel || expGain || data.support_levels?.length || data.resistance_levels?.length;
        const tradingSetupHtml = hasTradingSetup ? `
            <div class="trading-setup" style="margin-top:16px">
                <div class="card-title">Trading Setup</div>
                ${actionTrigger ? `<div class="action-trigger-box"><div class="action-trigger-label">Action Trigger</div><div class="action-trigger-text">${actionTrigger}</div></div>` : ''}
                <div class="setup-grid">
                    <div><div class="setup-section-title">Support Levels</div>${supportHtml}</div>
                    <div><div class="setup-section-title">Resistance Levels</div>${resistanceHtml}</div>
                </div>
                <div class="breakout-box">
                    ${breakoutLevel ? `<div class="breakout-item"><div class="breakout-item-label">Breakout Level</div><div class="breakout-item-value ${breakoutDir === 'BULLISH' ? 'green' : breakoutDir === 'BEARISH' ? 'red' : 'blue'}">${breakoutLevel}</div></div>` : ''}
                    ${expGain ? `<div class="breakout-item"><div class="breakout-item-label">Expected Gain</div><div class="breakout-item-value green">+${expGain.replace('+','')}</div></div>` : ''}
                    ${expLoss ? `<div class="breakout-item"><div class="breakout-item-label">Expected Loss</div><div class="breakout-item-value red">-${expLoss.replace('-','')}</div></div>` : ''}
                    ${rrRatio ? `<div class="breakout-item"><div class="breakout-item-label">Risk / Reward</div><div class="breakout-item-value accent">${rrRatio}</div></div>` : ''}
                </div>
                ${timeframe ? `<div class="timeframe-row">Expected timeframe: <strong>${timeframe}</strong></div>` : ''}
            </div>
        ` : '';

        // Targets & Stop Loss + Key Factors + Metrics
        let factorsHtml = '';
        if (data.key_factors && data.key_factors.length) {
            factorsHtml = '<ul>' + data.key_factors.map(f => `<li>${f}</li>`).join('') + '</ul>';
        }

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

        const cardsHtml = `
            <div class="cards-grid" style="margin-top:16px">
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
        `;

        // News
        let newsHtml = '';
        if (data.news_data && data.news_data.length) {
            newsHtml = '<div class="news-card" style="margin-top:16px"><div class="card-title">News (' + data.news_data.length + ')</div><ul class="news-list">' + data.news_data.map(a =>
                `<li class="news-item"><a href="${a.link}" target="_blank">${a.title}</a><div class="news-source">${a.source} ${a.published ? '&mdash; ' + a.published : ''}</div></li>`
            ).join('') + '</ul></div>';
        }

        // User info section
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
            userInfoHtml = `<div class="user-info-card"><div class="card-title">User Info</div>${rows}</div>`;
        }

        // Block/unblock button for telegram users (admin only)
        let blockBtnHtml = '';
        if (currentUserRole === 'admin' && data.source === 'telegram' && data.telegram_user_id) {
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
            <div class="result-hero" style="margin-bottom:0">
                <div class="result-top">
                    <div class="result-ticker-wrap">
                        <span class="result-ticker">${data.ticker}</span>
                        <span class="result-company">${data.company_name || ''}</span>
                    </div>
                    <span class="result-price" style="color:${priceColor}">${price}</span>
                </div>
                <div class="badges">
                    <span class="badge ${cls}">${rec}</span>
                    <span class="badge ${confClass}">${data.confidence} confidence</span>
                    ${data.risk_level ? `<span class="badge ${riskClass}">${data.risk_level} risk</span>` : ''}
                    ${data.trend_status ? `<span class="badge badge-info">${data.trend_status}</span>` : ''}
                    <span class="source-badge ${data.source === 'telegram' ? 'telegram' : ''}">${data.source}</span>
                    ${data.share_token ? `<button class="btn-share" onclick="copyShareLink('${data.share_token}', this)"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M4 12v8a2 2 0 002 2h12a2 2 0 002-2v-8"/><polyline points="16 6 12 2 8 6"/><line x1="12" y1="2" x2="12" y2="15"/></svg> Share</button>` : ''}
                </div>
                <p style="color:var(--text3);font-size:12px;margin-bottom:12px">${date}${data.telegram_user ? ' &mdash; ' + data.telegram_user : ''}</p>
                ${patternHtml}
                <div class="result-summary">${data.short_summary}</div>
            </div>
            ${blockBtnHtml}
            ${userInfoHtml}
            ${tradingSetupHtml}
            ${cardsHtml}
            <div class="chart-card" style="margin-top:16px">
                <div class="card-title">Candlestick Chart</div>
                <img src="${API}/api/chart/${data.ticker}" alt="Chart" onerror="this.parentElement.style.display='none'" />
            </div>
            ${data.news_digest ? `
            <div class="news-digest-card" style="margin-top:16px">
                <div class="card-title">AI News Digest</div>
                <span class="sentiment-badge sentiment-${(data.news_digest.sentiment || '').toLowerCase()}">${data.news_digest.sentiment || 'N/A'}</span>
                <ul class="digest-bullets">
                    ${(data.news_digest.summary_bullets || []).map(b => `<li>${b}</li>`).join('')}
                </ul>
            </div>
            ` : ''}
            <div class="analysis-card" style="margin-top:16px">
                <div class="card-title">Full Analysis</div>
                <div class="full-analysis">${data.full_analysis || 'N/A'}</div>
            </div>
            ${newsHtml}
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

// Chart zoom overlay
document.addEventListener('click', function(e) {
    if (e.target.matches('.chart-card img')) {
        const overlay = document.createElement('div');
        overlay.className = 'chart-overlay';
        overlay.innerHTML = '<img src="' + e.target.src + '" alt="Chart">';
        overlay.addEventListener('click', function() { overlay.remove(); });
        document.body.appendChild(overlay);
    }
});

// Filters
filterTicker.addEventListener('input', debounce(loadHistory, 500));
filterSource.addEventListener('change', loadHistory);

function debounce(fn, ms) { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; }

// --- API Usage Dashboard ---
async function loadUsage() {
    const grid = document.getElementById('usageGrid');
    if (!grid) return;
    try {
        const resp = await fetch(`${API}/api/usage`);
        if (!resp.ok) return;
        const data = await resp.json();
        grid.innerHTML = data.services.map(s => {
            const limitStr = s.limit > 0 ? s.limit : 'Unlimited';
            const pct = s.limit > 0 ? s.pct : 0;
            const barColor = pct > 85 ? 'var(--red)' : pct > 60 ? 'var(--yellow)' : 'var(--green)';
            return `<div class="usage-card">
                <div class="usage-card-label">${s.label}</div>
                <div class="usage-card-count">${s.used} <span class="usage-card-limit">/ ${limitStr}</span></div>
                ${s.limit > 0 ? `<div class="usage-bar-bg"><div class="usage-bar-fill" style="width:${Math.min(pct, 100)}%;background:${barColor}"></div></div>` : '<div class="usage-bar-bg"><div class="usage-bar-fill" style="width:0"></div></div>'}
            </div>`;
        }).join('');
    } catch (err) { console.error('Usage error:', err); }
}

// --- Role-based UI ---
async function fetchCurrentUser() {
    try {
        const resp = await fetch(`${API}/api/me`);
        if (!resp.ok) return;
        const data = await resp.json();
        currentUserRole = data.role || 'viewer';
        if (currentUserRole === 'admin') {
            const navUsers = document.getElementById('navUsers');
            if (navUsers) navUsers.style.display = '';
            const navUsage = document.getElementById('navUsage');
            if (navUsage) navUsage.style.display = '';
        }
        // Hide delete buttons for non-admins
        if (currentUserRole !== 'admin') {
            const clearBtn = document.getElementById('clearAllBtn');
            if (clearBtn) clearBtn.style.display = 'none';
        }
    } catch (err) { console.error('Failed to fetch user info:', err); }
}

// --- User Management (admin) ---
async function loadUsers() {
    const tbody = document.getElementById('usersBody');
    if (!tbody) return;
    try {
        const resp = await fetch(`${API}/api/users`);
        if (!resp.ok) return;
        const users = await resp.json();
        if (!users.length) {
            tbody.innerHTML = '<tr><td colspan="4" class="empty-row">No users</td></tr>';
            return;
        }
        tbody.innerHTML = users.map(u => {
            const d = u.created_at ? new Date(u.created_at).toLocaleString() : '';
            const roleCls = u.role === 'admin' ? 'badge-buy' : 'badge-info';
            const deleteBtn = u.role === 'admin' ? '' :
                `<button class="btn-delete-row" onclick="deleteUserAccount(${u.id}, '${u.username.replace(/'/g, "\\'")}')" title="Delete">&times;</button>`;
            return `<tr>
                <td><strong>${u.username}</strong></td>
                <td><span class="badge ${roleCls}" style="font-size:10px;padding:3px 8px">${u.role}</span></td>
                <td style="color:var(--text2);font-size:12px">${d}</td>
                <td>${deleteBtn}</td>
            </tr>`;
        }).join('');
    } catch (err) { console.error('Users error:', err); }
}

async function createUser() {
    const username = document.getElementById('newUsername').value.trim();
    const password = document.getElementById('newPassword').value;
    const role = document.getElementById('newUserRole').value;
    const msg = document.getElementById('createUserMsg');

    if (!username || !password) {
        msg.style.display = 'block';
        msg.style.color = 'var(--red)';
        msg.textContent = 'Username and password are required';
        return;
    }
    if (password.length < 4) {
        msg.style.display = 'block';
        msg.style.color = 'var(--red)';
        msg.textContent = 'Password must be at least 4 characters';
        return;
    }

    try {
        const resp = await fetch(`${API}/api/users`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password, role }),
        });
        const data = await resp.json();
        if (!resp.ok) {
            msg.style.display = 'block';
            msg.style.color = 'var(--red)';
            msg.textContent = data.error || 'Failed to create user';
            return;
        }
        msg.style.display = 'block';
        msg.style.color = 'var(--green)';
        msg.textContent = `User "${data.user.username}" created as ${data.user.role}`;
        document.getElementById('newUsername').value = '';
        document.getElementById('newPassword').value = '';
        loadUsers();
    } catch (err) {
        msg.style.display = 'block';
        msg.style.color = 'var(--red)';
        msg.textContent = 'Connection error';
    }
}

async function deleteUserAccount(id, username) {
    if (!confirm(`Delete user "${username}"? They will no longer be able to log in.`)) return;
    try {
        const resp = await fetch(`${API}/api/users/${id}`, { method: 'DELETE' });
        if (!resp.ok) { const err = await resp.json(); throw new Error(err.error || 'Delete failed'); }
        loadUsers();
    } catch (err) { alert(`Error: ${err.message}`); }
}

// --- Portfolio ---

function isMarketOpen() {
    const now = new Date();
    // Convert to EST (UTC-5) / EDT (UTC-4)
    const est = new Date(now.toLocaleString('en-US', { timeZone: 'America/New_York' }));
    const day = est.getDay(); // 0=Sun, 6=Sat
    const hours = est.getHours();
    const mins = est.getMinutes();
    const time = hours * 60 + mins;
    return day >= 1 && day <= 5 && time >= 570 && time < 960; // 9:30-16:00
}

function updateMarketStatus() {
    const dot = document.getElementById('marketDot');
    const text = document.getElementById('marketStatusText');
    if (!dot || !text) return;
    if (isMarketOpen()) {
        dot.classList.add('open');
        text.textContent = 'Market Open';
    } else {
        dot.classList.remove('open');
        text.textContent = 'Market Closed';
    }
}

async function loadPortfolio() {
    updateMarketStatus();
    await refreshPortfolioPrices();
    startPortfolioRefresh();
}

async function refreshPortfolioPrices() {
    try {
        const resp = await fetch(`${API}/api/portfolio/refresh`);
        if (!resp.ok) return;
        portfolioData = await resp.json();
        renderPortfolioSummary(portfolioData);
        renderPortfolioTable(portfolioData.items);
    } catch (err) {
        console.error('Portfolio refresh error:', err);
    }
}

function startPortfolioRefresh() {
    stopPortfolioRefresh();
    portfolioRefreshCountdown = 60;
    portfolioRefreshTimer = setInterval(function() {
        portfolioRefreshCountdown--;
        const timerEl = document.getElementById('refreshTimer');
        if (timerEl) timerEl.textContent = 'Next refresh: ' + portfolioRefreshCountdown + 's';
        if (portfolioRefreshCountdown <= 0) {
            portfolioRefreshCountdown = 60;
            updateMarketStatus();
            refreshPortfolioPrices();
        }
    }, 1000);
}

function stopPortfolioRefresh() {
    if (portfolioRefreshTimer) {
        clearInterval(portfolioRefreshTimer);
        portfolioRefreshTimer = null;
    }
}

function renderPortfolioSummary(data) {
    const t = data.totals || {};
    const valEl = document.getElementById('pfTotalValue');
    const costEl = document.getElementById('pfTotalCost');
    const pnlEl = document.getElementById('pfTotalPnl');
    const retEl = document.getElementById('pfTotalReturn');
    if (valEl) valEl.textContent = '$' + (t.total_value || 0).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
    if (costEl) costEl.textContent = '$' + (t.total_cost || 0).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
    if (pnlEl) {
        const pnl = t.total_pnl || 0;
        pnlEl.textContent = (pnl >= 0 ? '+$' : '-$') + Math.abs(pnl).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
        pnlEl.style.color = pnl >= 0 ? 'var(--green)' : 'var(--red)';
    }
    if (retEl) {
        const ret = t.total_return_pct || 0;
        retEl.textContent = (ret >= 0 ? '+' : '') + ret.toFixed(2) + '%';
        retEl.style.color = ret >= 0 ? 'var(--green)' : 'var(--red)';
    }
}

function renderPortfolioTable(items) {
    const tbody = document.getElementById('portfolioBody');
    if (!tbody) return;
    if (!items || !items.length) {
        tbody.innerHTML = '<tr><td colspan="9" class="empty-row">No stocks in portfolio yet</td></tr>';
        return;
    }
    tbody.innerHTML = items.map(function(it) {
        const price = it.current_price != null ? '$' + it.current_price.toFixed(2) : 'N/A';
        const mktVal = it.market_value != null ? '$' + it.market_value.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2}) : 'N/A';
        const pnl = it.pnl != null ? ((it.pnl >= 0 ? '+$' : '-$') + Math.abs(it.pnl).toFixed(2)) : 'N/A';
        const pnlPct = it.pnl_pct != null ? ((it.pnl_pct >= 0 ? '+' : '') + it.pnl_pct.toFixed(2) + '%') : 'N/A';
        const pnlColor = it.pnl != null ? (it.pnl >= 0 ? 'var(--green)' : 'var(--red)') : 'var(--text2)';
        const dayChg = it.day_change_pct != null ? ((it.day_change_pct >= 0 ? '+' : '') + it.day_change_pct.toFixed(2) + '%') : '';
        const dayColor = it.day_change_pct != null ? (it.day_change_pct >= 0 ? 'var(--green)' : 'var(--red)') : 'var(--text2)';

        var signalsHtml = '';
        if (it.signals && it.signals.length) {
            signalsHtml = it.signals.map(function(s) {
                return '<span class="signal-badge signal-' + s.color + '">' + s.text + '</span>';
            }).join('');
        }

        return '<tr>' +
            '<td><strong style="font-family:\'JetBrains Mono\',monospace">' + it.ticker + '</strong>' +
                (it.company_name ? '<br><span style="font-size:11px;color:var(--text3)">' + it.company_name + '</span>' : '') + '</td>' +
            '<td style="font-family:\'JetBrains Mono\',monospace">' + it.shares + '</td>' +
            '<td style="font-family:\'JetBrains Mono\',monospace">$' + it.purchase_price.toFixed(2) + '</td>' +
            '<td style="font-family:\'JetBrains Mono\',monospace">' + price +
                (dayChg ? '<br><span style="font-size:11px;color:' + dayColor + '">' + dayChg + '</span>' : '') + '</td>' +
            '<td style="font-family:\'JetBrains Mono\',monospace">' + mktVal + '</td>' +
            '<td style="font-family:\'JetBrains Mono\',monospace;color:' + pnlColor + '">' + pnl + '</td>' +
            '<td style="font-family:\'JetBrains Mono\',monospace;color:' + pnlColor + ';font-weight:600">' + pnlPct + '</td>' +
            '<td style="max-width:200px">' + signalsHtml + '</td>' +
            '<td style="white-space:nowrap"><button class="btn-pf-analyze" onclick="analyzePortfolioItem(' + it.id + ',\'' + it.ticker + '\')">Analyze</button> ' +
                '<button class="btn-delete-row" onclick="removePortfolioItem(' + it.id + ',\'' + it.ticker + '\')" title="Remove">&times;</button></td>' +
            '</tr>';
    }).join('');
}

async function addStockToPortfolio() {
    var ticker = document.getElementById('pfTicker').value.trim().toUpperCase();
    var shares = parseFloat(document.getElementById('pfShares').value);
    var price = parseFloat(document.getElementById('pfPrice').value);
    var stopLoss = parseFloat(document.getElementById('pfStopLoss').value);

    if (!ticker) { alert('Enter a ticker symbol'); return; }
    if (!shares || shares <= 0) { alert('Enter valid number of shares'); return; }
    if (!price || price <= 0) { alert('Enter valid average cost'); return; }

    var body = { ticker: ticker, shares: shares, purchase_price: price };
    if (stopLoss && stopLoss > 0) body.stop_loss = stopLoss;

    try {
        var resp = await fetch(API + '/api/portfolio', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        var data = await resp.json();
        if (!resp.ok) { alert(data.error || 'Failed to add'); return; }
        document.getElementById('pfTicker').value = '';
        document.getElementById('pfShares').value = '';
        document.getElementById('pfPrice').value = '';
        document.getElementById('pfStopLoss').value = '';
        refreshPortfolioPrices();
    } catch (err) { alert('Error: ' + err.message); }
}

async function removePortfolioItem(id, ticker) {
    if (!confirm('Remove ' + ticker + ' from portfolio?')) return;
    try {
        var resp = await fetch(API + '/api/portfolio/' + id, { method: 'DELETE' });
        if (!resp.ok) { var err = await resp.json(); alert(err.error || 'Delete failed'); return; }
        refreshPortfolioPrices();
    } catch (err) { alert('Error: ' + err.message); }
}

async function analyzePortfolioItem(id, ticker) {
    try {
        // Show loading in modal
        modalContent.innerHTML = '<div style="text-align:center;padding:40px"><div class="pulse-ring"></div><p style="margin-top:16px;color:var(--text2)">Analyzing ' + ticker + '...</p></div>';
        modalOverlay.classList.add('active');

        var resp = await fetch(API + '/api/portfolio/' + id + '/analyze', { method: 'POST' });
        if (!resp.ok) { var err = await resp.json(); throw new Error(err.error || 'Analysis failed'); }
        var data = await resp.json();
        // Reuse showDetail to render in modal by calling the analysis detail endpoint
        modalOverlay.classList.remove('active');
        showDetail(data.id);
        // Refresh portfolio to pick up updated stop_loss
        refreshPortfolioPrices();
    } catch (err) {
        modalContent.innerHTML = '<p style="color:var(--red);padding:20px">Error: ' + err.message + '</p>';
    }
}

function showAddToPortfolioFromAnalysis(ticker, company, price) {
    var sharesStr = prompt('Add ' + ticker + ' to portfolio.\n\nHow many shares?', '10');
    if (sharesStr === null) return;
    var shares = parseFloat(sharesStr);
    if (!shares || shares <= 0) { alert('Invalid number of shares'); return; }

    var priceStr = prompt('Average cost per share?', price > 0 ? price.toFixed(2) : '');
    if (priceStr === null) return;
    var avgCost = parseFloat(priceStr);
    if (!avgCost || avgCost <= 0) { alert('Invalid price'); return; }

    fetch(API + '/api/portfolio', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ticker: ticker, shares: shares, purchase_price: avgCost, company_name: company }),
    }).then(function(resp) {
        return resp.json().then(function(data) {
            if (!resp.ok) { alert(data.error || 'Failed to add'); return; }
            alert(ticker + ' added to your portfolio!');
        });
    }).catch(function(err) { alert('Error: ' + err.message); });
}

fetchCurrentUser();
loadHistory();
