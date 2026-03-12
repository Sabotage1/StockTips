import datetime
import json
import uuid
from typing import Optional, List
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Float, UniqueConstraint
from sqlalchemy.orm import declarative_base, sessionmaker

from config import DATABASE_URL

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


class TickerAnalysis(Base):
    __tablename__ = "ticker_analyses"

    id = Column(Integer, primary_key=True, index=True)
    ticker = Column(String(20), index=True, nullable=False)
    company_name = Column(String(200), default="")
    current_price = Column(Float, nullable=True)
    recommendation = Column(String(200), default="")  # e.g. "BUY at $298.50 (stop $280.00)"
    confidence = Column(String(20), default="")  # HIGH, MEDIUM, LOW
    short_summary = Column(Text, default="")
    full_analysis = Column(Text, default="")
    news_data = Column(Text, default="")  # JSON string of news articles used
    stock_data = Column(Text, default="")  # JSON string of stock metrics
    analysis_json = Column(Text, default="")  # Full AI analysis JSON (all fields)
    source = Column(String(50), default="web")  # web, telegram
    telegram_user = Column(String(200), default="")
    telegram_user_id = Column(String(50), default="")  # Telegram numeric user ID
    user_ip = Column(String(100), default="")  # Client IP address
    web_user = Column(String(100), default="")  # Logged-in web username who requested
    share_token = Column(String(32), unique=True, index=True)  # Public share link token
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class BlockedUser(Base):
    __tablename__ = "blocked_users"

    id = Column(Integer, primary_key=True, index=True)
    telegram_user_id = Column(String(50), unique=True, index=True, nullable=False)
    telegram_username = Column(String(200), default="")
    reason = Column(Text, default="")
    blocked_at = Column(DateTime, default=datetime.datetime.utcnow)


_RESERVED_CODES = {"1337", "5555"}


def _generate_user_code():
    """Generate a unique random 4-digit user code, avoiding reserved codes."""
    import random
    code = str(random.randint(1000, 9999))
    while code in _RESERVED_CODES:
        code = str(random.randint(1000, 9999))
    return code


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, index=True, nullable=False)
    password_hash = Column(String(200), nullable=False)
    role = Column(String(20), default="viewer")  # "admin" or "viewer"
    user_code = Column(String(4), unique=True, index=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class WatchlistItem(Base):
    __tablename__ = "watchlist"

    id = Column(Integer, primary_key=True, index=True)
    ticker = Column(String(20), unique=True, index=True, nullable=False)
    added_at = Column(DateTime, default=datetime.datetime.utcnow)
    notes = Column(Text, default="")


class PortfolioItem(Base):
    __tablename__ = "portfolio_items"
    __table_args__ = (UniqueConstraint("user_id", "ticker", name="uq_user_ticker"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True, nullable=False)
    ticker = Column(String(20), nullable=False)
    company_name = Column(String(200), default="")
    shares = Column(Float, nullable=False)
    purchase_price = Column(Float, nullable=False)
    purchase_date = Column(String(20), default="")
    stop_loss = Column(Float, nullable=True)
    notes = Column(Text, default="")
    sort_order = Column(Integer, default=0)
    added_at = Column(DateTime, default=datetime.datetime.utcnow)


class PortfolioTransaction(Base):
    __tablename__ = "portfolio_transactions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True, nullable=False)
    portfolio_item_id = Column(Integer, index=True, nullable=True)
    ticker = Column(String(20), index=True, nullable=False)
    action = Column(String(10), nullable=False)  # BUY or SELL
    shares = Column(Float, nullable=False)
    price = Column(Float, nullable=False)
    total_amount = Column(Float, nullable=False)
    avg_cost_at_time = Column(Float, nullable=True)
    realized_pnl = Column(Float, nullable=True)
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class UserSettings(Base):
    __tablename__ = "user_settings"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, unique=True, index=True, nullable=False)
    settings_json = Column(Text, default="{}")
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)


def init_db():
    Base.metadata.create_all(bind=engine)
    # Migrate: add new columns to existing tables (safe for SQLite)
    _migrate_add_columns()
    # Seed the admin user if no users exist
    _seed_admin_user()


def _migrate_add_columns():
    """Add new columns to existing tables if they don't exist."""
    from sqlalchemy import text
    db = SessionLocal()
    try:
        migrations = [
            ("ticker_analyses", "telegram_user_id", "VARCHAR(50) DEFAULT ''"),
            ("ticker_analyses", "user_ip", "VARCHAR(100) DEFAULT ''"),
            ("ticker_analyses", "share_token", "VARCHAR(32)"),
            ("ticker_analyses", "web_user", "VARCHAR(100) DEFAULT ''"),
            ("portfolio_items", "sort_order", "INTEGER DEFAULT 0"),
            ("users", "user_code", "VARCHAR(5)"),
        ]
        for table, col, col_type in migrations:
            try:
                db.execute(text("ALTER TABLE {} ADD COLUMN {} {}".format(table, col, col_type)))
                db.commit()
            except Exception:
                db.rollback()  # Column already exists
        # Widen recommendation column for longer values like "BUY at $298.50 (stop $280.00)"
        try:
            db.execute(text("ALTER TABLE ticker_analyses ALTER COLUMN recommendation TYPE VARCHAR(200)"))
            db.commit()
        except Exception:
            db.rollback()  # SQLite ignores column type changes; Postgres may already be correct
        # Backfill share_token for existing rows that don't have one
        try:
            rows = db.execute(text("SELECT id FROM ticker_analyses WHERE share_token IS NULL")).fetchall()
            for row in rows:
                db.execute(text("UPDATE ticker_analyses SET share_token = :token WHERE id = :id"),
                           {"token": uuid.uuid4().hex, "id": row[0]})
            if rows:
                db.commit()
        except Exception:
            db.rollback()
        # Backfill user_code for existing users that don't have one
        try:
            rows = db.execute(text("SELECT id, username FROM users WHERE user_code IS NULL OR user_code = ''")).fetchall()
            existing_codes = set()
            if rows:
                existing = db.execute(text("SELECT user_code FROM users WHERE user_code IS NOT NULL AND user_code != ''")).fetchall()
                existing_codes = {r[0] for r in existing}
            # Hardcoded codes for founding users
            _hardcoded = {"sabotage": "1337", "adam": "5555"}
            for row in rows:
                uid, uname = row[0], row[1].lower()
                if uname in _hardcoded:
                    code = _hardcoded[uname]
                else:
                    code = _generate_user_code()
                    while code in existing_codes:
                        code = _generate_user_code()
                existing_codes.add(code)
                db.execute(text("UPDATE users SET user_code = :code WHERE id = :id"),
                           {"code": code, "id": uid})
            if rows:
                db.commit()
        except Exception:
            db.rollback()
    finally:
        db.close()


def _seed_admin_user():
    """Create the Sabotage admin user if no users exist yet."""
    from config import AUTH_USERNAME, AUTH_PASSWORD_HASH
    db = SessionLocal()
    try:
        if db.query(User).count() == 0 and AUTH_USERNAME and AUTH_PASSWORD_HASH:
            admin = User(
                username=AUTH_USERNAME,
                password_hash=AUTH_PASSWORD_HASH,
                role="admin",
            )
            db.add(admin)
            db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


_ERROR_MARKERS = ["parsing failed", "error analyzing", "quota exhausted",
                   "an error occurred", "analysis failed"]


def _is_error_analysis(confidence: str, short_summary: str) -> bool:
    """Check if an analysis result is an error/failure."""
    lower = short_summary.lower()
    return confidence == "LOW" and any(m in lower for m in _ERROR_MARKERS)


def _delete_old_analyses(db, ticker: str, web_user: str = "", source: str = "web", telegram_user_id: str = "", hours: int = 24):
    """Delete previous analyses for the same ticker+user from the past N hours."""
    cutoff = datetime.datetime.utcnow() - datetime.timedelta(hours=hours)
    query = db.query(TickerAnalysis).filter(
        TickerAnalysis.ticker == ticker.upper(),
        TickerAnalysis.created_at >= cutoff,
    )
    if source == "telegram" and telegram_user_id:
        query = query.filter(TickerAnalysis.telegram_user_id == telegram_user_id)
    elif web_user:
        query = query.filter(TickerAnalysis.web_user == web_user)
    query.delete(synchronize_session=False)


def save_analysis(
    ticker: str,
    company_name: str,
    current_price: Optional[float],
    recommendation: str,
    confidence: str,
    short_summary: str,
    full_analysis: str,
    news_data: str,
    stock_data: str,
    source: str = "web",
    telegram_user: str = "",
    telegram_user_id: str = "",
    user_ip: str = "",
    analysis_json: str = "",
    web_user: str = "",
) -> TickerAnalysis:
    db = SessionLocal()
    try:
        if not _is_error_analysis(confidence, short_summary):
            _delete_old_analyses(db, ticker, web_user=web_user, source=source, telegram_user_id=telegram_user_id)
        record = TickerAnalysis(
            ticker=ticker.upper(),
            company_name=company_name,
            current_price=current_price,
            recommendation=recommendation,
            confidence=confidence,
            short_summary=short_summary,
            full_analysis=full_analysis,
            news_data=news_data,
            stock_data=stock_data,
            analysis_json=analysis_json,
            source=source,
            telegram_user=telegram_user,
            telegram_user_id=telegram_user_id,
            user_ip=user_ip,
            web_user=web_user,
            share_token=uuid.uuid4().hex,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return record
    finally:
        db.close()


def get_history(days: int = 30, ticker: Optional[str] = None, web_user: Optional[str] = None) -> List[TickerAnalysis]:
    """Get analysis history for the last N days (default 30).
    If web_user is provided, only return that user's analyses."""
    db = SessionLocal()
    try:
        cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=days)
        query = (
            db.query(TickerAnalysis)
            .filter(TickerAnalysis.created_at >= cutoff)
            .order_by(TickerAnalysis.created_at.desc())
        )
        if ticker:
            query = query.filter(TickerAnalysis.ticker == ticker.upper())
        if web_user:
            query = query.filter(TickerAnalysis.web_user == web_user)
        return query.all()
    finally:
        db.close()


def get_analysis_by_id(analysis_id: int) -> Optional[TickerAnalysis]:
    db = SessionLocal()
    try:
        return db.query(TickerAnalysis).filter(TickerAnalysis.id == analysis_id).first()
    finally:
        db.close()


def get_analysis_by_share_token(token: str) -> Optional[TickerAnalysis]:
    """Look up an analysis by its public share token."""
    db = SessionLocal()
    try:
        return db.query(TickerAnalysis).filter(TickerAnalysis.share_token == token).first()
    finally:
        db.close()


def get_recent_analysis(ticker: str, max_age_minutes: int = 60, web_user: Optional[str] = None) -> Optional[TickerAnalysis]:
    """Get the most recent analysis for a ticker if it's within max_age_minutes.
    If web_user is provided, only return that user's analysis."""
    db = SessionLocal()
    try:
        cutoff = datetime.datetime.utcnow() - datetime.timedelta(minutes=max_age_minutes)
        query = (
            db.query(TickerAnalysis)
            .filter(TickerAnalysis.ticker == ticker.upper())
            .filter(TickerAnalysis.created_at >= cutoff)
        )
        if web_user:
            query = query.filter(TickerAnalysis.web_user == web_user)
        return query.order_by(TickerAnalysis.created_at.desc()).first()
    finally:
        db.close()


def delete_analysis(analysis_id: int) -> bool:
    """Delete a single analysis record by ID. Returns True if deleted."""
    db = SessionLocal()
    try:
        record = db.query(TickerAnalysis).filter(TickerAnalysis.id == analysis_id).first()
        if not record:
            return False
        db.delete(record)
        db.commit()
        return True
    finally:
        db.close()


def delete_all_history(ticker: Optional[str] = None) -> int:
    """Delete all history (or filtered by ticker). Returns count deleted."""
    db = SessionLocal()
    try:
        query = db.query(TickerAnalysis)
        if ticker:
            query = query.filter(TickerAnalysis.ticker == ticker.upper())
        count = query.count()
        query.delete(synchronize_session=False)
        db.commit()
        return count
    finally:
        db.close()


def get_unique_tickers(web_user: Optional[str] = None) -> List[str]:
    db = SessionLocal()
    try:
        query = db.query(TickerAnalysis.ticker)
        if web_user:
            query = query.filter(TickerAnalysis.web_user == web_user)
        results = query.distinct().all()
        return [r[0] for r in results]
    finally:
        db.close()


# --- Blocked Users ---

def block_user(telegram_user_id: str, telegram_username: str = "", reason: str = "") -> BlockedUser:
    """Block a Telegram user by their numeric user ID."""
    db = SessionLocal()
    try:
        existing = db.query(BlockedUser).filter(BlockedUser.telegram_user_id == telegram_user_id).first()
        if existing:
            return existing
        record = BlockedUser(
            telegram_user_id=telegram_user_id,
            telegram_username=telegram_username,
            reason=reason,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return record
    finally:
        db.close()


def unblock_user(telegram_user_id: str) -> bool:
    """Unblock a Telegram user. Returns True if a record was deleted."""
    db = SessionLocal()
    try:
        record = db.query(BlockedUser).filter(BlockedUser.telegram_user_id == telegram_user_id).first()
        if not record:
            return False
        db.delete(record)
        db.commit()
        return True
    finally:
        db.close()


def is_user_blocked(telegram_user_id: str) -> bool:
    """Check if a Telegram user is blocked."""
    db = SessionLocal()
    try:
        return db.query(BlockedUser).filter(BlockedUser.telegram_user_id == telegram_user_id).first() is not None
    finally:
        db.close()


def get_blocked_users() -> List[BlockedUser]:
    """Get all blocked users."""
    db = SessionLocal()
    try:
        return db.query(BlockedUser).order_by(BlockedUser.blocked_at.desc()).all()
    finally:
        db.close()


# --- User Management ---

def get_user_by_username(username: str) -> Optional[User]:
    """Look up a user by username (case-insensitive)."""
    db = SessionLocal()
    try:
        return db.query(User).filter(User.username.ilike(username)).first()
    finally:
        db.close()


def get_all_users() -> List[User]:
    """Return all users ordered by creation date."""
    db = SessionLocal()
    try:
        return db.query(User).order_by(User.created_at).all()
    finally:
        db.close()


def create_user(username: str, password_hash: str, role: str = "viewer") -> User:
    """Create a new user. Raises ValueError if username already exists."""
    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.username.ilike(username)).first()
        if existing:
            raise ValueError("Username already exists")
        # Generate unique 4-digit user code
        existing_codes = {u.user_code for u in db.query(User).filter(User.user_code.isnot(None)).all()}
        existing_codes.update(_RESERVED_CODES)
        code = _generate_user_code()
        while code in existing_codes:
            code = _generate_user_code()
        user = User(username=username, password_hash=password_hash, role=role, user_code=code)
        db.add(user)
        db.commit()
        db.refresh(user)
        return user
    finally:
        db.close()


def delete_user(user_id: int) -> bool:
    """Delete a user by ID. Returns True if deleted."""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return False
        db.delete(user)
        db.commit()
        return True
    finally:
        db.close()


# --- Portfolio ---

def get_user_portfolio(user_id: int) -> List[PortfolioItem]:
    """Return all portfolio items for a user, ordered by sort_order then newest."""
    db = SessionLocal()
    try:
        return (
            db.query(PortfolioItem)
            .filter(PortfolioItem.user_id == user_id)
            .order_by(PortfolioItem.sort_order.asc(), PortfolioItem.added_at.desc())
            .all()
        )
    finally:
        db.close()


def add_portfolio_item(
    user_id: int,
    ticker: str,
    shares: float,
    purchase_price: float,
    company_name: str = "",
    stop_loss: Optional[float] = None,
    notes: str = "",
) -> PortfolioItem:
    """Add a stock to the user's portfolio. Raises ValueError if duplicate."""
    db = SessionLocal()
    try:
        existing = (
            db.query(PortfolioItem)
            .filter(PortfolioItem.user_id == user_id, PortfolioItem.ticker == ticker.upper())
            .first()
        )
        if existing:
            raise ValueError("Ticker {} is already in your portfolio".format(ticker.upper()))
        max_order = db.query(PortfolioItem).filter(PortfolioItem.user_id == user_id).count()
        item = PortfolioItem(
            user_id=user_id,
            ticker=ticker.upper(),
            company_name=company_name,
            shares=shares,
            purchase_price=purchase_price,
            stop_loss=stop_loss,
            notes=notes,
            sort_order=max_order,
        )
        db.add(item)
        db.commit()
        db.refresh(item)
        return item
    finally:
        db.close()


def update_portfolio_item(
    item_id: int,
    user_id: int,
    shares: Optional[float] = None,
    purchase_price: Optional[float] = None,
    stop_loss: Optional[float] = None,
    notes: Optional[str] = None,
) -> Optional[PortfolioItem]:
    """Partial update of a portfolio item. Returns updated item or None."""
    db = SessionLocal()
    try:
        item = (
            db.query(PortfolioItem)
            .filter(PortfolioItem.id == item_id, PortfolioItem.user_id == user_id)
            .first()
        )
        if not item:
            return None
        if shares is not None:
            item.shares = shares
        if purchase_price is not None:
            item.purchase_price = purchase_price
        if stop_loss is not None:
            item.stop_loss = stop_loss
        if notes is not None:
            item.notes = notes
        db.commit()
        db.refresh(item)
        return item
    finally:
        db.close()


def delete_portfolio_item(item_id: int, user_id: int) -> bool:
    """Remove a stock from portfolio. Returns True if deleted."""
    db = SessionLocal()
    try:
        item = (
            db.query(PortfolioItem)
            .filter(PortfolioItem.id == item_id, PortfolioItem.user_id == user_id)
            .first()
        )
        if not item:
            return False
        db.delete(item)
        db.commit()
        return True
    finally:
        db.close()


# --- Portfolio Transactions (Buy More / Sell) ---

def buy_more_shares(item_id: int, user_id: int, new_shares: float, new_price: float, notes: str = "") -> Optional[PortfolioItem]:
    """Buy more shares of an existing position. Recalculates weighted average cost."""
    db = SessionLocal()
    try:
        item = (
            db.query(PortfolioItem)
            .filter(PortfolioItem.id == item_id, PortfolioItem.user_id == user_id)
            .first()
        )
        if not item:
            return None
        old_shares = item.shares
        old_avg = item.purchase_price
        total_shares = old_shares + new_shares
        new_avg = (old_shares * old_avg + new_shares * new_price) / total_shares
        item.shares = total_shares
        item.purchase_price = round(new_avg, 4)
        # Log transaction
        txn = PortfolioTransaction(
            user_id=user_id,
            portfolio_item_id=item.id,
            ticker=item.ticker,
            action="BUY",
            shares=new_shares,
            price=new_price,
            total_amount=round(new_shares * new_price, 2),
            avg_cost_at_time=round(new_avg, 4),
            notes=notes,
        )
        db.add(txn)
        db.commit()
        db.refresh(item)
        return item
    finally:
        db.close()


def sell_shares(item_id: int, user_id: int, sell_shares_count: float, sell_price: float, notes: str = "") -> dict:
    """Sell shares from a position. Returns dict with updated item (or None if fully sold) and realized P&L."""
    db = SessionLocal()
    try:
        item = (
            db.query(PortfolioItem)
            .filter(PortfolioItem.id == item_id, PortfolioItem.user_id == user_id)
            .first()
        )
        if not item:
            return {"error": "not_found"}
        if sell_shares_count > item.shares:
            return {"error": "insufficient_shares", "available": item.shares}
        avg_cost = item.purchase_price
        realized_pnl = round((sell_price - avg_cost) * sell_shares_count, 2)
        remaining = round(item.shares - sell_shares_count, 6)
        # Log transaction
        txn = PortfolioTransaction(
            user_id=user_id,
            portfolio_item_id=item.id,
            ticker=item.ticker,
            action="SELL",
            shares=sell_shares_count,
            price=sell_price,
            total_amount=round(sell_shares_count * sell_price, 2),
            avg_cost_at_time=avg_cost,
            realized_pnl=realized_pnl,
            notes=notes,
        )
        db.add(txn)
        if remaining <= 0:
            db.delete(item)
            db.commit()
            return {"item": None, "realized_pnl": realized_pnl, "fully_sold": True, "ticker": item.ticker}
        else:
            item.shares = remaining
            db.commit()
            db.refresh(item)
            return {"item": item, "realized_pnl": realized_pnl, "fully_sold": False, "ticker": item.ticker}
    finally:
        db.close()


def get_portfolio_transactions(user_id: int, portfolio_item_id: Optional[int] = None, ticker: Optional[str] = None) -> List[PortfolioTransaction]:
    """Get transaction history for a user, optionally filtered by item or ticker."""
    db = SessionLocal()
    try:
        query = (
            db.query(PortfolioTransaction)
            .filter(PortfolioTransaction.user_id == user_id)
        )
        if portfolio_item_id is not None:
            query = query.filter(PortfolioTransaction.portfolio_item_id == portfolio_item_id)
        if ticker:
            query = query.filter(PortfolioTransaction.ticker == ticker.upper())
        return query.order_by(PortfolioTransaction.created_at.desc()).all()
    finally:
        db.close()


def get_realized_pnl_total(user_id: int) -> float:
    """Sum all realized P&L for a user."""
    db = SessionLocal()
    try:
        from sqlalchemy import func
        result = (
            db.query(func.coalesce(func.sum(PortfolioTransaction.realized_pnl), 0.0))
            .filter(PortfolioTransaction.user_id == user_id, PortfolioTransaction.action == "SELL")
            .scalar()
        )
        return round(float(result), 2)
    finally:
        db.close()


# --- User Settings ---

DEFAULT_SETTINGS = {
    "visible_columns": {
        "ticker": True, "shares": True, "avg_cost": True, "price": True,
        "mkt_value": True, "pct_port": True, "pnl": True, "pnl_pct": True,
        "day_pnl": True, "day_pct": True, "signals": True, "actions": True,
    },
    "visible_cards": {
        "total_value": True, "total_cost": True, "total_pnl": True,
        "total_return": True, "day_pnl": True, "realized_pnl": True,
    },
    "show_pie_chart": True,
}


def get_user_settings(user_id: int) -> dict:
    """Return user settings merged with defaults."""
    db = SessionLocal()
    try:
        record = db.query(UserSettings).filter(UserSettings.user_id == user_id).first()
        result = json.loads(json.dumps(DEFAULT_SETTINGS))  # deep copy defaults
        if record and record.settings_json:
            stored = json.loads(record.settings_json)
            # Merge stored into defaults
            for key in ("visible_columns", "visible_cards"):
                if key in stored and isinstance(stored[key], dict):
                    result[key].update(stored[key])
            if "show_pie_chart" in stored:
                result["show_pie_chart"] = stored["show_pie_chart"]
        return result
    finally:
        db.close()


def save_user_settings(user_id: int, settings: dict) -> dict:
    """Upsert user settings. Returns the saved settings."""
    db = SessionLocal()
    try:
        record = db.query(UserSettings).filter(UserSettings.user_id == user_id).first()
        settings_str = json.dumps(settings)
        if record:
            record.settings_json = settings_str
            record.updated_at = datetime.datetime.utcnow()
        else:
            record = UserSettings(user_id=user_id, settings_json=settings_str)
            db.add(record)
        db.commit()
        return settings
    finally:
        db.close()


def reorder_portfolio(user_id: int, item_ids: List[int]) -> bool:
    """Set sort_order for portfolio items based on the given ID order."""
    db = SessionLocal()
    try:
        for idx, item_id in enumerate(item_ids):
            db.query(PortfolioItem).filter(
                PortfolioItem.id == item_id,
                PortfolioItem.user_id == user_id,
            ).update({"sort_order": idx})
        db.commit()
        return True
    finally:
        db.close()
