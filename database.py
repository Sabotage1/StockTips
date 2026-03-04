import datetime
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
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class WatchlistItem(Base):
    __tablename__ = "watchlist"

    id = Column(Integer, primary_key=True, index=True)
    ticker = Column(String(20), unique=True, index=True, nullable=False)
    added_at = Column(DateTime, default=datetime.datetime.utcnow)
    notes = Column(Text, default="")


def init_db():
    Base.metadata.create_all(bind=engine)


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
