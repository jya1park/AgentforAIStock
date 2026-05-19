"""News fetchers: Naver (KR tickers) + yfinance.news + NewsAPI (US tickers)."""

import os
import re
from datetime import datetime, timedelta, timezone

import requests
import yfinance as yf

from src import config  # noqa: F401 — triggers .env autoload
from src.ontology import Ontology

NAVER_API_URL = "https://openapi.naver.com/v1/search/news.json"
NEWSAPI_URL = "https://newsapi.org/v2/everything"
NEWSAPI_DOMAINS = (
    "reuters.com,bloomberg.com,ft.com,wsj.com,cnbc.com,"
    "marketwatch.com,barrons.com,seekingalpha.com"
)


def _clean(text: str) -> str:
    text = re.sub(r"</?b>", "", text)
    text = text.replace("&quot;", '"').replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    return text.strip()


def search_news(query: str, count: int = 5) -> list[dict]:
    """Naver Search News API. Returns [{title, link, pubDate, publisher}]. Empty on failure."""
    headers = {
        "X-Naver-Client-Id": os.environ.get("NAVER_CLIENT_ID", ""),
        "X-Naver-Client-Secret": os.environ.get("NAVER_CLIENT_SECRET", ""),
    }
    params = {"query": query, "display": count, "sort": "sim"}
    try:
        resp = requests.get(NAVER_API_URL, headers=headers, params=params, timeout=10)
        resp.raise_for_status()
    except requests.RequestException:
        return []
    return [
        {
            "title": _clean(it["title"]),
            "link": it["link"],
            "pubDate": it.get("pubDate", ""),
            "publisher": "Naver",
        }
        for it in resp.json().get("items", [])
    ]


def search_news_yahoo(ticker: str, count: int = 5) -> list[dict]:
    """yfinance.Ticker(t).news. Bloomberg/Reuters/MarketWatch surfaced via publisher field."""
    try:
        items = yf.Ticker(ticker).news or []
    except Exception:
        return []
    out = []
    for it in items[:count]:
        content = it.get("content", it)
        title = content.get("title", "")
        if not title:
            continue
        out.append({
            "title": title,
            "link": (content.get("canonicalUrl") or {}).get("url") or content.get("link", ""),
            "pubDate": content.get("pubDate") or "",
            "publisher": (content.get("provider") or {}).get("displayName") or content.get("publisher", ""),
        })
    return out


def search_news_newsapi(query: str, count: int = 5) -> list[dict]:
    """NewsAPI.org /everything restricted to tier-1 financial outlets, sorted by relevance.
    Empty if no key or on failure."""
    api_key = os.environ.get("NEWSAPI_KEY", "")
    if not api_key:
        return []
    today = datetime.now(timezone.utc).date()
    params = {
        "q": query,
        "language": "en",
        "sortBy": "relevancy",
        "domains": NEWSAPI_DOMAINS,
        "from": (today - timedelta(days=7)).isoformat(),
        "to": today.isoformat(),
        "pageSize": count,
        "apiKey": api_key,
    }
    try:
        resp = requests.get(NEWSAPI_URL, params=params, timeout=10)
        resp.raise_for_status()
    except requests.RequestException:
        return []
    out = []
    for it in resp.json().get("articles", [])[:count]:
        title = it.get("title", "")
        if not title:
            continue
        out.append({
            "title": title,
            "link": it.get("url", ""),
            "pubDate": it.get("publishedAt", ""),
            "publisher": (it.get("source") or {}).get("name", "NewsAPI"),
        })
    return out


def _dedupe(items: list[dict]) -> list[dict]:
    seen_titles, seen_urls, out = set(), set(), []
    for it in items:
        title_key = it["title"].strip().lower()
        url_key = it.get("link", "")
        if title_key in seen_titles or (url_key and url_key in seen_urls):
            continue
        seen_titles.add(title_key)
        if url_key:
            seen_urls.add(url_key)
        out.append(it)
    return out


def _is_kr(ticker: str) -> bool:
    return ticker.endswith(".KS") or ticker.endswith(".KQ")


def fetch_headlines(tickers: list[str], ontology: Ontology, per_ticker: int = 3) -> dict[str, list[dict]]:
    """Route per ticker: KR (.KS/.KQ) → Naver; US → Yahoo + NewsAPI (deduped)."""
    out = {}
    for t in tickers:
        if _is_kr(t):
            query = ontology.name_for(t) or t
            out[t] = search_news(query, count=per_ticker)
        else:
            name = ontology.name_for(t) or t
            combined = (
                search_news_yahoo(t, count=per_ticker)
                + search_news_newsapi(name, count=per_ticker)
            )
            out[t] = _dedupe(combined)[:per_ticker]
    return out
