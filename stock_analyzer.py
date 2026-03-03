import json
import httpx
from bs4 import BeautifulSoup
import google.generativeai as genai
from news_fetcher import fetch_all_news
from config import GEMINI_API_KEY, ALPHA_VANTAGE_KEY
from database import get_recent_analysis

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.5-flash")

SYSTEM_PROMPT = """You are an elite stock market analyst with over 20 years of experience in the stock exchange.
You specialize in a combined technical + fundamental approach, inspired by methods from William O'Neil (CANSLIM),
Mark Minervini (Trend Template), and Stan Weinstein (Stage Analysis).

YOUR CORE TECHNICAL FRAMEWORK:
1. **Moving Average Analysis (CRITICAL)**:
   - SMA 200: Long-term trend. Price ABOVE SMA200 = bullish regime. BELOW = bearish.
   - SMA 150: Intermediate trend confirmation. Should be above SMA200 in an uptrend.
   - SMA 20: Short-term momentum. Pullbacks to SMA20 in an uptrend = potential entry.
   - Proper alignment (bullish): Price > SMA20 > SMA150 > SMA200 (all rising).
   - The Minervini Trend Template: Stock must be above SMA150 and SMA200, SMA150 > SMA200,
     price at least 25% above 52-week low, within 25% of 52-week high.

2. **ATR (Average True Range)**:
   - Use ATR to assess volatility and set stop-loss levels.
   - Low ATR = consolidation (potential breakout setup).
   - High ATR = volatile, may need wider stops.
   - Suggest stop-loss as a multiple of ATR (e.g., 2x ATR below entry).

3. **Chart Pattern Recognition** — Flag any patterns suggested by the price/volume data:
   - **Cup and Handle**: U-shaped recovery followed by small consolidation (handle). Bullish breakout pattern.
   - **Double Bottom (W-pattern)**: Two lows at similar level. Bullish reversal.
   - **Head and Shoulders**: Three peaks, middle highest. Bearish reversal when neckline breaks.
   - **Ascending/Descending Triangle**: Flat resistance/support with rising/falling trendline.
   - **Bull/Bear Flag**: Sharp move followed by tight consolidation. Continuation pattern.
   - **Flat Base / VCP (Volatility Contraction Pattern)**: Tightening price range before breakout.
   - Analyze the recent price history data to identify which patterns may be forming.

4. **Volume Analysis**:
   - Volume should confirm price moves (up on high volume = strong).
   - Look for volume drying up during consolidation (VCP/handle formation).
   - Breakouts on above-average volume are much more reliable.

5. **RSI and Stochastic**:
   - RSI > 70 = overbought, RSI < 30 = oversold.
   - Stochastic crossovers confirm momentum shifts.

YOUR FUNDAMENTAL CHECKS:
- Earnings growth (EPS Q/Q, quarterly), revenue growth, profit margins
- P/E vs Forward P/E (expansion or contraction?)
- Analyst consensus and target prices
- Debt levels and ROE

IMPORTANT: You must ALWAYS respond in valid JSON format ONLY with this exact structure:
{
    "recommendation": "BUY" | "SELL" | "HOLD",
    "confidence": "HIGH" | "MEDIUM" | "LOW",
    "short_summary": "One-line actionable summary (max 150 chars)",
    "full_analysis": "Detailed multi-paragraph analysis. MUST include sections on: 1) Moving Average Setup (SMA 200/150/20 alignment), 2) ATR & Volatility, 3) Chart Pattern (any cup&handle, double bottom, H&S, flags, VCP etc.), 4) Volume Analysis, 5) Fundamentals, 6) News Sentiment, 7) Risk & Stop-Loss (using ATR)",
    "key_factors": ["factor1", "factor2", "factor3", "factor4", "factor5"],
    "risk_level": "HIGH" | "MEDIUM" | "LOW",
    "price_target_short": "Short-term price target or range",
    "price_target_long": "Long-term price target or range",
    "stop_loss": "Suggested stop-loss level based on ATR and support",
    "chart_pattern": "Identified chart pattern (e.g., Cup and Handle forming, Bull Flag, Flat Base, etc.) or None detected",
    "trend_status": "STAGE 1 (Basing) | STAGE 2 (Advancing) | STAGE 3 (Topping) | STAGE 4 (Declining)"
}

DISCLAIMER: Always note in the full_analysis that this is AI-generated analysis for informational purposes and not financial advice."""

HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}


def _parse_number(val):
    """Parse a string like '3886.39B' or '48.25M' or '33.49' into a float."""
    if not val or val == "-":
        return None
    val = val.replace(",", "").replace("%", "").strip()
    multiplier = 1
    if val.endswith("B"):
        multiplier = 1e9
        val = val[:-1]
    elif val.endswith("M"):
        multiplier = 1e6
        val = val[:-1]
    elif val.endswith("K"):
        multiplier = 1e3
        val = val[:-1]
    elif val.endswith("T"):
        multiplier = 1e12
        val = val[:-1]
    try:
        return float(val) * multiplier
    except ValueError:
        return None


def _compute_sma(closes, period):
    """Compute Simple Moving Average for the last N periods."""
    if len(closes) < period:
        return None
    return round(sum(closes[-period:]) / period, 2)


def _compute_atr(highs, lows, closes, period=14):
    """Compute Average True Range."""
    if len(closes) < period + 1:
        return None
    true_ranges = []
    for i in range(-period, 0):
        high = highs[i]
        low = lows[i]
        prev_close = closes[i - 1]
        if high is None or low is None or prev_close is None:
            continue
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        true_ranges.append(tr)
    if not true_ranges:
        return None
    return round(sum(true_ranges) / len(true_ranges), 2)


def _get_price_history(ticker):
    """Fetch 1 year of daily price data from Yahoo Chart API."""
    try:
        resp = httpx.get(
            "https://query1.finance.yahoo.com/v8/finance/chart/{}?range=1y&interval=1d".format(ticker),
            headers=HEADERS,
            timeout=10,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        result = data["chart"]["result"][0]
        quotes = result["indicators"]["quote"][0]
        timestamps = result.get("timestamp", [])

        # Filter out None values
        closes = [c for c in quotes.get("close", []) if c is not None]
        highs = [h for h in quotes.get("high", []) if h is not None]
        lows = [l for l in quotes.get("low", []) if l is not None]
        volumes = [v for v in quotes.get("volume", []) if v is not None]

        meta = result.get("meta", {})
        return {
            "closes": closes,
            "highs": highs,
            "lows": lows,
            "volumes": volumes,
            "timestamps": timestamps,
            "current_price": meta.get("regularMarketPrice"),
            "short_name": meta.get("shortName", ""),
        }
    except Exception as e:
        print("Yahoo chart history error for {}: {}".format(ticker, e))
        return None


def get_stock_data(ticker: str) -> dict:
    """Fetch stock data from multiple sources with SMA/ATR computation."""
    result = {
        "ticker": ticker.upper(),
        "company_name": ticker.upper(),
        "current_price": None,
    }

    # Source 1: Yahoo Chart API — price history for SMA 200/150/20 and ATR
    history = _get_price_history(ticker)
    if history and history["closes"]:
        closes = history["closes"]
        highs = history["highs"]
        lows = history["lows"]
        volumes = history["volumes"]

        result["current_price"] = history["current_price"]
        if history["short_name"]:
            result["company_name"] = history["short_name"]

        # Simple Moving Averages
        result["sma_20"] = _compute_sma(closes, 20)
        result["sma_150"] = _compute_sma(closes, 150)
        result["sma_200"] = _compute_sma(closes, 200)

        # ATR (14-day)
        result["atr_14"] = _compute_atr(highs, lows, closes, 14)

        # Moving average alignment check
        price = closes[-1] if closes else None
        sma20 = result.get("sma_20")
        sma150 = result.get("sma_150")
        sma200 = result.get("sma_200")
        if price and sma20 and sma150 and sma200:
            if price > sma20 > sma150 > sma200:
                result["ma_alignment"] = "BULLISH (Price > SMA20 > SMA150 > SMA200)"
            elif price < sma20 < sma150 < sma200:
                result["ma_alignment"] = "BEARISH (Price < SMA20 < SMA150 < SMA200)"
            elif price > sma200:
                result["ma_alignment"] = "ABOVE SMA200 but not fully aligned"
            else:
                result["ma_alignment"] = "BELOW SMA200 — caution"

        # Recent price action (last 20 days for pattern analysis)
        recent_closes = closes[-20:]
        recent_highs = highs[-20:] if len(highs) >= 20 else highs
        recent_lows = lows[-20:] if len(lows) >= 20 else lows
        recent_vols = volumes[-20:] if len(volumes) >= 20 else volumes
        result["recent_20d_prices"] = [round(c, 2) for c in recent_closes]
        result["recent_20d_highs"] = [round(h, 2) for h in recent_highs]
        result["recent_20d_lows"] = [round(l, 2) for l in recent_lows]
        result["recent_20d_volumes"] = recent_vols

        # 52-week high/low from data
        if len(closes) >= 200:
            result["52w_high_calc"] = round(max(highs[-252:] if len(highs) >= 252 else highs), 2)
            result["52w_low_calc"] = round(min(lows[-252:] if len(lows) >= 252 else lows), 2)

        # Volatility contraction check (VCP indicator)
        if len(recent_closes) >= 20:
            range_first_half = max(recent_closes[:10]) - min(recent_closes[:10])
            range_second_half = max(recent_closes[10:]) - min(recent_closes[10:])
            if range_second_half < range_first_half * 0.7:
                result["volatility_contraction"] = "YES — price range tightening (potential VCP/breakout setup)"
            else:
                result["volatility_contraction"] = "NO"

        # Volume trend
        if len(recent_vols) >= 20:
            avg_vol_first = sum(recent_vols[:10]) / 10
            avg_vol_second = sum(recent_vols[10:]) / 10
            if avg_vol_second < avg_vol_first * 0.8:
                result["volume_trend"] = "DECLINING (volume drying up — consolidation)"
            elif avg_vol_second > avg_vol_first * 1.2:
                result["volume_trend"] = "INCREASING (accumulation or distribution)"
            else:
                result["volume_trend"] = "STABLE"

    # Source 2: Finviz — comprehensive fundamentals
    try:
        resp = httpx.get(
            "https://finviz.com/quote.ashx?t={}".format(ticker),
            headers=HEADERS,
            timeout=10,
        )
        soup = BeautifulSoup(resp.text, "html.parser")

        title_tag = soup.find("h2", class_="quote-header_ticker-wrapper_company")
        if title_tag:
            result["company_name"] = title_tag.text.strip()

        table = soup.find("table", class_="snapshot-table2")
        if table:
            fv = {}
            for row in table.find_all("tr"):
                cells = row.find_all("td")
                for i in range(0, len(cells) - 1, 2):
                    fv[cells[i].text.strip()] = cells[i + 1].text.strip()

            if result["current_price"] is None:
                result["current_price"] = _parse_number(fv.get("Price"))
            result["market_cap"] = fv.get("Market Cap", "")
            result["pe_ratio"] = _parse_number(fv.get("P/E"))
            result["forward_pe"] = _parse_number(fv.get("Forward P/E"))
            result["eps"] = _parse_number(fv.get("EPS (ttm)"))
            result["dividend_yield"] = fv.get("Dividend %", "")
            result["52_week_high"] = fv.get("52W High", "")
            result["52_week_low"] = fv.get("52W Low", "")
            result["beta"] = _parse_number(fv.get("Beta"))
            result["volume"] = fv.get("Volume", "")
            result["avg_volume"] = fv.get("Avg Volume", "")
            result["profit_margin"] = fv.get("Profit Margin", "")
            result["debt_to_equity"] = _parse_number(fv.get("Debt/Eq"))
            result["roe"] = fv.get("ROE", "")
            result["roi"] = fv.get("ROI", "")
            result["analyst_target"] = _parse_number(fv.get("Target Price"))
            result["analyst_recommendation"] = fv.get("Recom", "")
            result["sector"] = fv.get("Sector", "")
            result["industry"] = fv.get("Industry", "")
            result["earnings_date"] = fv.get("Earnings", "")
            result["sales_growth"] = fv.get("Sales Q/Q", "")
            result["eps_growth"] = fv.get("EPS Q/Q", "")
            result["atr_finviz"] = fv.get("ATR", "")
    except Exception as e:
        print("Finviz error for {}: {}".format(ticker, e))

    # Source 3: Alpha Vantage — deep fundamentals + technical indicators
    if ALPHA_VANTAGE_KEY:
        av_base = "https://www.alphavantage.co/query?apikey={}&symbol={}".format(ALPHA_VANTAGE_KEY, ticker)

        def _av_get(function, extra="&interval=daily&time_period=14&series_type=close"):
            try:
                resp = httpx.get("{}&function={}{}".format(av_base, function, extra), timeout=10)
                data = resp.json()
                if "Information" in data or "Error Message" in data:
                    return None
                return data
            except Exception:
                return None

        # Company Overview
        overview = _av_get("OVERVIEW", "")
        if overview and "Name" in overview:
            result["operating_margin"] = overview.get("OperatingMarginTTM", "")
            result["return_on_equity"] = overview.get("ReturnOnEquityTTM", "")
            result["revenue_per_share"] = overview.get("RevenuePerShareTTM", "")
            result["quarterly_earnings_growth"] = overview.get("QuarterlyEarningsGrowthYOY", "")
            result["quarterly_revenue_growth"] = overview.get("QuarterlyRevenueGrowthYOY", "")
            result["book_value"] = overview.get("BookValue", "")
            result["price_to_book"] = overview.get("PriceToBookRatio", "")
            strong_buy = overview.get("AnalystRatingStrongBuy", "0")
            buy = overview.get("AnalystRatingBuy", "0")
            hold = overview.get("AnalystRatingHold", "0")
            sell = overview.get("AnalystRatingSell", "0")
            strong_sell = overview.get("AnalystRatingStrongSell", "0")
            result["analyst_ratings"] = "Strong Buy: {}, Buy: {}, Hold: {}, Sell: {}, Strong Sell: {}".format(
                strong_buy, buy, hold, sell, strong_sell
            )

        # RSI (14-day)
        rsi_data = _av_get("RSI")
        if rsi_data:
            rsi_values = rsi_data.get("Technical Analysis: RSI", {})
            if rsi_values:
                latest = list(rsi_values.keys())[0]
                result["rsi_14"] = round(float(rsi_values[latest]["RSI"]), 2)

        # Stochastic
        stoch_data = _av_get("STOCH", "&interval=daily")
        if stoch_data:
            stoch_values = stoch_data.get("Technical Analysis: STOCH", {})
            if stoch_values:
                latest = list(stoch_values.keys())[0]
                entry = stoch_values[latest]
                result["stoch_k"] = round(float(entry["SlowK"]), 2)
                result["stoch_d"] = round(float(entry["SlowD"]), 2)

        # ADX (14-day)
        adx_data = _av_get("ADX", "&interval=daily&time_period=14")
        if adx_data:
            adx_values = adx_data.get("Technical Analysis: ADX", {})
            if adx_values:
                latest = list(adx_values.keys())[0]
                result["adx_14"] = round(float(adx_values[latest]["ADX"]), 2)

    return result


async def analyze_stock(ticker: str) -> dict:
    """Full AI-powered stock analysis combining news + stock data + Gemini AI.
    Returns cached result if the same ticker was analyzed within the last hour."""
    # Check for recent cached analysis (within last hour)
    cached = get_recent_analysis(ticker, max_age_minutes=60)
    if cached:
        news_data = []
        try:
            news_data = json.loads(cached.news_data) if cached.news_data else []
        except json.JSONDecodeError:
            pass
        stock_data_cached = {}
        try:
            stock_data_cached = json.loads(cached.stock_data) if cached.stock_data else {}
        except json.JSONDecodeError:
            pass

        # Reconstruct full analysis from stored JSON, fall back to basic fields
        analysis = None
        if cached.analysis_json:
            try:
                analysis = json.loads(cached.analysis_json)
            except json.JSONDecodeError:
                pass
        if not analysis:
            analysis = {
                "recommendation": cached.recommendation,
                "confidence": cached.confidence,
                "short_summary": cached.short_summary,
                "full_analysis": cached.full_analysis or "",
                "key_factors": [],
                "risk_level": "",
                "price_target_short": "",
                "price_target_long": "",
                "stop_loss": "",
                "chart_pattern": "",
                "trend_status": "",
            }

        return {
            "ticker": cached.ticker,
            "company_name": cached.company_name,
            "current_price": cached.current_price,
            "stock_data": stock_data_cached,
            "news_articles": news_data,
            "analysis": analysis,
            "cached": True,
            "cached_id": cached.id,
        }

    stock_data = get_stock_data(ticker)
    company_name = stock_data.get("company_name", ticker)
    news_articles = await fetch_all_news(ticker, company_name)

    # Build the analysis prompt
    news_text = ""
    for i, article in enumerate(news_articles[:15], 1):
        news_text += "\n{}. [{}] {}".format(i, article["source"], article["title"])
        if article.get("summary"):
            news_text += "\n   {}".format(article["summary"][:200])
        if article.get("published"):
            news_text += "\n   Published: {}".format(article["published"])

    stock_info = json.dumps(
        {k: v for k, v in stock_data.items() if v is not None and v != ""},
        indent=2,
        default=str,
    )

    user_prompt = """{system}

---

Analyze the stock {ticker} ({company}) and provide your expert recommendation.

## STOCK DATA & TECHNICAL INDICATORS
{stock}

## RECENT NEWS ({count} articles found)
{news}

IMPORTANT INSTRUCTIONS:
1. Start with the Moving Average setup: Is price above/below SMA 200/150/20? What is the alignment?
2. Analyze ATR for volatility and suggest a stop-loss level (e.g., 2x ATR below current price or key support).
3. Look at the recent_20d_prices, recent_20d_highs, recent_20d_lows data and identify any chart patterns
   (cup and handle, double bottom, head and shoulders, bull flag, flat base, VCP, ascending triangle, etc.).
4. Check volume_trend and volatility_contraction for breakout potential.
5. Combine with fundamentals and news for your final recommendation.
Respond ONLY with valid JSON.""".format(
        system=SYSTEM_PROMPT,
        ticker=ticker.upper(),
        company=company_name,
        stock=stock_info,
        count=len(news_articles),
        news=news_text if news_text else "No recent news articles found.",
    )

    # Call Gemini AI
    response_text = ""
    try:
        response = model.generate_content(
            user_prompt,
            generation_config=genai.types.GenerationConfig(
                response_mime_type="application/json",
                max_output_tokens=8192,
                temperature=0.7,
            ),
        )
        response_text = response.text
        analysis = json.loads(response_text)
    except json.JSONDecodeError:
        analysis = {
            "recommendation": "HOLD",
            "confidence": "LOW",
            "short_summary": "Analysis for {} completed but response parsing failed. Manual review recommended.".format(ticker.upper()),
            "full_analysis": response_text or "Analysis failed.",
            "key_factors": [],
            "risk_level": "MEDIUM",
            "price_target_short": "N/A",
            "price_target_long": "N/A",
            "stop_loss": "N/A",
            "chart_pattern": "N/A",
            "trend_status": "N/A",
        }
    except Exception as e:
        analysis = {
            "recommendation": "HOLD",
            "confidence": "LOW",
            "short_summary": "Error analyzing {}: {}".format(ticker.upper(), str(e)[:100]),
            "full_analysis": "An error occurred during analysis: {}".format(str(e)),
            "key_factors": [],
            "risk_level": "MEDIUM",
            "price_target_short": "N/A",
            "price_target_long": "N/A",
            "stop_loss": "N/A",
            "chart_pattern": "N/A",
            "trend_status": "N/A",
        }

    return {
        "ticker": ticker.upper(),
        "company_name": company_name,
        "current_price": stock_data.get("current_price"),
        "stock_data": stock_data,
        "news_articles": news_articles,
        "analysis": analysis,
    }
