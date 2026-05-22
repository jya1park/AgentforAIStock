"""Unit tests for auto.py best-of-N selection logic."""

from evals import auto


def test_overall_score_normalizes_llm_dimensions():
    """rule means stay 0-1, llm_ means get /5."""
    results = {
        "stock_analyst": {"summary": {"means": {
            "headline_ticker_mapping": 1.0,
            "llm_thesis_usage": 3.5,
        }}},
        "chat_assistant": {"summary": {"means": {}}},
    }
    # avg of [1.0, 3.5/5=0.7] = 0.85
    assert auto._overall_score(results) == 0.85


def test_overall_score_empty_returns_zero():
    results = {"stock_analyst": {"summary": {"means": {}}},
               "chat_assistant": {"summary": {"means": {}}}}
    assert auto._overall_score(results) == 0.0


def test_select_best_identifies_max_score(monkeypatch, capsys, tmp_path):
    """Best round should be the one with the highest score, regardless of order."""
    git_calls = []
    monkeypatch.setattr(auto, "_git", lambda *args: git_calls.append(args) or "abc12345" * 5)
    monkeypatch.setattr(auto, "_revert_to", lambda h: git_calls.append(("revert", h)))
    monkeypatch.setattr(auto, "_commit_best_summary", lambda b, r: None)

    history = [
        {"round": 1, "commit": "aaaa1111" * 5, "score": 0.70},
        {"round": 2, "commit": "bbbb2222" * 5, "score": 0.82},  # best
        {"round": 3, "commit": "cccc3333" * 5, "score": 0.75},
    ]
    auto._select_best(history, skip=False)
    out = capsys.readouterr().out
    assert "Best round: R2" in out
    assert "0.8200" in out
    # Should have called revert to bbbb...
    assert any(c[0] == "revert" and c[1].startswith("bbbb") for c in git_calls)


def test_select_best_skips_when_already_at_best(monkeypatch, capsys):
    """If current HEAD == best commit, no reset needed."""
    monkeypatch.setattr(auto, "_git", lambda *args: "current_hash_at_best")
    revert_calls = []
    monkeypatch.setattr(auto, "_revert_to", lambda h: revert_calls.append(h))
    monkeypatch.setattr(auto, "_commit_best_summary", lambda b, r: None)

    history = [{"round": 5, "commit": "current_hash_at_best", "score": 0.9}]
    auto._select_best(history, skip=False)
    assert revert_calls == []
    assert "Already at best" in capsys.readouterr().out


def test_select_best_respects_skip_flag(monkeypatch, capsys):
    """--no-select-best: print ranking but don't reset."""
    monkeypatch.setattr(auto, "_git", lambda *args: "head_hash")
    revert_calls = []
    monkeypatch.setattr(auto, "_revert_to", lambda h: revert_calls.append(h))
    monkeypatch.setattr(auto, "_commit_best_summary", lambda b, r: None)

    history = [
        {"round": 1, "commit": "a" * 40, "score": 0.7},
        {"round": 2, "commit": "b" * 40, "score": 0.9},
    ]
    auto._select_best(history, skip=True)
    assert revert_calls == []
    assert "--no-select-best" in capsys.readouterr().out


def test_select_best_handles_empty_history(capsys):
    auto._select_best([], skip=False)
    assert "no rounds completed" in capsys.readouterr().out


def test_commit_best_summary_writes_ranking_table(monkeypatch, tmp_path):
    """best_round.md must list every round with its commit + score, marking the winner."""
    monkeypatch.setattr(auto, "_git", lambda *args: "" if args[0] == "status" else "ok")

    fake_patches_dir = tmp_path / "patches"
    fake_patches_dir.mkdir()
    monkeypatch.setattr(auto, "__file__", str(tmp_path / "auto.py"))

    # Use a tmp_path-based path resolution
    import evals.auto as auto_mod
    original_write = auto_mod._commit_best_summary

    best = {"round": 2, "commit": "b" * 40, "score": 0.85}
    other = {"round": 1, "commit": "a" * 40, "score": 0.70}
    ranked = [best, other]  # identity match for "← best" marker
    original_write(best, ranked)

    summary = (auto_mod.Path(auto_mod.__file__).resolve().parent / "patches" / "best_round.md")
    text = summary.read_text(encoding="utf-8")
    assert "Round 2" in text
    assert "0.8500" in text
    assert "← best" in text
    assert "| R1 |" in text
