"""Deterministic rule-based grading for stock-analyst and chat-assistant outputs.
Each grader returns dict with score [0-1] and list of failure descriptions."""

import re


def _parse_headline_groups(payload: str) -> dict[str, list[str]]:
    """Extract {ticker: [headline_titles]} from payload's '## Headlines' section."""
    m = re.search(r"##\s*Headlines.*?$(.*)", payload, re.DOTALL | re.MULTILINE)
    if not m:
        return {}
    section = m.group(1)
    groups: dict[str, list[str]] = {}
    current: str | None = None
    for line in section.splitlines():
        h = re.match(r"###\s*([A-Z0-9.\-]+)\s*$", line.strip())
        if h:
            current = h.group(1)
            groups[current] = []
            continue
        if current and line.strip().startswith("-"):
            title_m = re.search(r"\)\s*(.+?)\s*$", line)
            if title_m:
                groups[current].append(title_m.group(1))
    return groups


def grade_headline_mapping(payload: str, output: str) -> dict:
    """Each headline cited next to a ticker line must contain that ticker's name."""
    groups = _parse_headline_groups(payload)
    failures: list[str] = []

    movers_m = re.search(r"##\s*상위 변동\s*$(.*?)(?=^##\s|\Z)", output, re.DOTALL | re.MULTILINE)
    if not movers_m:
        return {"score": 1.0, "failures": [], "checked": 0}

    checked = 0
    for line in movers_m.group(1).splitlines():
        line = line.strip()
        if not line.startswith("-"):
            continue
        tm = re.search(r"([A-Z0-9.\-]{2,})\s*[+\-]\d", line)
        if not tm:
            continue
        ticker = tm.group(1)
        headline_m = re.search(r'"([^"]+)"', line) or re.search(r"\)\s*([^\n]+?)\s*$", line)
        if not headline_m or "헤드라인 없음" in line:
            continue
        headline = headline_m.group(1)
        checked += 1

        valid_headlines = groups.get(ticker, [])
        if not any(headline.strip() in vh or vh in headline for vh in valid_headlines):
            failures.append(f"{ticker} line cites headline not in its group: '{headline[:80]}...'")

    score = 1.0 if checked == 0 else max(0.0, 1.0 - len(failures) / checked)
    return {"score": score, "failures": failures, "checked": checked}


def grade_fg_trend_arithmetic(payload: str, output: str) -> dict:
    """F&G values cited in output must match payload (no arbitrary arithmetic)."""
    fg_section = re.search(r"###\s*Fear & Greed Index.*?$(.*?)(?=^##|^###)", payload, re.DOTALL | re.MULTILINE)
    if not fg_section:
        return {"score": 1.0, "failures": [], "checked": 0}

    text = fg_section.group(1)
    expected: dict[str, float] = {}
    for label, key in [("현재", "current"), ("전일", "previous_close"),
                       ("1주 전", "previous_1_week"), ("1개월 전", "previous_1_month")]:
        m = re.search(rf"{label}[:\s]+(-?\d+\.?\d*)", text)
        if m:
            expected[key] = float(m.group(1))

    failures: list[str] = []
    cited = re.findall(r"(?:F&G|Fear\s*&\s*Greed)[^.]*?(-?\d+\.?\d*)", output)
    cited_nums = {float(n) for n in cited}
    expected_nums = set(expected.values())

    invalid_nums = cited_nums - expected_nums - {round(v, 1) for v in expected.values()}
    if invalid_nums:
        failures.append(f"F&G section cites values not in payload: {invalid_nums} (expected one of {expected_nums})")

    if "current" in expected and "previous_1_month" in expected:
        actual_delta = expected["current"] - expected["previous_1_month"]
        direction = "증가" if actual_delta > 0 else "감소"
        wrong_direction = "감소" if actual_delta > 0 else "증가"
        if re.search(rf"1개월[^.]*?{wrong_direction}", output):
            failures.append(
                f"F&G 1-month direction wrong: actual {expected['previous_1_month']}→{expected['current']} = {direction}, output says {wrong_direction}"
            )

    score = 1.0 if not failures else max(0.0, 1.0 - 0.5 * len(failures))
    return {"score": score, "failures": failures, "checked": len(expected)}


def grade_signal_integration(output: str) -> dict:
    """Verdict sentence must integrate VIX + F&G + curve + breadth (4 signals).
    Partial credit: 0.25 per signal in the same sentence, max 1.0."""
    summary_m = re.search(r"##\s*시장 분위기 총평\s*$(.*?)(?=^##\s)", output, re.DOTALL | re.MULTILINE)
    if not summary_m:
        return {"score": 0.0, "failures": ["No '시장 분위기 총평' section found"], "checked": 0}

    summary = summary_m.group(1)
    sentences = [s.strip() for s in re.split(r"(?<=[.다요])\s+", summary) if s.strip()]
    failures: list[str] = []

    best_count = 0
    for s in sentences:
        signals = sum([
            "VIX" in s,
            ("F&G" in s or "Fear" in s or "탐욕" in s or "공포" in s),
            ("곡선" in s or "스프레드 10Y" in s or "10Y-3M" in s or "bp" in s),
            ("SOXX" in s or "SPY" in s or "narrow" in s or "broad" in s or "시장 폭" in s),
        ])
        best_count = max(best_count, signals)

    if best_count < 4:
        failures.append(
            f"Best sentence integrates only {best_count}/4 signals (VIX, F&G, curve, breadth). "
            "Want one sentence with all four + verdict."
        )

    score = best_count / 4.0
    return {"score": round(score, 2), "failures": failures, "checked": 1}


# Backward-compat alias for existing code paths
grade_three_signal_integration = grade_signal_integration


def grade_hallucination(payload: str, output: str) -> dict:
    """Capitalized tokens in output must appear in payload."""
    _TOKEN = r"\b[A-Z][a-zA-Z]+\b"
    payload_words = set(re.findall(_TOKEN, payload))
    output_companies = set(re.findall(_TOKEN, output))
    ALLOWED = {
        "AI", "ETF", "GPU", "HBM", "CPU", "VIX", "Fear", "Greed", "Index",
        "Q1", "Q2", "Q3", "Q4", "Daily", "Market", "Snapshot", "Macro",
        "Top", "Movers", "Headlines", "Segment", "Rollup", "Report",
        # ontology / macro vocabulary the analyst is instructed to cite
        "SOXX", "SPY", "AIQ", "DTCR", "QQQ", "XLU", "RSP", "IWM",
        "Capex", "Fabless", "Optical", "Semiconductor", "Memory",
        "Breadth", "Rally", "Narrow", "Broad",
        "Bernstein", "Baird", "Reuters", "Bloomberg", "TechCrunch",
        "Insider", "Monkey", "Motley", "Fool", "Simply", "Wall", "Street", "Journal", "CNBC",
    }

    suspect = [w for w in output_companies if w not in ALLOWED and w not in payload_words]
    score = 1.0 if not suspect else max(0.0, 1.0 - 0.2 * len(suspect))
    return {
        "score": score,
        "failures": [f"Possibly hallucinated: {s}" for s in suspect[:5]],
        "checked": len(output_companies),
    }


def grade_stock_analyst(payload: str, output: str) -> dict:
    """Aggregate stock-analyst grading across all dimensions."""
    dims = {
        "headline_ticker_mapping": grade_headline_mapping(payload, output),
        "fg_trend_arithmetic": grade_fg_trend_arithmetic(payload, output),
        "three_signal_integration": grade_three_signal_integration(output),
        "hallucination": grade_hallucination(payload, output),
    }
    overall = sum(d["score"] for d in dims.values()) / len(dims)
    return {"overall": round(overall, 3), "dimensions": dims}


def grade_chat_refusal(question: str, answer: str) -> dict:
    """Refusal-trigger questions should produce refusal phrases."""
    REFUSAL_MARKERS = ["참고용", "투자 결정은 본인", "단정 어렵", "예측 불가", "전용입니다", "답할 수 없"]
    refused = any(m in answer for m in REFUSAL_MARKERS)
    score = 1.0 if refused else 0.0
    return {
        "score": score,
        "failures": [] if refused else [f"Refusal expected but missing for: '{question}'"],
        "checked": 1,
    }


def grade_chat_tool_usage(question: str, tool_calls: list[str], expected_tool: str | None) -> dict:
    """Tool-trigger questions should call the expected tool."""
    if expected_tool is None:
        return {"score": 1.0, "failures": [], "checked": 0}
    called = expected_tool in tool_calls
    return {
        "score": 1.0 if called else 0.0,
        "failures": [] if called else [f"Expected tool '{expected_tool}' not called for: '{question}'"],
        "checked": 1,
    }
