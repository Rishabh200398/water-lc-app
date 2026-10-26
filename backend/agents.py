"""The ten Water LC agents, their tools and what each one must return.

  1. Research scout     web news + member wishes + what we've done + locked ideas -> a brief
  2. Event strategist   brief + co-leads' answers -> 3 event ideas to choose from
  3. Speaker scout      YSE alumni shortlist for the chosen idea (East Coast first for in person)
  4. Speaker outreach   invitation email in the co-leads' voice, asking for a time to talk
  5. Coordinator        reads meeting notes and Jim's replies, writes recaps and the briefing
  6. Budget analyst     event budget by format and mode, checked against hard limits in budget.py
  7. Catering planner   itemized order from a caterer's menu, priced by code, within the catering budget
  8. Approvals & email  request to Jim, then the order to Cristina
  9. Marketing          Yale Connect, WhatsApp, reminder and poster text
 10. Newsletter editor  monthly issue in the house template, with web research

Every agent shares the handbook (prompts/handbook.md) as the first, unchanging part of its
instructions, so OpenAI can cache it. Every run goes through run_agent(), which logs tokens,
cost and estimated water to the usage meter.
"""

from __future__ import annotations

import asyncio
import time
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field
from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.capabilities import WebSearch
from pydantic_ai.exceptions import ModelConnectionError
from pydantic_ai.models.openai import OpenAIResponsesModelSettings

import budget
import store
import usage
from model_config import build_model

PROMPTS = Path(__file__).resolve().parent / "prompts"

FORMATS = ["lunch and learn", "seminar", "student-led webinar", "career session", "field visit", "social"]
EXTRAS = ("Bottled water", "Plates cutlery and napkins")


def _instructions(role: str) -> str:
    return (PROMPTS / "handbook.md").read_text() + "\n\n" + (PROMPTS / f"{role}.md").read_text()


# Lower reasoning effort where scripts/cost_experiment.py showed no quality loss (all checks passed,
# 10-14% cheaper per run, up to 45% fewer output tokens).
LOW_EFFORT = {"strategist", "catering_planner"}


def _settings(role: str) -> OpenAIResponsesModelSettings:
    s = OpenAIResponsesModelSettings(openai_prompt_cache_key=f"waterlc-{role}", openai_cache_instructions=True)
    if role in LOW_EFFORT:
        s["openai_reasoning_effort"] = "low"
    return s


# ================================================================ output shapes


class EmailDraft(BaseModel):
    to_name: str = Field(description="Who the email is for, e.g. 'Jim Saiers'.")
    subject: str
    body: str = Field(description="Plain-text email body, ready to send after review.")


class NewsHook(BaseModel):
    headline: str
    why_it_matters: str = Field(description="One sentence on why it could anchor a Water LC event.")
    source: str
    url: str


class ResearchBrief(BaseModel):
    news_hooks: list[NewsHook] = Field(default_factory=list, max_length=5)
    top_student_interests: list[str] = Field(max_length=8)
    already_covered: list[str] = Field(description="Themes Water LC already did this year or last year.", max_length=12)
    gaps: list[str] = Field(description="Wanted by members but not yet covered.", max_length=6)
    do_not_repeat: list[str] = Field(default_factory=list, description="Ideas already confirmed with a speaker.")
    collab_candidates: list[str] = Field(default_factory=list, max_length=4,
                                         description="Only groups whose focus genuinely overlaps; empty if collaboration is not wanted.")


class Collab(BaseModel):
    group: str
    why: str


class Idea(BaseModel):
    title: str
    theme: str
    format: Literal["lunch and learn", "seminar", "student-led webinar", "career session", "field visit", "social"]
    description: str = Field(description="2-3 sentences for members.")
    why_now: str = Field(description="The member interest, gap or news hook behind it.")
    learning_goals: list[str] = Field(min_length=2, max_length=4)
    collab: Collab | None = Field(default=None, description="Only if collaboration is wanted (or open) and genuinely fits.")
    speaker_profile: str = Field(description="What kind of YSE alum (or host site for a field visit) to look for.")
    expected_attendance: int = Field(ge=5, le=200)
    cost_drivers: str = Field(description="What will drive cost: catering only, speaker travel, student transport, etc.")


class IdeaSet(BaseModel):
    ideas: list[Idea] = Field(min_length=3, max_length=3)


class Candidate(BaseModel):
    name: str
    organization: str
    role: str
    degree: str
    location: str
    why: str = Field(description="Why this person fits the event.")
    travel_note: str = Field(description="e.g. 'Local, easy in person', 'Train from NYC (~$60)', 'Far away: virtual'.")
    suggested_mode: Literal["virtual", "in_person"]


class SpeakerShortlist(BaseModel):
    candidates: list[Candidate] = Field(min_length=1, max_length=5)


class MeetingReading(BaseModel):
    outcome: Literal["confirmed", "interested", "declined", "unclear"]
    summary: str = Field(description="Two or three sentences, facts only.")
    mode: Literal["virtual", "in_person", "unknown"] = "unknown"
    proposed_dates: list[str] = Field(default_factory=list, description="YYYY-MM-DD dates mentioned, earliest first.")
    proposed_time: str = ""
    travel_from: str = ""
    honorarium_requested: float | None = None
    costs_mentioned: list[str] = Field(default_factory=list)
    talk_focus: str = ""
    needs: list[str] = Field(default_factory=list, description="AV, parking, dietary or other needs.")
    next_step: str


class ReplyReading(BaseModel):
    outcome: Literal["accepted", "declined", "changes_requested", "unclear"]
    summary: str = Field(description="One or two sentences, facts only.")
    requested_changes: list[str] = Field(default_factory=list)
    next_step: str


class CostLine(BaseModel):
    category: Literal["catering", "honorarium", "travel", "lodging", "supplies", "transport", "other"]
    description: str
    amount: float = Field(ge=0)
    basis: str


class BudgetProposal(BaseModel):
    lines: list[CostLine]
    impact: str = Field(description="2-3 sentences: total, and semester money before/after.")
    decision_needed: str = Field(default="", description="If real costs could not fit the limits: what the co-leads must decide and the options. Empty if none.")


class OrderItem(BaseModel):
    item: str = Field(description="Exact item name from the caterer's menu.")
    quantity: int = Field(ge=1)


class CateringOrder(BaseModel):
    caterer: str
    cuisine: str
    headcount: int = Field(ge=1)
    items: list[OrderItem] = Field(min_length=1)
    order_notes: str = Field(description="What Cristina needs: pickup/delivery, timing, tax exempt, minimums.")
    why: str


class Marketing(BaseModel):
    yale_connect: str
    whatsapp: str
    reminder: str
    poster_headline: str
    poster_subhead: str
    poster_bullets: list[str] = Field(min_length=2, max_length=4)


class Recap(BaseModel):
    recap: str = Field(description="One newsletter-style paragraph.")


class Briefing(BaseModel):
    headline: str = Field(description="One sentence on how things stand.")
    todos: list[str] = Field(min_length=1, max_length=8, description="Prioritized, most urgent first.")
    risks: list[str] = Field(default_factory=list, max_length=4)


class NewsItem(BaseModel):
    scope: Literal["Global", "National", "Local (Connecticut)"]
    title: str
    summary: str
    source: str
    url: str


class SpotlightItem(BaseModel):
    title: str
    summary: str
    url: str


class Conference(BaseModel):
    name: str
    dates: str
    location: str
    description: str
    url: str


class Job(BaseModel):
    title: str
    organization: str
    location: str
    deadline: str = Field(description="'Apply here by <Month D>' style date, or 'Rolling'.")
    url: str


class Research(BaseModel):
    news: list[NewsItem] = Field(default_factory=list, max_length=4)
    spotlight: list[SpotlightItem] = Field(default_factory=list, max_length=2)
    conferences: list[Conference] = Field(default_factory=list, max_length=4)
    jobs: list[Job] = Field(default_factory=list, max_length=8)


class NewsletterDraft(BaseModel):
    subject: str
    greeting: str
    event_recaps: str
    upcoming_events: str
    water_in_the_news: str
    spotlight: str
    helpful_links: str
    upcoming_conferences: str
    jobs_and_internships: str


# ================================================================ tools (read-only, code-backed)


def _used_cuisines() -> dict[str, str]:
    """cuisine -> last date used this semester, from events that have a catering order."""
    s = store.snapshot()
    out: dict[str, str] = {}
    start = budget.semester_for(date.today())["start"]
    for e in s["events"]:
        c = e.get("catering")
        if c and c.get("cuisine") and (e.get("date") or "9999") >= start:
            out[c["cuisine"].lower()] = max(out.get(c["cuisine"].lower(), ""), e.get("date") or "")
    return out


def tool_member_interests() -> list[dict[str, Any]]:
    """What members asked for at the Fall Splash (priority 1 = biggest in the word cloud)."""
    return store.read_csv("member_interests_fall_2026.csv")[:30]


def tool_events_this_year() -> list[dict[str, str]]:
    """Water LC events this academic year: date, title, format, hosts, stage, theme."""
    s = store.snapshot()
    return [{"date": e.get("date", ""), "title": e["title"], "format": e.get("event_type", ""),
             "hosts": e.get("hosts", ""), "stage": e["stage"],
             "theme": (e.get("plan") or {}).get("theme", "")}
            for e in s["events"] if e.get("plan") or e["stage"] == "done"]


def tool_events_last_year() -> list[dict[str, str]]:
    """Water LC events from 2025-26 (title and type)."""
    return [{"event": r["event"], "type": r["event_type"]} for r in store.read_csv("past_events_2025_26.csv")]


def tool_locked_ideas() -> list[dict[str, str]]:
    """Ideas already confirmed with a speaker. Never propose these again."""
    return [{"title": e["title"], "theme": (e.get("plan") or {}).get("theme", ""),
             "speaker": (e.get("speaker") or {}).get("name", "")}
            for e in store.snapshot()["events"] if e.get("locked")]


def tool_learning_communities() -> list[dict[str, str]]:
    """YSE learning communities and student groups, their focus and natural overlap with water."""
    return store.read_csv("learning_communities.csv")


def tool_search_alumni(keywords: str) -> list[dict[str, str]]:
    """YSE alumni whose expertise, role or organization matches any of the keywords (comma or space separated)."""
    words = [w.strip().lower() for w in keywords.replace(",", " ").split() if len(w.strip()) > 2]
    rows = store.read_csv("alumni_speakers.csv")
    scored = []
    for r in rows:
        hay = " ".join([r["expertise"], r["role"], r["organization"]]).lower()
        score = sum(hay.count(w) for w in words)
        if score:
            scored.append((score, r))
    scored.sort(key=lambda x: -x[0])
    pick = [r for _, r in scored[:8]] or rows[:6]
    return [{k: v for k, v in r.items() if k != "email"} for r in pick]


def tool_semester_status() -> dict[str, Any]:
    """Exact semester money: budget, wages logged and forecast, event spending, what is available."""
    st = budget.semester_status(store.snapshot())
    return {k: st[k] for k in ("semester", "budget", "wages_logged", "wages_forecast", "events_paid",
                               "events_approved", "events_pending", "available_for_events",
                               "available_after_pending", "reserve", "warnings")}


def tool_list_caterers() -> dict[str, Any]:
    """Our caterers with cuisine and ordering notes, and cuisines already used this semester."""
    used = _used_cuisines()
    menus = {r["caterer"] for r in store.read_csv("caterer_menus.csv")}
    return {
        "caterers": [{"name": r["name"], "cuisine": r["cuisine"] or "unknown", "ordering_notes": r["ordering_notes"],
                      "has_menu": r["name"] in menus,
                      "cuisine_used_this_semester_on": used.get((r["cuisine"] or "").lower())}
                     for r in store.read_csv("caterers.csv")],
        "max_per_person_usd": budget.rules()["limits"]["catering_max_per_person_usd"],
    }


def tool_get_menu(caterer: str) -> list[dict[str, str]]:
    """A caterer's menu (vegetarian/vegan items) with unit, how many each serves, and price. Includes shared extras."""
    rows = store.read_csv("caterer_menus.csv")
    return [r for r in rows if r["caterer"].lower() in (caterer.lower(), "any caterer")]


def price_order(caterer: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    """Code prices the order from the menu file. The AI never sets a price."""
    menu = {r["item"].lower(): r for r in tool_get_menu(caterer)}
    lines, unknown = [], []
    for it in items:
        row = menu.get(it["item"].lower())
        if row is None:
            unknown.append(it["item"])
            continue
        unit = float(row["price_usd"])
        lines.append({"item": row["item"], "unit": row["unit"], "serves": int(row["serves"]), "diet": row["diet"],
                      "quantity": it["quantity"], "unit_price": unit, "subtotal": round(unit * it["quantity"], 2)})
    total = round(sum(l["subtotal"] for l in lines), 2)
    servings = sum(l["serves"] * l["quantity"] for l in lines if l["item"] not in EXTRAS)
    return {"lines": lines, "unknown_items": unknown, "total": total, "servings": servings}


# ================================================================ agent factories


@lru_cache
def model():
    return build_model()


def _agent(role: str, output_type: Any, tools: list | None = None, web: bool = False, deps_type: Any = None) -> Agent:
    kw: dict[str, Any] = {}
    if deps_type is not None:
        kw["deps_type"] = deps_type
    return Agent(
        model(),
        output_type=output_type,
        instructions=_instructions(role),
        model_settings=_settings(role),
        tools=tools or [],
        capabilities=[WebSearch()] if web else None,
        retries=3,
        name=role,
        **kw,
    )


@lru_cache
def research_scout() -> Agent:
    return _agent("research_scout", ResearchBrief,
                  [tool_member_interests, tool_events_this_year, tool_events_last_year, tool_locked_ideas,
                   tool_learning_communities], web=True)


@lru_cache
def strategist() -> Agent:
    a = _agent("strategist", IdeaSet)

    @a.output_validator
    def _different(out: IdeaSet) -> IdeaSet:
        locked = {i["title"].lower() for i in tool_locked_ideas()}
        clash = [i.title for i in out.ideas if i.title.lower() in locked]
        if clash:
            raise ModelRetry(f"These ideas are already confirmed with a speaker: {clash}. Propose different ones.")
        return out

    return a


@lru_cache
def speaker_scout() -> Agent:
    a = _agent("speaker_scout", SpeakerShortlist, [tool_search_alumni])

    @a.output_validator
    def _real(out: SpeakerShortlist) -> SpeakerShortlist:
        names = {r["name"] for r in store.read_csv("alumni_speakers.csv")}
        fake = [c.name for c in out.candidates if c.name not in names]
        if fake:
            raise ModelRetry(f"Only suggest people returned by search_alumni (exact names). Not found: {fake}.")
        return out

    return a


@lru_cache
def speaker_invite() -> Agent:
    return _agent("speaker_outreach", EmailDraft)


class BudgetDeps(BaseModel):
    headcount: int
    mode: str
    event_format: str


@lru_cache
def budget_analyst() -> Agent:
    a = _agent("budget_analyst", BudgetProposal, [tool_semester_status], deps_type=BudgetDeps)

    @a.tool
    def check_budget(ctx: RunContext[BudgetDeps], lines: list[CostLine]) -> dict[str, Any]:
        """Check cost lines against every hard limit for this event's format and mode."""
        st = budget.semester_status(store.snapshot())
        problems = budget.validate_lines([l.model_dump() for l in lines], ctx.deps.headcount,
                                         st["available_after_pending"], ctx.deps.mode, ctx.deps.event_format)
        return {"total": round(sum(l.amount for l in lines), 2), "problems": problems, "ok": not problems}

    @a.output_validator
    def _limits(ctx: RunContext[BudgetDeps], p: BudgetProposal) -> BudgetProposal:
        if not any(l.category == "catering" for l in p.lines):
            raise ModelRetry("Include one catering line: the catering budget for the event (use $0 if no food).")
        st = budget.semester_status(store.snapshot())
        problems = budget.validate_lines([l.model_dump() for l in p.lines], ctx.deps.headcount,
                                         st["available_after_pending"], ctx.deps.mode, ctx.deps.event_format)
        if problems:
            raise ModelRetry("Budget breaks hard limits: " + " ".join(problems))
        return p

    return a


class CateringDeps(BaseModel):
    catering_budget: float
    headcount: int


@lru_cache
def catering_planner() -> Agent:
    a = _agent("catering_planner", CateringOrder, [tool_list_caterers, tool_get_menu], deps_type=CateringDeps)

    @a.tool
    def price_this_order(ctx: RunContext[CateringDeps], caterer: str, items: list[OrderItem]) -> dict[str, Any]:
        """Price an order exactly from the menu. Returns line subtotals, total, servings and the catering budget."""
        priced = price_order(caterer, [i.model_dump() for i in items])
        priced["catering_budget"] = ctx.deps.catering_budget
        priced["within_budget"] = priced["total"] <= ctx.deps.catering_budget
        return priced

    @a.output_validator
    def _valid(ctx: RunContext[CateringDeps], o: CateringOrder) -> CateringOrder:
        names = {r["name"].lower() for r in store.read_csv("caterers.csv")}
        if o.caterer.lower() not in names:
            raise ModelRetry(f"{o.caterer} is not on our caterer list.")
        priced = price_order(o.caterer, [i.model_dump() for i in o.items])
        if priced["unknown_items"]:
            raise ModelRetry(f"Not on {o.caterer}'s menu: {priced['unknown_items']}. Use exact names from get_menu.")
        if priced["total"] > ctx.deps.catering_budget + 0.01:
            raise ModelRetry(f"Order total ${priced['total']:.2f} is over the ${ctx.deps.catering_budget:.2f} catering budget.")
        if priced["servings"] < ctx.deps.headcount * 0.9:
            raise ModelRetry(f"The order serves about {priced['servings']} but {ctx.deps.headcount} people are expected.")
        return o

    return a


@lru_cache
def coordinator_meeting() -> Agent:
    return _agent("coordinator", MeetingReading)


@lru_cache
def coordinator_reader() -> Agent:
    return _agent("coordinator", ReplyReading)


@lru_cache
def coordinator_recap() -> Agent:
    return _agent("coordinator", Recap)


@lru_cache
def coordinator_briefing() -> Agent:
    return _agent("coordinator", Briefing)


@lru_cache
def approvals() -> Agent:
    return _agent("approvals", EmailDraft)


@lru_cache
def marketing() -> Agent:
    return _agent("marketing", Marketing)


@lru_cache
def newsletter_research() -> Agent:
    return _agent("newsletter_editor", Research, web=True)


@lru_cache
def newsletter_writer() -> Agent:
    return _agent("newsletter_editor", NewsletterDraft)


AGENT_LABELS = {
    "research_scout": "Research scout",
    "strategist": "Event strategist",
    "speaker_scout": "Speaker scout",
    "speaker_outreach": "Speaker outreach",
    "coordinator": "Coordinator",
    "budget_analyst": "Budget analyst",
    "catering_planner": "Catering planner",
    "approvals": "Approvals & email",
    "marketing": "Marketing",
    "newsletter_editor": "Newsletter editor",
}


class AIUnavailable(RuntimeError):
    """The AI service couldn't be reached (network down, DNS, Portkey outage)."""


async def run_agent(role: str, agent: Agent, prompt: str, ref: str | None = None, deps: Any = None) -> Any:
    """Run one agent and log its tokens, cost and estimated water.

    A dropped connection is retried three times (after 2s, 5s and 10s) before giving up with a clear message.
    """
    t0 = time.time()
    for wait in (2, 5, 10, None):
        try:
            result = await agent.run(prompt, deps=deps) if deps is not None else await agent.run(prompt)
            break
        except ModelConnectionError:
            if wait is None:
                raise AIUnavailable("Couldn't reach the AI service (Portkey). Check your internet connection "
                                    "and try again.") from None
            await asyncio.sleep(wait)
    with store.txn() as s:
        usage.record(s, role, result.usage, ref, time.time() - t0)
    return result.output
