# AI-generated: written with Claude (Anthropic) and reviewed by the team.
"""Latency and cost per session, from the session results. No LLM call.

- latency: engine time per session and per step (ms, p50 and p95). The user's time
           (or the simulated user's LLM call) is never counted.
- cost:    the LLM engine's USD per session, as OpenRouter reports it for each call;
           the decision tree makes no call and costs nothing.
- calls and tokens per session, and the share of sessions with a fallback or an error.
- the simulated user's calls and tokens: benchmark overhead, not part of the app.

"Recommend now" copies are benchmark overhead, not part of a session: their calls
and cost are counted apart.
"""

from __future__ import annotations

import statistics

import numpy as np

from . import ENGINES


def percentile(values, q):
    return float(np.percentile(values, q)) if values else None


def _mean(values):
    return statistics.fmean(values) if values else None


def summary(records) -> dict[str, dict]:
    """{engine: latency and cost figures} for the engines present in `records`."""
    out = {}
    for engine in ENGINES:
        rows = [r for r in records if r["engine"] == engine]
        if not rows:
            continue
        sessions = [r["engine_ms"] for r in rows]
        steps = [ms for r in rows for ms in r.get("step_ms", [])]
        llm = [r.get("llm") or {} for r in rows]
        extra = [r.get("anytime_llm") or {} for r in rows]
        user = [r.get("simulator") or {} for r in rows]
        out[engine] = {
            "sessions": len(rows),
            "session_ms_p50": percentile(sessions, 50), "session_ms_p95": percentile(sessions, 95),
            "step_ms_p50": percentile(steps, 50), "step_ms_p95": percentile(steps, 95),
            "llm_calls": _mean([u.get("calls", 0) for u in llm]),
            "input_tokens": _mean([u.get("input_tokens", 0) for u in llm]),
            "output_tokens": _mean([u.get("output_tokens", 0) for u in llm]),
            "cost_usd": _mean([u.get("cost_usd", 0.0) for u in llm]),
            "cost_usd_p95": percentile([u.get("cost_usd", 0.0) for u in llm], 95),
            "fallback_rate": _mean([u.get("fallbacks", 0) > 0 for u in llm]),
            "error_rate": _mean([r["outcome"] == "error" for r in rows]),
            "recommend_now_calls": sum(u.get("calls", 0) for u in extra),
            "recommend_now_cost_usd": sum(u.get("cost_usd", 0.0) for u in extra),
            "simulator_calls": sum(u.get("calls", 0) for u in user),
            "simulator_input_tokens": sum(u.get("input_tokens", 0) for u in user),
            "simulator_output_tokens": sum(u.get("output_tokens", 0) for u in user),
        }
    return out
