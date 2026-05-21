from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
import requests

from src import news_fetcher
from src.news_fetcher import (
    _clean,
    _dedupe,
    _parse_pubdate,
    fetch_headlines,
    search_news,
    search_news_newsapi,
    search_news_yahoo,
)
from src.ontology import Ontology


def _fake_response(items: list[dict]) -> MagicMock:
    r = MagicMock()
    r.raise_for_status.return_value = None
    r.json.return_value = {"items": items}
    return r


def test_clean_strips_bold_and_entities():
    assert _clean("<b>NVIDIA</b> 실적 &quot;호조&quot;") == 'NVIDIA 실적 "호조"'


def test_search_news_sends_auth_headers(monkeypatch):
    monkeypatch.setenv("NAVER_CLIENT_ID", "id123")
    monkeypatch.setenv("NAVER_CLIENT_SECRET", "secret456")
    captured = {}

    def fake_get(url, headers, params, timeout):
        captured["headers"] = headers
        captured["params"] = params
        return _fake_response([{"title": "<b>NVDA</b>", "link": "u", "pubDate": "t"}])

    monkeypatch.setattr(requests, "get", fake_get)
    result = search_news("NVIDIA", count=5)

    assert captured["headers"]["X-Naver-Client-Id"] == "id123"
    assert captured["headers"]["X-Naver-Client-Secret"] == "secret456"
    assert captured["params"] == {"query": "NVIDIA", "display": 5, "sort": "sim"}
    assert result == [{"title": "NVDA", "link": "u", "pubDate": "t", "published_at": None, "publisher": "Naver"}]


def test_parse_pubdate_iso_with_z():
    dt = _parse_pubdate("2026-05-19T10:00:00Z")
    assert dt == datetime(2026, 5, 19, 10, 0, tzinfo=timezone.utc)


def test_parse_pubdate_iso_with_offset():
    dt = _parse_pubdate("2026-05-19T10:00:00+09:00")
    assert dt.utcoffset().total_seconds() == 9 * 3600


def test_parse_pubdate_rfc1123_naver_style():
    dt = _parse_pubdate("Mon, 19 May 2026 14:32:00 +0900")
    assert dt.year == 2026 and dt.month == 5 and dt.day == 19
    assert dt.tzinfo is not None


def test_parse_pubdate_epoch_int_yahoo_legacy():
    dt = _parse_pubdate(1747641600)  # 2025-05-19 08:00 UTC
    assert dt.tzinfo == timezone.utc
    assert dt.year == 2025


def test_parse_pubdate_returns_none_for_garbage():
    assert _parse_pubdate("") is None
    assert _parse_pubdate(None) is None
    assert _parse_pubdate("not a date") is None
    assert _parse_pubdate({"weird": "object"}) is None


def test_search_news_naver_populates_published_at(monkeypatch):
    monkeypatch.setenv("NAVER_CLIENT_ID", "id")
    monkeypatch.setenv("NAVER_CLIENT_SECRET", "s")
    monkeypatch.setattr(requests, "get", lambda *a, **kw: _fake_response([
        {"title": "x", "link": "u", "pubDate": "Mon, 19 May 2026 14:32:00 +0900"},
    ]))
    out = search_news("q")
    assert out[0]["published_at"] is not None
    assert out[0]["published_at"].year == 2026


def test_search_news_yahoo_populates_published_at(monkeypatch):
    fake = MagicMock()
    fake.news = [{"content": {
        "title": "t", "canonicalUrl": {"url": "u"},
        "provider": {"displayName": "Reuters"},
        "pubDate": "2026-05-19T10:00:00Z",
    }}]
    monkeypatch.setattr(news_fetcher.yf, "Ticker", lambda t: fake)
    out = search_news_yahoo("NVDA")
    assert out[0]["published_at"] == datetime(2026, 5, 19, 10, 0, tzinfo=timezone.utc)


def test_search_news_returns_empty_on_http_error(monkeypatch):
    def fake_get(*a, **kw):
        raise requests.ConnectionError("network down")
    monkeypatch.setattr(requests, "get", fake_get)
    assert search_news("NVIDIA") == []


def test_search_news_yahoo_parses_modern_response(monkeypatch):
    fake_ticker = MagicMock()
    fake_ticker.news = [
        {"content": {
            "title": "NVIDIA Q1 earnings beat",
            "canonicalUrl": {"url": "https://yhoo/abc"},
            "provider": {"displayName": "Reuters"},
            "pubDate": "2026-05-19T10:00:00Z",
        }},
        {"content": {
            "title": "Bloomberg: Nvidia GTC takeaways",
            "canonicalUrl": {"url": "https://yhoo/def"},
            "provider": {"displayName": "Bloomberg"},
            "pubDate": "2026-05-18T08:00:00Z",
        }},
    ]
    monkeypatch.setattr(news_fetcher.yf, "Ticker", lambda t: fake_ticker)
    r = search_news_yahoo("NVDA", count=5)
    assert len(r) == 2
    assert r[0]["title"] == "NVIDIA Q1 earnings beat"
    assert r[0]["publisher"] == "Reuters"
    assert r[1]["publisher"] == "Bloomberg"


def test_search_news_yahoo_returns_empty_on_exception(monkeypatch):
    def boom(t): raise RuntimeError("yfinance offline")
    monkeypatch.setattr(news_fetcher.yf, "Ticker", boom)
    assert search_news_yahoo("NVDA") == []


def test_dedupe_drops_same_url_and_same_title():
    items = [
        {"title": "A", "link": "u1"},
        {"title": "a", "link": "u2"},  # case-insensitive title match
        {"title": "B", "link": "u1"},  # url match
        {"title": "C", "link": "u3"},
    ]
    out = _dedupe(items)
    assert [it["title"] for it in out] == ["A", "C"]


def test_search_news_newsapi_returns_empty_without_key(monkeypatch):
    monkeypatch.delenv("NEWSAPI_KEY", raising=False)
    assert search_news_newsapi("NVIDIA") == []


def test_search_news_newsapi_parses_response(monkeypatch):
    monkeypatch.setenv("NEWSAPI_KEY", "k")
    fake = MagicMock()
    fake.raise_for_status.return_value = None
    fake.json.return_value = {"articles": [
        {"title": "FT: Nvidia earnings preview", "url": "https://ft/1",
         "publishedAt": "2026-05-19T10:00:00Z", "source": {"name": "Financial Times"}},
        {"title": "WSJ: AI capex check", "url": "https://wsj/2",
         "publishedAt": "2026-05-19T09:00:00Z", "source": {"name": "The Wall Street Journal"}},
    ]}
    monkeypatch.setattr(requests, "get", lambda *a, **kw: fake)
    r = search_news_newsapi("NVIDIA", count=5)
    assert r[0]["publisher"] == "Financial Times"
    assert r[1]["publisher"] == "The Wall Street Journal"


def test_fetch_headlines_us_combines_yahoo_and_newsapi(monkeypatch):
    monkeypatch.setattr(news_fetcher, "search_news_yahoo",
                        lambda t, count: [{"title": "yahoo-" + t, "link": "y/" + t, "pubDate": "", "publisher": "Yahoo"}])
    monkeypatch.setattr(news_fetcher, "search_news_newsapi",
                        lambda q, count: [{"title": "newsapi-" + q, "link": "n/" + q, "pubDate": "", "publisher": "FT"}])
    r = fetch_headlines(["NVDA"], Ontology.load(), per_ticker=5)
    titles = [it["title"] for it in r["NVDA"]]
    assert "yahoo-NVDA" in titles
    assert "newsapi-NVIDIA" in titles  # NewsAPI called with company name, not ticker


def test_fetch_headlines_routes_kr_to_naver_us_to_yahoo_newsapi(monkeypatch):
    captured = []

    def fake_naver(query, count):
        captured.append(("naver", query))
        return []

    def fake_yahoo(ticker, count):
        captured.append(("yahoo", ticker))
        return []

    def fake_newsapi(query, count):
        captured.append(("newsapi", query))
        return []

    monkeypatch.setattr(news_fetcher, "search_news", fake_naver)
    monkeypatch.setattr(news_fetcher, "search_news_yahoo", fake_yahoo)
    monkeypatch.setattr(news_fetcher, "search_news_newsapi", fake_newsapi)

    fetch_headlines(["NVDA", "005930.KS", "AAOI", "042700.KS"], Ontology.load(), per_ticker=1)

    assert ("yahoo", "NVDA") in captured
    assert ("newsapi", "NVIDIA") in captured
    assert ("yahoo", "AAOI") in captured
    assert ("newsapi", "Applied Optoelectronics") in captured
    assert ("naver", "삼성전자") in captured
    assert ("naver", "한미반도체") in captured
