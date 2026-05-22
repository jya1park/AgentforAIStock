"""Patcher: read round_N.json, ask Claude Opus for surgical prompt edits, apply them.

Safety:
- Whitelist: only stock-analyst.md / chat-assistant.md / red-team.md can be edited.
- Surgical edits only — `old_text` must be unique inside the target file or the patch is skipped.
- Max 3 patches per round (LLM is instructed; runner also enforces).
- Every applied patch is logged to evals/patches/round_NNN.md as an audit trail.
"""

import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

from anthropic import Anthropic

ROOT = Path(__file__).resolve().parent.parent
AGENTS_DIR = ROOT / ".claude" / "agents"
PATCHES_DIR = Path(__file__).resolve().parent / "patches"

ALLOWED_FILES = {
    "stock-analyst.md": AGENTS_DIR / "stock-analyst.md",
    "chat-assistant.md": AGENTS_DIR / "chat-assistant.md",
    "red-team.md": AGENTS_DIR / "red-team.md",
}

MAX_PATCHES_PER_ROUND = 3
DEFAULT_PATCHER_MODEL = "claude-opus-4-7"

_PATCHER_PROMPT = """You analyze evaluation failures for a Korean stock-analyst LLM system and propose surgical prompt edits.

# Round {round_num} aggregate scores
{summary}

# Failure patterns (most common first)
{failure_summary}

# Sample failure details (first 15)
{failure_samples}

# Current prompts you can edit

## stock-analyst.md
```
{stock_analyst}
```

## chat-assistant.md
```
{chat_assistant}
```

## red-team.md
```
{red_team}
```

# Your task
Propose **up to {max_patches} atomic edits** that should improve the worst-scoring dimension(s).

Rules:
1. Each edit is a string-replace: `old_text` (must be unique inside the target file, copy it verbatim from the prompt above) → `new_text`.
2. Prefer adding 1-3 lines or swapping a sentence over rewriting whole sections.
3. Anchor edits to specific failure quotes from the round when possible — quoting the actual broken output in a negative example makes the rule sticky.
4. If you can't safely improve any dimension, return an empty patches list. Don't make changes you're unsure about.
5. Never edit non-rule sections (frontmatter, agent name, description).

Return JSON only:
{{"patches": [
  {{"file": "stock-analyst.md", "old_text": "...verbatim...", "new_text": "...", "reason": "one sentence", "target_dimension": "three_signal_integration"}},
  ...
]}}"""


def _read_prompt(name: str) -> str:
    return ALLOWED_FILES[name].read_text(encoding="utf-8")


def _summarize_failures(failures: list[str]) -> tuple[str, str]:
    """Group failures by '[dimension]' tag prefix; return (count_summary, top_examples)."""
    dim_counts: Counter = Counter()
    by_dim: dict[str, list[str]] = {}
    for f in failures:
        m = re.search(r"\[([^\]]+)\]:?\s*(.*)", f)
        if m:
            dim = m.group(1)
            rest = m.group(2)
        else:
            dim = "other"
            rest = f
        dim_counts[dim] += 1
        by_dim.setdefault(dim, []).append(rest[:240])

    count_lines = [f"- {dim}: {n} failures" for dim, n in dim_counts.most_common()]
    sample_lines = []
    for dim, items in by_dim.items():
        for s in items[:3]:
            sample_lines.append(f"[{dim}] {s}")
        if len(sample_lines) >= 15:
            break
    return "\n".join(count_lines), "\n".join(sample_lines[:15])


def propose_patches(round_results: dict, round_num: int, model: str = DEFAULT_PATCHER_MODEL,
                    max_patches: int = MAX_PATCHES_PER_ROUND) -> list[dict]:
    """Call Claude Opus to propose surgical prompt edits. Returns list of patch dicts."""
    failures = (round_results.get("stock_analyst", {}).get("summary", {}).get("failures", []) +
                round_results.get("chat_assistant", {}).get("summary", {}).get("failures", []))
    means = {
        "stock": round_results.get("stock_analyst", {}).get("summary", {}).get("means", {}),
        "chat": round_results.get("chat_assistant", {}).get("summary", {}).get("means", {}),
    }
    count_sum, samples = _summarize_failures(failures)
    prompt = _PATCHER_PROMPT.format(
        round_num=round_num,
        max_patches=max_patches,
        summary=json.dumps(means, ensure_ascii=False, indent=2),
        failure_summary=count_sum,
        failure_samples=samples,
        stock_analyst=_read_prompt("stock-analyst.md"),
        chat_assistant=_read_prompt("chat-assistant.md"),
        red_team=_read_prompt("red-team.md"),
    )
    resp = Anthropic().messages.create(
        model=model, max_tokens=8192,
        messages=[{"role": "user", "content": prompt}],
    )
    text = resp.content[0].text
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        raise ValueError(f"patcher returned no JSON: {text[:300]}")
    patches = json.loads(m.group(0)).get("patches", [])
    return patches[:max_patches]


def apply_patches(patches: list[dict]) -> list[dict]:
    """Apply each patch as a string-replace. Returns list of {patch, status, error?}."""
    results = []
    for p in patches:
        fname = p.get("file")
        path = ALLOWED_FILES.get(fname)
        if not path:
            results.append({"patch": p, "status": "skipped", "error": f"file not whitelisted: {fname}"})
            continue
        text = path.read_text(encoding="utf-8")
        old = p.get("old_text", "")
        new = p.get("new_text", "")
        count = text.count(old)
        if count == 0:
            results.append({"patch": p, "status": "skipped", "error": "old_text not found in file"})
            continue
        if count > 1:
            results.append({"patch": p, "status": "skipped", "error": f"old_text matches {count} places — not unique"})
            continue
        path.write_text(text.replace(old, new, 1), encoding="utf-8")
        results.append({"patch": p, "status": "applied"})
    return results


def write_audit(round_num: int, round_results: dict, patches: list[dict],
                application: list[dict]) -> Path:
    """Write evals/patches/round_NNN.md as the audit log."""
    PATCHES_DIR.mkdir(exist_ok=True)
    means_stock = round_results.get("stock_analyst", {}).get("summary", {}).get("means", {})
    means_chat = round_results.get("chat_assistant", {}).get("summary", {}).get("means", {})

    lines = [
        f"# Round {round_num} — auto-patch audit",
        f"_generated: {datetime.now().isoformat(timespec='seconds')}_",
        "",
        "## Scores before this round's patches",
        "### stock-analyst",
        "```json",
        json.dumps(means_stock, ensure_ascii=False, indent=2),
        "```",
        "### chat-assistant",
        "```json",
        json.dumps(means_chat, ensure_ascii=False, indent=2),
        "```",
        "",
        f"## Patches proposed: {len(patches)}",
    ]
    for i, p in enumerate(patches, 1):
        applied = next((a for a in application if a["patch"] is p), {"status": "unknown"})
        status_icon = {"applied": "✅", "skipped": "⚠️"}.get(applied["status"], "❓")
        lines.extend([
            f"",
            f"### Patch {i}: {status_icon} `{p.get('file')}` — {p.get('target_dimension', 'n/a')}",
            f"**Reason**: {p.get('reason', '(no reason)')}",
            f"**Status**: {applied['status']}" + (f" ({applied['error']})" if applied.get("error") else ""),
            "",
            "**Diff**:",
            "```diff",
            *[f"- {line}" for line in p.get("old_text", "").splitlines()],
            *[f"+ {line}" for line in p.get("new_text", "").splitlines()],
            "```",
        ])

    applied_count = sum(1 for a in application if a["status"] == "applied")
    lines.extend([
        "",
        f"## Summary",
        f"- Proposed: {len(patches)}",
        f"- Applied: {applied_count}",
        f"- Skipped: {len(patches) - applied_count}",
    ])
    path = PATCHES_DIR / f"round_{round_num:03d}.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
