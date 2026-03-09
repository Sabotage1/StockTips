# -*- coding: utf-8 -*-
import asyncio
import json
import re
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

from config import TELEGRAM_BOT_TOKEN, EXTERNAL_URL
from stock_analyzer import analyze_stock
from database import save_analysis, is_user_blocked
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

    if rec.startswith("BUY"):
        rec_label = "[+] " + rec
    elif rec.startswith("SELL"):
        rec_label = "[-] " + rec
    else:
        rec_label = "[=] " + rec
    conf_label = {"HIGH": "High", "MEDIUM": "Medium", "LOW": "Low"}.get(conf, conf)

    price_str = "${:.2f}".format(price) if price else "N/A"

    purchase_price = result.get("purchase_price")

    msg = "*{ticker}* -- *{rec}*\n\n".format(ticker=ticker, rec=rec_label)
    msg += "Price: {}\n".format(price_str)
    if purchase_price is not None and price is not None:
        pnl = price - purchase_price
        pnl_pct = (pnl / purchase_price) * 100
        pnl_sign = "+" if pnl >= 0 else ""
        msg += "Entry: ${:.2f} ({}{:.2f}%)\n".format(purchase_price, pnl_sign, pnl_pct)
    msg += "Confidence: {}\n".format(conf_label)
    msg += "Risk: {}\n".format(analysis.get("risk_level", "N/A"))

    trend = analysis.get("trend_status", "")
    if trend:
        msg += "Trend: {}\n".format(trend)

    pattern = analysis.get("chart_pattern", "")
    if pattern and pattern != "N/A" and pattern.lower() != "none detected":
        msg += "Pattern: {}\n".format(pattern)

    msg += "\n{}\n".format(analysis["short_summary"])

    # Action trigger
    action_trigger = analysis.get("action_trigger", "")
    if action_trigger and action_trigger != "N/A":
        msg += "\n>> {}\n".format(action_trigger)

    # Support & Resistance
    supports = analysis.get("support_levels", [])
    resistances = analysis.get("resistance_levels", [])
    if supports or resistances:
        msg += "\n*Levels:*"
        for s in supports[:2]:
            msg += "\nSupport: {}".format(s)
        for r in resistances[:2]:
            msg += "\nResistance: {}".format(r)
        msg += "\n"

    # Breakout info
    breakout = analysis.get("breakout_level", "")
    if breakout and breakout != "N/A":
        direction = analysis.get("breakout_direction", "")
        msg += "\nBreakout: {} ({})".format(breakout, direction)

    exp_gain = analysis.get("expected_gain_pct", "")
    exp_loss = analysis.get("expected_loss_pct", "")
    rr_ratio = analysis.get("risk_reward_ratio", "")
    if exp_gain and exp_gain != "N/A":
        msg += "\nExpected gain: +{}".format(exp_gain.replace("+", ""))
    if exp_loss and exp_loss != "N/A":
        msg += "\nExpected loss: -{}".format(exp_loss.replace("-", ""))
    if rr_ratio and rr_ratio != "N/A":
        msg += "\nRisk/Reward: {}".format(rr_ratio)

    timeframe = analysis.get("breakout_timeframe", "")
    if timeframe and timeframe != "N/A":
        msg += "\nTimeframe: {}".format(timeframe)

    msg += "\n\nShort-term target: {}\n".format(analysis.get("price_target_short", "N/A"))
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
    if update.effective_user and is_user_blocked(str(update.effective_user.id)):
        return
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
    if update.effective_user and is_user_blocked(str(update.effective_user.id)):
        return
    help_text = (
        "*StockTips AI -- Help*\n\n"
        "*Send a ticker symbol* like `AAPL` or `GOOGL` and I'll analyze it.\n\n"
        "*Own a stock?* Add your buy price after the ticker:\n"
        "`AAPL 150` or `/analyze TSLA 220.50`\n"
        "I'll tailor the analysis to your position with P&L and exit strategy.\n\n"
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
    """Handle /analyze TICKER [price] command."""
    if not context.args:
        await update.message.reply_text("Usage: /analyze TICKER [price]\nExample: /analyze AAPL\nExample: /analyze AAPL 150.50")
        return
    ticker = context.args[0].upper().strip()
    purchase_price = None
    if len(context.args) >= 2:
        raw = context.args[1].replace("$", "").replace(",", "").strip()
        try:
            p = float(raw)
            if p > 0:
                purchase_price = p
        except ValueError:
            pass
    await process_ticker(update, ticker, purchase_price=purchase_price)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle plain text messages -- treat them as ticker symbols.

    Supports optional purchase price after the ticker:
      AAPL 150   or   AAPL $150.50
    """
    text = update.message.text.strip()
    # Match ticker optionally followed by a dollar price
    pairs = re.findall(r"\b([A-Za-z]{1,5})\b(?:\s+\$?([\d]+(?:\.[\d]{1,2})?))?", text)
    tickers_with_price = []
    for match in pairs:
        ticker = match[0].upper()
        price_str = match[1]
        purchase_price = None
        if price_str:
            try:
                p = float(price_str)
                if p > 0:
                    purchase_price = p
            except ValueError:
                pass
        tickers_with_price.append((ticker, purchase_price))

    if not tickers_with_price:
        await update.message.reply_text(
            "I didn't recognize any stock ticker. Send a ticker like AAPL or TSLA.\nTo include your buy price: AAPL 150",
        )
        return

    for ticker, purchase_price in tickers_with_price[:3]:
        await process_ticker(update, ticker, purchase_price=purchase_price)


async def process_ticker(update: Update, ticker: str, purchase_price=None):
    """Analyze a ticker and send the result."""
    user = update.effective_user
    if user and is_user_blocked(str(user.id)):
        return  # Silently ignore blocked users

    price_note = ""
    if purchase_price is not None:
        price_note = " (bought at ${:.2f})".format(purchase_price)
    waiting_msg = await update.message.reply_text(
        "Analyzing {}{}... Fetching news, stock data, and running AI analysis. This may take a moment.".format(ticker, price_note),
    )

    try:
        result = await analyze_stock(ticker, purchase_price=purchase_price)

        # Always save to history so every telegram search is recorded
        analysis = result["analysis"]
        user = update.effective_user
        telegram_user = "{} {}".format(user.first_name or "", user.last_name or "").strip()
        if user.username:
            telegram_user += " (@{})".format(user.username)
        telegram_user_id = str(user.id) if user.id else ""

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
            telegram_user_id=telegram_user_id,
        )

        # Attach purchase price so the formatter can show P&L
        if purchase_price is not None:
            result["purchase_price"] = purchase_price

        # Send formatted response
        msg = format_telegram_message(result)
        await waiting_msg.edit_text(msg, parse_mode="Markdown")

        # Send candlestick chart with analysis overlays
        try:
            chart_bytes = generate_chart(result["ticker"], result.get("company_name", ""), analysis_data=analysis)
            if chart_bytes:
                await update.message.reply_photo(
                    photo=chart_bytes,
                    caption="{} -- 6 Month Chart with S/R Levels".format(result["ticker"]),
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


async def start_telegram_bot_async(skip_webhook_set=False):
    """Start the Telegram bot in async mode (non-blocking, for use with FastAPI).

    On Vercel (EXTERNAL_URL set): webhook mode (webhook set externally or via /setup-webhook).
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
        if not skip_webhook_set:
            webhook_url = "{}/webhook/telegram".format(EXTERNAL_URL)
            await app.bot.set_webhook(url=webhook_url, allowed_updates=Update.ALL_TYPES)
            logger.info("Telegram bot started (webhook mode): {}".format(webhook_url))
        else:
            logger.info("Telegram bot initialized (serverless webhook mode).")
    else:
        await app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
        logger.info("Telegram bot started (polling mode)!")

    return app
