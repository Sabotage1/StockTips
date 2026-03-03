# StockTips AI

AI-powered stock analysis app with Telegram bot and web dashboard.

## Project Structure

```
StockTips/
├── app.py               # FastAPI server — API endpoints + serves web UI
├── stock_analyzer.py     # Core analysis engine — fetches data + calls Gemini AI
├── news_fetcher.py       # Multi-source news aggregation (Yahoo, Google, Finviz, NewsAPI)
├── telegram_bot.py       # Telegram bot — receives tickers, sends recommendations
├── database.py           # SQLite + SQLAlchemy models and CRUD operations
├── config.py             # Environment variable loading
├── .env                  # API keys (DO NOT COMMIT)
├── requirements.txt      # Python dependencies
├── run.sh               # One-click launcher script
├── stocktips.db          # SQLite database (auto-created)
├── templates/
│   └── index.html        # Web dashboard (Jinja2 template)
└── static/
    ├── style.css         # Dark theme UI styles
    └── script.js         # Frontend logic (fetch API, render results, history)
```

## Tech Stack

- **Backend**: FastAPI + Uvicorn
- **AI**: Google Gemini 2.5 Flash (free tier, `response_mime_type="application/json"`)
- **Database**: SQLite via SQLAlchemy
- **Telegram**: python-telegram-bot 21.x (async polling mode, runs alongside FastAPI)
- **Stock Data**: Finviz (scraping) + Yahoo Chart API (price history) + Alpha Vantage (technicals + overview)
- **News**: Yahoo Finance RSS, Google News RSS, Finviz news table, NewsAPI (optional)
- **Frontend**: Vanilla HTML/CSS/JS, dark theme, no build step

## Data Sources

| Source | What it provides | Rate limits |
|--------|-----------------|-------------|
| Finviz (scraping) | Price, P/E, EPS, margins, 52W range, volume, sector, analyst target | No hard limit |
| Yahoo Chart API (v8) | 1yr daily OHLCV for SMA/ATR computation | Generous |
| Alpha Vantage | Company Overview (fundamentals + analyst ratings), RSI, Stochastic, ADX | 5 calls/min, 25/day (free) |
| Google News RSS | News articles by ticker/company | No limit |
| Finviz news table | Ticker-specific news | No hard limit |
| NewsAPI | Additional news (requires key) | 100 req/day (free) |

## Technical Analysis Framework

The AI analyzes stocks using the Minervini/O'Neil/Weinstein approach:

- **SMA 200/150/50/20**: Computed from Yahoo 1yr daily data. Checks alignment (bullish = Price > SMA20 > SMA150 > SMA200).
- **ATR (14-day)**: Computed from high/low/close. Used for stop-loss suggestions (2x ATR).
- **Chart Patterns**: AI examines 20 days of price/high/low/volume data for cup & handle, double bottom, head & shoulders, bull flags, VCP, ascending triangles.
- **Volatility Contraction**: Detects tightening price ranges (VCP/breakout setup).
- **Volume Trend**: Compares recent vs prior 10-day average volume.
- **RSI/Stochastic/ADX**: From Alpha Vantage (when within rate limit).

## AI Response Schema

The Gemini AI always returns this JSON structure:

```json
{
  "recommendation": "BUY | SELL | HOLD",
  "confidence": "HIGH | MEDIUM | LOW",
  "short_summary": "One-line summary",
  "full_analysis": "Multi-paragraph analysis",
  "key_factors": ["factor1", "factor2", ...],
  "risk_level": "HIGH | MEDIUM | LOW",
  "price_target_short": "$XXX",
  "price_target_long": "$XXX",
  "stop_loss": "$XXX based on ATR",
  "chart_pattern": "Cup and Handle | Bull Flag | etc.",
  "trend_status": "STAGE 1 | STAGE 2 | STAGE 3 | STAGE 4"
}
```

## API Endpoints

- `GET /` — Web dashboard
- `POST /api/analyze` — Analyze a ticker `{"ticker": "AAPL"}`
- `GET /api/history?ticker=AAPL&limit=50` — Analysis history
- `GET /api/analysis/{id}` — Single analysis detail
- `GET /api/tickers` — All analyzed tickers

## Telegram Bot Commands

- `/start` — Welcome message
- `/help` — Usage help
- `/analyze TICKER` — Analyze a stock
- Any plain text with 1-5 letter words is treated as ticker(s)

## Running

```bash
./run.sh
# Or manually:
source venv/bin/activate
python3 -m uvicorn app:app --host 0.0.0.0 --port 8000
```

Web dashboard: http://localhost:8000
Telegram bot: Runs automatically alongside the web server.

## Important Notes

- **Python 3.9**: This project runs on Python 3.9. Avoid `X | Y` union type syntax — use `Optional[X]` from typing instead.
- **No emojis in Telegram messages**: Python 3.9 + httpx has a Unicode surrogate encoding bug. Use plain text only in telegram_bot.py.
- **Gemini JSON mode**: Always use `response_mime_type="application/json"` when calling Gemini to avoid parsing issues.
- **yfinance is disabled**: Yahoo Finance `stock.info` endpoint returns 429. We use Finviz scraping + Yahoo Chart API v8 instead.
- **Alpha Vantage free tier**: 5 calls/min, 25/day. MACD and Bollinger Bands are premium-only. RSI, Stochastic, ADX, SMA, EMA are free.
- **Secrets in .env**: Never commit .env. Keys: GEMINI_API_KEY, TELEGRAM_BOT_TOKEN, ALPHA_VANTAGE_KEY, NEWS_API_KEY (optional).
