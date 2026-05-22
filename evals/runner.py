"""Eval runner: generate payloads/questions → run agents → grade → aggregate.
Usage:
  python -m evals.runner --round 1 --n-payloads 10 --n-questions 30
  python -m evals.runner --round 2 --n-payloads 10 --skip-chat
"""

import argparse
import json
from datetime import datetime
from pathlib import Path

from src import config  # noqa: F401 — autoload .env
from src.agents import call_agent
from src.chat_handler import answer as chat_answer
from src.main import _extract_long_body

from evals import generators, graders, judges

RESULTS_DIR = Path(__file__).resolve().parent / "results"


def run_stock_analyst_evals(n: int, gen_model: str, judge_model: str) -> list[dict]:
    """Generate N payload variants, run stock-analyst (production gpt-4o), Claude-judge."""
    variants = generators.perturb_payloads(n=n, model=gen_model)
    results = []
    for v in variants:
        payload = v["payload"]
        print(f"  [stock-analyst] {v['id']}...")
        try:
            raw = call_agent("stock-analyst", f"mode=morning\n\n{payload}", model=gen_model)
            output = _extract_long_body(raw)
        except Exception as e:
            results.append({"id": v["id"], "error": str(e)})
            continue
        rule_grade = graders.grade_stock_analyst(payload, output)
        try:
            llm_grade = judges.judge_stock_analyst(payload, output, model=judge_model)
        except Exception as e:
            llm_grade = {"error": str(e)}
        results.append({
            "id": v["id"],
            "payload": payload,
            "output": output,
            "rule_grade": rule_grade,
            "llm_grade": llm_grade,
        })
    return results


_SAMPLE_REPORT_PATH = Path(__file__).resolve().parent / "seeds" / "sample_report.md"


def run_chat_evals(n: int, gen_model: str, judge_model: str) -> list[dict]:
    """Generate N chat questions, run chat-assistant with a fixed sample report context, Claude-judge.
    Using a fixed context makes grounding measurable — judge sees the same report the model saw."""
    sample_context = _SAMPLE_REPORT_PATH.read_text(encoding="utf-8")
    questions = generators.perturb_questions(n=n, model=gen_model)
    results = []
    for q in questions:
        print(f"  [chat] {q['id']} ({q['category']})...")
        try:
            reply = chat_answer(q["text"], context_override=sample_context)
        except Exception as e:
            results.append({"id": q["id"], "error": str(e)})
            continue

        rule_grade = {}
        if q["category"] == "refusal_triggers":
            rule_grade["refusal"] = graders.grade_chat_refusal(q["text"], reply)

        try:
            llm_grade = judges.judge_chat_answer(q["text"], sample_context, reply, model=judge_model)
        except Exception as e:
            llm_grade = {"error": str(e)}

        results.append({
            "id": q["id"],
            "category": q["category"],
            "question": q["text"],
            "answer": reply,
            "rule_grade": rule_grade,
            "llm_grade": llm_grade,
        })
    return results


def aggregate(results: list[dict], kind: str) -> dict:
    """Average scores across results; collect all failure strings."""
    failures: list[str] = []
    dim_scores: dict[str, list[float]] = {}

    for r in results:
        if "error" in r:
            failures.append(f"{r['id']}: ERROR {r['error']}")
            continue
        for d, payload in (r.get("rule_grade") or {}).get("dimensions", {}).items() if kind == "stock" else r.get("rule_grade", {}).items():
            dim_scores.setdefault(d, []).append(payload["score"])
            for f in payload.get("failures", []):
                failures.append(f"{r['id']} [{d}]: {f}")
        if kind == "chat":
            for d, payload in (r.get("rule_grade") or {}).items():
                dim_scores.setdefault(d, []).append(payload["score"])
        llm = r.get("llm_grade") or {}
        if isinstance(llm, dict) and "error" not in llm:
            for k, v in llm.items():
                if isinstance(v, (int, float)):
                    dim_scores.setdefault(f"llm_{k}", []).append(v)
            for issue in (llm.get("issues") or []):
                failures.append(f"{r['id']} [llm]: {issue}")

    means = {k: round(sum(v) / len(v), 3) for k, v in dim_scores.items() if v}
    return {"n": len(results), "means": means, "failures": failures}


def save_round(round_num: int, stock: dict, chat: dict, stock_results: list, chat_results: list) -> Path:
    RESULTS_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    payload = {
        "round": round_num,
        "timestamp": stamp,
        "stock_analyst": {"summary": stock, "results": stock_results},
        "chat_assistant": {"summary": chat, "results": chat_results},
    }
    path = RESULTS_DIR / f"round_{round_num:03d}_{stamp}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--round", type=int, required=True)
    p.add_argument("--n-payloads", type=int, default=10)
    p.add_argument("--n-questions", type=int, default=30)
    p.add_argument("--gen-model", default="gpt-5.4", help="OpenAI model for generation + production responses")
    p.add_argument("--judge-model", default="claude-sonnet-4-6", help="Claude model for qualitative judging")
    p.add_argument("--skip-stock", action="store_true")
    p.add_argument("--skip-chat", action="store_true")
    args = p.parse_args()

    print(f"=== Round {args.round} (gen={args.gen_model}, judge={args.judge_model}) ===")
    stock_results, chat_results = [], []
    stock_summary, chat_summary = {}, {}

    if not args.skip_stock:
        print(f"Stock-analyst evals (n={args.n_payloads})...")
        stock_results = run_stock_analyst_evals(args.n_payloads, args.gen_model, args.judge_model)
        stock_summary = aggregate(stock_results, "stock")
        print(f"  means: {stock_summary['means']}")
        print(f"  failures: {len(stock_summary['failures'])}")

    if not args.skip_chat:
        print(f"Chat-assistant evals (n={args.n_questions})...")
        chat_results = run_chat_evals(args.n_questions, args.gen_model, args.judge_model)
        chat_summary = aggregate(chat_results, "chat")
        print(f"  means: {chat_summary['means']}")
        print(f"  failures: {len(chat_summary['failures'])}")

    out = save_round(args.round, stock_summary, chat_summary, stock_results, chat_results)
    print(f"saved {out}")


if __name__ == "__main__":
    main()
