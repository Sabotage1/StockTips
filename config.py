import os
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
ALPHA_VANTAGE_KEY = os.getenv("ALPHA_VANTAGE_KEY", "")
NEWS_API_KEY = os.getenv("NEWS_API_KEY", "")
AUTH_USERNAME = os.getenv("AUTH_USERNAME", "")
AUTH_PASSWORD_HASH = os.getenv("AUTH_PASSWORD_HASH", "")
AUTH_SECRET_KEY = os.getenv("AUTH_SECRET_KEY", "")
if not AUTH_SECRET_KEY:
    import secrets as _secrets
    AUTH_SECRET_KEY = _secrets.token_hex(32)
TELEGRAM_WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")
if not TELEGRAM_WEBHOOK_SECRET:
    import secrets as _secrets
    TELEGRAM_WEBHOOK_SECRET = _secrets.token_hex(16)
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))
_vercel_url = os.getenv("VERCEL_PROJECT_PRODUCTION_URL", "") or os.getenv("VERCEL_URL", "")
EXTERNAL_URL = "https://{}".format(_vercel_url) if _vercel_url else ""
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./stocktips.db")
