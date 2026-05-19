"""Naver Search News fetcher for top-mover headlines."""

import os
import re

import requests

from src import config  # noqa: F401 — triggers .env autoload
from src.ontology import Ontology

API_URL = "https://openapi.naver.com/v1/search/news.json"


def _clean(text: str) -> str:
    text = re.sub(r"</?b>", "", text)
    text = text.replace("&quot;", '"').replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    return text.strip()


def search_news(query: str, count: int = 5) -> list[dict]:
    """Call Naver Search News API. Returns [{title, link, pubDate}]. Empty list on failure."""
    headers = {
        "X-Naver-Client-Id": os.environ.get("NAVER_CLIENT_ID", ""),
        "X-Naver-Client-Secret": os.environ.get("NAVER_CLIENT_SECRET", ""),
    }
    params = {"query": query, "display": count, "sort": "sim"}
    try:
        resp = requests.get(API_URL, headers=headers, params=params, timeout=10)
        resp.raise_for_status()
    except requests.RequestException:
        return []
    return [
        {"title": _clean(it["title"]), "link": it["link"], "pubDate": it.get("pubDate", "")}
        for it in resp.json().get("items", [])
    ]


def fetch_headlines(tickers: list[str], ontology: Ontology, per_ticker: int = 3) -> dict[str, list[dict]]:
    """For each ticker, search Naver news with its ontology name (fallback: ticker)."""
    out = {}
    for t in tickers:
        query = ontology.name_for(t) or t
        out[t] = search_news(query, count=per_ticker)
    return out
