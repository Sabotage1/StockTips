import json
import httpx
from bs4 import BeautifulSoup
import google.generativeai as genai
from news_fetcher import fetch_all_news
from config import GEMINI_API_KEY, ALPHA_VANTAGE_KEY
from database import get_recent_analysis
from api_tracker import track

genai.configure(api_key=GEMINI_API_KEY)

# Model tiering for analysis: Pro first (best quality), fall through on quota errors
_GEMINI_MODELS = [
    ("gemini_pro", genai.GenerativeModel("gemini-2.5-pro")),
    ("gemini_flash", genai.GenerativeModel("gemini-2.5-flash")),
    ("gemini_flash_lite", genai.GenerativeModel("gemini-2.5-flash-lite")),
]

# Models for news digest: Flash first (smarter), Flash-Lite as fallback (skip Pro)
_GEMINI_DIGEST_MODELS = [
    ("gemini_flash", genai.GenerativeModel("gemini-2.5-flash")),
    ("gemini_flash_lite", genai.GenerativeModel("gemini-2.5-flash-lite")),
]

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

8. **Pre-Market / After-Hours Data** (when available):
   - Factor in premarket or after-hours price moves as early signals of sentiment shifts.
   - A significant pre-market gap up/down may indicate news-driven momentum.
   - Use extended-hours prices to refine entry/exit levels and adjust recommendations accordingly.

6. **Support & Resistance Analysis (CRITICAL)**:
   - Identify key SUPPORT zones: prior swing lows, high-volume areas, SMA levels acting as support.
   - Identify key RESISTANCE zones: prior swing highs, historical price ceilings, trendline resistance.
   - Determine if price is near support (buying opportunity) or near resistance (breakout or rejection risk).
   - Use the computed support/resistance levels provided in the data as starting points but refine them.
   - A breakout above resistance with volume = strong BUY signal.
   - A breakdown below support = SELL signal.

7. **Breakout & Expected Move Analysis**:
   - If a pattern is forming (VCP, cup & handle, triangle, flag), identify the BREAKOUT LEVEL.
   - Calculate the expected % gain from breakout level to measured move target.
   - Calculate the expected % loss if the trade fails (breakout level to stop-loss).
   - Provide a risk/reward ratio.
   - Estimate a timeframe for when the breakout or breakdown may occur based on the pattern.

YOUR FUNDAMENTAL CHECKS:
- Earnings growth (EPS Q/Q, quarterly), revenue growth, profit margins
- P/E vs Forward P/E (expansion or contraction?)
- Analyst consensus and target prices
- Debt levels and ROE

IMPORTANT: You must ALWAYS respond in valid JSON format ONLY with this exact structure:
{
    "recommendation": "BUY at $XXX.XX (stop $XXX.XX)" | "BUY if breaks $XXX.XX (stop $XXX.XX)" | "SELL at $XXX.XX" | "SELL if drops below $XXX.XX" | "HOLD",
    "confidence": "HIGH" | "MEDIUM" | "LOW",
    "short_summary": "One-line actionable summary (max 150 chars)",
    "full_analysis": "Detailed multi-paragraph analysis. MUST include sections on: 1) Moving Average Setup (SMA 200/150/20 alignment), 2) ATR & Volatility, 3) Chart Pattern (any cup&handle, double bottom, H&S, flags, VCP etc.), 4) Support & Resistance Zones, 5) Breakout/Breakdown Scenarios, 6) Volume Analysis, 7) Fundamentals, 8) News Sentiment, 9) Risk & Stop-Loss (using ATR)",
    "key_factors": ["factor1", "factor2", "factor3", "factor4", "factor5"],
    "risk_level": "HIGH" | "MEDIUM" | "LOW",
    "price_target_short": "$XX.XX (short-term target, 1-4 weeks)",
    "price_target_long": "$XX.XX (long-term target, 2-6 months)",
    "stop_loss": "$XX.XX (based on ATR and nearest support)",
    "chart_pattern": "Identified chart pattern (e.g., Cup and Handle forming, Bull Flag, Flat Base, etc.) or None detected",
    "trend_status": "STAGE 1 (Basing) | STAGE 2 (Advancing) | STAGE 3 (Topping) | STAGE 4 (Declining)",
    "support_levels": ["$XX.XX - $XX.XX (description)", "$XX.XX (description)"],
    "resistance_levels": ["$XX.XX - $XX.XX (description)", "$XX.XX (description)"],
    "breakout_level": "$XX.XX (the key price level that triggers a breakout or breakdown)",
    "breakout_direction": "BULLISH | BEARISH | NEUTRAL",
    "expected_gain_pct": "XX.X% (potential upside from current price to target if breakout succeeds)",
    "expected_loss_pct": "XX.X% (potential downside from current price to stop-loss if trade fails)",
    "risk_reward_ratio": "1:X.X (risk to reward ratio)",
    "action_trigger": "Specific condition that triggers the trade (e.g., 'BUY on break above $16.10 with volume > 2M' or 'SELL if price closes below $14.50')",
    "breakout_timeframe": "Expected timeframe for the move (e.g., '1-2 weeks', 'Within 5 trading days', 'After earnings on Mar 18')"
}

CRITICAL RULES FOR RECOMMENDATION:
- The "recommendation" field MUST include a specific dollar price for BUY and SELL. Examples:
  - "BUY at $298.50 (stop $280.00)" — buy now at market price with stop loss
  - "BUY if breaks $300.00 (stop $288.00)" — conditional buy on breakout with stop loss
  - "SELL at $285.00" — sell now at market price
  - "SELL if drops below $275.00" — conditional sell on breakdown below a level
  - "HOLD" — no price needed for HOLD
- NEVER use bare "BUY" or "SELL" without a price. Always specify the dollar amount.
- Every BUY recommendation MUST include a stop loss in parentheses. This is non-negotiable.
  The stop loss should be based on ATR, nearest support, or the pattern's invalidation level.

CRITICAL STOP-LOSS RULES FOR BREAKOUT TRADES:
- When recommending a BUY on a breakout (e.g., "BUY if breaks $XX.XX"), the stop-loss MUST be placed
  just below the breakout level (1-3% below, or 0.5-1x ATR below the breakout price).
  This protects against false breakouts. Do NOT place the stop at a distant support that is 8-10% below
  the breakout — that creates an unacceptable risk/reward ratio.
- Example: If breakout level is $50.00, stop should be around $48.50-$49.00, NOT at $45.00 support.
- The logic: if the stock breaks out and immediately falls back below the breakout level, the breakout
  has failed and you should exit quickly with a small loss rather than waiting for a distant support.
- For non-breakout BUY recommendations (e.g., buying at support), the stop can be placed below
  the support level as usual.

POSITION-AWARE ANALYSIS RULES:
- If the user has NOT provided a purchase/buy-in price, assume they do NOT own the stock.
  In this case:
  - Do NOT recommend buying at the current price if the stock has already broken out and run up.
  - Instead, recommend waiting for a pullback to a specific support level or moving average.
  - Identify the NEXT key support zone where they should look to enter (e.g., "Wait for pullback to $XX.XX area").
  - OR identify the NEXT breakout level to watch if the stock is still consolidating.
  - In the full_analysis, include a section called "Entry Strategy for New Positions" that explains
    where and when to enter if not already in the stock.
- If the user HAS provided a purchase/buy-in price, they ARE in the stock.
  In this case:
  - Highlight the NEXT support level to watch (where to tighten stops or add).
  - Highlight the NEXT price target/goal for the stock.
  - Frame the analysis around managing their existing position.
  - In the full_analysis, include a section called "Position Management" that explains
    the next support, next target, and what to watch for.

CRITICAL RULES FOR THE NEW FIELDS:
- support_levels and resistance_levels MUST be arrays of strings, each with a dollar price and brief description.
- breakout_level MUST be a specific dollar price, not a range.
- expected_gain_pct and expected_loss_pct MUST be calculated from current price.
- action_trigger MUST be a specific, actionable statement with exact price levels and conditions.
- breakout_timeframe MUST give a realistic estimate based on the pattern and catalysts (e.g., earnings date).

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


def _find_support_resistance(highs, lows, closes, current_price):
    """Find key support and resistance levels from historical price data.

    Uses swing highs/lows with clustering to identify zones.
    """
    if len(closes) < 20 or current_price is None:
        return [], []

    # Find swing highs and swing lows (local extremes using 5-bar lookback/forward)
    swing_highs = []
    swing_lows = []
    window = 5

    for i in range(window, len(closes) - window):
        # Swing high: higher than surrounding bars
        if highs[i] == max(highs[i - window:i + window + 1]):
            swing_highs.append(round(highs[i], 2))
        # Swing low: lower than surrounding bars
        if lows[i] == min(lows[i - window:i + window + 1]):
            swing_lows.append(round(lows[i], 2))

    # Cluster nearby levels (within 2% of each other)
    def cluster_levels(levels, threshold_pct=0.02):
        if not levels:
            return []
        levels = sorted(levels)
        clusters = []
        current_cluster = [levels[0]]
        for i in range(1, len(levels)):
            if abs(levels[i] - current_cluster[0]) / current_cluster[0] <= threshold_pct:
                current_cluster.append(levels[i])
            else:
                avg = round(sum(current_cluster) / len(current_cluster), 2)
                clusters.append((avg, len(current_cluster)))
                current_cluster = [levels[i]]
        if current_cluster:
            avg = round(sum(current_cluster) / len(current_cluster), 2)
            clusters.append((avg, len(current_cluster)))
        # Sort by number of touches (strength), then by proximity to current price
        clusters.sort(key=lambda x: (-x[1], abs(x[0] - current_price)))
        return clusters

    high_clusters = cluster_levels(swing_highs)
    low_clusters = cluster_levels(swing_lows)

    # Separate into support (below price) and resistance (above price)
    supports = []
    resistances = []

    for level, touches in low_clusters:
        if level < current_price * 1.02:  # Allow slight overlap
            supports.append({"price": level, "touches": touches})
    for level, touches in high_clusters:
        if level > current_price * 0.98:  # Allow slight overlap
            resistances.append({"price": level, "touches": touches})

    # Sort supports descending (nearest first), resistances ascending (nearest first)
    supports.sort(key=lambda x: -x["price"])
    resistances.sort(key=lambda x: x["price"])

    return supports[:4], resistances[:4]


def _get_price_history(ticker):
    """Fetch 1 year of daily price data from Yahoo Chart API."""
    try:
        resp = httpx.get(
            "https://query1.finance.yahoo.com/v8/finance/chart/{}?range=1y&interval=1d".format(ticker),
            headers=HEADERS,
            timeout=10,
        )
        track("yahoo_chart")
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
        pre_post = {}
        if meta.get("preMarketPrice"):
            pre_post["pre_market_price"] = meta["preMarketPrice"]
            if meta.get("preMarketChange") is not None:
                pre_post["pre_market_change"] = round(meta["preMarketChange"], 2)
            if meta.get("preMarketChangePercent") is not None:
                pre_post["pre_market_change_pct"] = round(meta["preMarketChangePercent"], 2)
        if meta.get("postMarketPrice"):
            pre_post["post_market_price"] = meta["postMarketPrice"]
            if meta.get("postMarketChange") is not None:
                pre_post["post_market_change"] = round(meta["postMarketChange"], 2)
            if meta.get("postMarketChangePercent") is not None:
                pre_post["post_market_change_pct"] = round(meta["postMarketChangePercent"], 2)
        return {
            "closes": closes,
            "highs": highs,
            "lows": lows,
            "volumes": volumes,
            "timestamps": timestamps,
            "current_price": meta.get("regularMarketPrice"),
            "short_name": meta.get("shortName", ""),
            "pre_post": pre_post,
        }
    except Exception as e:
        print("Yahoo chart history error for {}: {}".format(ticker, e))
        return None


def get_quick_signals(ticker, purchase_price, stop_loss=None):
    """Lightweight signals using only Yahoo Chart API (no Finviz/Alpha Vantage/Gemini).

    Returns dict with current_price, day_change, SMAs, ATR, volume_ratio, and
    color-coded signal alerts (green/yellow/red/blue).
    """
    history = _get_price_history(ticker)
    if not history or not history["closes"] or len(history["closes"]) < 2:
        return {"ticker": ticker.upper(), "error": "No price data available"}

    closes = history["closes"]
    highs = history["highs"]
    lows = history["lows"]
    volumes = history["volumes"]

    current_price = history["current_price"] or closes[-1]
    previous_close = closes[-2] if len(closes) >= 2 else current_price
    day_change = round(current_price - previous_close, 2)
    day_change_pct = round((day_change / previous_close) * 100, 2) if previous_close else 0

    sma_20 = _compute_sma(closes, 20)
    sma_50 = _compute_sma(closes, 50)
    sma_200 = _compute_sma(closes, 200)
    atr_14 = _compute_atr(highs, lows, closes, 14)

    # Volume ratio (today vs 10-day avg)
    volume_ratio = None
    if len(volumes) >= 11 and volumes[-1]:
        avg_10 = sum(volumes[-11:-1]) / 10 if sum(volumes[-11:-1]) > 0 else 1
        volume_ratio = round(volumes[-1] / avg_10, 2)

    signals = []

    # --- Green signals (bullish) ---
    if sma_20 and sma_50 and sma_200:
        if current_price > sma_20 and current_price > sma_50 and current_price > sma_200:
            signals.append({"color": "green", "text": "Above all SMAs - strong trend"})
    if sma_200 and current_price > sma_200:
        if sma_20 and current_price > sma_20:
            pass  # already covered
        elif sma_200:
            signals.append({"color": "green", "text": "Above SMA 200 - bullish regime"})
    if purchase_price and current_price > purchase_price * 1.15:
        signals.append({"color": "green", "text": "Consider taking partial profits (+{:.1f}%)".format(
            (current_price - purchase_price) / purchase_price * 100)})

    # --- Yellow signals (caution) ---
    if sma_20 and current_price < sma_20:
        signals.append({"color": "yellow", "text": "Price below SMA 20 - weakening"})
    elif sma_20 and current_price < sma_20 * 1.02:
        signals.append({"color": "yellow", "text": "Testing SMA 20 support"})
    if stop_loss and current_price < stop_loss * 1.05 and current_price > stop_loss:
        signals.append({"color": "yellow", "text": "Within 5% of stop-loss"})

    # --- Red signals (danger) ---
    if stop_loss and current_price <= stop_loss:
        signals.append({"color": "red", "text": "BELOW stop-loss ${:.2f}".format(stop_loss)})
    elif stop_loss and current_price < stop_loss * 1.02:
        signals.append({"color": "red", "text": "Approaching stop-loss"})
    if sma_200 and current_price < sma_200:
        signals.append({"color": "red", "text": "Below SMA 200 - bearish"})
    if purchase_price and current_price < purchase_price * 0.85:
        signals.append({"color": "red", "text": "Significant loss - review position ({:.1f}%)".format(
            (current_price - purchase_price) / purchase_price * 100)})

    # --- Blue signals (informational) ---
    if volume_ratio and volume_ratio >= 2.0:
        signals.append({"color": "blue", "text": "Volume spike detected ({:.1f}x avg)".format(volume_ratio)})
    elif volume_ratio and volume_ratio >= 1.5:
        signals.append({"color": "blue", "text": "Above-average volume ({:.1f}x)".format(volume_ratio)})

    # Extra live data from history (no new API calls)
    company_name = history.get("short_name", "")
    day_high = round(highs[-1], 2) if highs else None
    day_low = round(lows[-1], 2) if lows else None
    open_price = round(closes[-2], 2) if len(closes) >= 2 else None  # proxy: prev close
    week_52_high = round(max(highs), 2) if highs else None
    week_52_low = round(min(lows), 2) if lows else None
    pre_post = history.get("pre_post", {})

    return {
        "ticker": ticker.upper(),
        "company_name": company_name,
        "current_price": current_price,
        "previous_close": previous_close,
        "day_change": day_change,
        "day_change_pct": day_change_pct,
        "day_high": day_high,
        "day_low": day_low,
        "open_price": open_price,
        "week_52_high": week_52_high,
        "week_52_low": week_52_low,
        "sma_20": sma_20,
        "sma_50": sma_50,
        "sma_200": sma_200,
        "atr_14": atr_14,
        "volume_ratio": volume_ratio,
        "pre_post": pre_post,
        "signals": signals,
    }


def get_quick_signals_batch(items):
    """Fetch quick signals for a list of portfolio items.

    items: list of dicts with 'ticker', 'purchase_price', and optional 'stop_loss'.
    Returns dict keyed by ticker.
    """
    results = {}
    for item in items:
        ticker = item["ticker"]
        results[ticker] = get_quick_signals(
            ticker,
            item["purchase_price"],
            stop_loss=item.get("stop_loss"),
        )
    return results


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

        # Pre-market / After-hours data
        for k, v in history.get("pre_post", {}).items():
            result[k] = v

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

        # Extended price action (last 60 days for better support/resistance analysis)
        ext_closes = closes[-60:] if len(closes) >= 60 else closes
        ext_highs = highs[-60:] if len(highs) >= 60 else highs
        ext_lows = lows[-60:] if len(lows) >= 60 else lows
        result["recent_60d_prices"] = [round(c, 2) for c in ext_closes]
        result["recent_60d_highs"] = [round(h, 2) for h in ext_highs]
        result["recent_60d_lows"] = [round(l, 2) for l in ext_lows]

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

        # Support & Resistance levels
        price = result.get("current_price") or (closes[-1] if closes else None)
        if price:
            supports, resistances = _find_support_resistance(highs, lows, closes, price)
            if supports:
                result["computed_supports"] = [
                    "${:.2f} ({} touches)".format(s["price"], s["touches"]) for s in supports
                ]
            if resistances:
                result["computed_resistances"] = [
                    "${:.2f} ({} touches)".format(r["price"], r["touches"]) for r in resistances
                ]

            # Nearest support & resistance for quick reference
            if supports:
                result["nearest_support"] = supports[0]["price"]
            if resistances:
                result["nearest_resistance"] = resistances[0]["price"]

            # Distance to support/resistance as %
            if supports:
                dist_support = round((price - supports[0]["price"]) / price * 100, 1)
                result["distance_to_support_pct"] = "{}%".format(dist_support)
            if resistances:
                dist_resistance = round((resistances[0]["price"] - price) / price * 100, 1)
                result["distance_to_resistance_pct"] = "{}%".format(dist_resistance)

    # Source 2: Finviz — comprehensive fundamentals
    try:
        resp = httpx.get(
            "https://finviz.com/quote.ashx?t={}".format(ticker),
            headers=HEADERS,
            timeout=10,
        )
        track("finviz")
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
                track("alpha_vantage")
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


def generate_news_digest(news_articles):
    """Summarize news articles into sentiment + bullet points using Flash-Lite.

    Returns dict with 'sentiment' and 'summary_bullets', or None on failure.
    Fallback chain: Flash-Lite -> Flash (skip Pro to preserve quota for analysis).
    """
    if not news_articles:
        return None

    news_text = ""
    for i, article in enumerate(news_articles[:15], 1):
        news_text += "\n{}. [{}] {}".format(i, article.get("source", ""), article.get("title", ""))
        if article.get("summary"):
            news_text += "\n   {}".format(article["summary"][:200])

    prompt = """Summarize the following news articles into 3-5 concise bullet points.
Then determine the overall sentiment: BULLISH, NEUTRAL, or BEARISH.

NEWS ARTICLES:
{}

Respond ONLY with valid JSON in this exact format:
{{
    "sentiment": "BULLISH" | "NEUTRAL" | "BEARISH",
    "summary_bullets": ["bullet 1", "bullet 2", "bullet 3"]
}}""".format(news_text)

    digest_config = genai.types.GenerationConfig(
        response_mime_type="application/json",
        max_output_tokens=1024,
        temperature=0.4,
    )

    for model_key, model_instance in _GEMINI_DIGEST_MODELS:
        try:
            response = model_instance.generate_content(prompt, generation_config=digest_config)
            track(model_key)
            result = json.loads(response.text)
            # Validate structure
            if "sentiment" in result and "summary_bullets" in result:
                return result
            return None
        except json.JSONDecodeError:
            continue
        except Exception as e:
            err_str = str(e).lower()
            quota_keywords = ["resource exhausted", "quota", "rate limit", "429",
                              "too many requests", "limit exceeded", "resourceexhausted"]
            if any(kw in err_str for kw in quota_keywords):
                continue
            return None
    return None


async def analyze_stock(ticker: str, purchase_price=None) -> dict:
    """Full AI-powered stock analysis combining news + stock data + Gemini AI.
    Returns cached result if the same ticker was analyzed within the last hour.
    If purchase_price is provided, skips cache and tailors advice to that entry price."""
    # Skip cache when a purchase price is provided — analysis must be personalized
    if purchase_price is None:
        cached = get_recent_analysis(ticker, max_age_minutes=60)
    else:
        cached = None
    # Skip cached error results — re-analyze instead
    _error_markers = ["parsing failed", "error analyzing", "quota exhausted",
                      "an error occurred", "analysis failed", "failed across all models"]
    if cached and cached.short_summary:
        _cached_lower = cached.short_summary.lower()
        if cached.confidence == "LOW" and any(m in _cached_lower for m in _error_markers):
            cached = None

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
                "support_levels": [],
                "resistance_levels": [],
                "breakout_level": "",
                "breakout_direction": "",
                "expected_gain_pct": "",
                "expected_loss_pct": "",
                "risk_reward_ratio": "",
                "action_trigger": "",
                "breakout_timeframe": "",
            }

        return {
            "ticker": cached.ticker,
            "company_name": cached.company_name,
            "current_price": cached.current_price,
            "stock_data": stock_data_cached,
            "news_articles": news_data,
            "analysis": analysis,
            "news_digest": analysis.get("news_digest") if analysis else None,
            "cached": True,
            "cached_id": cached.id,
        }

    import asyncio as _asyncio
    _loop = _asyncio.get_event_loop()
    stock_data = await _loop.run_in_executor(None, get_stock_data, ticker)
    company_name = stock_data.get("company_name", ticker)
    news_articles = await fetch_all_news(ticker, company_name)

    # Generate AI news digest (non-critical — analysis works without it)
    news_digest = await _loop.run_in_executor(None, generate_news_digest, news_articles)

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

    purchase_section = ""
    if purchase_price is not None:
        purchase_section = """
## PORTFOLIO CONTEXT
The user ALREADY OWNS this stock. They bought at ${:.2f}.
Your analysis MUST be tailored to this position:
- Calculate their current P&L (current price vs ${:.2f} entry).
- Recommend whether to HOLD, SELL (take profit / cut loss), or ADD MORE at a specific price.
- If in profit: identify where to take partial/full profits and where to trail the stop loss.
- If at a loss: assess whether to hold for recovery, average down, or cut the loss.
- The stop loss in your recommendation must protect their entry price or limit further downside.
- Frame all targets and risk/reward relative to their ${:.2f} entry, not just the current price.
- Include a "Position Management" section in full_analysis highlighting:
  * The NEXT key support level to watch (where to tighten stop or add to position).
  * The NEXT price target/goal for this stock.
  * What signals to watch for that would change the outlook.
""".format(purchase_price, purchase_price, purchase_price)
    else:
        purchase_section = """
## PORTFOLIO CONTEXT
The user does NOT currently own this stock. They are evaluating whether to enter a position.
Your analysis MUST account for this:
- If the stock has already broken out and run up significantly, do NOT recommend chasing it.
  Instead, recommend waiting for a pullback to a specific support/moving average level.
- Identify the BEST entry point: either a pullback to support or a fresh breakout level to watch.
- Include an "Entry Strategy for New Positions" section in full_analysis that explains:
  * Where to buy: the ideal entry price or zone (pullback level, support, or next breakout).
  * When to buy: what conditions must be met (e.g., "on a pullback to SMA20 around $XX" or "on break above $XX with volume").
  * Where to set stop-loss relative to the recommended entry (NOT a distant support).
- If recommending a breakout trade, the stop-loss MUST be just below the breakout level (1-3% below),
  not at a far-away support that would result in a large loss on a false breakout.
"""

    user_prompt = """{system}

---

Analyze the stock {ticker} ({company}) and provide your expert recommendation.
{purchase}
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
5. Use the computed_supports and computed_resistances data to identify key support/resistance zones.
   Refine these levels and express them as price ranges where appropriate.
6. Identify the key BREAKOUT or BREAKDOWN level and calculate the expected % gain and % loss.
7. Provide a specific ACTION TRIGGER — the exact price and condition to act on (e.g., "BUY on close above $16.10 with volume > 1.5x average").
8. Estimate when the expected move will happen based on pattern maturity, earnings date, and catalysts.
9. Combine with fundamentals and news for your final recommendation.
Respond ONLY with valid JSON.""".format(
        system=SYSTEM_PROMPT,
        ticker=ticker.upper(),
        company=company_name,
        purchase=purchase_section,
        stock=stock_info,
        count=len(news_articles),
        news=news_text if news_text else "No recent news articles found.",
    )

    # Call Gemini AI
    response_text = ""
    _FALLBACK_FIELDS = {
        "key_factors": [],
        "risk_level": "MEDIUM",
        "price_target_short": "N/A",
        "price_target_long": "N/A",
        "stop_loss": "N/A",
        "chart_pattern": "N/A",
        "trend_status": "N/A",
        "support_levels": [],
        "resistance_levels": [],
        "breakout_level": "N/A",
        "breakout_direction": "NEUTRAL",
        "expected_gain_pct": "N/A",
        "expected_loss_pct": "N/A",
        "risk_reward_ratio": "N/A",
        "action_trigger": "N/A",
        "breakout_timeframe": "N/A",
    }

    def _make_error_analysis(summary, detail):
        a = {"recommendation": "HOLD", "confidence": "LOW",
             "short_summary": summary, "full_analysis": detail}
        a.update(_FALLBACK_FIELDS)
        return a

    def _detect_quota_error(err_str):
        """Check if an error string indicates Gemini API quota exhaustion."""
        quota_keywords = ["resource exhausted", "quota", "rate limit", "429",
                          "too many requests", "limit exceeded", "resourceexhausted"]
        lower = err_str.lower()
        for kw in quota_keywords:
            if kw in lower:
                return True
        return False

    def _quota_error_message():
        """Build a user-friendly quota error message with reset time."""
        import datetime as _dt
        # Gemini free tier resets daily at midnight Pacific Time (UTC-8 / UTC-7 DST)
        now_utc = _dt.datetime.utcnow()
        # Approximate Pacific midnight as 08:00 UTC (PST) or 07:00 UTC (PDT)
        pacific_offset = 8  # PST; close enough for estimate
        next_reset_utc = now_utc.replace(hour=pacific_offset, minute=0, second=0, microsecond=0)
        if next_reset_utc <= now_utc:
            next_reset_utc += _dt.timedelta(days=1)
        hours_left = (next_reset_utc - now_utc).total_seconds() / 3600
        reset_str = "{:.1f} hours (resets at ~midnight Pacific Time)".format(hours_left)
        return (
            "Gemini AI API free tier quota exhausted. Daily limit resets in approximately {}.".format(reset_str),
            "The Gemini API free tier has a daily request/token limit. "
            "Your quota has been exceeded for today. "
            "The limit resets at approximately midnight Pacific Time (~{} hours from now). "
            "You can try again after the reset, or upgrade to a paid Gemini API plan for higher limits.".format(
                "{:.1f}".format(hours_left)
            ),
        )

    gen_config = genai.types.GenerationConfig(
        response_mime_type="application/json",
        max_output_tokens=16384,
        temperature=0.7,
    )

    def _extract_json(text):
        """Try multiple strategies to extract valid JSON from response text."""
        if not text:
            return None
        # Strategy 1: parse as-is
        try:
            return json.loads(text)
        except (json.JSONDecodeError, ValueError):
            pass
        cleaned = text.strip()
        # Strategy 2: strip markdown code fences
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            try:
                return json.loads(cleaned)
            except (json.JSONDecodeError, ValueError):
                pass
        # Strategy 3: find outermost { ... } and parse that
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except (json.JSONDecodeError, ValueError):
                pass
        return None

    def _run_gemini_models():
        """Run Gemini model fallback chain (blocking). Called via executor."""
        _analysis = None
        _last_response_text = ""
        _last_error = ""
        for model_key, model_instance in _GEMINI_MODELS:
            try:
                response = model_instance.generate_content(user_prompt, generation_config=gen_config)
                track(model_key)
                resp_text = response.text
                if resp_text:
                    _last_response_text = resp_text
                parsed = _extract_json(resp_text)
                if parsed is not None:
                    _analysis = parsed
                    break  # success
                print("Gemini {} returned unparseable response for {}: {}".format(
                    model_key, ticker.upper(), (resp_text or "")[:200]))
                _last_error = "JSON parse failed"
                continue
            except Exception as e:
                err_str = str(e)
                print("Gemini {} error for {}: {}".format(model_key, ticker.upper(), err_str[:200]))
                _last_error = err_str
                continue
        return _analysis, _last_response_text, _last_error

    analysis, last_response_text, last_error = await _loop.run_in_executor(None, _run_gemini_models)

    # All models exhausted
    if analysis is None:
        if _detect_quota_error(last_error):
            summary, detail = _quota_error_message()
            analysis = _make_error_analysis(summary, detail)
        else:
            analysis = _make_error_analysis(
                "Analysis for {} failed across all models. {}".format(
                    ticker.upper(), last_error[:100] if last_error else "Unknown error"),
                last_response_text or "No response received from any model.",
            )

    # Embed news_digest inside analysis dict so it's stored with analysis_json
    if news_digest:
        analysis["news_digest"] = news_digest

    return {
        "ticker": ticker.upper(),
        "company_name": company_name,
        "current_price": stock_data.get("current_price"),
        "stock_data": stock_data,
        "news_articles": news_articles,
        "analysis": analysis,
        "news_digest": news_digest,
    }
