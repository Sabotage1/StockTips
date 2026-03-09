import io
import os
import re
import tempfile
from datetime import datetime

import httpx
import matplotlib
matplotlib.use("Agg")  # Non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D
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


def _parse_price_from_str(s):
    """Extract the first dollar amount from a string like '$15.27 - $16.09 (resistance zone)'."""
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return float(s)
    matches = re.findall(r'\$?([\d]+\.?\d*)', str(s))
    if matches:
        return float(matches[0])
    return None


def _parse_price_range(s):
    """Extract up to two prices from a string like '$15.27 - $16.09'."""
    if s is None:
        return None, None
    matches = re.findall(r'\$?([\d]+\.?\d*)', str(s))
    if len(matches) >= 2:
        return float(matches[0]), float(matches[1])
    elif len(matches) == 1:
        return float(matches[0]), None
    return None, None


def generate_chart(ticker, company_name="", analysis_data=None):
    """Generate a candlestick chart with SMA overlays and optional analysis overlays.

    analysis_data: dict with optional keys:
        support_levels, resistance_levels, breakout_level, breakout_direction,
        stop_loss, price_target_short, price_target_long,
        expected_gain_pct, expected_loss_pct
    Returns PNG bytes.
    """
    df = _fetch_chart_data(ticker, period="6mo")
    if df is None or len(df) < 20:
        return None

    # Compute SMAs
    sma_plots = []
    sma_colors = {"SMA 20": "#74b9ff", "SMA 150": "#6c5ce7", "SMA 200": "#e74c3c"}

    if len(df) >= 20:
        sma_plots.append(mpf.make_addplot(df["Close"].rolling(20).mean(), color=sma_colors["SMA 20"], width=1.0, linestyle="-"))

    # For SMA 150 and 200, we need more data — fetch 1yr
    df_long = _fetch_chart_data(ticker, period="1y")
    if df_long is not None and len(df_long) >= 150:
        sma150_full = df_long["Close"].rolling(150).mean()
        sma150_trimmed = sma150_full.reindex(df.index)
        if sma150_trimmed.notna().sum() > 10:
            sma_plots.append(mpf.make_addplot(sma150_trimmed, color=sma_colors["SMA 150"], width=1.2, linestyle="-"))

    if df_long is not None and len(df_long) >= 200:
        sma200_full = df_long["Close"].rolling(200).mean()
        sma200_trimmed = sma200_full.reindex(df.index)
        if sma200_trimmed.notna().sum() > 10:
            sma_plots.append(mpf.make_addplot(sma200_trimmed, color=sma_colors["SMA 200"], width=1.2, linestyle="--"))

    title = "{} ({})".format(ticker.upper(), company_name) if company_name else ticker.upper()

    fig, axes = mpf.plot(
        df,
        type="candle",
        style=DARK_STYLE,
        volume=True,
        addplot=sma_plots if sma_plots else None,
        title=title,
        figsize=(14, 8),
        tight_layout=True,
        returnfig=True,
    )

    ax_main = axes[0]
    current_price = df["Close"].iloc[-1]
    y_min, y_max = ax_main.get_ylim()
    x_min, x_max = ax_main.get_xlim()

    # Build legend entries
    legend_lines = []
    legend_labels = []
    for label, color in sma_colors.items():
        period_num = int(label.split()[-1])
        if len(df) >= period_num or (df_long is not None and len(df_long) >= period_num):
            legend_lines.append(Line2D([0], [0], color=color, linewidth=1.5))
            legend_labels.append(label)

    # --- Draw analysis overlays ---
    if analysis_data:
        _draw_analysis_overlays(ax_main, analysis_data, current_price, x_min, x_max, y_min, y_max, legend_lines, legend_labels)

    if legend_lines:
        ax_main.legend(legend_lines, legend_labels, loc="upper left", fontsize=8,
                       facecolor="#1a1d27", edgecolor="#2d3148", labelcolor="#e4e6f0",
                       framealpha=0.9)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130, bbox_inches="tight",
                facecolor="#0f1117", edgecolor="none")
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()


def _draw_analysis_overlays(ax, data, current_price, x_min, x_max, y_min, y_max, legend_lines, legend_labels):
    """Draw support/resistance lines, breakout level, and expected gain/loss on the chart."""
    label_x = x_max + (x_max - x_min) * 0.01  # Just past the right edge
    # Expand right margin slightly for labels
    ax.set_xlim(x_min, x_max + (x_max - x_min) * 0.12)

    drawn_supports = 0
    drawn_resistances = 0

    # Draw support levels (green dashed lines)
    for level_str in (data.get("support_levels") or [])[:3]:
        p1, p2 = _parse_price_range(level_str)
        if p1 is None or p1 < y_min or p1 > y_max:
            continue

        if p2 is not None and abs(p2 - p1) > 0.01:
            # Draw a shaded zone
            ax.axhspan(min(p1, p2), max(p1, p2), color="#00b894", alpha=0.08)
            ax.axhline(y=(p1 + p2) / 2, color="#00b894", linewidth=1.0, linestyle="--", alpha=0.7)
            ax.annotate(
                "S ${:.2f}".format((p1 + p2) / 2),
                xy=(label_x, (p1 + p2) / 2), fontsize=8, fontweight="bold",
                color="#00b894", va="center",
                annotation_clip=False,
            )
        else:
            ax.axhline(y=p1, color="#00b894", linewidth=1.0, linestyle="--", alpha=0.7)
            ax.annotate(
                "S ${:.2f}".format(p1),
                xy=(label_x, p1), fontsize=8, fontweight="bold",
                color="#00b894", va="center",
                annotation_clip=False,
            )
        drawn_supports += 1

    # Draw resistance levels (red dashed lines)
    for level_str in (data.get("resistance_levels") or [])[:3]:
        p1, p2 = _parse_price_range(level_str)
        if p1 is None or p1 < y_min or p1 > y_max:
            continue

        if p2 is not None and abs(p2 - p1) > 0.01:
            ax.axhspan(min(p1, p2), max(p1, p2), color="#e74c3c", alpha=0.08)
            ax.axhline(y=(p1 + p2) / 2, color="#e74c3c", linewidth=1.0, linestyle="--", alpha=0.7)
            ax.annotate(
                "R ${:.2f}".format((p1 + p2) / 2),
                xy=(label_x, (p1 + p2) / 2), fontsize=8, fontweight="bold",
                color="#e74c3c", va="center",
                annotation_clip=False,
            )
        else:
            ax.axhline(y=p1, color="#e74c3c", linewidth=1.0, linestyle="--", alpha=0.7)
            ax.annotate(
                "R ${:.2f}".format(p1),
                xy=(label_x, p1), fontsize=8, fontweight="bold",
                color="#e74c3c", va="center",
                annotation_clip=False,
            )
        drawn_resistances += 1

    if drawn_supports > 0:
        legend_lines.append(Line2D([0], [0], color="#00b894", linewidth=1.5, linestyle="--"))
        legend_labels.append("Support")
    if drawn_resistances > 0:
        legend_lines.append(Line2D([0], [0], color="#e74c3c", linewidth=1.5, linestyle="--"))
        legend_labels.append("Resistance")

    # Draw breakout level (bright yellow/orange solid line)
    breakout_price = _parse_price_from_str(data.get("breakout_level"))
    breakout_dir = data.get("breakout_direction", "")
    if breakout_price and y_min <= breakout_price <= y_max:
        bo_color = "#ffd700" if breakout_dir == "BULLISH" else "#ff6b6b" if breakout_dir == "BEARISH" else "#ffa500"
        ax.axhline(y=breakout_price, color=bo_color, linewidth=1.8, linestyle="-", alpha=0.9)
        ax.annotate(
            "BREAKOUT ${:.2f}".format(breakout_price),
            xy=(label_x, breakout_price), fontsize=8, fontweight="bold",
            color=bo_color, va="center",
            annotation_clip=False,
        )
        legend_lines.append(Line2D([0], [0], color=bo_color, linewidth=2.0))
        legend_labels.append("Breakout")

    # Draw stop loss level (red solid line)
    stop_price = _parse_price_from_str(data.get("stop_loss"))
    if stop_price and y_min <= stop_price <= y_max:
        ax.axhline(y=stop_price, color="#ff4757", linewidth=1.2, linestyle="-.", alpha=0.8)
        ax.annotate(
            "STOP ${:.2f}".format(stop_price),
            xy=(label_x, stop_price), fontsize=8, fontweight="bold",
            color="#ff4757", va="center",
            annotation_clip=False,
        )

    # Draw target price (green solid line for short-term target)
    target_price = _parse_price_from_str(data.get("price_target_short"))
    if target_price and y_min <= target_price <= y_max:
        ax.axhline(y=target_price, color="#2ed573", linewidth=1.2, linestyle="-.", alpha=0.8)
        ax.annotate(
            "TARGET ${:.2f}".format(target_price),
            xy=(label_x, target_price), fontsize=8, fontweight="bold",
            color="#2ed573", va="center",
            annotation_clip=False,
        )

    # Draw expected gain/loss annotation box in top-right area
    exp_gain = data.get("expected_gain_pct", "")
    exp_loss = data.get("expected_loss_pct", "")
    rr_ratio = data.get("risk_reward_ratio", "")

    info_lines = []
    if exp_gain and exp_gain != "N/A":
        info_lines.append("Exp. Gain: +{}".format(exp_gain.replace("+", "")))
    if exp_loss and exp_loss != "N/A":
        info_lines.append("Exp. Loss: -{}".format(exp_loss.replace("-", "")))
    if rr_ratio and rr_ratio != "N/A":
        info_lines.append("R/R: {}".format(rr_ratio))

    if info_lines:
        info_text = "\n".join(info_lines)
        ax.annotate(
            info_text,
            xy=(0.98, 0.97), xycoords="axes fraction",
            fontsize=9, fontweight="bold", color="#e4e6f0",
            ha="right", va="top",
            bbox=dict(
                boxstyle="round,pad=0.5",
                facecolor="#1a1d27",
                edgecolor="#6c5ce7",
                alpha=0.92,
                linewidth=1.5,
            ),
            annotation_clip=False,
        )


def generate_chart_to_file(ticker, company_name="", analysis_data=None):
    """Generate chart and save to a temp file. Returns file path or None."""
    png_bytes = generate_chart(ticker, company_name, analysis_data=analysis_data)
    if png_bytes is None:
        return None
    tmp = tempfile.NamedTemporaryFile(suffix=".png", prefix="chart_{}_".format(ticker), delete=False)
    tmp.write(png_bytes)
    tmp.close()
    return tmp.name
