# -*- coding: utf-8 -*-
import asyncio
import json
import re
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

from config import TELEGRAM_BOT_TOKEN, EXTERNAL_URL
from stock_analyzer import analyze_stock
from database import save_analysis
from chart_generator import generate_chart

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def format_telegram_message(result: dict) -> str:
    """Format analysis result into a concise Telegram message."""
    analysis = result["analysis"]
    rec = analysis["recommendation"]
    conf = analysis["confidence"]
    ticker = result["ticker"]
    price = result.get("current_price")

    rec_label = {"BUY": "[+] BUY", "SELL": "[-] SELL", "HOLD": "[=] HOLD"}.get(rec, rec)
    conf_label = {"HIGH": "High", "MEDIUM": "Medium", "LOW": "Low"}.get(conf, conf)

    price_str = "${:.2f}".format(price) if price else "N/A"

    msg = "*{ticker}* -- *{rec}*\n\n".format(ticker=ticker, rec=rec_label)
    msg += "Price: {}\n".format(price_str)
    msg += "Confidence: {}\n".format(conf_label)
    msg += "Risk: {}\n".format(analysis.get("risk_level", "N/A"))

    trend = analysis.get("trend_status", "")
    if trend:
        msg += "Trend: {}\n".format(trend)

    pattern = analysis.get("chart_pattern", "")
    if pattern and pattern != "N/A" and pattern.lower() != "none detected":
        msg += "Pattern: {}\n".format(pattern)

    msg += "\n{}\n\n".format(analysis["short_summary"])
    msg += "Short-term target: {}\n".format(analysis.get("price_target_short", "N/A"))
    msg += "Long-term target: {}\n".format(analysis.get("price_target_long", "N/A"))

    stop = analysis.get("stop_loss", "")
    if stop and stop != "N/A":
        msg += "Stop Loss: {}\n".format(stop)

    key_factors = analysis.get("key_factors", [])
    if key_factors:
        msg += "\nKey Factors:"
        for factor in key_factors[:5]:
            msg += "\n- {}".format(factor)

    msg += "\n\n_AI analysis for informational purposes only. Not financial advice._"
    return msg


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    welcome = (
        "*StockTips AI Bot*\n\n"
        "Welcome! I analyze stocks using AI with 20+ years of market expertise.\n\n"
        "*How to use:*\n"
        "- Send any stock ticker (e.g. `AAPL`, `TSLA`, `MSFT`)\n"
        "- Send multiple tickers separated by spaces\n"
        "- Use /analyze TICKER for detailed analysis\n\n"
        "*Commands:*\n"
        "/start -- Show this message\n"
        "/analyze TICKER -- Analyze a stock\n"
        "/help -- Show help\n\n"
        "Just send me a ticker symbol and I'll give you a recommendation!"
    )
    await update.message.reply_text(welcome, parse_mode="Markdown")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command."""
    help_text = (
        "*StockTips AI -- Help*\n\n"
        "*Send a ticker symbol* like `AAPL` or `GOOGL` and I'll analyze it.\n\n"
        "*What I analyze:*\n"
        "- Current price & key financial metrics\n"
        "- Recent news from multiple sources\n"
        "- Technical indicators & trends\n"
        "- Analyst consensus & sentiment\n"
        "- Risk factors\n\n"
        "*I'll respond with:*\n"
        "- BUY / SELL / HOLD recommendation\n"
        "- Confidence level\n"
        "- Price targets\n"
        "- Key factors driving the recommendation\n\n"
        "All history is saved and viewable on the web dashboard."
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")


async def analyze_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /analyze TICKER command."""
    if not context.args:
        await update.message.reply_text("Usage: /analyze TICKER\nExample: /analyze AAPL")
        return
    ticker = context.args[0].upper().strip()
    await process_ticker(update, ticker)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle plain text messages -- treat them as ticker symbols."""
    text = update.message.text.strip().upper()
    # Extract potential tickers (1-5 uppercase letters)
    tickers = re.findall(r"\b[A-Z]{1,5}\b", text)
    if not tickers:
        await update.message.reply_text(
            "I didn't recognize any stock ticker. Send a ticker like AAPL or TSLA.",
        )
        return

    for ticker in tickers[:3]:  # Limit to 3 tickers per message
        await process_ticker(update, ticker)


async def process_ticker(update: Update, ticker: str):
    """Analyze a ticker and send the result."""
    waiting_msg = await update.message.reply_text(
        "Analyzing {}... Fetching news, stock data, and running AI analysis. This may take a moment.".format(ticker),
    )

    try:
        result = await analyze_stock(ticker)

        # Always save to history so every telegram search is recorded
        analysis = result["analysis"]
        user = update.effective_user
        telegram_user = "{} {}".format(user.first_name or "", user.last_name or "").strip()
        if user.username:
            telegram_user += " (@{})".format(user.username)

        save_analysis(
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
            source="telegram",
            telegram_user=telegram_user,
        )

        # Send formatted response
        msg = format_telegram_message(result)
        await waiting_msg.edit_text(msg, parse_mode="Markdown")

        # Send candlestick chart
        try:
            chart_bytes = generate_chart(result["ticker"], result.get("company_name", ""))
            if chart_bytes:
                await update.message.reply_photo(
                    photo=chart_bytes,
                    caption="{} -- 6 Month Candlestick Chart (SMA 20/150/200)".format(result["ticker"]),
                )
        except Exception as chart_err:
            logger.warning("Chart generation failed for {}: {}".format(ticker, chart_err))

    except Exception as e:
        logger.error("Error analyzing {}: {}".format(ticker, e))
        await waiting_msg.edit_text(
            "Error analyzing {}: {}\n\nPlease try again.".format(ticker, str(e)[:200]),
        )


def run_telegram_bot():
    """Start the Telegram bot (blocking)."""
    if not TELEGRAM_BOT_TOKEN:
        logger.warning("TELEGRAM_BOT_TOKEN not set -- Telegram bot disabled.")
        return

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("analyze", analyze_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Telegram bot started!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


async def start_telegram_bot_async():
    """Start the Telegram bot in async mode (non-blocking, for use with FastAPI).

    On Vercel (EXTERNAL_URL set): configures webhook mode.
    Locally: falls back to polling mode.
    """
    if not TELEGRAM_BOT_TOKEN:
        logger.warning("TELEGRAM_BOT_TOKEN not set -- Telegram bot disabled.")
        return None

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("analyze", analyze_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    await app.initialize()
    await app.start()

    if EXTERNAL_URL:
        webhook_url = "{}/webhook/telegram".format(EXTERNAL_URL)
        await app.bot.set_webhook(url=webhook_url, allowed_updates=Update.ALL_TYPES)
        logger.info("Telegram bot started (webhook mode): {}".format(webhook_url))
    else:
        await app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
        logger.info("Telegram bot started (polling mode)!")

    return app
