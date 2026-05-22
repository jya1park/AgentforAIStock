"""Unit tests for the patcher and the apply/audit pipeline."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

from evals import patcher


def _claude_response(payload: dict):
    return SimpleNamespace(content=[SimpleNamespace(text=json.dumps(payload))])


def test_apply_patches_writes_replacement(monkeypatch, tmp_path):
    fake_prompt = tmp_path / "stock-analyst.md"
    fake_prompt.write_text("rule A\nrule B\nrule C", encoding="utf-8")
    monkeypatch.setitem(patcher.ALLOWED_FILES, "stock-analyst.md", fake_prompt)

    results = patcher.apply_patches([{
        "file": "stock-analyst.md",
        "old_text": "rule B",
        "new_text": "rule B (refined)",
        "reason": "refinement",
    }])
    assert results[0]["status"] == "applied"
    assert "rule B (refined)" in fake_prompt.read_text(encoding="utf-8")


def test_apply_patches_skips_when_old_text_missing(monkeypatch, tmp_path):
    fake = tmp_path / "stock-analyst.md"
    fake.write_text("only content", encoding="utf-8")
    monkeypatch.setitem(patcher.ALLOWED_FILES, "stock-analyst.md", fake)

    results = patcher.apply_patches([{
        "file": "stock-analyst.md", "old_text": "nonexistent", "new_text": "x", "reason": "r",
    }])
    assert results[0]["status"] == "skipped"
    assert "not found" in results[0]["error"]
    assert fake.read_text(encoding="utf-8") == "only content"  # unchanged


def test_apply_patches_skips_when_old_text_not_unique(monkeypatch, tmp_path):
    fake = tmp_path / "stock-analyst.md"
    fake.write_text("dup\nother\ndup", encoding="utf-8")
    monkeypatch.setitem(patcher.ALLOWED_FILES, "stock-analyst.md", fake)

    results = patcher.apply_patches([{
        "file": "stock-analyst.md", "old_text": "dup", "new_text": "x", "reason": "r",
    }])
    assert results[0]["status"] == "skipped"
    assert "not unique" in results[0]["error"]
    assert fake.read_text(encoding="utf-8") == "dup\nother\ndup"


def test_apply_patches_rejects_non_whitelisted_file(tmp_path):
    results = patcher.apply_patches([{
        "file": "ontology.yaml", "old_text": "x", "new_text": "y", "reason": "evil",
    }])
    assert results[0]["status"] == "skipped"
    assert "not whitelisted" in results[0]["error"]


def test_summarize_failures_groups_by_dimension():
    failures = [
        "v01 [three_signal_integration]: nothing integrated",
        "v02 [three_signal_integration]: missing curve",
        "v03 [hallucination]: SPY",
        "q01 [refusal]: missed disclaimer",
    ]
    counts, samples = patcher._summarize_failures(failures)
    assert "three_signal_integration: 2 failures" in counts
    assert "hallucination: 1 failures" in counts
    assert "[three_signal_integration]" in samples


def test_propose_patches_truncates_to_max(monkeypatch, tmp_path):
    monkeypatch.setattr(patcher, "AGENTS_DIR", tmp_path)
    for f in ("stock-analyst.md", "chat-assistant.md", "red-team.md"):
        (tmp_path / f).write_text(f"# {f}\nrule", encoding="utf-8")
        monkeypatch.setitem(patcher.ALLOWED_FILES, f, tmp_path / f)

    fake_client = MagicMock()
    fake_client.messages.create = lambda **kw: _claude_response({
        "patches": [
            {"file": "stock-analyst.md", "old_text": "rule", "new_text": "rule v1", "reason": "r", "target_dimension": "d"},
            {"file": "stock-analyst.md", "old_text": "rule", "new_text": "rule v2", "reason": "r", "target_dimension": "d"},
            {"file": "stock-analyst.md", "old_text": "rule", "new_text": "rule v3", "reason": "r", "target_dimension": "d"},
            {"file": "stock-analyst.md", "old_text": "rule", "new_text": "rule v4", "reason": "r", "target_dimension": "d"},
        ]
    })
    monkeypatch.setattr(patcher, "Anthropic", lambda: fake_client)

    results = {"stock_analyst": {"summary": {"means": {}, "failures": []}},
               "chat_assistant": {"summary": {"means": {}, "failures": []}}}
    patches = patcher.propose_patches(results, round_num=2, max_patches=3)
    assert len(patches) == 3


def test_write_audit_renders_markdown(monkeypatch, tmp_path):
    monkeypatch.setattr(patcher, "PATCHES_DIR", tmp_path)
    results = {
        "stock_analyst": {"summary": {"means": {"three_signal_integration": 0.1}, "failures": []}},
        "chat_assistant": {"summary": {"means": {"llm_refusal_appropriateness": 4.6}, "failures": []}},
    }
    patches = [{"file": "stock-analyst.md", "old_text": "old line", "new_text": "new line",
                "reason": "test reason", "target_dimension": "three_signal_integration"}]
    application = [{"patch": patches[0], "status": "applied"}]
    audit_path = patcher.write_audit(2, results, patches, application)
    text = audit_path.read_text(encoding="utf-8")
    assert "Round 2" in text
    assert "0.1" in text  # score before
    assert "test reason" in text
    assert "✅" in text
    assert "- old line" in text
    assert "+ new line" in text
