"""Single-turn question answering grounded in latest report + ontology thesis."""

from src.agents import call_agent
from src.main import REPORTS_DIR, _thesis_block
from src.ontology import Ontology


def _latest_report() -> str:
    """Return text of the most recent reports/YYYY-MM-DD_{morning,evening}.md, '' if none."""
    if not REPORTS_DIR.exists():
        return ""
    reports = [p for p in REPORTS_DIR.glob("*.md") if "_redteam" not in p.name]
    if not reports:
        return ""
    return sorted(reports)[-1].read_text(encoding="utf-8")


def _build_context() -> str:
    report = _latest_report() or "(아직 생성된 리포트가 없습니다)"
    thesis = _thesis_block(Ontology.load().thesis_entries())
    return f"# 최근 리포트\n{report}\n\n{thesis}"


def answer(question: str) -> str:
    """GPT-4o response to user question, grounded in latest report + ontology."""
    payload = f"{_build_context()}\n\n# 질문\n{question}"
    return call_agent("chat-assistant", payload, model="gpt-4o")
