"""Usage meter: tokens, estimated cost and estimated water for every agent run.

Tokens come straight from the API response (exact). Cost and water are estimates built
from the assumptions in data/usage_rules.json, shown as a low / typical / high range.
"""

from __future__ import annotations

from typing import Any

import store


def rules() -> dict[str, Any]:
    return store.read_json("usage_rules.json")


def estimate(input_tokens: int, cached_tokens: int, output_tokens: int) -> dict[str, Any]:
    r = rules()
    p = r["price_usd_per_million_tokens"]
    uncached = max(input_tokens - cached_tokens, 0)
    cost = (uncached * p["input"] + cached_tokens * p["cached_input"] + output_tokens * p["output"]) / 1e6
    weighted = output_tokens + 0.25 * uncached + 0.05 * cached_tokens
    water = {}
    for level in ("low", "typical", "high"):
        wh = weighted / 1000 * r["energy_wh_per_1k_tokens"][level]
        water[level] = round(wh / 1000 * r["water_l_per_kwh"][level] * 1000, 3)  # mL
    return {"cost_usd": round(cost, 6), "water_ml": water}


def record(s: dict[str, Any], agent: str, run_usage: Any, ref: str | None, seconds: float) -> dict[str, Any]:
    inp = run_usage.input_tokens or 0
    cached = run_usage.cache_read_tokens or 0
    out = run_usage.output_tokens or 0
    reasoning = (run_usage.details or {}).get("reasoning_tokens", 0)
    entry = {
        "id": store.new_id("use"),
        "ts": store.now(),
        "agent": agent,
        "ref": ref,
        "requests": run_usage.requests,
        "tool_calls": getattr(run_usage, "tool_calls", 0),
        "input_tokens": inp,
        "cached_input_tokens": cached,
        "output_tokens": out,
        "reasoning_tokens": reasoning,
        "seconds": round(seconds, 1),
        **estimate(inp, cached, out),
    }
    s["usage"].append(entry)
    return entry


def summary(s: dict[str, Any]) -> dict[str, Any]:
    u = s["usage"]
    tot = {k: sum(x[k] for x in u) for k in ("input_tokens", "cached_input_tokens", "output_tokens",
                                             "reasoning_tokens", "cost_usd")}
    water = {lvl: round(sum(x["water_ml"][lvl] for x in u), 2) for lvl in ("low", "typical", "high")}
    by_agent: dict[str, dict[str, Any]] = {}
    for x in u:
        a = by_agent.setdefault(x["agent"], {"agent": x["agent"], "runs": 0, "input_tokens": 0,
                                             "cached_input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0,
                                             "water_ml_typical": 0.0})
        a["runs"] += 1
        a["input_tokens"] += x["input_tokens"]
        a["cached_input_tokens"] += x["cached_input_tokens"]
        a["output_tokens"] += x["output_tokens"]
        a["cost_usd"] += x["cost_usd"]
        a["water_ml_typical"] += x["water_ml"]["typical"]
    cache_rate = tot["cached_input_tokens"] / tot["input_tokens"] if tot["input_tokens"] else 0
    r = rules()
    return {
        "runs": len(u),
        **{k: round(v, 6) if k == "cost_usd" else v for k, v in tot.items()},
        "cache_hit_rate": round(cache_rate, 3),
        "water_ml": water,
        "by_agent": sorted(by_agent.values(), key=lambda a: -a["output_tokens"]),
        "recent": list(reversed(u[-40:])),
        "assumptions": {k: v for k, v in r.items() if k != "comparisons_ml"},
        "comparisons_ml": r["comparisons_ml"],
    }
