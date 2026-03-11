import json
import os
import asyncio
import logging
import time
from contextlib import asynccontextmanager

import bcrypt
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse, Response, RedirectResponse
from starlette.background import BackgroundTask
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from telegram import Update

from config import HOST, PORT, EXTERNAL_URL, AUTH_SECRET_KEY
from database import (
    init_db, save_analysis, get_history, get_analysis_by_id,
    get_analysis_by_share_token, get_unique_tickers, delete_analysis,
    delete_all_history, block_user, unblock_user, is_user_blocked,
    get_blocked_users, get_user_by_username, get_all_users, create_user,
    delete_user, get_user_portfolio, add_portfolio_item,
    update_portfolio_item, delete_portfolio_item,
    get_user_settings, save_user_settings, reorder_portfolio,
)
from stock_analyzer import analyze_stock, get_quick_signals, get_quick_signals_batch
from chart_generator import generate_chart
from telegram_bot import start_telegram_bot_async
from api_tracker import get_usage

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


def _create_session_token(username: str, role: str = "viewer") -> str:
    """Create a signed session token."""
    return _session_serializer.dumps({"user": username, "role": role, "t": int(time.time())})


def _validate_session_token(token: str):
    """Validate a session token. Returns dict with 'user' and 'role', or None."""
    try:
        data = _session_serializer.loads(token, max_age=SESSION_MAX_AGE)
        return {"user": data.get("user"), "role": data.get("role", "viewer")}
    except (BadSignature, SignatureExpired):
        return None


def _get_session(request: Request):
    """Return session dict {'user', 'role'} or None."""
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    return _validate_session_token(token)


def _is_authenticated(request: Request) -> bool:
    """Check if the current request has a valid session."""
    return _get_session(request) is not None


def _is_admin(request: Request) -> bool:
    """Check if the current user is an admin (verified from DB)."""
    session = _get_session(request)
    if not session:
        return False
    user = get_user_by_username(session["user"])
    return user is not None and user.role == "admin"


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
    """Validate credentials against DB users and set session cookie."""
    ensure_db()
    user = get_user_by_username(username)
    if user:
        try:
            valid = bcrypt.checkpw(
                password.encode("utf-8"),
                user.password_hash.encode("utf-8"),
            )
        except Exception:
            valid = False
        if valid:
            token = _create_session_token(user.username, user.role)
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


@app.get("/api/me")
async def api_me(request: Request):
    """Return the current user's info (username + role) from DB."""
    ensure_db()
    session = _get_session(request)
    if not session:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    # Always look up the real role from DB (old session tokens may lack role)
    user = get_user_by_username(session["user"])
    if not user:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    settings = get_user_settings(user.id)
    return JSONResponse({"username": user.username, "role": user.role, "settings": settings})


@app.post("/webhook/telegram")
async def telegram_webhook(request: Request):
    """Receive Telegram updates via webhook.

    Returns immediately so Telegram doesn't time out, then processes
    the update in a background task (analysis can take 30-60s).
    """
    ensure_db()
    tg_app = await get_telegram_app()
    if tg_app is None:
        return JSONResponse({"error": "Bot not initialized"}, status_code=503)
    data = await request.json()
    update = Update.de_json(data, tg_app.bot)
    # Run analysis in background — respond to Telegram immediately
    return JSONResponse(
        {"ok": True},
        background=BackgroundTask(tg_app.process_update, update),
    )


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
    raw_price = body.get("purchase_price")
    purchase_price = None
    if raw_price is not None:
        try:
            purchase_price = float(str(raw_price).replace("$", "").replace(",", "").strip())
            if purchase_price <= 0:
                purchase_price = None
        except (ValueError, TypeError):
            pass

    if not ticker or len(ticker) > 10:
        return JSONResponse({"error": "Invalid ticker symbol"}, status_code=400)

    try:
        result = await analyze_stock(ticker, purchase_price=purchase_price)
        analysis = result["analysis"]

        # Capture client IP
        client_ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        if not client_ip:
            client_ip = request.headers.get("x-real-ip", "")
        if not client_ip and request.client:
            client_ip = request.client.host or ""

        # Capture web username from session
        session = _get_session(request)
        web_user = session["user"] if session else ""

        # Skip saving error results to history
        _error_markers = ["parsing failed", "error analyzing", "quota exhausted",
                          "an error occurred", "analysis failed"]
        _summary_lower = analysis.get("short_summary", "").lower()
        is_error = analysis.get("confidence") == "LOW" and any(
            m in _summary_lower for m in _error_markers
        )
        if is_error:
            return JSONResponse({
                "error": analysis.get("short_summary", "Analysis failed"),
                "full_analysis": analysis.get("full_analysis", ""),
            }, status_code=502)

        # Save successful results to history
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
            web_user=web_user,
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
            "news_digest": result.get("news_digest"),
            "purchase_price": purchase_price,
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
            "web_user": getattr(r, "web_user", "") or "",
            "share_token": getattr(r, "share_token", "") or "",
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

    # Parse analysis_json for full detail parity
    analysis_extra = {}
    try:
        analysis_extra = json.loads(record.analysis_json) if record.analysis_json else {}
    except json.JSONDecodeError:
        pass

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
        "news_digest": analysis_extra.get("news_digest"),
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
        "news_digest": analysis_extra.get("news_digest"),
        "news_count": len(news_data),
        "news_articles": news_data[:10],
        "created_at": record.created_at.isoformat() if record.created_at else "",
    })


@app.delete("/api/analysis/{analysis_id}")
async def api_delete_analysis(request: Request, analysis_id: int):
    """Delete a single analysis record (admin only)."""
    if not _is_admin(request):
        return JSONResponse({"error": "Admin access required"}, status_code=403)
    ensure_db()
    deleted = delete_analysis(analysis_id)
    if not deleted:
        return JSONResponse({"error": "Not found"}, status_code=404)
    return JSONResponse({"ok": True, "deleted_id": analysis_id})


@app.delete("/api/history")
async def api_delete_history(request: Request, ticker: str = ""):
    """Delete all history, optionally filtered by ticker (admin only)."""
    if not _is_admin(request):
        return JSONResponse({"error": "Admin access required"}, status_code=403)
    ensure_db()
    count = delete_all_history(ticker=ticker or None)
    return JSONResponse({"ok": True, "deleted_count": count})


@app.get("/api/tickers")
async def api_tickers():
    """Get all unique tickers that have been analyzed."""
    ensure_db()
    return JSONResponse(get_unique_tickers())


@app.get("/api/usage")
async def api_usage(request: Request):
    """Return API usage counters (admin only)."""
    if not _is_admin(request):
        return JSONResponse({"error": "Admin access required"}, status_code=403)
    return JSONResponse(get_usage())


# --- Blocked Users API ---

@app.post("/api/block-user")
async def api_block_user(request: Request):
    """Block a Telegram user by their user ID (admin only)."""
    if not _is_admin(request):
        return JSONResponse({"error": "Admin access required"}, status_code=403)
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
    """Unblock a Telegram user (admin only)."""
    if not _is_admin(request):
        return JSONResponse({"error": "Admin access required"}, status_code=403)
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


# --- User Management API (admin only) ---

@app.get("/api/users")
async def api_list_users(request: Request):
    """List all users (admin only)."""
    if not _is_admin(request):
        return JSONResponse({"error": "Admin access required"}, status_code=403)
    ensure_db()
    users = get_all_users()
    return JSONResponse([
        {
            "id": u.id,
            "username": u.username,
            "role": u.role,
            "created_at": u.created_at.isoformat() if u.created_at else "",
        }
        for u in users
    ])


@app.post("/api/users")
async def api_create_user(request: Request):
    """Create a new user (admin only). Viewers can search & view but not delete."""
    if not _is_admin(request):
        return JSONResponse({"error": "Admin access required"}, status_code=403)
    ensure_db()
    body = await request.json()
    username = body.get("username", "").strip()
    password = body.get("password", "")
    role = body.get("role", "viewer")
    if not username or not password:
        return JSONResponse({"error": "Username and password are required"}, status_code=400)
    if len(username) > 100:
        return JSONResponse({"error": "Username too long"}, status_code=400)
    if len(password) < 4:
        return JSONResponse({"error": "Password must be at least 4 characters"}, status_code=400)
    if role not in ("admin", "viewer"):
        role = "viewer"
    try:
        hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        user = create_user(username, hashed, role)
        return JSONResponse({
            "ok": True,
            "user": {
                "id": user.id,
                "username": user.username,
                "role": user.role,
                "created_at": user.created_at.isoformat() if user.created_at else "",
            },
        })
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=409)


@app.delete("/api/users/{user_id}")
async def api_delete_user(request: Request, user_id: int):
    """Delete a user (admin only). Cannot delete yourself."""
    if not _is_admin(request):
        return JSONResponse({"error": "Admin access required"}, status_code=403)
    ensure_db()
    session = _get_session(request)
    # Prevent admin from deleting themselves
    current_user = get_user_by_username(session["user"])
    if current_user and current_user.id == user_id:
        return JSONResponse({"error": "Cannot delete your own account"}, status_code=400)
    deleted = delete_user(user_id)
    if not deleted:
        return JSONResponse({"error": "User not found"}, status_code=404)
    return JSONResponse({"ok": True, "deleted_id": user_id})


# --- Portfolio API ---

def _get_current_user_id(request: Request):
    """Return the logged-in user's DB id, or None."""
    session = _get_session(request)
    if not session:
        return None
    user = get_user_by_username(session["user"])
    return user.id if user else None


@app.get("/api/portfolio")
async def api_portfolio_list(request: Request):
    """List the current user's portfolio items."""
    ensure_db()
    user_id = _get_current_user_id(request)
    if not user_id:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    items = get_user_portfolio(user_id)
    return JSONResponse([
        {
            "id": it.id,
            "ticker": it.ticker,
            "company_name": it.company_name,
            "shares": it.shares,
            "purchase_price": it.purchase_price,
            "stop_loss": it.stop_loss,
            "notes": it.notes,
            "added_at": it.added_at.isoformat() if it.added_at else "",
        }
        for it in items
    ])


@app.post("/api/portfolio")
async def api_portfolio_add(request: Request):
    """Add a stock to the user's portfolio."""
    ensure_db()
    user_id = _get_current_user_id(request)
    if not user_id:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    body = await request.json()
    ticker = body.get("ticker", "").strip().upper()
    if not ticker or len(ticker) > 10:
        return JSONResponse({"error": "Invalid ticker"}, status_code=400)
    try:
        shares = float(body.get("shares", 0))
        purchase_price = float(body.get("purchase_price", 0))
    except (ValueError, TypeError):
        return JSONResponse({"error": "Invalid shares or price"}, status_code=400)
    if shares <= 0 or purchase_price <= 0:
        return JSONResponse({"error": "Shares and price must be positive"}, status_code=400)
    stop_loss = None
    if body.get("stop_loss"):
        try:
            stop_loss = float(body["stop_loss"])
            if stop_loss <= 0:
                stop_loss = None
        except (ValueError, TypeError):
            pass
    try:
        item = add_portfolio_item(
            user_id=user_id,
            ticker=ticker,
            shares=shares,
            purchase_price=purchase_price,
            company_name=body.get("company_name", ""),
            stop_loss=stop_loss,
            notes=body.get("notes", ""),
        )
        return JSONResponse({
            "ok": True,
            "item": {
                "id": item.id,
                "ticker": item.ticker,
                "company_name": item.company_name,
                "shares": item.shares,
                "purchase_price": item.purchase_price,
                "stop_loss": item.stop_loss,
                "notes": item.notes,
                "added_at": item.added_at.isoformat() if item.added_at else "",
            },
        })
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=409)


@app.put("/api/portfolio/{item_id}")
async def api_portfolio_update(request: Request, item_id: int):
    """Update a portfolio item (shares, price, stop_loss, notes)."""
    ensure_db()
    user_id = _get_current_user_id(request)
    if not user_id:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    body = await request.json()
    kwargs = {}
    for key in ("shares", "purchase_price", "stop_loss"):
        if key in body and body[key] is not None:
            try:
                kwargs[key] = float(body[key])
            except (ValueError, TypeError):
                pass
    if "notes" in body:
        kwargs["notes"] = str(body["notes"])
    item = update_portfolio_item(item_id, user_id, **kwargs)
    if not item:
        return JSONResponse({"error": "Not found"}, status_code=404)
    return JSONResponse({
        "ok": True,
        "item": {
            "id": item.id,
            "ticker": item.ticker,
            "shares": item.shares,
            "purchase_price": item.purchase_price,
            "stop_loss": item.stop_loss,
            "notes": item.notes,
        },
    })


@app.delete("/api/portfolio/{item_id}")
async def api_portfolio_delete(request: Request, item_id: int):
    """Remove a stock from the user's portfolio."""
    ensure_db()
    user_id = _get_current_user_id(request)
    if not user_id:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    deleted = delete_portfolio_item(item_id, user_id)
    if not deleted:
        return JSONResponse({"error": "Not found"}, status_code=404)
    return JSONResponse({"ok": True, "deleted_id": item_id})


@app.get("/api/settings")
async def api_settings_get(request: Request):
    """Return the current user's portfolio settings."""
    ensure_db()
    user_id = _get_current_user_id(request)
    if not user_id:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    settings = get_user_settings(user_id)
    return JSONResponse(settings)


@app.put("/api/settings")
async def api_settings_put(request: Request):
    """Save the current user's portfolio settings."""
    ensure_db()
    user_id = _get_current_user_id(request)
    if not user_id:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    body = await request.json()
    saved = save_user_settings(user_id, body)
    return JSONResponse({"ok": True, "settings": saved})


@app.put("/api/portfolio/reorder")
async def api_portfolio_reorder(request: Request):
    """Persist drag-and-drop order for portfolio items."""
    ensure_db()
    user_id = _get_current_user_id(request)
    if not user_id:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    body = await request.json()
    order = body.get("order", [])
    if not isinstance(order, list):
        return JSONResponse({"error": "order must be a list of item IDs"}, status_code=400)
    reorder_portfolio(user_id, order)
    return JSONResponse({"ok": True})


@app.get("/api/portfolio/refresh")
async def api_portfolio_refresh(request: Request):
    """Fetch live prices + quick signals for all portfolio stocks."""
    ensure_db()
    user_id = _get_current_user_id(request)
    if not user_id:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    items = get_user_portfolio(user_id)
    if not items:
        return JSONResponse({"items": [], "totals": {}})

    batch_input = [
        {"ticker": it.ticker, "purchase_price": it.purchase_price, "stop_loss": it.stop_loss}
        for it in items
    ]
    # Run sync Yahoo calls in executor to avoid blocking
    loop = asyncio.get_event_loop()
    signals_map = await loop.run_in_executor(None, get_quick_signals_batch, batch_input)

    enriched = []
    total_value = 0
    total_cost = 0
    total_day_pnl = 0
    for it in items:
        sig = signals_map.get(it.ticker, {})
        cur_price = sig.get("current_price")
        market_value = cur_price * it.shares if cur_price else None
        cost_basis = it.purchase_price * it.shares
        pnl = (market_value - cost_basis) if market_value else None
        pnl_pct = (pnl / cost_basis * 100) if pnl is not None and cost_basis else None

        day_change = sig.get("day_change")
        day_pnl = round(day_change * it.shares, 2) if day_change is not None else None
        if day_pnl is not None:
            total_day_pnl += day_pnl

        if market_value:
            total_value += market_value
        total_cost += cost_basis

        enriched.append({
            "id": it.id,
            "ticker": it.ticker,
            "company_name": it.company_name,
            "shares": it.shares,
            "purchase_price": it.purchase_price,
            "stop_loss": it.stop_loss,
            "notes": it.notes,
            "current_price": cur_price,
            "day_change": day_change,
            "day_change_pct": sig.get("day_change_pct"),
            "day_pnl": day_pnl,
            "market_value": round(market_value, 2) if market_value else None,
            "pnl": round(pnl, 2) if pnl is not None else None,
            "pnl_pct": round(pnl_pct, 2) if pnl_pct is not None else None,
            "signals": sig.get("signals", []),
        })

    # Compute % of portfolio for each item
    for item in enriched:
        if total_value > 0 and item["market_value"] is not None:
            item["pct_of_portfolio"] = round(item["market_value"] / total_value * 100, 2)
        else:
            item["pct_of_portfolio"] = None

    total_pnl = total_value - total_cost if total_value else None
    total_return_pct = (total_pnl / total_cost * 100) if total_pnl is not None and total_cost else None

    return JSONResponse({
        "items": enriched,
        "totals": {
            "total_value": round(total_value, 2),
            "total_cost": round(total_cost, 2),
            "total_pnl": round(total_pnl, 2) if total_pnl is not None else None,
            "total_return_pct": round(total_return_pct, 2) if total_return_pct is not None else None,
            "total_day_pnl": round(total_day_pnl, 2),
        },
    })


@app.get("/api/portfolio/{item_id}/detail")
async def api_portfolio_detail(request: Request, item_id: int):
    """Fetch enriched live data for a single portfolio stock (price, SMAs, signals, P&L)."""
    ensure_db()
    user_id = _get_current_user_id(request)
    if not user_id:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    items = get_user_portfolio(user_id)
    item = None
    for it in items:
        if it.id == item_id:
            item = it
            break
    if not item:
        return JSONResponse({"error": "Portfolio item not found"}, status_code=404)

    loop = asyncio.get_event_loop()
    sig = await loop.run_in_executor(
        None, get_quick_signals, item.ticker, item.purchase_price, item.stop_loss
    )

    cur_price = sig.get("current_price")
    cost_basis = item.purchase_price * item.shares
    market_value = cur_price * item.shares if cur_price else None
    pnl = (market_value - cost_basis) if market_value else None
    pnl_pct = (pnl / cost_basis * 100) if pnl is not None and cost_basis else None

    return JSONResponse({
        "id": item.id,
        "ticker": item.ticker,
        "company_name": sig.get("company_name") or item.company_name,
        "shares": item.shares,
        "purchase_price": item.purchase_price,
        "stop_loss": item.stop_loss,
        "notes": item.notes,
        "current_price": cur_price,
        "previous_close": sig.get("previous_close"),
        "day_change": sig.get("day_change"),
        "day_change_pct": sig.get("day_change_pct"),
        "day_high": sig.get("day_high"),
        "day_low": sig.get("day_low"),
        "open_price": sig.get("open_price"),
        "week_52_high": sig.get("week_52_high"),
        "week_52_low": sig.get("week_52_low"),
        "sma_20": sig.get("sma_20"),
        "sma_50": sig.get("sma_50"),
        "sma_200": sig.get("sma_200"),
        "atr_14": sig.get("atr_14"),
        "volume_ratio": sig.get("volume_ratio"),
        "pre_post": sig.get("pre_post", {}),
        "signals": sig.get("signals", []),
        "market_value": round(market_value, 2) if market_value else None,
        "pnl": round(pnl, 2) if pnl is not None else None,
        "pnl_pct": round(pnl_pct, 2) if pnl_pct is not None else None,
    })


@app.post("/api/portfolio/{item_id}/analyze")
async def api_portfolio_analyze(request: Request, item_id: int):
    """Full AI re-analysis for a portfolio stock, using purchase_price context."""
    ensure_db()
    user_id = _get_current_user_id(request)
    if not user_id:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    items = get_user_portfolio(user_id)
    item = None
    for it in items:
        if it.id == item_id:
            item = it
            break
    if not item:
        return JSONResponse({"error": "Portfolio item not found"}, status_code=404)

    try:
        result = await analyze_stock(item.ticker, purchase_price=item.purchase_price)
        analysis = result["analysis"]

        session = _get_session(request)
        web_user = session["user"] if session else ""

        # Check for error results
        _error_markers = ["parsing failed", "error analyzing", "quota exhausted",
                          "an error occurred", "analysis failed"]
        _summary_lower = analysis.get("short_summary", "").lower()
        is_error = analysis.get("confidence") == "LOW" and any(
            m in _summary_lower for m in _error_markers
        )
        if is_error:
            return JSONResponse({
                "error": analysis.get("short_summary", "Analysis failed"),
                "full_analysis": analysis.get("full_analysis", ""),
            }, status_code=502)

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
            web_user=web_user,
        )

        # Auto-update stop_loss if analysis provides one
        stop_str = analysis.get("stop_loss", "")
        if stop_str and stop_str != "N/A":
            import re
            match = re.search(r'\$?([\d,.]+)', stop_str)
            if match:
                try:
                    new_sl = float(match.group(1).replace(",", ""))
                    if new_sl > 0:
                        update_portfolio_item(item.id, user_id, stop_loss=new_sl)
                except (ValueError, TypeError):
                    pass

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
            "news_digest": result.get("news_digest"),
            "purchase_price": item.purchase_price,
            "news_count": len(result["news_articles"]),
            "news_articles": result["news_articles"][:10],
            "stock_data": result["stock_data"],
            "created_at": record.created_at.isoformat(),
        })
    except Exception as e:
        logger.error("Portfolio analysis error for {}: {}".format(item.ticker, e))
        return JSONResponse({"error": str(e)}, status_code=500)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host=HOST, port=PORT, reload=True)
