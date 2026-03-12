import datetime
import json
import uuid
from typing import Optional, List
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Float, UniqueConstraint, and_
from sqlalchemy.orm import declarative_base, sessionmaker

from config import DATABASE_URL

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine_kwargs = {"connect_args": connect_args}
if not DATABASE_URL.startswith("sqlite"):
    engine_kwargs["pool_pre_ping"] = True
engine = create_engine(DATABASE_URL, **engine_kwargs)
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
    display_name = Column(String(100), nullable=True)
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


class Friendship(Base):
    __tablename__ = "friendships"
    __table_args__ = (UniqueConstraint("user_id", "friend_id", name="uq_friendship"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True, nullable=False)      # requester
    friend_id = Column(Integer, index=True, nullable=False)     # recipient
    status = Column(String(20), default="pending")              # pending / accepted / declined
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    sender_id = Column(Integer, index=True, nullable=False)
    receiver_id = Column(Integer, index=True, nullable=False)
    content = Column(Text, nullable=False)
    is_read = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class Tip(Base):
    __tablename__ = "tips"

    id = Column(Integer, primary_key=True, index=True)
    sender_id = Column(Integer, index=True, nullable=False)
    receiver_id = Column(Integer, index=True, nullable=False)
    ticker = Column(String(20), nullable=False)
    breakout_price = Column(Float, nullable=True)
    stop_loss = Column(Float, nullable=True)
    message = Column(Text, default="")
    analysis_share_token = Column(String(32), nullable=True)
    expires_at = Column(DateTime, nullable=True)
    is_read = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class Reaction(Base):
    __tablename__ = "reactions"
    __table_args__ = (
        UniqueConstraint("user_id", "target_type", "target_id", "emoji", name="uq_reaction"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True, nullable=False)
    target_type = Column(String(20), nullable=False)  # "message" or "tip"
    target_id = Column(Integer, nullable=False)
    emoji = Column(String(30), nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True, nullable=False)
    type = Column(String(30), nullable=False)                   # friend_request / friend_accepted / message / tip
    title = Column(String(200), default="")
    body = Column(Text, default="")
    reference_id = Column(Integer, nullable=True)
    is_read = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


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
            ("tips", "expires_at", "TIMESTAMP"),
            ("users", "display_name", "VARCHAR(100)"),
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
        # Ensure founding users have their assigned codes
        try:
            _hardcoded = {"sabotage": "1337", "adam": "5555"}
            for uname, code in _hardcoded.items():
                db.execute(text("UPDATE users SET user_code = :code WHERE LOWER(username) = :uname"),
                           {"code": code, "uname": uname})
            db.commit()
        except Exception:
            db.rollback()
        # Backfill display_name for founding users
        try:
            _display_names = {"sabotage": "Roy", "adam": "Adam"}
            for uname, dname in _display_names.items():
                db.execute(text("UPDATE users SET display_name = :dname WHERE LOWER(username) = :uname AND (display_name IS NULL OR display_name = '')"),
                           {"dname": dname, "uname": uname})
            db.commit()
        except Exception:
            db.rollback()
        # Backfill user_code for any users that don't have one
        try:
            rows = db.execute(text("SELECT id FROM users WHERE user_code IS NULL OR user_code = ''")).fetchall()
            existing_codes = set()
            if rows:
                existing = db.execute(text("SELECT user_code FROM users WHERE user_code IS NOT NULL AND user_code != ''")).fetchall()
                existing_codes = {r[0] for r in existing}
                existing_codes.update(_RESERVED_CODES)
            for row in rows:
                code = _generate_user_code()
                while code in existing_codes:
                    code = _generate_user_code()
                existing_codes.add(code)
                db.execute(text("UPDATE users SET user_code = :code WHERE id = :id"),
                           {"code": code, "id": row[0]})
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


def create_user(username: str, password_hash: str, role: str = "viewer", display_name: Optional[str] = None) -> User:
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
        user = User(username=username, password_hash=password_hash, role=role, user_code=code, display_name=display_name)
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


# --- User Lookups for Social ---

def get_user_by_id(user_id: int) -> Optional[User]:
    db = SessionLocal()
    try:
        return db.query(User).filter(User.id == user_id).first()
    finally:
        db.close()


def get_user_by_code(code: str) -> Optional[User]:
    db = SessionLocal()
    try:
        return db.query(User).filter(User.user_code == code).first()
    finally:
        db.close()


# --- Friendships ---

def create_friendship(user_id: int, friend_id: int) -> Friendship:
    """Send a friend request. Raises ValueError if already exists."""
    db = SessionLocal()
    try:
        existing = db.query(Friendship).filter(
            ((Friendship.user_id == user_id) & (Friendship.friend_id == friend_id)) |
            ((Friendship.user_id == friend_id) & (Friendship.friend_id == user_id))
        ).first()
        if existing:
            if existing.status == "declined":
                existing.user_id = user_id
                existing.friend_id = friend_id
                existing.status = "pending"
                existing.updated_at = datetime.datetime.utcnow()
                db.commit()
                db.refresh(existing)
                return existing
            raise ValueError("Friend request already exists")
        f = Friendship(user_id=user_id, friend_id=friend_id, status="pending")
        db.add(f)
        db.commit()
        db.refresh(f)
        return f
    finally:
        db.close()


def get_friends(user_id: int) -> List[dict]:
    """Get accepted friends with user info."""
    db = SessionLocal()
    try:
        rows = db.query(Friendship).filter(
            Friendship.status == "accepted",
            (Friendship.user_id == user_id) | (Friendship.friend_id == user_id)
        ).all()
        other_ids = [f.friend_id if f.user_id == user_id else f.user_id for f in rows]
        if not other_ids:
            return []
        users = {u.id: u for u in db.query(User).filter(User.id.in_(other_ids)).all()}
        result = []
        for f in rows:
            other_id = f.friend_id if f.user_id == user_id else f.user_id
            other = users.get(other_id)
            if other:
                result.append({
                    "friendship_id": f.id,
                    "user_id": other.id,
                    "username": other.username,
                    "display_name": other.display_name or "",
                    "user_code": other.user_code or "",
                    "since": f.updated_at.isoformat() if f.updated_at else "",
                })
        return result
    finally:
        db.close()


def get_incoming_friend_requests(user_id: int) -> List[dict]:
    db = SessionLocal()
    try:
        rows = db.query(Friendship).filter(
            Friendship.friend_id == user_id,
            Friendship.status == "pending"
        ).order_by(Friendship.created_at.desc()).all()
        sender_ids = [f.user_id for f in rows]
        if not sender_ids:
            return []
        users = {u.id: u for u in db.query(User).filter(User.id.in_(sender_ids)).all()}
        result = []
        for f in rows:
            sender = users.get(f.user_id)
            if sender:
                result.append({
                    "id": f.id,
                    "user_id": sender.id,
                    "username": sender.username,
                    "display_name": sender.display_name or "",
                    "user_code": sender.user_code or "",
                    "created_at": f.created_at.isoformat() if f.created_at else "",
                })
        return result
    finally:
        db.close()


def get_outgoing_friend_requests(user_id: int) -> List[dict]:
    db = SessionLocal()
    try:
        rows = db.query(Friendship).filter(
            Friendship.user_id == user_id,
            Friendship.status == "pending"
        ).order_by(Friendship.created_at.desc()).all()
        recipient_ids = [f.friend_id for f in rows]
        if not recipient_ids:
            return []
        users = {u.id: u for u in db.query(User).filter(User.id.in_(recipient_ids)).all()}
        result = []
        for f in rows:
            recipient = users.get(f.friend_id)
            if recipient:
                result.append({
                    "id": f.id,
                    "user_id": recipient.id,
                    "username": recipient.username,
                    "display_name": recipient.display_name or "",
                    "user_code": recipient.user_code or "",
                    "created_at": f.created_at.isoformat() if f.created_at else "",
                })
        return result
    finally:
        db.close()


def accept_friend_request(friendship_id: int, user_id: int) -> Optional[Friendship]:
    """Accept a pending friend request. user_id must be the recipient."""
    db = SessionLocal()
    try:
        f = db.query(Friendship).filter(
            Friendship.id == friendship_id,
            Friendship.friend_id == user_id,
            Friendship.status == "pending"
        ).first()
        if not f:
            return None
        f.status = "accepted"
        f.updated_at = datetime.datetime.utcnow()
        db.commit()
        db.refresh(f)
        return f
    finally:
        db.close()


def decline_friend_request(friendship_id: int, user_id: int) -> bool:
    db = SessionLocal()
    try:
        f = db.query(Friendship).filter(
            Friendship.id == friendship_id,
            Friendship.friend_id == user_id,
            Friendship.status == "pending"
        ).first()
        if not f:
            return False
        f.status = "declined"
        f.updated_at = datetime.datetime.utcnow()
        db.commit()
        return True
    finally:
        db.close()


def delete_friendship(friendship_id: int, user_id: int) -> bool:
    """Remove a friend (either party can do it)."""
    db = SessionLocal()
    try:
        f = db.query(Friendship).filter(
            Friendship.id == friendship_id,
            (Friendship.user_id == user_id) | (Friendship.friend_id == user_id)
        ).first()
        if not f:
            return False
        db.delete(f)
        db.commit()
        return True
    finally:
        db.close()


def are_friends(user_id: int, other_id: int) -> bool:
    db = SessionLocal()
    try:
        return db.query(Friendship).filter(
            Friendship.status == "accepted",
            ((Friendship.user_id == user_id) & (Friendship.friend_id == other_id)) |
            ((Friendship.user_id == other_id) & (Friendship.friend_id == user_id))
        ).first() is not None
    finally:
        db.close()


# --- Messages ---

def create_message(sender_id: int, receiver_id: int, content: str) -> Message:
    db = SessionLocal()
    try:
        msg = Message(sender_id=sender_id, receiver_id=receiver_id, content=content[:2000])
        db.add(msg)
        db.commit()
        db.refresh(msg)
        return msg
    finally:
        db.close()


def get_conversation_messages(user_id: int, other_id: int, limit: int = 100, before_id: Optional[int] = None) -> List[dict]:
    db = SessionLocal()
    try:
        query = db.query(Message).filter(
            ((Message.sender_id == user_id) & (Message.receiver_id == other_id)) |
            ((Message.sender_id == other_id) & (Message.receiver_id == user_id))
        )
        if before_id:
            query = query.filter(Message.id < before_id)
        rows = query.order_by(Message.created_at.desc()).limit(limit).all()
        rows.reverse()
        return [{
            "id": m.id,
            "sender_id": m.sender_id,
            "receiver_id": m.receiver_id,
            "content": m.content,
            "is_read": m.is_read,
            "created_at": m.created_at.isoformat() if m.created_at else "",
        } for m in rows]
    finally:
        db.close()


def get_conversations(user_id: int) -> List[dict]:
    """Get list of conversations with last message and unread count."""
    from sqlalchemy import func, case, or_, and_
    db = SessionLocal()
    try:
        # Get all unique conversation partners
        sent = db.query(Message.receiver_id.label("other_id")).filter(Message.sender_id == user_id)
        received = db.query(Message.sender_id.label("other_id")).filter(Message.receiver_id == user_id)
        partner_ids = set()
        for row in sent.all():
            partner_ids.add(row.other_id)
        for row in received.all():
            partner_ids.add(row.other_id)

        # Also include friends who sent tips (tips show in chat)
        tip_senders = db.query(Tip.sender_id.label("other_id")).filter(Tip.receiver_id == user_id)
        tip_receivers = db.query(Tip.receiver_id.label("other_id")).filter(Tip.sender_id == user_id)
        for row in tip_senders.all():
            partner_ids.add(row.other_id)
        for row in tip_receivers.all():
            partner_ids.add(row.other_id)

        convos = []
        for pid in partner_ids:
            other = db.query(User).filter(User.id == pid).first()
            if not other:
                continue
            # Last message
            last_msg = db.query(Message).filter(
                ((Message.sender_id == user_id) & (Message.receiver_id == pid)) |
                ((Message.sender_id == pid) & (Message.receiver_id == user_id))
            ).order_by(Message.created_at.desc()).first()
            # Last tip between these users
            last_tip = db.query(Tip).filter(
                ((Tip.sender_id == user_id) & (Tip.receiver_id == pid)) |
                ((Tip.sender_id == pid) & (Tip.receiver_id == user_id))
            ).order_by(Tip.created_at.desc()).first()
            # Determine which is most recent
            last_time = None
            last_preview = ""
            if last_msg:
                last_time = last_msg.created_at
                last_preview = last_msg.content[:60]
            if last_tip:
                tip_time = last_tip.created_at
                if not last_time or tip_time > last_time:
                    last_time = tip_time
                    last_preview = "[Tip] " + last_tip.ticker
            # Unread messages count
            unread = db.query(Message).filter(
                Message.sender_id == pid,
                Message.receiver_id == user_id,
                Message.is_read == 0
            ).count()
            # Unread tips count
            unread_tips = db.query(Tip).filter(
                Tip.sender_id == pid,
                Tip.receiver_id == user_id,
                Tip.is_read == 0
            ).count()
            convos.append({
                "user_id": other.id,
                "username": other.username,
                "display_name": other.display_name or "",
                "user_code": other.user_code or "",
                "last_message": last_preview,
                "last_time": last_time.isoformat() if last_time else "",
                "unread": unread + unread_tips,
            })
        convos.sort(key=lambda c: c["last_time"] or "", reverse=True)
        return convos
    finally:
        db.close()


def mark_messages_read(user_id: int, sender_id: int) -> int:
    """Mark all messages from sender_id to user_id as read."""
    db = SessionLocal()
    try:
        count = db.query(Message).filter(
            Message.sender_id == sender_id,
            Message.receiver_id == user_id,
            Message.is_read == 0
        ).update({"is_read": 1})
        db.commit()
        return count
    finally:
        db.close()


# --- Tips ---

def create_tip(sender_id: int, receiver_id: int, ticker: str,
               breakout_price: Optional[float] = None,
               stop_loss: Optional[float] = None,
               message: str = "",
               analysis_share_token: Optional[str] = None,
               expiry_hours: Optional[int] = None) -> Tip:
    db = SessionLocal()
    try:
        expires_at = None
        if expiry_hours and expiry_hours > 0:
            expires_at = datetime.datetime.utcnow() + datetime.timedelta(hours=expiry_hours)
        tip = Tip(
            sender_id=sender_id,
            receiver_id=receiver_id,
            ticker=ticker.upper(),
            breakout_price=breakout_price,
            stop_loss=stop_loss,
            message=message[:2000],
            analysis_share_token=analysis_share_token,
            expires_at=expires_at,
        )
        db.add(tip)
        db.commit()
        db.refresh(tip)
        return tip
    finally:
        db.close()


def get_tips(user_id: int, direction: str = "received") -> List[dict]:
    db = SessionLocal()
    try:
        if direction == "sent":
            rows = db.query(Tip).filter(Tip.sender_id == user_id).order_by(Tip.created_at.desc()).all()
        else:
            rows = db.query(Tip).filter(Tip.receiver_id == user_id).order_by(Tip.created_at.desc()).all()
        other_ids = list(set(t.receiver_id if direction == "sent" else t.sender_id for t in rows))
        users = {u.id: u for u in db.query(User).filter(User.id.in_(other_ids)).all()} if other_ids else {}
        result = []
        for t in rows:
            other_id = t.receiver_id if direction == "sent" else t.sender_id
            other = users.get(other_id)
            result.append({
                "id": t.id,
                "sender_id": t.sender_id,
                "receiver_id": t.receiver_id,
                "other_username": other.username if other else "",
                "other_display_name": other.display_name if other else "",
                "ticker": t.ticker,
                "breakout_price": t.breakout_price,
                "stop_loss": t.stop_loss,
                "message": t.message,
                "analysis_share_token": t.analysis_share_token,
                "expires_at": t.expires_at.isoformat() if t.expires_at else None,
                "is_read": t.is_read,
                "created_at": t.created_at.isoformat() if t.created_at else "",
            })
        return result
    finally:
        db.close()


def get_tip_by_id(tip_id: int) -> Optional[dict]:
    db = SessionLocal()
    try:
        t = db.query(Tip).filter(Tip.id == tip_id).first()
        if not t:
            return None
        sender = db.query(User).filter(User.id == t.sender_id).first()
        receiver = db.query(User).filter(User.id == t.receiver_id).first()
        return {
            "id": t.id,
            "sender_id": t.sender_id,
            "receiver_id": t.receiver_id,
            "sender_username": sender.username if sender else "",
            "sender_display_name": sender.display_name if sender else "",
            "receiver_username": receiver.username if receiver else "",
            "receiver_display_name": receiver.display_name if receiver else "",
            "ticker": t.ticker,
            "breakout_price": t.breakout_price,
            "stop_loss": t.stop_loss,
            "message": t.message,
            "analysis_share_token": t.analysis_share_token,
            "expires_at": t.expires_at.isoformat() if t.expires_at else None,
            "is_read": t.is_read,
            "created_at": t.created_at.isoformat() if t.created_at else "",
        }
    finally:
        db.close()


def mark_tip_read(tip_id: int, user_id: int) -> bool:
    db = SessionLocal()
    try:
        t = db.query(Tip).filter(Tip.id == tip_id, Tip.receiver_id == user_id).first()
        if not t:
            return False
        t.is_read = 1
        db.commit()
        return True
    finally:
        db.close()


# --- Notifications ---

def create_notification(user_id: int, ntype: str, title: str, body: str = "", reference_id: Optional[int] = None) -> Notification:
    db = SessionLocal()
    try:
        n = Notification(
            user_id=user_id,
            type=ntype,
            title=title,
            body=body,
            reference_id=reference_id,
        )
        db.add(n)
        db.commit()
        db.refresh(n)
        return n
    finally:
        db.close()


def get_notifications(user_id: int, limit: int = 50) -> List[dict]:
    db = SessionLocal()
    try:
        rows = db.query(Notification).filter(
            Notification.user_id == user_id
        ).order_by(Notification.created_at.desc()).limit(limit).all()
        return [{
            "id": n.id,
            "type": n.type,
            "title": n.title,
            "body": n.body,
            "reference_id": n.reference_id,
            "is_read": n.is_read,
            "created_at": n.created_at.isoformat() if n.created_at else "",
        } for n in rows]
    finally:
        db.close()


def get_unread_notification_counts(user_id: int) -> dict:
    db = SessionLocal()
    try:
        rows = db.query(Notification).filter(
            Notification.user_id == user_id,
            Notification.is_read == 0
        ).all()
        counts = {"total": 0, "friend_request": 0, "friend_accepted": 0, "message": 0, "tip": 0}
        for n in rows:
            counts["total"] += 1
            if n.type in counts:
                counts[n.type] += 1
        return counts
    finally:
        db.close()


def mark_notification_read(notification_id: int, user_id: int) -> bool:
    db = SessionLocal()
    try:
        n = db.query(Notification).filter(
            Notification.id == notification_id,
            Notification.user_id == user_id
        ).first()
        if not n:
            return False
        n.is_read = 1
        db.commit()
        return True
    finally:
        db.close()


def mark_all_notifications_read(user_id: int) -> int:
    db = SessionLocal()
    try:
        count = db.query(Notification).filter(
            Notification.user_id == user_id,
            Notification.is_read == 0
        ).update({"is_read": 1})
        db.commit()
        return count
    finally:
        db.close()


def get_tips_in_conversation(user_id: int, other_id: int) -> List[dict]:
    """Get tips exchanged between two users, for displaying in chat timeline."""
    db = SessionLocal()
    try:
        rows = db.query(Tip).filter(
            ((Tip.sender_id == user_id) & (Tip.receiver_id == other_id)) |
            ((Tip.sender_id == other_id) & (Tip.receiver_id == user_id))
        ).order_by(Tip.created_at.asc()).all()
        return [{
            "id": t.id,
            "sender_id": t.sender_id,
            "receiver_id": t.receiver_id,
            "ticker": t.ticker,
            "breakout_price": t.breakout_price,
            "stop_loss": t.stop_loss,
            "message": t.message,
            "analysis_share_token": t.analysis_share_token,
            "expires_at": t.expires_at.isoformat() if t.expires_at else None,
            "is_read": t.is_read,
            "created_at": t.created_at.isoformat() if t.created_at else "",
            "type": "tip",
        } for t in rows]
    finally:
        db.close()


# --- Delete message / tip ---

def delete_message(message_id: int, user_id: int) -> bool:
    """Delete a message (sender only)."""
    db = SessionLocal()
    try:
        msg = db.query(Message).filter(Message.id == message_id, Message.sender_id == user_id).first()
        if not msg:
            return False
        db.delete(msg)
        db.commit()
        return True
    finally:
        db.close()


def delete_tip(tip_id: int, user_id: int) -> bool:
    """Delete a tip (sender only)."""
    db = SessionLocal()
    try:
        tip = db.query(Tip).filter(Tip.id == tip_id, Tip.sender_id == user_id).first()
        if not tip:
            return False
        db.delete(tip)
        db.commit()
        return True
    finally:
        db.close()


# --- Reactions ---

def toggle_reaction(user_id: int, target_type: str, target_id: int, emoji: str) -> dict:
    """Add or remove a reaction. Returns {"action": "added"/"removed", "emoji": ...}."""
    db = SessionLocal()
    try:
        existing = db.query(Reaction).filter(
            and_(Reaction.user_id == user_id, Reaction.target_type == target_type,
                 Reaction.target_id == target_id, Reaction.emoji == emoji)
        ).first()
        if existing:
            db.delete(existing)
            db.commit()
            return {"action": "removed", "emoji": emoji}
        else:
            r = Reaction(user_id=user_id, target_type=target_type, target_id=target_id, emoji=emoji)
            db.add(r)
            db.commit()
            return {"action": "added", "emoji": emoji}
    finally:
        db.close()


def get_reactions_for_items(target_type: str, target_ids: List[int]) -> dict:
    """Batch fetch reactions grouped by target_id.
    Returns {target_id: [{"emoji": ..., "count": ..., "user_ids": [...]}, ...]}
    """
    if not target_ids:
        return {}
    db = SessionLocal()
    try:
        rows = db.query(Reaction).filter(
            Reaction.target_type == target_type,
            Reaction.target_id.in_(target_ids)
        ).all()
        # Group by target_id -> emoji
        grouped = {}  # type: dict
        for r in rows:
            tid = r.target_id
            if tid not in grouped:
                grouped[tid] = {}
            if r.emoji not in grouped[tid]:
                grouped[tid][r.emoji] = []
            grouped[tid][r.emoji].append(r.user_id)
        # Convert to list format
        result = {}
        for tid, emojis in grouped.items():
            result[tid] = [{"emoji": e, "count": len(uids), "user_ids": uids} for e, uids in emojis.items()]
        return result
    finally:
        db.close()
