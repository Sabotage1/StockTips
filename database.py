import datetime
import uuid
from typing import Optional, List
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Float
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
    recommendation = Column(String(20), default="")  # BUY, SELL, HOLD
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
    share_token = Column(String(32), unique=True, index=True)  # Public share link token
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class BlockedUser(Base):
    __tablename__ = "blocked_users"

    id = Column(Integer, primary_key=True, index=True)
    telegram_user_id = Column(String(50), unique=True, index=True, nullable=False)
    telegram_username = Column(String(200), default="")
    reason = Column(Text, default="")
    blocked_at = Column(DateTime, default=datetime.datetime.utcnow)


class WatchlistItem(Base):
    __tablename__ = "watchlist"

    id = Column(Integer, primary_key=True, index=True)
    ticker = Column(String(20), unique=True, index=True, nullable=False)
    added_at = Column(DateTime, default=datetime.datetime.utcnow)
    notes = Column(Text, default="")


def init_db():
    Base.metadata.create_all(bind=engine)
    # Migrate: add new columns to existing tables (safe for SQLite)
    _migrate_add_columns()


def _migrate_add_columns():
    """Add new columns to existing tables if they don't exist."""
    from sqlalchemy import text
    db = SessionLocal()
    try:
        migrations = [
            ("ticker_analyses", "telegram_user_id", "VARCHAR(50) DEFAULT ''"),
            ("ticker_analyses", "user_ip", "VARCHAR(100) DEFAULT ''"),
            ("ticker_analyses", "share_token", "VARCHAR(32)"),
        ]
        for table, col, col_type in migrations:
            try:
                db.execute(text("ALTER TABLE {} ADD COLUMN {} {}".format(table, col, col_type)))
                db.commit()
            except Exception:
                db.rollback()  # Column already exists
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
    finally:
        db.close()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


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
) -> TickerAnalysis:
    db = SessionLocal()
    try:
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
            share_token=uuid.uuid4().hex,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return record
    finally:
        db.close()


def get_history(days: int = 30, ticker: Optional[str] = None) -> List[TickerAnalysis]:
    """Get analysis history for the last N days (default 30)."""
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


def get_recent_analysis(ticker: str, max_age_minutes: int = 60) -> Optional[TickerAnalysis]:
    """Get the most recent analysis for a ticker if it's within max_age_minutes."""
    db = SessionLocal()
    try:
        cutoff = datetime.datetime.utcnow() - datetime.timedelta(minutes=max_age_minutes)
        return (
            db.query(TickerAnalysis)
            .filter(TickerAnalysis.ticker == ticker.upper())
            .filter(TickerAnalysis.created_at >= cutoff)
            .order_by(TickerAnalysis.created_at.desc())
            .first()
        )
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


def get_unique_tickers() -> List[str]:
    db = SessionLocal()
    try:
        results = db.query(TickerAnalysis.ticker).distinct().all()
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
