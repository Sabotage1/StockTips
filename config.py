import os
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
ALPHA_VANTAGE_KEY = os.getenv("ALPHA_VANTAGE_KEY", "")
NEWS_API_KEY = os.getenv("NEWS_API_KEY", "")
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))
_vercel_url = os.getenv("VERCEL_URL", "")
EXTERNAL_URL = "https://{}".format(_vercel_url) if _vercel_url else ""
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./stocktips.db")
