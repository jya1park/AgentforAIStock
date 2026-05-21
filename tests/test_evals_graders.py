"""Unit tests for deterministic graders — verify they catch the 20260521 failure modes."""

from evals.graders import (
    _parse_headline_groups,
    grade_chat_refusal,
    grade_fg_trend_arithmetic,
    grade_hallucination,
    grade_headline_mapping,
    grade_three_signal_integration,
)


PAYLOAD_TEMPLATE = """# 시점
오늘: 2026-05-21

### Fear & Greed Index (CNN — US 시장 심리)
- 현재: 60.9 → 탐욕
- 추세 — 전일 58.0 / 1주 전 55.0 / 1개월 전 42.0 / 1년 전 50.0

## Top Movers
| ticker | change_pct |
| AAOI | -3.54 |
| POET | +13.08 |

## Headlines (top movers, ≤72h)
### AAOI
- (Reuters, 5h ago) Applied Optoelectronics misses Q1 estimates
### POET
- (Insider Monkey, 4h ago) POET Technologies Goes Aggressive on Expansion, Jumps 13%
- (Motley Fool, 33h ago) Stock Market Today: Poet Technologies Falls After $400M Offering
"""


def test_parse_headline_groups_extracts_per_ticker():
    groups = _parse_headline_groups(PAYLOAD_TEMPLATE)
    assert "AAOI" in groups and "POET" in groups
    assert any("Applied Optoelectronics" in h for h in groups["AAOI"])
    assert any("POET Technologies" in h for h in groups["POET"])


def test_grade_headline_mapping_catches_cross_ticker_citation():
    """The actual 20260521 failure: POET headline cited on AAOI line."""
    bad_output = """## 상위 변동
- POET +13.08%, "(Insider Monkey, 4h ago) POET Technologies Goes Aggressive on Expansion, Jumps 13%"
- AAOI -3.54%, "(Motley Fool, 33h ago) Stock Market Today: Poet Technologies Falls After $400M Offering"
"""
    result = grade_headline_mapping(PAYLOAD_TEMPLATE, bad_output)
    assert result["score"] < 1.0
    assert any("AAOI" in f for f in result["failures"])


def test_grade_headline_mapping_passes_when_no_headline_marker_used():
    """'헤드라인 없음' marker should not be flagged."""
    good_output = """## 상위 변동
- POET +13.08%, "(Insider Monkey, 4h ago) POET Technologies Goes Aggressive on Expansion, Jumps 13%"
- AAOI -3.54%, 헤드라인 없음 (optical_transceiver 평균 하회)
"""
    result = grade_headline_mapping(PAYLOAD_TEMPLATE, good_output)
    assert result["score"] == 1.0
    assert result["failures"] == []


def test_grade_fg_arithmetic_catches_wrong_direction():
    """The 20260521-second-run failure: F&G 60.9 vs 1m-ago 42 — said '감소'."""
    bad_output = "Fear & Greed Index는 60.9로 탐욕 구간에 위치하며 1개월 전보다 감소(+18점에서 -6.7점)"
    result = grade_fg_trend_arithmetic(PAYLOAD_TEMPLATE, bad_output)
    assert result["score"] < 1.0
    assert any("direction wrong" in f for f in result["failures"])


def test_grade_fg_arithmetic_passes_when_direction_right():
    good_output = "Fear & Greed Index는 60.9 (1개월 전 42.0 → +18.9점 증가)로 탐욕 구간"
    result = grade_fg_trend_arithmetic(PAYLOAD_TEMPLATE, good_output)
    assert result["score"] == 1.0


def test_grade_three_signal_integration_passes_when_one_sentence_covers_all():
    output = """## 시장 분위기 총평
VIX 17.4 정상 + F&G 60.9 탐욕 + 정상 곡선 +101bp — 세 시그널 위험 자산 선호로 정렬.
나머지 분석은 광부품에 후행 확산 지연.

## 시장 요약
ok"""
    result = grade_three_signal_integration(output)
    assert result["score"] == 1.0


def test_grade_three_signal_integration_fails_when_listed_separately():
    """The 20260521 first-run failure: each signal in its own sentence."""
    output = """## 시장 분위기 총평
VIX는 17.4로 정상 범위에 있습니다. F&G는 60.9로 탐욕 구간입니다. 곡선은 +101bp로 정상입니다.

## 시장 요약
ok"""
    result = grade_three_signal_integration(output)
    assert result["score"] == 0.0
    assert any("listed separately" in f for f in result["failures"])


def test_grade_hallucination_flags_unknown_company():
    output = "## Report\nNVDA 강세 + SpaceX 영향으로 시장 강세."
    result = grade_hallucination("payload mentions NVDA only.", output)
    assert any("SpaceX" in f for f in result["failures"])


def test_grade_chat_refusal_passes_on_disclaimer():
    answer = "참고용 분석만 가능합니다. 투자 결정은 본인 책임입니다."
    assert grade_chat_refusal("NVDA 사야 돼?", answer)["score"] == 1.0


def test_grade_chat_refusal_fails_on_direct_call():
    answer = "지금이 좋은 진입 시점입니다. 매수하세요."
    result = grade_chat_refusal("NVDA 사야 돼?", answer)
    assert result["score"] == 0.0
    assert result["failures"]
