import json
import os
import asyncio
import logging
import time
from contextlib import asynccontextmanager

import bcrypt
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse, Response, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from telegram import Update

from config import HOST, PORT, EXTERNAL_URL, AUTH_USERNAME, AUTH_PASSWORD_HASH, AUTH_SECRET_KEY
from database import init_db, save_analysis, get_history, get_analysis_by_id, get_analysis_by_share_token, get_unique_tickers, delete_analysis, delete_all_history, block_user, unblock_user, is_user_blocked, get_blocked_users
from stock_analyzer import analyze_stock
from chart_generator import generate_chart
from telegram_bot import start_telegram_bot_async

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IS_SERVERLESS = bool(os.getenv("VERCEL"))

telegram_app = None
_db_initialized = False

# --- Authentication ---
_session_serializer = URLSafeTimedSerializer(AUTH_SECRET_KEY)
SESSION_COOKIE = "stocktips_session"
SESSION_MAX_AGE = 60 * 60 * 24 * 7  # 7 days

# Routes that don't require authentication
PUBLIC_PATHS = frozenset({"/login", "/webhook/telegram"})


def _verify_password(plain_password: str) -> bool:
    """Verify a plain password against the stored bcrypt hash."""
    if not AUTH_PASSWORD_HASH:
        return False
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            AUTH_PASSWORD_HASH.encode("utf-8"),
        )
    except Exception:
        return False


def _create_session_token(username: str) -> str:
    """Create a signed session token."""
    return _session_serializer.dumps({"user": username, "t": int(time.time())})


def _validate_session_token(token: str):
    """Validate a session token. Returns username or None."""
    try:
        data = _session_serializer.loads(token, max_age=SESSION_MAX_AGE)
        return data.get("user")
    except (BadSignature, SignatureExpired):
        return None


def _is_authenticated(request: Request) -> bool:
    """Check if the current request has a valid session."""
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return False
    return _validate_session_token(token) is not None


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


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """Require authentication for all routes except public ones."""
    path = request.url.path
    # Allow public paths, static files, favicon, share pages, and chart API
    if path in PUBLIC_PATHS or path.startswith("/static") or path == "/favicon.ico" \
            or path.startswith("/share/") or path.startswith("/api/share/") \
            or path.startswith("/api/chart/"):
        return await call_next(request)
    if not _is_authenticated(request):
        # API calls get 401, browser requests get redirected to login
        if path.startswith("/api/"):
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        return RedirectResponse(url="/login", status_code=302)
    return await call_next(request)


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Show the login form."""
    if _is_authenticated(request):
        return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/login")
async def login_submit(request: Request, username: str = Form(...), password: str = Form(...)):
    """Validate credentials and set session cookie."""
    if username == AUTH_USERNAME and _verify_password(password):
        token = _create_session_token(username)
        response = RedirectResponse(url="/", status_code=302)
        response.set_cookie(
            key=SESSION_COOKIE,
            value=token,
            max_age=SESSION_MAX_AGE,
            httponly=True,
            samesite="lax",
        )
        return response
    return JSONResponse({"error": "Invalid username or password"}, status_code=401)


@app.get("/logout")
async def logout():
    """Clear the session cookie and redirect to login."""
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie(SESSION_COOKIE)
    return response


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
            "share_token": record.share_token,
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

    tg_user_id = getattr(record, "telegram_user_id", "") or ""
    blocked = is_user_blocked(tg_user_id) if tg_user_id else False

    return JSONResponse({
        "id": record.id,
        "share_token": getattr(record, "share_token", "") or "",
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
        "telegram_user_id": tg_user_id,
        "user_ip": getattr(record, "user_ip", "") or "",
        "is_blocked": blocked,
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


@app.get("/share/{token}")
async def share_page(request: Request, token: str):
    """Serve the public share page for a given share token."""
    ensure_db()
    record = get_analysis_by_share_token(token)
    if not record:
        return HTMLResponse("<h1>404 - Analysis not found</h1><p>This share link is invalid or has expired.</p>", status_code=404)
    return templates.TemplateResponse("share.html", {"request": request, "token": token})


@app.get("/api/share/{token}")
async def api_share_detail(token: str):
    """Public API: return analysis data for a share token (no sensitive fields)."""
    ensure_db()
    record = get_analysis_by_share_token(token)
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

    analysis_extra = {}
    try:
        analysis_extra = json.loads(record.analysis_json) if record.analysis_json else {}
    except json.JSONDecodeError:
        pass

    return JSONResponse({
        "ticker": record.ticker,
        "company_name": record.company_name,
        "current_price": record.current_price,
        "recommendation": record.recommendation,
        "confidence": record.confidence,
        "short_summary": record.short_summary,
        "full_analysis": record.full_analysis,
        "news_data": news_data,
        "stock_data": stock_data,
        "key_factors": analysis_extra.get("key_factors", []),
        "risk_level": analysis_extra.get("risk_level", ""),
        "price_target_short": analysis_extra.get("price_target_short", ""),
        "price_target_long": analysis_extra.get("price_target_long", ""),
        "stop_loss": analysis_extra.get("stop_loss", ""),
        "chart_pattern": analysis_extra.get("chart_pattern", ""),
        "trend_status": analysis_extra.get("trend_status", ""),
        "support_levels": analysis_extra.get("support_levels", []),
        "resistance_levels": analysis_extra.get("resistance_levels", []),
        "breakout_level": analysis_extra.get("breakout_level", ""),
        "breakout_direction": analysis_extra.get("breakout_direction", ""),
        "expected_gain_pct": analysis_extra.get("expected_gain_pct", ""),
        "expected_loss_pct": analysis_extra.get("expected_loss_pct", ""),
        "risk_reward_ratio": analysis_extra.get("risk_reward_ratio", ""),
        "action_trigger": analysis_extra.get("action_trigger", ""),
        "breakout_timeframe": analysis_extra.get("breakout_timeframe", ""),
        "news_count": len(news_data),
        "news_articles": news_data[:10],
        "created_at": record.created_at.isoformat() if record.created_at else "",
    })


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


# --- Blocked Users API ---

@app.post("/api/block-user")
async def api_block_user(request: Request):
    """Block a Telegram user by their user ID."""
    ensure_db()
    body = await request.json()
    telegram_user_id = str(body.get("telegram_user_id", "")).strip()
    if not telegram_user_id:
        return JSONResponse({"error": "telegram_user_id is required"}, status_code=400)
    telegram_username = body.get("telegram_username", "")
    reason = body.get("reason", "")
    record = block_user(telegram_user_id, telegram_username, reason)
    return JSONResponse({
        "ok": True,
        "blocked": {
            "id": record.id,
            "telegram_user_id": record.telegram_user_id,
            "telegram_username": record.telegram_username,
            "blocked_at": record.blocked_at.isoformat() if record.blocked_at else "",
        },
    })


@app.post("/api/unblock-user")
async def api_unblock_user(request: Request):
    """Unblock a Telegram user."""
    ensure_db()
    body = await request.json()
    telegram_user_id = str(body.get("telegram_user_id", "")).strip()
    if not telegram_user_id:
        return JSONResponse({"error": "telegram_user_id is required"}, status_code=400)
    deleted = unblock_user(telegram_user_id)
    if not deleted:
        return JSONResponse({"error": "User not found in block list"}, status_code=404)
    return JSONResponse({"ok": True, "unblocked_user_id": telegram_user_id})


@app.get("/api/blocked-users")
async def api_blocked_users():
    """List all blocked Telegram users."""
    ensure_db()
    records = get_blocked_users()
    return JSONResponse([
        {
            "id": r.id,
            "telegram_user_id": r.telegram_user_id,
            "telegram_username": r.telegram_username,
            "reason": r.reason,
            "blocked_at": r.blocked_at.isoformat() if r.blocked_at else "",
        }
        for r in records
    ])


@app.get("/api/is-blocked/{telegram_user_id}")
async def api_is_blocked(telegram_user_id: str):
    """Check if a Telegram user is blocked."""
    ensure_db()
    blocked = is_user_blocked(telegram_user_id)
    return JSONResponse({"telegram_user_id": telegram_user_id, "blocked": blocked})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host=HOST, port=PORT, reload=True)
