import json
import asyncio
import xml.etree.ElementTree as ET
import httpx
from bs4 import BeautifulSoup
from config import NEWS_API_KEY


def parse_rss_entries(xml_text, max_entries=10):
    """Parse RSS XML and return a list of entry dicts."""
    entries = []
    try:
        root = ET.fromstring(xml_text)
        for item in root.iter("item"):
            if len(entries) >= max_entries:
                break
            entries.append({
                "title": (item.findtext("title") or "").strip(),
                "summary": (item.findtext("description") or "").strip(),
                "link": (item.findtext("link") or "").strip(),
                "published": (item.findtext("pubDate") or "").strip(),
            })
    except ET.ParseError:
        pass
    return entries


async def fetch_yahoo_finance_news(ticker: str) -> list[dict]:
    """Fetch news from Yahoo Finance RSS feed for a given ticker."""
    articles = []
    url = "https://feeds.finance.yahoo.com/rss/2.0/headline?s={}&region=US&lang=en-US".format(ticker)
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url)
            for entry in parse_rss_entries(resp.text):
                entry["source"] = "Yahoo Finance"
                articles.append(entry)
    except Exception as e:
        print("Yahoo Finance news error for {}: {}".format(ticker, e))
    return articles


async def fetch_google_news(ticker: str, company_name: str = "") -> list[dict]:
    """Fetch news from Google News RSS for a given ticker/company."""
    articles = []
    search_term = "{} stock".format(company_name if company_name else ticker)
    url = "https://news.google.com/rss/search?q={}&hl=en-US&gl=US&ceid=US:en".format(search_term)
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(url)
            for entry in parse_rss_entries(resp.text):
                entry["source"] = "Google News"
                articles.append(entry)
    except Exception as e:
        print("Google News error for {}: {}".format(ticker, e))
    return articles


async def fetch_finviz_news(ticker: str) -> list[dict]:
    """Fetch news from Finviz for a given ticker."""
    articles = []
    url = f"https://finviz.com/quote.ashx?t={ticker}"
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
    try:
        async with httpx.AsyncClient(timeout=15, headers=headers) as client:
            resp = await client.get(url)
            soup = BeautifulSoup(resp.text, "html.parser")
            news_table = soup.find(id="news-table")
            if news_table:
                rows = news_table.find_all("tr")
                for row in rows[:10]:
                    link_tag = row.find("a")
                    if link_tag:
                        articles.append({
                            "title": link_tag.text.strip(),
                            "summary": "",
                            "link": link_tag.get("href", ""),
                            "source": "Finviz",
                            "published": row.td.text.strip() if row.td else "",
                        })
    except Exception as e:
        print(f"Finviz news error for {ticker}: {e}")
    return articles


async def fetch_newsapi(ticker: str, company_name: str = "") -> list[dict]:
    """Fetch news from NewsAPI (requires API key)."""
    if not NEWS_API_KEY:
        return []
    articles = []
    query = company_name if company_name else ticker
    url = f"https://newsapi.org/v2/everything?q={query}+stock&sortBy=publishedAt&pageSize=10&apiKey={NEWS_API_KEY}"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url)
            data = resp.json()
            for article in data.get("articles", [])[:10]:
                articles.append({
                    "title": article.get("title", ""),
                    "summary": article.get("description", ""),
                    "link": article.get("url", ""),
                    "source": article.get("source", {}).get("name", "NewsAPI"),
                    "published": article.get("publishedAt", ""),
                })
    except Exception as e:
        print(f"NewsAPI error for {ticker}: {e}")
    return articles


async def fetch_all_news(ticker: str, company_name: str = "") -> list[dict]:
    """Aggregate news from all sources concurrently."""
    results = await asyncio.gather(
        fetch_yahoo_finance_news(ticker),
        fetch_google_news(ticker, company_name),
        fetch_finviz_news(ticker),
        fetch_newsapi(ticker, company_name),
        return_exceptions=True,
    )

    all_articles = []
    for result in results:
        if isinstance(result, list):
            all_articles.extend(result)

    # Deduplicate by title similarity
    seen_titles = set()
    unique_articles = []
    for article in all_articles:
        title_key = article["title"].lower().strip()[:60]
        if title_key and title_key not in seen_titles:
            seen_titles.add(title_key)
            unique_articles.append(article)

    return unique_articles
