from unittest.mock import MagicMock

import pytest
import requests

from src import news_fetcher
from src.news_fetcher import _clean, fetch_headlines, search_news, search_news_yahoo
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
    assert result == [{"title": "NVDA", "link": "u", "pubDate": "t", "publisher": "Naver"}]


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


def test_fetch_headlines_routes_kr_to_naver_us_to_yahoo(monkeypatch):
    captured = []

    def fake_naver(query, count):
        captured.append(("naver", query))
        return []

    def fake_yahoo(ticker, count):
        captured.append(("yahoo", ticker))
        return []

    monkeypatch.setattr(news_fetcher, "search_news", fake_naver)
    monkeypatch.setattr(news_fetcher, "search_news_yahoo", fake_yahoo)

    fetch_headlines(["NVDA", "005930.KS", "AAOI", "042700.KS"], Ontology.load(), per_ticker=1)

    assert ("yahoo", "NVDA") in captured
    assert ("yahoo", "AAOI") in captured
    assert ("naver", "삼성전자") in captured
    assert ("naver", "한미반도체") in captured
