const API = '';
let currentPanel = 'analyze';
let currentUserRole = 'viewer';

// Portfolio state
let portfolioRefreshTimer = null;
let portfolioRefreshCountdown = 60;
let portfolioData = null;
let currentStockDetailId = null;

// Settings state
let userSettings = null;
let settingsSaveTimer = null;

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
document.querySelectorAll('.nav-btn[data-panel]').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        currentPanel = btn.dataset.panel;
        document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
        document.getElementById(`panel-${currentPanel}`).classList.add('active');
        // Stop portfolio refresh when leaving that tab
        if (currentPanel !== 'portfolio') {
            stopPortfolioRefresh();
            if (currentStockDetailId) closeStockDetail();
        }
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
tickerInput.addEventListener('focus', () => tickerInput.select());

let analyzeController = null;

async function analyze() {
    const ticker = tickerInput.value.trim().toUpperCase();
    if (!ticker) return;

    // Abort any previous in-flight analysis
    if (analyzeController) {
        analyzeController.abort();
        analyzeController = null;
    }

    analyzeBtn.disabled = true;
    resultCard.classList.remove('active');
    resultCard.innerHTML = '';

    // Show loading with ticker name
    loadingEl.classList.add('active');
    const loadingText = loadingEl.querySelector('.loading-text');
    const loadingSub = loadingEl.querySelector('.loading-sub');
    if (loadingText) loadingText.textContent = 'Analyzing ' + ticker;
    if (loadingSub) loadingSub.textContent = 'Gathering data from multiple sources...';

    window.scrollTo({ top: 0, behavior: 'smooth' });

    const priceInput = document.getElementById('purchasePriceInput');
    const rawPrice = priceInput ? priceInput.value.trim().replace('$', '').replace(',', '') : '';
    const body = { ticker };
    if (rawPrice && !isNaN(parseFloat(rawPrice)) && parseFloat(rawPrice) > 0) {
        body.purchase_price = parseFloat(rawPrice);
    }

    analyzeController = new AbortController();
    const signal = analyzeController.signal;

    try {
        const resp = await fetch(`${API}/api/analyze`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
            signal: signal,
        });
        if (!resp.ok) { const err = await resp.json(); throw new Error(err.error || 'Analysis failed'); }
        renderResult(await resp.json());
    } catch (err) {
        if (err.name === 'AbortError') return; // replaced by new analysis, don't show error
        resultCard.innerHTML = `<div style="text-align:center;padding:32px"><p style="color:var(--red);font-size:15px;font-weight:600">Error: ${err.message}</p><p style="color:var(--text3);font-size:13px;margin-top:8px">Try again or enter a different ticker</p></div>`;
        resultCard.classList.add('active');
    } finally {
        analyzeController = null;
        analyzeBtn.disabled = false;
        loadingEl.classList.remove('active');
        tickerInput.focus();
    }
}

function goToAnalyze(ticker, purchasePrice) {
    // Switch to analyze panel
    document.querySelectorAll('.nav-btn').forEach(function(b) { b.classList.remove('active'); });
    document.querySelectorAll('.panel').forEach(function(p) { p.classList.remove('active'); });
    var analyzeBtn = document.querySelector('.nav-btn[data-panel="analyze"]');
    if (analyzeBtn) analyzeBtn.classList.add('active');
    document.getElementById('panel-analyze').classList.add('active');
    currentPanel = 'analyze';
    stopPortfolioRefresh();

    // Fill ticker and purchase price, then trigger analysis
    tickerInput.value = ticker;
    var priceInput = document.getElementById('purchasePriceInput');
    if (priceInput && purchasePrice) priceInput.value = purchasePrice;
    analyze();
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
                <button class="btn-add-portfolio" onclick="showAddToPortfolioFromAnalysis('${data.ticker}', '${(data.company_name || '').replace(/'/g, "\\'")}', ${data.purchase_price || data.current_price || 0})">+ Portfolio</button>
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
var historyScope = 'user'; // 'user' or 'global' (admin only)

function toggleHistoryScope() {
    historyScope = historyScope === 'user' ? 'global' : 'user';
    loadHistory();
}

async function loadHistory() {
    const ticker = filterTicker.value.trim().toUpperCase();
    const source = filterSource.value;
    const isAdmin = currentUserRole === 'admin';
    let url = `${API}/api/history?days=30`;
    if (ticker) url += `&ticker=${ticker}`;
    if (isAdmin && historyScope === 'global') url += '&scope=global';

    // Show/hide global toggle button for admins
    var globalToggle = document.getElementById('globalHistoryToggle');
    if (globalToggle) {
        globalToggle.style.display = isAdmin ? '' : 'none';
        globalToggle.textContent = historyScope === 'global' ? 'My History' : 'Global History';
        globalToggle.className = historyScope === 'global' ? 'btn-global-history active' : 'btn-global-history';
    }

    try {
        const resp = await fetch(url);
        let records = await resp.json();
        if (source) records = records.filter(r => r.source === source);

        document.getElementById('statTotal').textContent = records.length;
        document.getElementById('statBuys').textContent = records.filter(r => r.recommendation.startsWith('BUY')).length;
        document.getElementById('statSells').textContent = records.filter(r => r.recommendation.startsWith('SELL')).length;
        document.getElementById('statHolds').textContent = records.filter(r => r.recommendation === 'HOLD').length;

        var showUserCol = isAdmin && historyScope === 'global';
        const colSpan = showUserCol ? 9 : 8;

        // Show/hide the User column header
        const userTh = document.getElementById('thUser');
        if (userTh) userTh.style.display = showUserCol ? '' : 'none';

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
                ${showUserCol ? `<td style="color:var(--text2);font-size:12px">${requestedBy}</td>` : ''}
                <td><span class="source-badge ${src}">${r.source}</span></td>
                <td style="color:var(--text2);font-size:12px">${d}</td>
                <td style="display:flex;gap:6px;align-items:center">
                    <button class="btn-add-portfolio" style="padding:3px 10px;font-size:10px" onclick="event.stopPropagation();showAddToPortfolioFromAnalysis('${r.ticker}', '${(r.company_name || '').replace(/'/g, "\\'")}', ${r.current_price || 0})">+ Portfolio</button>
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

// Portfolio modal - click outside to close
document.getElementById('pfModalOverlay').addEventListener('click', function(e) {
    if (e.target === this) closePfModal();
});

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
        if (data.settings) userSettings = data.settings;
        // Admin nav buttons are now rendered server-side via Jinja2
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
        if (!resp.ok) {
            // Fallback: try basic portfolio list if refresh fails
            const fallback = await fetch(`${API}/api/portfolio`);
            if (!fallback.ok) return;
            const items = await fallback.json();
            portfolioData = { items: items.map(function(it) {
                return { id: it.id, ticker: it.ticker, company_name: it.company_name,
                    shares: it.shares, purchase_price: it.purchase_price, stop_loss: it.stop_loss,
                    current_price: null, market_value: null, pnl: null, pnl_pct: null,
                    day_pnl: null, day_pnl_pct_avg: null, day_change_pct: null, pct_of_portfolio: null, signals: [] };
            }), totals: {} };
        } else {
            portfolioData = await resp.json();
        }
        renderPortfolioSummary(portfolioData);
        renderPortfolioTable(portfolioData.items);
        renderPortfolioPieChart(portfolioData.items);
        applySettings();
        initDragAndDrop();
    } catch (err) {
        console.error('Portfolio refresh error:', err);
    }
}

var PIE_COLORS = [
    '#7c6cf0', '#34d399', '#f59e0b', '#ef4444', '#60a5fa',
    '#f472b6', '#a78bfa', '#2dd4a0', '#fb923c', '#38bdf8',
    '#e879f9', '#4ade80', '#facc15', '#f87171', '#818cf8'
];

function renderPortfolioPieChart(items) {
    var wrap = document.getElementById('portfolioPieWrap');
    var canvas = document.getElementById('portfolioPieChart');
    var legendEl = document.getElementById('pieLegend');
    if (!wrap || !canvas || !legendEl) return;

    var valid = (items || []).filter(function(it) { return it.market_value != null && it.market_value > 0; });
    if (!valid.length) { wrap.style.display = 'none'; return; }
    wrap.style.display = 'flex';

    var total = valid.reduce(function(s, it) { return s + it.market_value; }, 0);
    var ctx = canvas.getContext('2d');
    var dpr = window.devicePixelRatio || 1;
    var size = 220;
    canvas.width = size * dpr;
    canvas.height = size * dpr;
    canvas.style.width = size + 'px';
    canvas.style.height = size + 'px';
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    var cx = size / 2, cy = size / 2, r = 90, innerR = 55;
    var startAngle = -Math.PI / 2;

    ctx.clearRect(0, 0, size, size);

    valid.forEach(function(it, i) {
        var slice = (it.market_value / total) * Math.PI * 2;
        var endAngle = startAngle + slice;
        ctx.beginPath();
        ctx.arc(cx, cy, r, startAngle, endAngle);
        ctx.arc(cx, cy, innerR, endAngle, startAngle, true);
        ctx.closePath();
        ctx.fillStyle = PIE_COLORS[i % PIE_COLORS.length];
        ctx.fill();
        startAngle = endAngle;
    });

    // Center text
    ctx.fillStyle = '#e2e8f0';
    ctx.font = '600 14px Inter, sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(valid.length + ' stock' + (valid.length !== 1 ? 's' : ''), cx, cy);

    // Legend
    legendEl.innerHTML = valid.map(function(it, i) {
        var pct = (it.market_value / total * 100).toFixed(1);
        return '<div class="pie-legend-item">' +
            '<span class="pie-legend-dot" style="background:' + PIE_COLORS[i % PIE_COLORS.length] + '"></span>' +
            '<span class="pie-legend-ticker">' + it.ticker + '</span>' +
            '<span class="pie-legend-pct">' + pct + '%</span>' +
            '</div>';
    }).join('');

    renderDiversityEval(valid, total);
}

function renderDiversityEval(items, total) {
    var el = document.getElementById('diversityEval');
    if (!el) return;
    if (!items.length) { el.innerHTML = ''; return; }

    // Compute HHI (Herfindahl-Hirschman Index) — sum of squared weight fractions
    var hhi = 0;
    var maxPct = 0;
    var maxTicker = '';
    items.forEach(function(it) {
        var w = it.market_value / total;
        hhi += w * w;
        var pct = w * 100;
        if (pct > maxPct) { maxPct = pct; maxTicker = it.ticker; }
    });

    // Normalize HHI to 0-100 score: 1/n (perfect) to 1.0 (single stock)
    // Diversity score: 100 = perfectly diversified, 0 = single stock
    var minHhi = 1 / items.length;
    var score;
    if (items.length <= 1) {
        score = 0;
    } else {
        score = Math.round(Math.max(0, Math.min(100, (1 - hhi) / (1 - minHhi) * 100)));
    }

    var grade, gradeClass, tips = [];

    if (score >= 80) {
        grade = 'Excellent';
        gradeClass = 'div-excellent';
    } else if (score >= 60) {
        grade = 'Good';
        gradeClass = 'div-good';
    } else if (score >= 40) {
        grade = 'Fair';
        gradeClass = 'div-fair';
    } else {
        grade = 'Poor';
        gradeClass = 'div-poor';
    }

    // Build recommendations
    if (items.length < 5) {
        tips.push('Consider adding more positions (aim for 5-15 stocks)');
    }
    if (maxPct > 30) {
        tips.push(maxTicker + ' is ' + maxPct.toFixed(0) + '% of portfolio -- consider trimming below 30%');
    } else if (maxPct > 20 && items.length >= 5) {
        tips.push(maxTicker + ' at ' + maxPct.toFixed(0) + '% is on the heavy side');
    }
    if (items.length > 20) {
        tips.push('Over-diversification can dilute returns -- consider consolidating');
    }

    var tipsHtml = tips.length
        ? '<div class="div-tips">' + tips.map(function(t) { return '<span class="div-tip">' + t + '</span>'; }).join('') + '</div>'
        : '';

    el.innerHTML =
        '<div class="div-header">' +
            '<span class="div-label">Diversity</span>' +
            '<span class="div-grade ' + gradeClass + '">' + grade + '</span>' +
            '<span class="div-score">' + score + '/100</span>' +
        '</div>' +
        '<div class="div-bar-track"><div class="div-bar-fill ' + gradeClass + '" style="width:' + score + '%"></div></div>' +
        tipsHtml;
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
            if (currentStockDetailId) {
                openStockDetail(currentStockDetailId);
            } else {
                refreshPortfolioPrices();
            }
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
    const dayPnlEl = document.getElementById('pfTotalDayPnl');
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
    if (dayPnlEl) {
        const dp = t.total_day_pnl || 0;
        dayPnlEl.textContent = (dp >= 0 ? '+$' : '-$') + Math.abs(dp).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
        dayPnlEl.style.color = dp >= 0 ? 'var(--green)' : 'var(--red)';
    }
    var realizedEl = document.getElementById('pfRealizedPnl');
    if (realizedEl) {
        var rp = t.realized_pnl || 0;
        realizedEl.textContent = (rp >= 0 ? '+$' : '-$') + Math.abs(rp).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
        realizedEl.style.color = rp >= 0 ? 'var(--green)' : 'var(--red)';
    }
}

function renderPortfolioTable(items) {
    const tbody = document.getElementById('portfolioBody');
    if (!tbody) return;
    if (!items || !items.length) {
        tbody.innerHTML = '<tr><td colspan="13" class="empty-row">No stocks in portfolio yet</td></tr>';
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
        const portPct = it.pct_of_portfolio != null ? it.pct_of_portfolio.toFixed(1) + '%' : 'N/A';
        const dayPnl = it.day_pnl != null ? ((it.day_pnl >= 0 ? '+$' : '-$') + Math.abs(it.day_pnl).toFixed(2)) : 'N/A';
        const dayPnlColor = it.day_pnl != null ? (it.day_pnl >= 0 ? 'var(--green)' : 'var(--red)') : 'var(--text2)';
        const dayPnlPctAvg = it.day_pnl_pct_avg != null ? ((it.day_pnl_pct_avg >= 0 ? '+' : '') + it.day_pnl_pct_avg.toFixed(2) + '%') : 'N/A';
        const dayPnlPctAvgColor = it.day_pnl_pct_avg != null ? (it.day_pnl_pct_avg >= 0 ? 'var(--green)' : 'var(--red)') : 'var(--text2)';

        var signalsHtml = '';
        if (it.signals && it.signals.length) {
            signalsHtml = it.signals.map(function(s) {
                return '<span class="signal-badge signal-' + s.color + '">' + s.text + '</span>';
            }).join('');
        }

        return '<tr data-item-id="' + it.id + '">' +
            '<td data-col="ticker"><a href="#" onclick="event.stopPropagation();goToAnalyze(\'' + it.ticker + '\',' + it.purchase_price + ');return false" style="text-decoration:none;color:inherit;cursor:pointer"><strong style="font-family:\'JetBrains Mono\',monospace;color:var(--accent2)">' + it.ticker + '</strong>' +
                (it.company_name ? '<br><span style="font-size:11px;color:var(--text3)">' + it.company_name + '</span>' : '') + '</a></td>' +
            '<td data-col="shares" style="font-family:\'JetBrains Mono\',monospace">' + it.shares + '</td>' +
            '<td data-col="avg_cost" style="font-family:\'JetBrains Mono\',monospace">$' + it.purchase_price.toFixed(2) + '</td>' +
            '<td data-col="price" style="font-family:\'JetBrains Mono\',monospace">' + price + '</td>' +
            '<td data-col="mkt_value" style="font-family:\'JetBrains Mono\',monospace">' + mktVal + '</td>' +
            '<td data-col="pct_port" style="font-family:\'JetBrains Mono\',monospace;color:var(--accent2);font-weight:600">' + portPct + '</td>' +
            '<td data-col="pnl" style="font-family:\'JetBrains Mono\',monospace;color:' + pnlColor + '">' + pnl + '</td>' +
            '<td data-col="pnl_pct" style="font-family:\'JetBrains Mono\',monospace;color:' + pnlColor + ';font-weight:600">' + pnlPct + '</td>' +
            '<td data-col="day_pnl" style="font-family:\'JetBrains Mono\',monospace;color:' + dayPnlColor + ';font-weight:600">' + dayPnl + '</td>' +
            '<td data-col="day_pnl_pct" style="font-family:\'JetBrains Mono\',monospace;color:' + dayPnlPctAvgColor + ';font-weight:600">' + dayPnlPctAvg + '</td>' +
            '<td data-col="day_pct" style="font-family:\'JetBrains Mono\',monospace;color:' + dayColor + ';font-weight:600">' + (dayChg || 'N/A') + '</td>' +
            '<td data-col="signals" style="max-width:200px">' + signalsHtml + '</td>' +
            '<td data-col="actions" style="white-space:nowrap">' +
                '<button class="btn-pf-buy" onclick="event.stopPropagation();openBuySharesModal(' + it.id + ',\'' + it.ticker + '\',' + it.shares + ',' + it.purchase_price + ')" title="Buy More">+Buy</button> ' +
                '<button class="btn-pf-sell" onclick="event.stopPropagation();openSellSharesModal(' + it.id + ',\'' + it.ticker + '\',' + it.shares + ',' + it.purchase_price + ',' + (it.current_price || 0) + ')" title="Sell">-Sell</button> ' +
                '<button class="btn-pf-edit" onclick="openEditPortfolioItem(' + it.id + ',' + it.shares + ',' + it.purchase_price + ',' + (it.stop_loss || 0) + ',\'' + it.ticker + '\')" title="Edit">Edit</button> ' +
                '<button class="btn-pf-analyze" onclick="analyzePortfolioItem(' + it.id + ',\'' + it.ticker + '\')">Analyze</button> ' +
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

function openEditPortfolioItem(id, shares, price, stopLoss, ticker) {
    var overlay = document.getElementById('editPfOverlay');
    if (!overlay) {
        overlay = document.createElement('div');
        overlay.id = 'editPfOverlay';
        overlay.className = 'modal-overlay';
        overlay.onclick = function(e) { if (e.target === overlay) closeEditPfModal(); };
        document.body.appendChild(overlay);
    }
    overlay.innerHTML =
        '<div class="modal" style="max-width:420px">' +
            '<button class="modal-close" onclick="closeEditPfModal()">&times;</button>' +
            '<div class="pf-modal-title">Edit ' + ticker + '</div>' +
            '<div class="pf-modal-sub">Update shares, average cost, or stop loss</div>' +
            '<div class="pf-modal-field">' +
                '<label class="pf-modal-label">Shares</label>' +
                '<input type="number" id="editPfShares" class="pf-modal-input" value="' + shares + '" min="0" step="any">' +
            '</div>' +
            '<div class="pf-modal-field">' +
                '<label class="pf-modal-label">Average Cost ($)</label>' +
                '<input type="number" id="editPfPrice" class="pf-modal-input" value="' + price.toFixed(2) + '" min="0" step="any">' +
            '</div>' +
            '<div class="pf-modal-field">' +
                '<label class="pf-modal-label">Stop Loss ($)</label>' +
                '<input type="number" id="editPfStopLoss" class="pf-modal-input" value="' + (stopLoss > 0 ? stopLoss.toFixed(2) : '') + '" min="0" step="any" placeholder="Optional">' +
            '</div>' +
            '<div class="pf-modal-error" id="editPfError"></div>' +
            '<button class="pf-modal-btn" id="editPfSaveBtn" onclick="saveEditPortfolioItem(' + id + ',\'' + ticker + '\')">Save Changes</button>' +
        '</div>';
    overlay.classList.add('active');
    document.getElementById('editPfShares').focus();
}

function closeEditPfModal() {
    var overlay = document.getElementById('editPfOverlay');
    if (overlay) overlay.classList.remove('active');
}

async function saveEditPortfolioItem(id, ticker) {
    var sharesVal = parseFloat(document.getElementById('editPfShares').value);
    var priceVal = parseFloat(document.getElementById('editPfPrice').value);
    var stopLossVal = parseFloat(document.getElementById('editPfStopLoss').value);
    var errorEl = document.getElementById('editPfError');
    var btn = document.getElementById('editPfSaveBtn');

    errorEl.style.display = 'none';
    if (!sharesVal || sharesVal <= 0) {
        errorEl.textContent = 'Please enter a valid number of shares';
        errorEl.style.display = 'block';
        return;
    }
    if (!priceVal || priceVal <= 0) {
        errorEl.textContent = 'Please enter a valid average cost';
        errorEl.style.display = 'block';
        return;
    }

    btn.disabled = true;
    btn.textContent = 'Saving...';
    try {
        var body = { shares: sharesVal, purchase_price: priceVal };
        if (stopLossVal && stopLossVal > 0) body.stop_loss = stopLossVal;
        var resp = await fetch(API + '/api/portfolio/' + id, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        var data = await resp.json();
        if (!resp.ok) {
            errorEl.textContent = data.error || 'Failed to save';
            errorEl.style.display = 'block';
            btn.disabled = false;
            btn.textContent = 'Save Changes';
            return;
        }
        // Show success briefly
        var overlay = document.getElementById('editPfOverlay');
        overlay.querySelector('.modal').innerHTML =
            '<div class="pf-modal-success">' +
                '<div class="pf-modal-success-icon"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="var(--green)" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg></div>' +
                '<div class="pf-modal-success-text">' + ticker + ' updated</div>' +
            '</div>';
        setTimeout(function() { closeEditPfModal(); }, 1000);
        refreshPortfolioPrices();
    } catch (err) {
        errorEl.textContent = 'Error: ' + err.message;
        errorEl.style.display = 'block';
        btn.disabled = false;
        btn.textContent = 'Save Changes';
    }
}

async function analyzePortfolioItem(id, ticker) {
    try {
        // Show loading in modal
        modalContent.innerHTML = '<div style="text-align:center;padding:40px"><div class="pulse-ring"></div><p style="margin-top:16px;color:var(--text2)">Analyzing ' + ticker + '...</p></div>';
        modalOverlay.classList.add('active');

        var resp = await fetch(API + '/api/portfolio/' + id + '/analyze', { method: 'POST' });
        if (!resp.ok) { var err = await resp.json(); throw new Error(err.error || 'Analysis failed'); }
        var data = await resp.json();
        // Render directly in modal with the response data (which includes purchase_price)
        renderAnalysisModal(data);
        // Refresh portfolio to pick up updated stop_loss
        refreshPortfolioPrices();
    } catch (err) {
        modalContent.innerHTML = '<p style="color:var(--red);padding:20px">Error: ' + err.message + '</p>';
    }
}

// --- Portfolio Settings ---

var COLUMN_LABELS = {
    ticker: 'Ticker', shares: 'Shares', avg_cost: 'Avg Cost', price: 'Price',
    mkt_value: 'Mkt Value', pct_port: '% Portfolio', pnl: 'P&L', pnl_pct: 'P&L %',
    day_pnl: 'Day P&L', day_pnl_pct: 'Day P&L %', day_pct: 'Day %', signals: 'Signals', actions: 'Actions'
};
var CARD_LABELS = {
    total_value: 'Total Value', total_cost: 'Total Cost', total_pnl: 'Unrealized P&L',
    total_return: 'Unrealized P&L %', day_pnl: 'Day P&L', realized_pnl: 'Realized P&L'
};

function toggleSettingsPanel() {
    var panel = document.getElementById('settingsPanel');
    var btn = document.querySelector('.btn-pf-settings');
    if (!panel) return;
    if (panel.style.display === 'none') {
        panel.style.display = '';
        if (btn) btn.classList.add('active');
        renderSettingsPanel();
    } else {
        panel.style.display = 'none';
        if (btn) btn.classList.remove('active');
    }
}

function renderSettingsPanel() {
    if (!userSettings) return;
    var colsEl = document.getElementById('settingsColumns');
    var cardsEl = document.getElementById('settingsCards');
    var chartEl = document.getElementById('settingsChart');
    if (!colsEl || !cardsEl || !chartEl) return;

    // Columns toggles
    var colKeys = Object.keys(COLUMN_LABELS);
    colsEl.innerHTML = colKeys.map(function(key) {
        var checked = userSettings.visible_columns[key] !== false;
        return '<div class="settings-toggle">' +
            '<span class="settings-toggle-label">' + COLUMN_LABELS[key] + '</span>' +
            '<label class="toggle-switch"><input type="checkbox" data-type="col" data-key="' + key + '"' + (checked ? ' checked' : '') + ' onchange="onSettingToggle(this)"><span class="toggle-slider"></span></label>' +
            '</div>';
    }).join('');

    // Cards toggles
    var cardKeys = Object.keys(CARD_LABELS);
    cardsEl.innerHTML = cardKeys.map(function(key) {
        var checked = userSettings.visible_cards[key] !== false;
        return '<div class="settings-toggle">' +
            '<span class="settings-toggle-label">' + CARD_LABELS[key] + '</span>' +
            '<label class="toggle-switch"><input type="checkbox" data-type="card" data-key="' + key + '"' + (checked ? ' checked' : '') + ' onchange="onSettingToggle(this)"><span class="toggle-slider"></span></label>' +
            '</div>';
    }).join('');

    // Pie chart toggle
    var pieChecked = userSettings.show_pie_chart !== false;
    chartEl.innerHTML = '<div class="settings-toggle">' +
        '<span class="settings-toggle-label">Pie Chart</span>' +
        '<label class="toggle-switch"><input type="checkbox" data-type="chart" data-key="pie"' + (pieChecked ? ' checked' : '') + ' onchange="onSettingToggle(this)"><span class="toggle-slider"></span></label>' +
        '</div>';
}

function onSettingToggle(el) {
    if (!userSettings) return;
    var type = el.getAttribute('data-type');
    var key = el.getAttribute('data-key');
    var val = el.checked;

    if (type === 'col') userSettings.visible_columns[key] = val;
    else if (type === 'card') userSettings.visible_cards[key] = val;
    else if (type === 'chart') userSettings.show_pie_chart = val;

    applySettings();

    // Debounced save
    if (settingsSaveTimer) clearTimeout(settingsSaveTimer);
    settingsSaveTimer = setTimeout(function() {
        fetch(API + '/api/settings', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(userSettings),
        }).catch(function(err) { console.error('Settings save error:', err); });
    }, 300);
}

function applySettings() {
    if (!userSettings) return;

    // Apply column visibility
    var cols = userSettings.visible_columns || {};
    Object.keys(cols).forEach(function(key) {
        var visible = cols[key] !== false;
        // Header
        var th = document.querySelector('#portfolioTable th[data-col="' + key + '"]');
        if (th) th.style.display = visible ? '' : 'none';
        // Body cells
        document.querySelectorAll('#portfolioTable td[data-col="' + key + '"]').forEach(function(td) {
            td.style.display = visible ? '' : 'none';
        });
    });

    // Apply card visibility
    var cards = userSettings.visible_cards || {};
    Object.keys(cards).forEach(function(key) {
        var visible = cards[key] !== false;
        var card = document.querySelector('[data-card="' + key + '"]');
        if (card) card.style.display = visible ? '' : 'none';
    });

    // Apply pie chart visibility
    var pieWrap = document.getElementById('portfolioPieWrap');
    if (pieWrap && userSettings.show_pie_chart === false) {
        pieWrap.style.display = 'none';
    }
}

// --- Drag and Drop (pointer events, live swap) ---

var _drag = { active: false, srcRow: null, startY: 0, offsetY: 0, raf: 0, lastY: 0 };

function initDragAndDrop() {
    var tbody = document.querySelector('#portfolioTable tbody');
    if (!tbody || tbody._dragInit) return;
    tbody._dragInit = true;
    var table = document.getElementById('portfolioTable');

    tbody.addEventListener('pointerdown', function(e) {
        var td = e.target.closest('td');
        if (!td || td !== td.parentElement.cells[0]) return;
        var row = td.parentElement;
        if (!row.hasAttribute('data-item-id')) return;

        e.preventDefault();
        row.setPointerCapture(e.pointerId);
        _drag.srcRow = row;
        _drag.startY = e.clientY;
        _drag.offsetY = 0;
        _drag.lastY = e.clientY;

        var onMove = function(ev) {
            ev.preventDefault();
            if (!_drag.active && Math.abs(ev.clientY - _drag.startY) < 5) return;
            if (!_drag.active) {
                _drag.active = true;
                row.classList.add('drag-src');
                table.classList.add('is-dragging');
            }
            _drag.lastY = ev.clientY;
            _drag.offsetY = ev.clientY - _drag.startY;
            if (!_drag.raf) {
                _drag.raf = requestAnimationFrame(function() {
                    _drag.raf = 0;
                    dragTick(tbody);
                });
            }
        };

        var onUp = function(ev) {
            row.releasePointerCapture(ev.pointerId);
            document.removeEventListener('pointermove', onMove);
            document.removeEventListener('pointerup', onUp);
            if (_drag.raf) { cancelAnimationFrame(_drag.raf); _drag.raf = 0; }

            row.style.transform = '';
            row.classList.remove('drag-src');
            table.classList.remove('is-dragging');

            // Remove swap transitions
            var all = tbody.querySelectorAll('.drag-swap');
            for (var i = 0; i < all.length; i++) {
                all[i].classList.remove('drag-swap');
                all[i].style.transform = '';
            }

            if (_drag.active) savePortfolioOrder();
            _drag.active = false;
            _drag.srcRow = null;
        };

        document.addEventListener('pointermove', onMove);
        document.addEventListener('pointerup', onUp);
    });
}

function dragTick(tbody) {
    var src = _drag.srcRow;
    if (!src || !_drag.active) return;

    // Move the dragged row visually
    src.style.transform = 'translateY(' + _drag.offsetY + 'px)';

    // Check if src center has crossed a sibling's midpoint
    var srcRect = src.getBoundingClientRect();
    var srcMid = srcRect.top + srcRect.height / 2;
    var rows = tbody.querySelectorAll('tr[data-item-id]');
    var srcIdx = -1;
    for (var i = 0; i < rows.length; i++) {
        if (rows[i] === src) { srcIdx = i; break; }
    }
    if (srcIdx < 0) return;

    // Moving down
    if (_drag.offsetY > 0 && srcIdx < rows.length - 1) {
        var next = rows[srcIdx + 1];
        var nextRect = next.getBoundingClientRect();
        var nextMid = nextRect.top + nextRect.height / 2;
        if (srcMid > nextMid) {
            swapRows(tbody, src, next, -srcRect.height);
        }
    }
    // Moving up
    if (_drag.offsetY < 0 && srcIdx > 0) {
        var prev = rows[srcIdx - 1];
        var prevRect = prev.getBoundingClientRect();
        var prevMid = prevRect.top + prevRect.height / 2;
        if (srcMid < prevMid) {
            swapRows(tbody, prev, src, srcRect.height);
        }
    }
}

function swapRows(tbody, rowA, rowB, animateOffset) {
    // Animate the displaced row
    rowB.classList.remove('drag-swap');
    rowB.style.transform = 'translateY(' + animateOffset + 'px)';
    // Force reflow so transition plays
    void rowB.offsetHeight;
    rowB.classList.add('drag-swap');
    rowB.style.transform = '';

    // DOM swap: move rowA before rowB's current position
    tbody.insertBefore(rowB, rowA);

    // Reset dragged row offset since DOM position changed
    _drag.startY = _drag.lastY;
    _drag.offsetY = 0;
    _drag.srcRow.style.transform = '';
}

function savePortfolioOrder() {
    var rows = document.querySelectorAll('#portfolioTable tbody tr[data-item-id]');
    var order = [];
    rows.forEach(function(row) {
        order.push(parseInt(row.getAttribute('data-item-id'), 10));
    });
    fetch(API + '/api/portfolio/reorder', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ order: order }),
    }).catch(function(err) { console.error('Reorder save error:', err); });
}


function renderAnalysisModal(data) {
    var rec = data.recommendation || 'HOLD';
    var cls = rec.startsWith('BUY') ? 'badge-buy' : rec.startsWith('SELL') ? 'badge-sell' : 'badge-hold';
    var confClass = data.confidence === 'HIGH' ? 'badge-high' : data.confidence === 'MEDIUM' ? 'badge-medium' : 'badge-low';
    var riskClass = data.risk_level === 'LOW' ? 'badge-high' : data.risk_level === 'HIGH' ? 'badge-low' : 'badge-medium';
    var price = data.current_price ? '$' + data.current_price.toFixed(2) : 'N/A';
    var priceColor = rec.startsWith('BUY') ? 'var(--green)' : rec.startsWith('SELL') ? 'var(--red)' : 'var(--yellow)';
    var date = data.created_at ? new Date(data.created_at).toLocaleString() : '';

    // Entry price & P&L banner
    var entryHtml = '';
    if (data.purchase_price) {
        var entryPnl = data.current_price ? data.current_price - data.purchase_price : null;
        var entryPnlPct = entryPnl !== null ? (entryPnl / data.purchase_price * 100) : null;
        var pnlColor = entryPnl !== null ? (entryPnl >= 0 ? 'var(--green)' : 'var(--red)') : 'var(--text2)';
        entryHtml = '<div style="display:flex;gap:16px;align-items:center;padding:10px 16px;margin-bottom:12px;background:rgba(124,108,240,0.06);border:1px solid rgba(124,108,240,0.2);border-radius:10px;font-size:13px">' +
            '<span style="color:var(--text2)">Entry: <strong style="color:var(--text);font-family:\'JetBrains Mono\',monospace">$' + data.purchase_price.toFixed(2) + '</strong></span>' +
            (entryPnl !== null ? '<span style="color:' + pnlColor + ';font-weight:600;font-family:\'JetBrains Mono\',monospace">' + (entryPnl >= 0 ? '+' : '') + '$' + entryPnl.toFixed(2) + ' (' + (entryPnlPct >= 0 ? '+' : '') + entryPnlPct.toFixed(2) + '%)</span>' : '') +
            '</div>';
    }

    // Pattern banner
    var patternHtml = data.chart_pattern && data.chart_pattern !== 'None detected' && data.chart_pattern !== 'N/A'
        ? '<div class="pattern-banner"><strong>Pattern Detected:</strong> ' + data.chart_pattern + '</div>' : '';

    // Trading Setup
    var actionTrigger = data.action_trigger && data.action_trigger !== 'N/A' ? data.action_trigger : '';
    var breakoutLevel = data.breakout_level && data.breakout_level !== 'N/A' ? data.breakout_level : '';
    var breakoutDir = data.breakout_direction || '';
    var expGain = data.expected_gain_pct && data.expected_gain_pct !== 'N/A' ? data.expected_gain_pct : '';
    var expLoss = data.expected_loss_pct && data.expected_loss_pct !== 'N/A' ? data.expected_loss_pct : '';
    var rrRatio = data.risk_reward_ratio && data.risk_reward_ratio !== 'N/A' ? data.risk_reward_ratio : '';
    var timeframe = data.breakout_timeframe && data.breakout_timeframe !== 'N/A' ? data.breakout_timeframe : '';

    var supportHtml = '';
    if (data.support_levels && data.support_levels.length) {
        supportHtml = '<ul class="level-list">' + data.support_levels.map(function(s) {
            return '<li class="level-item"><span class="level-dot support"></span>' + s + '</li>';
        }).join('') + '</ul>';
    } else {
        supportHtml = '<p style="color:var(--text3);font-size:13px">No key supports identified</p>';
    }
    var resistanceHtml = '';
    if (data.resistance_levels && data.resistance_levels.length) {
        resistanceHtml = '<ul class="level-list">' + data.resistance_levels.map(function(r) {
            return '<li class="level-item"><span class="level-dot resistance"></span>' + r + '</li>';
        }).join('') + '</ul>';
    } else {
        resistanceHtml = '<p style="color:var(--text3);font-size:13px">No key resistances identified</p>';
    }

    var hasTradingSetup = actionTrigger || breakoutLevel || expGain || (data.support_levels && data.support_levels.length) || (data.resistance_levels && data.resistance_levels.length);
    var tradingSetupHtml = hasTradingSetup ? '<div class="trading-setup" style="margin-top:16px"><div class="card-title">Trading Setup</div>' +
        (actionTrigger ? '<div class="action-trigger-box"><div class="action-trigger-label">Action Trigger</div><div class="action-trigger-text">' + actionTrigger + '</div></div>' : '') +
        '<div class="setup-grid"><div><div class="setup-section-title">Support Levels</div>' + supportHtml + '</div><div><div class="setup-section-title">Resistance Levels</div>' + resistanceHtml + '</div></div>' +
        '<div class="breakout-box">' +
        (breakoutLevel ? '<div class="breakout-item"><div class="breakout-item-label">Breakout Level</div><div class="breakout-item-value ' + (breakoutDir === 'BULLISH' ? 'green' : breakoutDir === 'BEARISH' ? 'red' : 'blue') + '">' + breakoutLevel + '</div></div>' : '') +
        (expGain ? '<div class="breakout-item"><div class="breakout-item-label">Expected Gain</div><div class="breakout-item-value green">+' + expGain.replace('+','') + '</div></div>' : '') +
        (expLoss ? '<div class="breakout-item"><div class="breakout-item-label">Expected Loss</div><div class="breakout-item-value red">-' + expLoss.replace('-','') + '</div></div>' : '') +
        (rrRatio ? '<div class="breakout-item"><div class="breakout-item-label">Risk / Reward</div><div class="breakout-item-value accent">' + rrRatio + '</div></div>' : '') +
        '</div>' +
        (timeframe ? '<div class="timeframe-row">Expected timeframe: <strong>' + timeframe + '</strong></div>' : '') +
        '</div>' : '';

    // Key factors
    var factorsHtml = '';
    if (data.key_factors && data.key_factors.length) {
        factorsHtml = '<ul>' + data.key_factors.map(function(f) { return '<li>' + f + '</li>'; }).join('') + '</ul>';
    }

    // Metrics
    var metricsHtml = '';
    if (data.stock_data) {
        var sd = data.stock_data;
        var fmt = function(v) { return typeof v === 'number' ? '$' + v.toFixed(2) : v; };
        var rows = [
            ['P/E', sd.pe_ratio], ['Fwd P/E', sd.forward_pe], ['EPS', sd.eps],
            ['Mkt Cap', sd.market_cap],
            ['SMA 20', sd.sma_20 ? fmt(sd.sma_20) : null],
            ['SMA 150', sd.sma_150 ? fmt(sd.sma_150) : null],
            ['SMA 200', sd.sma_200 ? fmt(sd.sma_200) : null],
            ['ATR(14)', sd.atr_14], ['RSI(14)', sd.rsi_14],
            ['Beta', sd.beta], ['Div Yield', sd.dividend_yield],
            ['MA Setup', sd.ma_alignment],
        ].filter(function(r) { return r[1] != null && r[1] !== ''; });
        metricsHtml = '<div class="metric-grid">' +
            rows.map(function(r) { return '<div><span class="metric-label">' + r[0] + '</span><span class="metric-val">' + r[1] + '</span></div>'; }).join('') +
            '</div>';
    }

    var cardsHtml = '<div class="cards-grid" style="margin-top:16px">' +
        '<div class="card"><div class="card-title">Targets & Stop Loss</div>' +
        '<div class="target-row"><span class="target-label">Short-term</span><span class="target-val">' + (data.price_target_short || 'N/A') + '</span></div>' +
        '<div class="target-row"><span class="target-label">Long-term</span><span class="target-val">' + (data.price_target_long || 'N/A') + '</span></div>' +
        '<div class="target-row"><span class="target-label">Stop Loss</span><span class="target-val red">' + (data.stop_loss || 'N/A') + '</span></div>' +
        '</div>' +
        '<div class="card"><div class="card-title">Key Factors</div>' + (factorsHtml || '<p style="color:var(--text3)">N/A</p>') + '</div>' +
        '<div class="card"><div class="card-title">Metrics</div>' + (metricsHtml || '<p style="color:var(--text3)">N/A</p>') + '</div>' +
        '</div>';

    // News
    var newsHtml = '';
    if (data.news_articles && data.news_articles.length) {
        newsHtml = '<div class="news-card" style="margin-top:16px"><div class="card-title">News (' + data.news_articles.length + ')</div><ul class="news-list">' +
            data.news_articles.map(function(a) {
                return '<li class="news-item"><a href="' + a.link + '" target="_blank">' + a.title + '</a><div class="news-source">' + a.source + (a.published ? ' &mdash; ' + a.published : '') + '</div></li>';
            }).join('') + '</ul></div>';
    }

    modalContent.innerHTML =
        '<div class="result-hero" style="margin-bottom:0">' +
            '<div class="result-top">' +
                '<div class="result-ticker-wrap">' +
                    '<span class="result-ticker">' + data.ticker + '</span>' +
                    '<span class="result-company">' + (data.company_name || '') + '</span>' +
                '</div>' +
                '<span class="result-price" style="color:' + priceColor + '">' + price + '</span>' +
            '</div>' +
            entryHtml +
            '<div class="badges">' +
                '<span class="badge ' + cls + '">' + rec + '</span>' +
                '<span class="badge ' + confClass + '">' + data.confidence + ' confidence</span>' +
                (data.risk_level ? '<span class="badge ' + riskClass + '">' + data.risk_level + ' risk</span>' : '') +
                (data.trend_status ? '<span class="badge badge-info">' + data.trend_status + '</span>' : '') +
                (data.share_token ? '<button class="btn-share" onclick="copyShareLink(\'' + data.share_token + '\', this)"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M4 12v8a2 2 0 002 2h12a2 2 0 002-2v-8"/><polyline points="16 6 12 2 8 6"/><line x1="12" y1="2" x2="12" y2="15"/></svg> Share</button>' : '') +
            '</div>' +
            '<p style="color:var(--text3);font-size:12px;margin-bottom:12px">' + date + '</p>' +
            patternHtml +
            '<div class="result-summary">' + data.short_summary + '</div>' +
        '</div>' +
        tradingSetupHtml +
        cardsHtml +
        '<div class="chart-card" style="margin-top:16px">' +
            '<div class="card-title">Candlestick Chart</div>' +
            '<img src="' + API + '/api/chart/' + data.ticker + '" alt="Chart" onerror="this.parentElement.style.display=\'none\'" />' +
        '</div>' +
        (data.news_digest ? '<div class="news-digest-card" style="margin-top:16px"><div class="card-title">AI News Digest</div>' +
            '<span class="sentiment-badge sentiment-' + ((data.news_digest.sentiment || '').toLowerCase()) + '">' + (data.news_digest.sentiment || 'N/A') + '</span>' +
            '<ul class="digest-bullets">' + (data.news_digest.summary_bullets || []).map(function(b) { return '<li>' + b + '</li>'; }).join('') + '</ul></div>' : '') +
        '<div class="analysis-card" style="margin-top:16px">' +
            '<div class="card-title">Full Analysis</div>' +
            '<div class="full-analysis">' + (data.full_analysis || 'N/A') + '</div>' +
        '</div>' +
        newsHtml;
    modalOverlay.classList.add('active');
}

function showAddToPortfolioFromAnalysis(ticker, company, price) {
    var overlay = document.getElementById('pfModalOverlay');
    var content = document.getElementById('pfModalContent');
    var hasPrice = price && price > 0;

    content.innerHTML =
        '<div class="pf-modal-title">Add ' + ticker + ' to Portfolio</div>' +
        '<div class="pf-modal-sub">' + (company || ticker) + '</div>' +
        '<div class="pf-modal-field">' +
            '<label class="pf-modal-label">Number of Shares</label>' +
            '<input type="number" id="pfModalShares" class="pf-modal-input" placeholder="e.g. 10" min="0" step="any" autofocus>' +
        '</div>' +
        '<div class="pf-modal-field">' +
            '<label class="pf-modal-label">Average Cost per Share</label>' +
            (hasPrice
                ? '<div class="pf-modal-price-display">$' + price.toFixed(2) + '</div>' +
                  '<input type="hidden" id="pfModalPrice" value="' + price.toFixed(2) + '">'
                : '<input type="number" id="pfModalPrice" class="pf-modal-input" placeholder="$0.00" min="0" step="any">') +
        '</div>' +
        '<button class="pf-modal-btn" id="pfModalSubmit" onclick="submitPfModal(\'' + ticker + '\', \'' + company.replace(/'/g, "\\'") + '\')">Add to Portfolio</button>' +
        '<div class="pf-modal-error" id="pfModalError"></div>';

    overlay.classList.add('active');
    // Focus the shares input after a tick
    setTimeout(function() {
        var inp = document.getElementById('pfModalShares');
        if (inp) inp.focus();
    }, 100);
}

function closePfModal() {
    document.getElementById('pfModalOverlay').classList.remove('active');
}

async function submitPfModal(ticker, company) {
    var errorEl = document.getElementById('pfModalError');
    var btn = document.getElementById('pfModalSubmit');
    var sharesVal = parseFloat(document.getElementById('pfModalShares').value);
    var priceVal = parseFloat(document.getElementById('pfModalPrice').value);

    errorEl.style.display = 'none';
    if (!sharesVal || sharesVal <= 0) {
        errorEl.textContent = 'Please enter a valid number of shares';
        errorEl.style.display = 'block';
        return;
    }
    if (!priceVal || priceVal <= 0) {
        errorEl.textContent = 'Please enter a valid price';
        errorEl.style.display = 'block';
        return;
    }

    btn.disabled = true;
    btn.textContent = 'Adding...';
    try {
        var resp = await fetch(API + '/api/portfolio', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ticker: ticker, shares: sharesVal, purchase_price: priceVal, company_name: company }),
        });
        var data = await resp.json();
        if (!resp.ok) {
            errorEl.textContent = data.error || 'Failed to add';
            errorEl.style.display = 'block';
            btn.disabled = false;
            btn.textContent = 'Add to Portfolio';
            return;
        }
        // Success state
        var content = document.getElementById('pfModalContent');
        content.innerHTML =
            '<div class="pf-modal-success">' +
                '<div class="pf-modal-success-icon"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="var(--green)" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg></div>' +
                '<div class="pf-modal-success-text">' + ticker + ' added to portfolio</div>' +
                '<div class="pf-modal-success-sub">' + sharesVal + ' shares at $' + priceVal.toFixed(2) + '</div>' +
            '</div>';
        setTimeout(closePfModal, 1500);
    } catch (err) {
        errorEl.textContent = 'Error: ' + err.message;
        errorEl.style.display = 'block';
        btn.disabled = false;
        btn.textContent = 'Add to Portfolio';
    }
}

// --- Stock Detail View ---

async function openStockDetail(itemId) {
    currentStockDetailId = itemId;
    var detailView = document.getElementById('portfolio-stock-detail');
    var detailContent = document.getElementById('stockDetailContent');
    var statusBar = document.querySelector('.portfolio-status-bar');
    var summary = document.getElementById('portfolioSummary');
    var addForm = document.querySelector('.portfolio-add-form');
    var tableWrap = document.getElementById('portfolioTableWrap');

    // Show loading in detail view
    detailContent.innerHTML = '<div style="text-align:center;padding:60px"><div class="pulse-ring"></div><p style="margin-top:16px;color:var(--text2)">Loading stock data...</p></div>';
    detailView.style.display = 'block';
    if (statusBar) statusBar.style.display = 'none';
    if (summary) summary.style.display = 'none';
    if (addForm) addForm.style.display = 'none';
    if (tableWrap) tableWrap.style.display = 'none';

    try {
        var resp = await fetch(API + '/api/portfolio/' + itemId + '/detail');
        if (!resp.ok) { var err = await resp.json(); throw new Error(err.error || 'Failed to load'); }
        var data = await resp.json();
        renderStockDetail(data);
    } catch (err) {
        detailContent.innerHTML = '<p style="color:var(--red);padding:20px">Error: ' + err.message + '</p>';
    }
}

function closeStockDetail() {
    currentStockDetailId = null;
    var detailView = document.getElementById('portfolio-stock-detail');
    var statusBar = document.querySelector('.portfolio-status-bar');
    var summary = document.getElementById('portfolioSummary');
    var addForm = document.querySelector('.portfolio-add-form');
    var tableWrap = document.getElementById('portfolioTableWrap');

    detailView.style.display = 'none';
    if (statusBar) statusBar.style.display = '';
    if (summary) summary.style.display = '';
    if (addForm) addForm.style.display = '';
    if (tableWrap) tableWrap.style.display = '';
}

function renderStockDetail(data) {
    var detailContent = document.getElementById('stockDetailContent');
    if (!detailContent) return;

    var curPrice = data.current_price;
    var priceStr = curPrice != null ? '$' + curPrice.toFixed(2) : 'N/A';
    var dayChg = data.day_change != null ? ((data.day_change >= 0 ? '+' : '') + '$' + Math.abs(data.day_change).toFixed(2)) : '';
    var dayChgPct = data.day_change_pct != null ? ((data.day_change_pct >= 0 ? '+' : '') + data.day_change_pct.toFixed(2) + '%') : '';
    var dayColor = data.day_change != null ? (data.day_change >= 0 ? 'var(--green)' : 'var(--red)') : 'var(--text2)';

    // P&L
    var pnl = data.pnl;
    var pnlPct = data.pnl_pct;
    var pnlStr = pnl != null ? ((pnl >= 0 ? '+$' : '-$') + Math.abs(pnl).toFixed(2)) : 'N/A';
    var pnlPctStr = pnlPct != null ? ((pnlPct >= 0 ? '+' : '') + pnlPct.toFixed(2) + '%') : '';
    var pnlColor = pnl != null ? (pnl >= 0 ? 'var(--green)' : 'var(--red)') : 'var(--text2)';

    var mktValStr = data.market_value != null ? '$' + data.market_value.toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:2}) : 'N/A';

    // Pre/post market
    var prePostHtml = '';
    var pp = data.pre_post || {};
    if (pp.pre_market_price) {
        var preColor = (pp.pre_market_change || 0) >= 0 ? 'var(--green)' : 'var(--red)';
        prePostHtml += '<span style="font-size:12px;color:var(--text3);margin-left:8px">Pre: <span style="color:' + preColor + ';font-weight:600">$' + pp.pre_market_price.toFixed(2) + '</span></span>';
    }
    if (pp.post_market_price) {
        var postColor = (pp.post_market_change || 0) >= 0 ? 'var(--green)' : 'var(--red)';
        prePostHtml += '<span style="font-size:12px;color:var(--text3);margin-left:8px">Post: <span style="color:' + postColor + ';font-weight:600">$' + pp.post_market_price.toFixed(2) + '</span></span>';
    }

    // Format helper
    var fmtPrice = function(v) { return v != null ? '$' + v.toFixed(2) : 'N/A'; };
    var fmtRatio = function(v) { return v != null ? v.toFixed(2) + 'x' : 'N/A'; };

    // Signals
    var signalsHtml = '';
    if (data.signals && data.signals.length) {
        signalsHtml = data.signals.map(function(s) {
            return '<span class="signal-badge signal-' + s.color + '">' + s.text + '</span>';
        }).join(' ');
    } else {
        signalsHtml = '<span style="color:var(--text3);font-size:13px">No signals</span>';
    }

    detailContent.innerHTML =
        // Header
        '<div class="stock-detail-header">' +
            '<div class="stock-detail-left">' +
                '<div class="stock-detail-ticker">' + data.ticker + '</div>' +
                '<div class="stock-detail-company">' + (data.company_name || '') + '</div>' +
            '</div>' +
            '<div class="stock-detail-right">' +
                '<div class="stock-detail-price">' + priceStr + '</div>' +
                '<div class="stock-detail-day-change" style="color:' + dayColor + '">' + dayChg + ' (' + dayChgPct + ')' + prePostHtml + '</div>' +
            '</div>' +
        '</div>' +

        // Entry / P&L row
        '<div class="stock-detail-entry-row">' +
            '<div class="stock-detail-entry-item">Entry: <strong>$' + data.purchase_price.toFixed(2) + '</strong></div>' +
            '<div class="stock-detail-entry-item">Shares: <strong>' + data.shares + '</strong></div>' +
            '<div class="stock-detail-entry-item">Mkt Value: <strong>' + mktValStr + '</strong></div>' +
            '<div class="stock-detail-entry-item">P&L: <strong style="color:' + pnlColor + '">' + pnlStr + ' ' + pnlPctStr + '</strong></div>' +
            (data.stop_loss ? '<div class="stock-detail-entry-item">Stop Loss: <strong style="color:var(--red)">$' + data.stop_loss.toFixed(2) + '</strong></div>' : '') +
        '</div>' +

        // Price Data + Technicals grid
        '<div class="stock-detail-grid">' +
            '<div class="card">' +
                '<div class="card-title">Price Data</div>' +
                '<div class="metric-grid">' +
                    '<div><span class="metric-label">Open</span><span class="metric-val">' + fmtPrice(data.open_price) + '</span></div>' +
                    '<div><span class="metric-label">Day High</span><span class="metric-val">' + fmtPrice(data.day_high) + '</span></div>' +
                    '<div><span class="metric-label">Day Low</span><span class="metric-val">' + fmtPrice(data.day_low) + '</span></div>' +
                    '<div><span class="metric-label">Prev Close</span><span class="metric-val">' + fmtPrice(data.previous_close) + '</span></div>' +
                    '<div><span class="metric-label">52W High</span><span class="metric-val">' + fmtPrice(data.week_52_high) + '</span></div>' +
                    '<div><span class="metric-label">52W Low</span><span class="metric-val">' + fmtPrice(data.week_52_low) + '</span></div>' +
                    '<div><span class="metric-label">Vol Ratio</span><span class="metric-val">' + fmtRatio(data.volume_ratio) + '</span></div>' +
                '</div>' +
            '</div>' +
            '<div class="card">' +
                '<div class="card-title">Technicals</div>' +
                '<div class="metric-grid">' +
                    '<div><span class="metric-label">SMA 20</span><span class="metric-val">' + fmtPrice(data.sma_20) + '</span></div>' +
                    '<div><span class="metric-label">SMA 50</span><span class="metric-val">' + fmtPrice(data.sma_50) + '</span></div>' +
                    '<div><span class="metric-label">SMA 200</span><span class="metric-val">' + fmtPrice(data.sma_200) + '</span></div>' +
                    '<div><span class="metric-label">ATR 14</span><span class="metric-val">' + fmtPrice(data.atr_14) + '</span></div>' +
                '</div>' +
            '</div>' +
        '</div>' +

        // Signals
        '<div class="stock-detail-signals">' +
            '<div class="card-title">Signals</div>' +
            signalsHtml +
        '</div>' +

        // Chart
        '<div class="chart-card">' +
            '<div class="card-title">Chart</div>' +
            '<img src="' + API + '/api/chart/' + data.ticker + '" alt="Chart" onerror="this.parentElement.style.display=\'none\'" />' +
        '</div>' +

        // Transaction History
        '<div class="card" style="margin-top:16px" id="txnHistoryCard">' +
            '<div class="card-title">Transaction History</div>' +
            '<div id="txnHistoryContent"><span style="color:var(--text3);font-size:13px">Loading...</span></div>' +
        '</div>' +

        // Actions
        '<div class="stock-detail-actions">' +
            '<button class="btn-pf-buy" style="padding:10px 22px;font-size:14px;border-radius:var(--radius-sm)" onclick="openBuySharesModal(' + data.id + ',\'' + data.ticker + '\',' + data.shares + ',' + data.purchase_price + ')">+Buy More</button>' +
            '<button class="btn-pf-sell" style="padding:10px 22px;font-size:14px;border-radius:var(--radius-sm)" onclick="openSellSharesModal(' + data.id + ',\'' + data.ticker + '\',' + data.shares + ',' + data.purchase_price + ',' + (data.current_price || 0) + ')">-Sell Shares</button>' +
            '<button class="btn-full-analysis" onclick="analyzePortfolioItem(' + data.id + ',\'' + data.ticker + '\')">Full AI Analysis</button>' +
        '</div>';

    // Load transaction history after rendering
    loadTransactionHistory(data.id);
}

// --- Buy More Shares Modal ---

function openBuySharesModal(id, ticker, currentShares, avgCost) {
    var overlay = document.getElementById('editPfOverlay');
    if (!overlay) {
        overlay = document.createElement('div');
        overlay.id = 'editPfOverlay';
        overlay.className = 'modal-overlay';
        overlay.onclick = function(e) { if (e.target === overlay) closeEditPfModal(); };
        document.body.appendChild(overlay);
    }
    overlay.innerHTML =
        '<div class="modal" style="max-width:420px">' +
            '<button class="modal-close" onclick="closeEditPfModal()">&times;</button>' +
            '<div class="pf-modal-title">Buy More ' + ticker + '</div>' +
            '<div class="pf-modal-sub">Current: ' + currentShares + ' shares at $' + avgCost.toFixed(2) + ' avg</div>' +
            '<div class="pf-modal-field">' +
                '<label class="pf-modal-label">Additional Shares</label>' +
                '<input type="number" id="buyMoreShares" class="pf-modal-input" placeholder="e.g. 10" min="0" step="any" oninput="updateBuyPreview(' + currentShares + ',' + avgCost + ')">' +
            '</div>' +
            '<div class="pf-modal-field">' +
                '<label class="pf-modal-label">Purchase Price ($)</label>' +
                '<input type="number" id="buyMorePrice" class="pf-modal-input" placeholder="$0.00" min="0" step="any" oninput="updateBuyPreview(' + currentShares + ',' + avgCost + ')">' +
            '</div>' +
            '<div class="txn-preview" id="buyPreview" style="display:none"></div>' +
            '<div class="pf-modal-error" id="buyMoreError"></div>' +
            '<button class="pf-modal-btn" id="buyMoreSubmitBtn" onclick="submitBuyMore(' + id + ',\'' + ticker + '\',' + currentShares + ',' + avgCost + ')">Buy Shares</button>' +
        '</div>';
    overlay.classList.add('active');
    setTimeout(function() { var inp = document.getElementById('buyMoreShares'); if (inp) inp.focus(); }, 100);
}

function updateBuyPreview(currentShares, avgCost) {
    var newShares = parseFloat(document.getElementById('buyMoreShares').value) || 0;
    var newPrice = parseFloat(document.getElementById('buyMorePrice').value) || 0;
    var preview = document.getElementById('buyPreview');
    if (newShares > 0 && newPrice > 0) {
        var totalShares = currentShares + newShares;
        var newAvg = (currentShares * avgCost + newShares * newPrice) / totalShares;
        preview.innerHTML =
            'Total shares: <strong>' + totalShares + '</strong><br>' +
            'New avg cost: <strong>$' + newAvg.toFixed(2) + '</strong> (was $' + avgCost.toFixed(2) + ')<br>' +
            'Cost of purchase: <strong>$' + (newShares * newPrice).toFixed(2) + '</strong>';
        preview.style.display = '';
    } else {
        preview.style.display = 'none';
    }
}

async function submitBuyMore(id, ticker, currentShares, avgCost) {
    var errorEl = document.getElementById('buyMoreError');
    var btn = document.getElementById('buyMoreSubmitBtn');
    var newShares = parseFloat(document.getElementById('buyMoreShares').value);
    var newPrice = parseFloat(document.getElementById('buyMorePrice').value);

    errorEl.style.display = 'none';
    if (!newShares || newShares <= 0) {
        errorEl.textContent = 'Please enter a valid number of shares';
        errorEl.style.display = 'block';
        return;
    }
    if (!newPrice || newPrice <= 0) {
        errorEl.textContent = 'Please enter a valid price';
        errorEl.style.display = 'block';
        return;
    }

    btn.disabled = true;
    btn.textContent = 'Buying...';
    try {
        var resp = await fetch(API + '/api/portfolio/' + id + '/buy', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ shares: newShares, price: newPrice }),
        });
        var data = await resp.json();
        if (!resp.ok) {
            errorEl.textContent = data.error || 'Failed to buy';
            errorEl.style.display = 'block';
            btn.disabled = false;
            btn.textContent = 'Buy Shares';
            return;
        }
        var overlay = document.getElementById('editPfOverlay');
        overlay.querySelector('.modal').innerHTML =
            '<div class="pf-modal-success">' +
                '<div class="pf-modal-success-icon"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="var(--green)" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg></div>' +
                '<div class="pf-modal-success-text">Bought ' + newShares + ' more ' + ticker + '</div>' +
                '<div class="pf-modal-success-sub">New avg: $' + data.purchase_price.toFixed(2) + ' | Total: ' + data.shares + ' shares</div>' +
            '</div>';
        setTimeout(function() { closeEditPfModal(); }, 1500);
        if (currentStockDetailId) { openStockDetail(currentStockDetailId); } else { refreshPortfolioPrices(); }
    } catch (err) {
        errorEl.textContent = 'Error: ' + err.message;
        errorEl.style.display = 'block';
        btn.disabled = false;
        btn.textContent = 'Buy Shares';
    }
}

// --- Sell Shares Modal ---

function openSellSharesModal(id, ticker, currentShares, avgCost, currentPrice) {
    var overlay = document.getElementById('editPfOverlay');
    if (!overlay) {
        overlay = document.createElement('div');
        overlay.id = 'editPfOverlay';
        overlay.className = 'modal-overlay';
        overlay.onclick = function(e) { if (e.target === overlay) closeEditPfModal(); };
        document.body.appendChild(overlay);
    }
    overlay.innerHTML =
        '<div class="modal" style="max-width:420px">' +
            '<button class="modal-close" onclick="closeEditPfModal()">&times;</button>' +
            '<div class="pf-modal-title">Sell ' + ticker + '</div>' +
            '<div class="pf-modal-sub">Current: ' + currentShares + ' shares at $' + avgCost.toFixed(2) + ' avg</div>' +
            '<div class="pf-modal-field">' +
                '<label class="pf-modal-label">Shares to Sell <a class="sell-all-link" onclick="document.getElementById(\'sellShares\').value=' + currentShares + ';updateSellPreview(' + currentShares + ',' + avgCost + ')">Sell All</a></label>' +
                '<input type="number" id="sellShares" class="pf-modal-input" placeholder="e.g. 5" min="0" max="' + currentShares + '" step="any" oninput="updateSellPreview(' + currentShares + ',' + avgCost + ')">' +
            '</div>' +
            '<div class="pf-modal-field">' +
                '<label class="pf-modal-label">Sell Price ($)</label>' +
                '<input type="number" id="sellPrice" class="pf-modal-input" value="' + (currentPrice > 0 ? currentPrice.toFixed(2) : '') + '" min="0" step="any" oninput="updateSellPreview(' + currentShares + ',' + avgCost + ')">' +
            '</div>' +
            '<div class="txn-preview" id="sellPreview" style="display:none"></div>' +
            '<div class="pf-modal-error" id="sellError"></div>' +
            '<button class="pf-modal-btn-sell" id="sellSubmitBtn" onclick="submitSellShares(' + id + ',\'' + ticker + '\',' + currentShares + ',' + avgCost + ')">Sell Shares</button>' +
        '</div>';
    overlay.classList.add('active');
    setTimeout(function() { var inp = document.getElementById('sellShares'); if (inp) inp.focus(); }, 100);
    // Trigger preview if price is pre-filled
    if (currentPrice > 0) {
        setTimeout(function() { updateSellPreview(currentShares, avgCost); }, 150);
    }
}

function updateSellPreview(currentShares, avgCost) {
    var sellCount = parseFloat(document.getElementById('sellShares').value) || 0;
    var sellPrice = parseFloat(document.getElementById('sellPrice').value) || 0;
    var preview = document.getElementById('sellPreview');
    if (sellCount > 0 && sellPrice > 0) {
        var pnl = (sellPrice - avgCost) * sellCount;
        var pnlSign = pnl >= 0 ? '+' : '-';
        var pnlColor = pnl >= 0 ? 'var(--green)' : 'var(--red)';
        var remaining = currentShares - sellCount;
        var proceeds = sellCount * sellPrice;
        preview.innerHTML =
            'Proceeds: <strong>$' + proceeds.toFixed(2) + '</strong><br>' +
            'Realized P&L: <strong style="color:' + pnlColor + '">' + pnlSign + '$' + Math.abs(pnl).toFixed(2) + '</strong><br>' +
            (remaining > 0 ? 'Remaining: <strong>' + remaining.toFixed(2) + ' shares</strong>' : '<strong style="color:var(--yellow)">Full position sold</strong>');
        preview.style.display = '';
        if (sellCount > currentShares) {
            preview.innerHTML += '<br><span style="color:var(--red)">Cannot sell more than you own</span>';
        }
    } else {
        preview.style.display = 'none';
    }
}

async function submitSellShares(id, ticker, currentShares, avgCost) {
    var errorEl = document.getElementById('sellError');
    var btn = document.getElementById('sellSubmitBtn');
    var sellCount = parseFloat(document.getElementById('sellShares').value);
    var sellPrice = parseFloat(document.getElementById('sellPrice').value);

    errorEl.style.display = 'none';
    if (!sellCount || sellCount <= 0) {
        errorEl.textContent = 'Please enter a valid number of shares';
        errorEl.style.display = 'block';
        return;
    }
    if (sellCount > currentShares) {
        errorEl.textContent = 'Cannot sell more than ' + currentShares + ' shares';
        errorEl.style.display = 'block';
        return;
    }
    if (!sellPrice || sellPrice <= 0) {
        errorEl.textContent = 'Please enter a valid sell price';
        errorEl.style.display = 'block';
        return;
    }

    btn.disabled = true;
    btn.textContent = 'Selling...';
    try {
        var resp = await fetch(API + '/api/portfolio/' + id + '/sell', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ shares: sellCount, price: sellPrice }),
        });
        var data = await resp.json();
        if (!resp.ok) {
            errorEl.textContent = data.error || 'Failed to sell';
            errorEl.style.display = 'block';
            btn.disabled = false;
            btn.textContent = 'Sell Shares';
            return;
        }
        var pnl = data.realized_pnl || 0;
        var pnlSign = pnl >= 0 ? '+' : '-';
        var pnlColor = pnl >= 0 ? 'var(--green)' : 'var(--red)';
        var overlay = document.getElementById('editPfOverlay');
        overlay.querySelector('.modal').innerHTML =
            '<div class="pf-modal-success">' +
                '<div class="pf-modal-success-icon"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="' + (pnl >= 0 ? 'var(--green)' : 'var(--red)') + '" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg></div>' +
                '<div class="pf-modal-success-text">Sold ' + sellCount + ' ' + ticker + '</div>' +
                '<div class="pf-modal-success-sub" style="color:' + pnlColor + '">Realized P&L: ' + pnlSign + '$' + Math.abs(pnl).toFixed(2) + '</div>' +
                (data.fully_sold ? '<div class="pf-modal-success-sub" style="margin-top:4px">Position fully closed</div>' : '') +
            '</div>';
        setTimeout(function() {
            closeEditPfModal();
            if (data.fully_sold && currentStockDetailId) {
                closeStockDetail();
            }
        }, 2000);
        if (data.fully_sold) {
            if (!currentStockDetailId) refreshPortfolioPrices();
        } else {
            if (currentStockDetailId) { openStockDetail(currentStockDetailId); } else { refreshPortfolioPrices(); }
        }
    } catch (err) {
        errorEl.textContent = 'Error: ' + err.message;
        errorEl.style.display = 'block';
        btn.disabled = false;
        btn.textContent = 'Sell Shares';
    }
}

// --- Transaction History ---

async function loadTransactionHistory(itemId) {
    var container = document.getElementById('txnHistoryContent');
    if (!container) return;
    try {
        var resp = await fetch(API + '/api/portfolio/' + itemId + '/transactions');
        if (!resp.ok) { container.innerHTML = '<span style="color:var(--text3);font-size:13px">No transactions yet</span>'; return; }
        var txns = await resp.json();
        if (!txns.length) {
            container.innerHTML = '<span style="color:var(--text3);font-size:13px">No buy/sell transactions recorded yet</span>';
            return;
        }
        var html = '<table class="txn-history-table"><thead><tr>' +
            '<th>Date</th><th>Action</th><th>Shares</th><th>Price</th><th>Total</th><th>Avg Cost</th><th>P&L</th>' +
            '</tr></thead><tbody>';
        txns.forEach(function(t) {
            var d = t.created_at ? new Date(t.created_at).toLocaleDateString() : '';
            var actionCls = t.action === 'BUY' ? 'txn-buy' : 'txn-sell';
            var pnlStr = '';
            if (t.action === 'SELL' && t.realized_pnl != null) {
                var pColor = t.realized_pnl >= 0 ? 'var(--green)' : 'var(--red)';
                pnlStr = '<span style="color:' + pColor + '">' + (t.realized_pnl >= 0 ? '+' : '-') + '$' + Math.abs(t.realized_pnl).toFixed(2) + '</span>';
            } else {
                pnlStr = '-';
            }
            html += '<tr>' +
                '<td>' + d + '</td>' +
                '<td><span class="txn-action-badge ' + actionCls + '">' + t.action + '</span></td>' +
                '<td>' + t.shares + '</td>' +
                '<td>$' + t.price.toFixed(2) + '</td>' +
                '<td>$' + t.total_amount.toFixed(2) + '</td>' +
                '<td>' + (t.avg_cost_at_time != null ? '$' + t.avg_cost_at_time.toFixed(2) : '-') + '</td>' +
                '<td>' + pnlStr + '</td>' +
                '</tr>';
        });
        html += '</tbody></table>';
        container.innerHTML = html;
    } catch (err) {
        container.innerHTML = '<span style="color:var(--text3);font-size:13px">Failed to load transactions</span>';
    }
}

fetchCurrentUser();
loadHistory();
