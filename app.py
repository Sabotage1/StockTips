import json
import os
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from telegram import Update

from config import HOST, PORT, EXTERNAL_URL
from database import init_db, save_analysis, get_history, get_analysis_by_id, get_unique_tickers, delete_analysis, delete_all_history
from stock_analyzer import analyze_stock
from chart_generator import generate_chart
from telegram_bot import start_telegram_bot_async

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IS_SERVERLESS = bool(os.getenv("VERCEL"))

telegram_app = None
_db_initialized = False


def ensure_db():
    global _db_initialized
    if not _db_initialized:
        init_db()
        logger.info("Database initialized.")
        _db_initialized = True


async def get_telegram_app():
    """Lazy-init the Telegram bot application."""
    global telegram_app
    if telegram_app is None:
        try:
            # In serverless, skip setting webhook on every cold start
            telegram_app = await start_telegram_bot_async(skip_webhook_set=IS_SERVERLESS)
        except Exception as e:
            logger.error("Failed to start Telegram bot: {}".format(e))
    return telegram_app


if IS_SERVERLESS:
    # Serverless: no lifespan, lazy init everything
    app = FastAPI(title="StockTips AI")
else:
    @asynccontextmanager
    async def lifespan(the_app: FastAPI):
        """Startup and shutdown logic for local/traditional hosting."""
        ensure_db()
        await get_telegram_app()
        yield
        if telegram_app:
            try:
                if telegram_app.updater and telegram_app.updater.running:
                    await telegram_app.updater.stop()
                await telegram_app.stop()
                await telegram_app.shutdown()
            except Exception:
                pass

    app = FastAPI(title="StockTips AI", lifespan=lifespan)

app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))


@app.post("/webhook/telegram")
async def telegram_webhook(request: Request):
    """Receive Telegram updates via webhook."""
    ensure_db()
    tg_app = await get_telegram_app()
    if tg_app is None:
        return JSONResponse({"error": "Bot not initialized"}, status_code=503)
    data = await request.json()
    update = Update.de_json(data, tg_app.bot)
    await tg_app.process_update(update)
    return JSONResponse({"ok": True})


@app.get("/setup-webhook")
async def setup_webhook():
    """Set the Telegram webhook to this server's URL. Call once after deploy."""
    if not EXTERNAL_URL:
        return JSONResponse({"error": "EXTERNAL_URL not set"}, status_code=400)
    tg_app = await get_telegram_app()
    if tg_app is None:
        return JSONResponse({"error": "Bot not initialized"}, status_code=503)
    webhook_url = "{}/webhook/telegram".format(EXTERNAL_URL)
    await tg_app.bot.set_webhook(url=webhook_url, allowed_updates=Update.ALL_TYPES)
    return JSONResponse({"ok": True, "webhook_url": webhook_url})


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Serve the main web dashboard."""
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/api/analyze")
async def api_analyze(request: Request):
    """Analyze a stock ticker via the API."""
    ensure_db()
    body = await request.json()
    ticker = body.get("ticker", "").strip().upper()

    if not ticker or len(ticker) > 10:
        return JSONResponse({"error": "Invalid ticker symbol"}, status_code=400)

    try:
        result = await analyze_stock(ticker)
        analysis = result["analysis"]

        # Capture client IP
        client_ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        if not client_ip:
            client_ip = request.headers.get("x-real-ip", "")
        if not client_ip and request.client:
            client_ip = request.client.host or ""

        # Always save to history (even cached results) so every search is recorded
        record = save_analysis(
            ticker=result["ticker"],
            company_name=result["company_name"],
            current_price=result.get("current_price"),
            recommendation=analysis["recommendation"],
            confidence=analysis["confidence"],
            short_summary=analysis["short_summary"],
            full_analysis=analysis.get("full_analysis", ""),
            news_data=json.dumps(result["news_articles"][:10], default=str),
            stock_data=json.dumps(result["stock_data"], default=str),
            analysis_json=json.dumps(analysis, default=str),
            source="web",
            user_ip=client_ip,
        )

        return JSONResponse({
            "id": record.id,
            "ticker": result["ticker"],
            "company_name": result["company_name"],
            "current_price": result.get("current_price"),
            "recommendation": analysis["recommendation"],
            "confidence": analysis["confidence"],
            "short_summary": analysis["short_summary"],
            "full_analysis": analysis.get("full_analysis", ""),
            "key_factors": analysis.get("key_factors", []),
            "risk_level": analysis.get("risk_level", ""),
            "price_target_short": analysis.get("price_target_short", ""),
            "price_target_long": analysis.get("price_target_long", ""),
            "stop_loss": analysis.get("stop_loss", ""),
            "chart_pattern": analysis.get("chart_pattern", ""),
            "trend_status": analysis.get("trend_status", ""),
            "support_levels": analysis.get("support_levels", []),
            "resistance_levels": analysis.get("resistance_levels", []),
            "breakout_level": analysis.get("breakout_level", ""),
            "breakout_direction": analysis.get("breakout_direction", ""),
            "expected_gain_pct": analysis.get("expected_gain_pct", ""),
            "expected_loss_pct": analysis.get("expected_loss_pct", ""),
            "risk_reward_ratio": analysis.get("risk_reward_ratio", ""),
            "action_trigger": analysis.get("action_trigger", ""),
            "breakout_timeframe": analysis.get("breakout_timeframe", ""),
            "news_count": len(result["news_articles"]),
            "news_articles": result["news_articles"][:10],
            "stock_data": result["stock_data"],
            "created_at": record.created_at.isoformat(),
        })
    except Exception as e:
        logger.error(f"Analysis error for {ticker}: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/history")
async def api_history(ticker: str = "", days: int = 30):
    """Get analysis history for the last N days."""
    ensure_db()
    records = get_history(days=days, ticker=ticker or None)
    return JSONResponse([
        {
            "id": r.id,
            "ticker": r.ticker,
            "company_name": r.company_name,
            "current_price": r.current_price,
            "recommendation": r.recommendation,
            "confidence": r.confidence,
            "short_summary": r.short_summary,
            "source": r.source,
            "telegram_user": r.telegram_user,
            "created_at": r.created_at.isoformat() if r.created_at else "",
        }
        for r in records
    ])


@app.get("/api/analysis/{analysis_id}")
async def api_analysis_detail(analysis_id: int):
    """Get detailed analysis by ID."""
    ensure_db()
    record = get_analysis_by_id(analysis_id)
    if not record:
        return JSONResponse({"error": "Not found"}, status_code=404)

    news_data = []
    try:
        news_data = json.loads(record.news_data) if record.news_data else []
    except json.JSONDecodeError:
        pass

    stock_data = {}
    try:
        stock_data = json.loads(record.stock_data) if record.stock_data else {}
    except json.JSONDecodeError:
        pass

    return JSONResponse({
        "id": record.id,
        "ticker": record.ticker,
        "company_name": record.company_name,
        "current_price": record.current_price,
        "recommendation": record.recommendation,
        "confidence": record.confidence,
        "short_summary": record.short_summary,
        "full_analysis": record.full_analysis,
        "news_data": news_data,
        "stock_data": stock_data,
        "source": record.source,
        "telegram_user": record.telegram_user,
        "telegram_user_id": getattr(record, "telegram_user_id", "") or "",
        "user_ip": getattr(record, "user_ip", "") or "",
        "created_at": record.created_at.isoformat() if record.created_at else "",
    })


@app.get("/api/chart/{ticker}")
async def api_chart(ticker: str):
    """Generate a candlestick chart PNG for a ticker with analysis overlays."""
    ensure_db()
    ticker = ticker.strip().upper()
    if not ticker or len(ticker) > 10:
        return JSONResponse({"error": "Invalid ticker"}, status_code=400)
    try:
        # Look up latest analysis for overlays
        from database import get_recent_analysis
        analysis_data = None
        cached = get_recent_analysis(ticker, max_age_minutes=120)
        if cached and cached.analysis_json:
            try:
                analysis_data = json.loads(cached.analysis_json)
            except (json.JSONDecodeError, TypeError):
                pass

        png_bytes = generate_chart(ticker, analysis_data=analysis_data)
        if png_bytes is None:
            return JSONResponse({"error": "Could not generate chart"}, status_code=500)
        return Response(content=png_bytes, media_type="image/png")
    except Exception as e:
        logger.error("Chart error for {}: {}".format(ticker, e))
        return JSONResponse({"error": str(e)}, status_code=500)


@app.delete("/api/analysis/{analysis_id}")
async def api_delete_analysis(analysis_id: int):
    """Delete a single analysis record."""
    ensure_db()
    deleted = delete_analysis(analysis_id)
    if not deleted:
        return JSONResponse({"error": "Not found"}, status_code=404)
    return JSONResponse({"ok": True, "deleted_id": analysis_id})


@app.delete("/api/history")
async def api_delete_history(ticker: str = ""):
    """Delete all history, optionally filtered by ticker."""
    ensure_db()
    count = delete_all_history(ticker=ticker or None)
    return JSONResponse({"ok": True, "deleted_count": count})


@app.get("/api/tickers")
async def api_tickers():
    """Get all unique tickers that have been analyzed."""
    ensure_db()
    return JSONResponse(get_unique_tickers())


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host=HOST, port=PORT, reload=True)
