import io
import os
import tempfile
from datetime import datetime

import httpx
import matplotlib
matplotlib.use("Agg")  # Non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd
import mplfinance as mpf

HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}

# Dark theme matching the web app
DARK_STYLE = mpf.make_mpf_style(
    base_mpf_style="nightclouds",
    marketcolors=mpf.make_marketcolors(
        up="#00b894",
        down="#e74c3c",
        edge={"up": "#00b894", "down": "#e74c3c"},
        wick={"up": "#00b894", "down": "#e74c3c"},
        volume={"up": "#00b89466", "down": "#e74c3c66"},
    ),
    facecolor="#0f1117",
    edgecolor="#2d3148",
    figcolor="#0f1117",
    gridcolor="#1a1d27",
    gridstyle="--",
    gridaxis="both",
    y_on_right=True,
    rc={
        "axes.labelcolor": "#9a9db8",
        "xtick.color": "#9a9db8",
        "ytick.color": "#9a9db8",
        "font.size": 10,
    },
)


def _fetch_chart_data(ticker, period="6mo"):
    """Fetch OHLCV data from Yahoo Chart API and return as DataFrame."""
    try:
        resp = httpx.get(
            "https://query1.finance.yahoo.com/v8/finance/chart/{}?range={}&interval=1d".format(ticker, period),
            headers=HEADERS,
            timeout=10,
        )
        if resp.status_code != 200:
            return None

        data = resp.json()
        result = data["chart"]["result"][0]
        timestamps = result["timestamp"]
        quotes = result["indicators"]["quote"][0]

        df = pd.DataFrame({
            "Date": [datetime.fromtimestamp(t) for t in timestamps],
            "Open": quotes["open"],
            "High": quotes["high"],
            "Low": quotes["low"],
            "Close": quotes["close"],
            "Volume": quotes["volume"],
        })
        df = df.dropna()
        df = df.set_index("Date")
        df.index = pd.DatetimeIndex(df.index)
        return df
    except Exception as e:
        print("Chart data error for {}: {}".format(ticker, e))
        return None


def generate_chart(ticker, company_name=""):
    """Generate a candlestick chart with SMA overlays. Returns PNG bytes."""
    df = _fetch_chart_data(ticker, period="6mo")
    if df is None or len(df) < 20:
        return None

    # Compute SMAs
    sma_plots = []
    colors = {"SMA 20": "#74b9ff", "SMA 150": "#6c5ce7", "SMA 200": "#e74c3c"}

    if len(df) >= 20:
        sma_plots.append(mpf.make_addplot(df["Close"].rolling(20).mean(), color=colors["SMA 20"], width=1.0, linestyle="-"))

    # For SMA 150 and 200, we need more data — fetch 1yr
    df_long = _fetch_chart_data(ticker, period="1y")
    if df_long is not None and len(df_long) >= 150:
        sma150_full = df_long["Close"].rolling(150).mean()
        # Align to the 6mo chart range
        sma150_trimmed = sma150_full.reindex(df.index)
        if sma150_trimmed.notna().sum() > 10:
            sma_plots.append(mpf.make_addplot(sma150_trimmed, color=colors["SMA 150"], width=1.2, linestyle="-"))

    if df_long is not None and len(df_long) >= 200:
        sma200_full = df_long["Close"].rolling(200).mean()
        sma200_trimmed = sma200_full.reindex(df.index)
        if sma200_trimmed.notna().sum() > 10:
            sma_plots.append(mpf.make_addplot(sma200_trimmed, color=colors["SMA 200"], width=1.2, linestyle="--"))

    title = "{} ({})".format(ticker.upper(), company_name) if company_name else ticker.upper()

    buf = io.BytesIO()
    fig, axes = mpf.plot(
        df,
        type="candle",
        style=DARK_STYLE,
        volume=True,
        addplot=sma_plots if sma_plots else None,
        title=title,
        figsize=(12, 7),
        tight_layout=True,
        returnfig=True,
    )

    # Add SMA legend manually
    ax_main = axes[0]
    legend_lines = []
    legend_labels = []
    for label, color in colors.items():
        period_num = int(label.split()[-1])
        if len(df) >= period_num or (df_long is not None and len(df_long) >= period_num):
            from matplotlib.lines import Line2D
            legend_lines.append(Line2D([0], [0], color=color, linewidth=1.5))
            legend_labels.append(label)

    if legend_lines:
        ax_main.legend(legend_lines, legend_labels, loc="upper left", fontsize=9,
                       facecolor="#1a1d27", edgecolor="#2d3148", labelcolor="#e4e6f0")

    fig.savefig(buf, format="png", dpi=130, bbox_inches="tight",
                facecolor="#0f1117", edgecolor="none")
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()


def generate_chart_to_file(ticker, company_name=""):
    """Generate chart and save to a temp file. Returns file path or None."""
    png_bytes = generate_chart(ticker, company_name)
    if png_bytes is None:
        return None
    tmp = tempfile.NamedTemporaryFile(suffix=".png", prefix="chart_{}_".format(ticker), delete=False)
    tmp.write(png_bytes)
    tmp.close()
    return tmp.name
