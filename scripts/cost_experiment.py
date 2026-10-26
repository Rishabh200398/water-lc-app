"""Cost-cutting experiment for the report (real gpt-6-luna calls; does not touch the app's usage log).

Compares, on identical inputs taken from the demo run:
  A. Event strategist: default reasoning vs reasoning_effort="low"  (3 ideas from the same research brief)
  B. Catering planner: default reasoning vs reasoning_effort="low"  (itemized order within the same budget)
  C. Re-brainstorm with vs without re-running the Research scout (the app reuses the brief by default)
Quality is checked by the same code validators the app uses (they must pass, retries are counted).

    .venv/bin/python scripts/cost_experiment.py      ->  output/cost_experiment.json
"""

import asyncio
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

import agents  # noqa: E402
import store  # noqa: E402
import usage  # noqa: E402
import workflow  # noqa: E402
from pydantic_ai import Agent  # noqa: E402
from pydantic_ai.models.openai import OpenAIResponsesModelSettings  # noqa: E402

N = 3


def with_effort(agent: Agent, role: str, effort: str | None) -> dict:
    s = OpenAIResponsesModelSettings(openai_prompt_cache_key=f"waterlc-{role}", openai_cache_instructions=True)
    if effort:
        s["openai_reasoning_effort"] = effort
    return s


async def measure(agent: Agent, role: str, prompt: str, effort: str | None, deps=None, check=None) -> dict:
    t = time.time()
    try:
        r = await agent.run(prompt, deps=deps, model_settings=with_effort(agent, role, effort))
        ok, note = (check(r.output) if check else (True, ""))
    except Exception as e:  # a failure counts against quality
        return {"ok": False, "note": f"{type(e).__name__}: {e}"[:200], "seconds": round(time.time() - t, 1)}
    u = r.usage
    est = usage.estimate(u.input_tokens, u.cache_read_tokens, u.output_tokens)
    return {"ok": ok, "note": note, "seconds": round(time.time() - t, 1), "requests": u.requests,
            "input": u.input_tokens, "cached": u.cache_read_tokens, "output": u.output_tokens,
            "reasoning": (u.details or {}).get("reasoning_tokens", 0), "cost": est["cost_usd"],
            "water_ml": est["water_ml"]["typical"]}


def summarize(rows: list[dict]) -> dict:
    good = [r for r in rows if "cost" in r]
    m = lambda k: round(statistics.mean(r[k] for r in good), 4) if good else None
    return {"runs": len(rows), "passed": sum(r["ok"] for r in rows), "avg_seconds": m("seconds"), "avg_requests": m("requests"),
            "avg_input": m("input"), "avg_cached": m("cached"), "avg_output": m("output"), "avg_reasoning": m("reasoning"),
            "avg_cost": m("cost"), "avg_water_ml": m("water_ml"), "rows": rows}


async def main() -> None:
    s = store.snapshot()
    ev = next(e for e in s["events"] if e.get("research") and e.get("catering") and e.get("locked"))
    print("Using event:", ev["title"])
    results = {}

    # A. strategist
    prompt_a = (f"Propose three Water LC event ideas.\n\nCO-LEADS' ANSWERS:\n{workflow._intake_text(ev['intake'])}\n\n"
                f"RESEARCH BRIEF:\n{json.dumps(ev['research'], indent=1)}")

    def check_ideas(out):
        titles = {i.title.lower() for i in out.ideas}
        formats_ok = all(i.format == ev["intake"]["format"] for i in out.ideas) if ev["intake"].get("format") else True
        anchored = all(any(w in i.why_now.lower() for w in ("member", "news", "gap", "interest", "report", "recent")) for i in out.ideas)
        return (len(titles) == 3 and formats_ok and anchored,
                f"3 distinct={len(titles) == 3}, format respected={formats_ok}, anchored in brief={anchored}")

    for label, effort in (("default", None), ("low", "low")):
        rows = [await measure(agents.strategist(), "strategist", prompt_a, effort, check=check_ideas) for _ in range(N)]
        results[f"strategist_{label}"] = summarize(rows)
        print("strategist", label, {k: v for k, v in results[f'strategist_{label}'].items() if k != 'rows'})

    # B. catering planner
    budget_env = ev["budget"]["catering_budget"]
    head = ev["expected_attendance"]
    prompt_b = f"Build the catering order.\n{workflow._event_brief(ev)}\nCatering budget: ${budget_env:.2f}. Headcount: {head}."
    deps = agents.CateringDeps(catering_budget=budget_env, headcount=head)

    def check_order(o):
        p = agents.price_order(o.caterer, [i.model_dump() for i in o.items])
        ok = not p["unknown_items"] and p["total"] <= budget_env and p["servings"] >= head * 0.9
        return ok, f"{o.caterer}: ${p['total']:.2f} of ${budget_env:.2f}, {p['servings']} portions"

    for label, effort in (("default", None), ("low", "low")):
        rows = [await measure(agents.catering_planner(), "catering_planner", prompt_b, effort, deps=deps, check=check_order) for _ in range(N)]
        results[f"catering_{label}"] = summarize(rows)
        print("catering", label, {k: v for k, v in results[f'catering_{label}'].items() if k != 'rows'})

    # C. re-brainstorm: reuse the research brief (app default) vs re-run the Research scout every time
    rs = [x for x in s["usage"] if x["agent"] == "research_scout"]
    st = [x for x in s["usage"] if x["agent"] == "strategist"]
    if rs and st:
        rs_cost = statistics.mean(x["cost_usd"] for x in rs)
        st_cost = statistics.mean(x["cost_usd"] for x in st)
        results["rebrainstorm"] = {"research_scout_avg_cost": round(rs_cost, 4), "strategist_avg_cost": round(st_cost, 4),
                                   "rerun_with_new_research": round(rs_cost + st_cost, 4), "rerun_reusing_brief": round(st_cost, 4),
                                   "research_seconds": round(statistics.mean(x["seconds"] for x in rs), 1),
                                   "strategist_seconds": round(statistics.mean(x["seconds"] for x in st), 1)}
        print("rebrainstorm", results["rebrainstorm"])

    (ROOT / "output" / "cost_experiment.json").write_text(json.dumps(results, indent=2))
    print("Saved output/cost_experiment.json")


asyncio.run(main())
