from unittest.mock import MagicMock

import pytest
import requests

from src import news_fetcher
from src.news_fetcher import _clean, fetch_headlines, search_news
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
    assert result == [{"title": "NVDA", "link": "u", "pubDate": "t"}]


def test_search_news_returns_empty_on_http_error(monkeypatch):
    def fake_get(*a, **kw):
        raise requests.ConnectionError("network down")
    monkeypatch.setattr(requests, "get", fake_get)
    assert search_news("NVIDIA") == []


def test_fetch_headlines_uses_ontology_name(monkeypatch):
    captured_queries = []

    def fake_search(query, count):
        captured_queries.append(query)
        return [{"title": f"news for {query}", "link": "u", "pubDate": "t"}]

    monkeypatch.setattr(news_fetcher, "search_news", fake_search)
    result = fetch_headlines(["NVDA", "005930.KS", "UNKNOWN"], Ontology.load(), per_ticker=1)

    assert "NVIDIA" in captured_queries
    assert "삼성전자" in captured_queries
    assert "UNKNOWN" in captured_queries  # fallback to ticker when no name
    assert set(result.keys()) == {"NVDA", "005930.KS", "UNKNOWN"}
