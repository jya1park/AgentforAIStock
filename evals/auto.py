"""Full-auto loop: run round → patch → commit → next round.
Rollback if overall score drops by more than --tolerance.

Usage:
  python -m evals.auto --start-round 2 --max-rounds 5 --n-payloads 10 --n-questions 30

Safety nets:
- Every round is git-committed BEFORE the next round runs, so rollback = `git reset --hard` to that commit.
- If the next round's overall score drops by more than `tolerance`, the patch commit is reverted
  and the loop stops with an explanation.
- Max-rounds cap (default 5) prevents runaway spend.
"""

import argparse
import json
import subprocess
from datetime import datetime
from pathlib import Path

from src import config  # noqa: F401 — .env autoload

from evals import patcher, runner


def _git(*args: str) -> str:
    """Run git with the given args from repo root; return stdout, raise on non-zero."""
    cp = subprocess.run(
        ["git", *args],
        cwd=Path(__file__).resolve().parent.parent,
        capture_output=True, text=True, check=True,
    )
    return cp.stdout.strip()


def _overall_score(round_results: dict) -> float:
    """Average of all numeric means from both stock-analyst and chat-assistant.
    Normalizes LLM judges (1-5 scale) to 0-1 so they weight comparably with rule graders."""
    nums: list[float] = []
    for section in ("stock_analyst", "chat_assistant"):
        means = round_results.get(section, {}).get("summary", {}).get("means", {})
        for key, val in means.items():
            if key.startswith("llm_"):
                nums.append(val / 5.0)
            else:
                nums.append(val)
    return round(sum(nums) / len(nums), 4) if nums else 0.0


def _commit_patches(round_num: int, n_applied: int) -> str | None:
    """Stage agent prompts + the audit file and commit. Returns commit hash, or None if nothing to commit."""
    _git("add", ".claude/agents/stock-analyst.md", ".claude/agents/chat-assistant.md",
         ".claude/agents/red-team.md", f"evals/patches/round_{round_num:03d}.md")
    status = _git("status", "--porcelain", "--", ".claude/agents/", "evals/patches/")
    if not status:
        return None
    _git("commit", "-m", f"eval round {round_num}: auto-patch ({n_applied} applied)")
    return _git("rev-parse", "HEAD")


def _revert_to(commit_hash: str) -> None:
    """Hard reset to the given commit (rolls back the last auto-patch commit)."""
    _git("reset", "--hard", commit_hash)


def run_one_round(round_num: int, n_payloads: int, n_questions: int,
                  gen_model: str, judge_model: str) -> tuple[Path, dict]:
    """Run a single eval round. Returns (results_path, parsed_results)."""
    print(f"--- Round {round_num} eval ---")
    stock_results = runner.run_stock_analyst_evals(n_payloads, gen_model, judge_model)
    chat_results = runner.run_chat_evals(n_questions, gen_model, judge_model)
    stock_summary = runner.aggregate(stock_results, "stock")
    chat_summary = runner.aggregate(chat_results, "chat")
    path = runner.save_round(round_num, stock_summary, chat_summary, stock_results, chat_results)
    results = {
        "round": round_num,
        "stock_analyst": {"summary": stock_summary, "results": stock_results},
        "chat_assistant": {"summary": chat_summary, "results": chat_results},
    }
    return path, results


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--start-round", type=int, required=True)
    p.add_argument("--max-rounds", type=int, default=5)
    p.add_argument("--n-payloads", type=int, default=10)
    p.add_argument("--n-questions", type=int, default=30)
    p.add_argument("--gen-model", default="gpt-4o")
    p.add_argument("--judge-model", default="claude-sonnet-4-6")
    p.add_argument("--patcher-model", default="claude-opus-4-7")
    p.add_argument("--tolerance", type=float, default=0.05,
                   help="Max score drop allowed before rollback (overall, 0-1 scale)")
    args = p.parse_args()

    print(f"=== Auto-loop start: rounds {args.start_round}..{args.start_round + args.max_rounds - 1} ===")
    print(f"gen={args.gen_model}, judge={args.judge_model}, patcher={args.patcher_model}, tolerance={args.tolerance}")

    last_score = None
    last_pre_patch_commit = _git("rev-parse", "HEAD")

    for r in range(args.start_round, args.start_round + args.max_rounds):
        path, results = run_one_round(r, args.n_payloads, args.n_questions,
                                       args.gen_model, args.judge_model)
        score = _overall_score(results)
        print(f"  → overall score: {score:.4f}")

        if last_score is not None and score < last_score - args.tolerance:
            print(f"  ⚠️ score dropped {last_score:.4f} → {score:.4f} (tolerance {args.tolerance})")
            print(f"  Rolling back to commit {last_pre_patch_commit[:8]}")
            _revert_to(last_pre_patch_commit)
            print(f"  Loop stopped. Inspect evals/patches/round_{r-1:03d}.md for the bad patch.")
            return

        last_score = score

        if r == args.start_round + args.max_rounds - 1:
            print(f"=== Reached max-rounds ({args.max_rounds}); stopping without patching ===")
            return

        # Patch + commit (pre-next-round)
        print(f"--- Round {r} patching ---")
        try:
            patches = patcher.propose_patches(results, round_num=r, model=args.patcher_model)
        except Exception as e:
            print(f"  patcher error: {e}; loop continues without patch")
            continue
        application = patcher.apply_patches(patches)
        audit_path = patcher.write_audit(r, results, patches, application)
        n_applied = sum(1 for a in application if a["status"] == "applied")
        print(f"  proposed {len(patches)}, applied {n_applied} → audit at {audit_path}")

        last_pre_patch_commit = _git("rev-parse", "HEAD")  # checkpoint BEFORE this round's commit
        commit_hash = _commit_patches(r, n_applied)
        if commit_hash:
            print(f"  committed {commit_hash[:8]}")
        else:
            print("  no agent-prompt changes to commit")


if __name__ == "__main__":
    main()
