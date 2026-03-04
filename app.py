import json
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from telegram import Update

from config import HOST, PORT, EXTERNAL_URL
from database import init_db, save_analysis, get_history, get_analysis_by_id, get_unique_tickers
from stock_analyzer import analyze_stock
from chart_generator import generate_chart
from telegram_bot import start_telegram_bot_async

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

telegram_app = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown logic."""
    global telegram_app
    init_db()
    logger.info("Database initialized.")

    # Start Telegram bot in background
    try:
        telegram_app = await start_telegram_bot_async()
    except Exception as e:
        logger.error(f"Failed to start Telegram bot: {e}")

    yield

    # Shutdown
    if telegram_app:
        try:
            if telegram_app.updater and telegram_app.updater.running:
                await telegram_app.updater.stop()
            await telegram_app.stop()
            await telegram_app.shutdown()
        except Exception:
            pass


app = FastAPI(title="StockTips AI", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


@app.post("/webhook/telegram")
async def telegram_webhook(request: Request):
    """Receive Telegram updates via webhook."""
    if telegram_app is None:
        return JSONResponse({"error": "Bot not initialized"}, status_code=503)
    data = await request.json()
    update = Update.de_json(data, telegram_app.bot)
    await telegram_app.process_update(update)
    return JSONResponse({"ok": True})


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Serve the main web dashboard."""
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/api/analyze")
async def api_analyze(request: Request):
    """Analyze a stock ticker via the API."""
    body = await request.json()
    ticker = body.get("ticker", "").strip().upper()

    if not ticker or len(ticker) > 10:
        return JSONResponse({"error": "Invalid ticker symbol"}, status_code=400)

    try:
        result = await analyze_stock(ticker)
        analysis = result["analysis"]

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
        "created_at": record.created_at.isoformat() if record.created_at else "",
    })


@app.get("/api/chart/{ticker}")
async def api_chart(ticker: str):
    """Generate a candlestick chart PNG for a ticker."""
    ticker = ticker.strip().upper()
    if not ticker or len(ticker) > 10:
        return JSONResponse({"error": "Invalid ticker"}, status_code=400)
    try:
        png_bytes = generate_chart(ticker)
        if png_bytes is None:
            return JSONResponse({"error": "Could not generate chart"}, status_code=500)
        return Response(content=png_bytes, media_type="image/png")
    except Exception as e:
        logger.error("Chart error for {}: {}".format(ticker, e))
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/tickers")
async def api_tickers():
    """Get all unique tickers that have been analyzed."""
    return JSONResponse(get_unique_tickers())


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host=HOST, port=PORT, reload=True)
