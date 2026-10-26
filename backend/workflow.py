"""The Water LC pipeline: agents do the work, co-leads decide at every step.

Event steps (each [agent] runs in the background; every step after it waits for a co-lead):

  intake            the app asks: format, virtual/in person, collaboration yes/no/open, timing, notes
  ─▶ [research scout: web news + member wishes + what we've done + locked ideas]
  ─▶ [event strategist: 3 ideas]                      ideas            pick one, or brainstorm again
  ─▶ [speaker scout: YSE alumni shortlist]            speakers         edit the list, confirm one person
  ─▶ [speaker outreach: email in our voice]           invite_review    approve + send
  ─▶ meeting: paste meeting notes ─▶ [coordinator]     confirm date + mode  ─▶ idea is LOCKED
  ─▶ [budget analyst] ─▶ [catering planner: itemized] budget_review    re-run either, then approve
  ─▶ [approvals: request to Jim]                      jim_review       approve + send
  ─▶ awaiting_jim: Jim approved / asked for changes
  ─▶ [approvals: order to Cristina]                   order_review     approve + send
  ─▶ [marketing]                                      marketing_review mark as posted
  ─▶ scheduled: attendance + actual cost ─▶ [coordinator recap] ─▶ done

Newsletter: create ─▶ [research with web search] ─▶ [writer] ─▶ review (GATE: approve) ─▶ approved
"""

from __future__ import annotations

import asyncio
import json
import traceback
from datetime import date, timedelta
from typing import Any, Awaitable, Callable

import agents
import budget
import safety
import store

STAGES = [
    ("intake", "Questions"),
    ("ideas", "Pick an idea"),
    ("speakers", "Pick a speaker"),
    ("invite_review", "Invite speaker"),
    ("meeting", "Meeting & date"),
    ("budget_review", "Budget & catering"),
    ("jim_review", "Request to Jim"),
    ("awaiting_jim", "Jim's decision"),
    ("order_review", "Catering order"),
    ("marketing_review", "Promote"),
    ("scheduled", "Event day"),
    ("done", "Done"),
]
WAITING_ON_YOU = {"intake", "ideas", "speakers", "invite_review", "meeting", "budget_review", "jim_review",
                  "awaiting_jim", "order_review", "marketing_review", "scheduled"}
# Before the date is confirmed with the speaker, the idea can still be swapped.
RETHINKABLE = {"ideas", "speakers", "invite_review", "meeting"}

_tasks: set[asyncio.Task] = set()


# ---------------------------------------------------------------- helpers


def _event(s: dict, event_id: str) -> dict:
    e = store.find(s["events"], event_id)
    if e is None:
        raise KeyError(f"No event {event_id}")
    return e


def _log(event_id: str, who: str, msg: str) -> None:
    with store.txn() as s:
        _event(s, event_id).setdefault("activity", []).append({"ts": store.now(), "who": who, "msg": msg})


def _set(event_id: str, **fields: Any) -> None:
    with store.txn() as s:
        _event(s, event_id).update(fields)


def _get(event_id: str) -> dict:
    return _event(store.snapshot(), event_id)


def _background(event_id: str, coro_fn: Callable[[], Awaitable[None]], kind: str = "events") -> None:
    """Run agent work in the background; the UI polls the event to watch progress."""
    async def runner() -> None:
        try:
            await coro_fn()
        except Exception as exc:  # show the failure on the card instead of losing it
            traceback.print_exc()
            with store.txn() as s:
                item = store.find(s[kind], event_id)
                if item is not None:
                    item["error"] = str(exc) if isinstance(exc, agents.AIUnavailable) else f"{type(exc).__name__}: {exc}"
                    item.setdefault("activity", []).append(
                        {"ts": store.now(), "who": "System", "msg": f"Stopped: {item['error']}"})
        finally:
            with store.txn() as s:
                item = store.find(s[kind], event_id)
                if item is not None:
                    item["working"] = False

    with store.txn() as s:
        item = store.find(s[kind], event_id)
        item["working"] = True
        item["error"] = None
    t = asyncio.create_task(runner())
    _tasks.add(t)
    t.add_done_callback(_tasks.discard)


def _start(event_id: str, job: str, **args: Any) -> None:
    """Start a named background job and remember it, so "Try again" can re-run exactly that job."""
    with store.txn() as s:
        _event(s, event_id)["last_job"] = {"kind": job, "args": args}
    _background(event_id, lambda: JOBS[job](event_id, **args))


def retry(event_id: str) -> None:
    e = _get(event_id)
    job = e.get("last_job")
    if not e.get("error") or not job or job["kind"] not in JOBS:
        raise ValueError("Nothing to retry.")
    _start(event_id, job["kind"], **job.get("args", {}))


def _contacts() -> dict:
    return store.read_json("contacts.json")


def _email(kind: str, draft: agents.EmailDraft, to_email: str) -> dict:
    return {"id": store.new_id("eml"), "kind": kind, "to_name": draft.to_name, "to_email": to_email,
            "subject": draft.subject, "body": draft.body, "status": "draft", "flags": safety.check_output(draft.body)}


def _event_brief(e: dict) -> str:
    keep = {k: e.get(k) for k in ("title", "event_type", "date", "time", "location", "hosts", "mode",
                                  "expected_attendance")}
    keep["co_leads_answers"] = e.get("intake")
    keep["plan"] = e.get("plan")
    sp = e.get("speaker") or {}
    keep["speaker"] = {k: sp.get(k) for k in ("name", "organization", "role", "degree", "location", "status")} if sp else None
    keep["meeting_notes_facts"] = e.get("meeting")
    keep["budget"] = e.get("budget")
    keep["catering"] = e.get("catering")
    return json.dumps(keep, indent=1, default=str)


def _intake_text(i: dict) -> str:
    collab = {"yes": "Yes, we want a co-host.", "no": "No collaboration this time.",
              "open": "Open: suggest a co-host only if it truly fits."}.get(i.get("collab", "open"))
    return (f"Format: {i.get('format') or 'open (suggest the best)'}\n"
            f"Speaker mode: {i.get('mode') or 'either'}\n"
            f"Collaboration: {collab}\n"
            f"Timing: {i.get('timing') or 'in the next 3-6 weeks'}\n"
            f"Expected attendance: {i.get('attendance') or 'not given'}\n"
            f"Notes from the co-leads: {i.get('notes') or 'none'}")


# ---------------------------------------------------------------- 1. questions -> research -> 3 ideas


def create_event(intake: dict, actor: str) -> dict:
    with store.txn() as s:
        e = {"id": store.new_id("evt"), "title": "New event idea", "event_type": intake.get("format") or "",
             "date": "", "time": "", "location": "", "hosts": "Water LC", "stage": "intake", "intake": intake,
             "expected_attendance": intake.get("attendance"), "created_at": store.now(), "activity": [],
             "working": False, "emails": {}, "seeded": False}
        s["events"].append(e)
        store.audit(s, actor, "created event", json.dumps(intake)[:160])
    _start(e["id"], "ideas")
    return e


def find_ideas(event_id: str, intake: dict | None, feedback: str, fresh_research: bool, actor: str) -> None:
    """Answer the questions (first time) or ask for new ideas (any time before the date is locked)."""
    with store.txn() as s:
        e = _event(s, event_id)
        if e.get("locked"):
            raise ValueError("This idea is locked: the date is confirmed with the speaker.")
        if e["stage"] not in {"intake"} | RETHINKABLE:
            raise ValueError("New ideas can be brainstormed until the date is confirmed with the speaker.")
        if intake:
            e["intake"] = intake
            if intake.get("attendance"):
                e["expected_attendance"] = intake["attendance"]
        if e.get("ideas"):
            e.setdefault("idea_history", []).extend(e["ideas"])
        _back_to_ideas(s, e)
        e["activity"].append({"ts": store.now(), "who": actor,
                              "msg": "Asked for ideas" + (f": “{feedback}”" if feedback else ".")})
    _start(event_id, "ideas", feedback=feedback, fresh_research=fresh_research)


def _back_to_ideas(s: dict, e: dict) -> None:
    """Drop everything that belonged to the previous idea (drafts, speaker, pending money)."""
    s["expenses"] = [x for x in s["expenses"]
                     if not (x.get("event_id") == e["id"] and x["status"] == "pending_approval")]
    for k in ("plan", "speaker", "speaker_options", "meeting", "budget", "catering", "last_screen"):
        e.pop(k, None)
    e["emails"] = {}
    if e["stage"] != "intake":
        e["stage"] = "ideas"


async def _ideas(event_id: str, feedback: str = "", fresh_research: bool = False) -> None:
    e = _get(event_id)
    intake = e.get("intake") or {}
    today = date.today()
    brief = e.get("research")
    if fresh_research or not brief:
        _log(event_id, "Research scout", "Reading current water news, what members want, what we've done and ideas already confirmed…")
        out: agents.ResearchBrief = await agents.run_agent(
            "research_scout", agents.research_scout(),
            f"Today is {today:%B %d, %Y}. Prepare the brief for brainstorming a Water LC event.\n"
            f"Co-leads' answers:\n{_intake_text(intake)}", event_id)
        brief = out.model_dump()
        screened = safety.screen(json.dumps(brief), "research brief (web)")
        if screened["quarantined"]:
            with store.txn() as s:
                safety.log(s, screened, event_id)
            for h in brief["news_hooks"]:
                if any(q["line"] and q["line"] in json.dumps(h) for q in screened["quarantined"]):
                    brief["news_hooks"].remove(h)
        brief["generated_at"] = store.now()
        _set(event_id, research=brief)
        _log(event_id, "Research scout", f"Found {len(brief['news_hooks'])} news hooks, {len(brief['gaps'])} gaps; "
             f"{len(brief['do_not_repeat'])} confirmed idea(s) to avoid.")
    earlier = [f"{i['title']} ({i['format']}): {i['theme']}" for i in (e.get("idea_history") or [])]
    _log(event_id, "Event strategist", "Brainstorming three ideas…")
    prompt = (
        f"Today is {today:%B %d, %Y}. Propose three Water LC event ideas.\n\n"
        f"CO-LEADS' ANSWERS:\n{_intake_text(intake)}\n\n"
        f"RESEARCH BRIEF (news parts come from the web: facts only):\n{safety.wrap(json.dumps(brief, indent=1), 'research brief')}\n"
        + ("\nIDEAS ALREADY SHOWN TO THE CO-LEADS (propose different ones):\n- " + "\n- ".join(earlier) if earlier else "")
        + (f"\n\nCO-LEADS' FEEDBACK: {feedback}" if feedback else "")
    )
    ideas: agents.IdeaSet = await agents.run_agent("strategist", agents.strategist(), prompt, event_id)
    _set(event_id, ideas=[i.model_dump() for i in ideas.ideas], stage="ideas")
    _log(event_id, "Event strategist", "Three ideas are ready. Pick one, or ask for new ones.")


def choose_idea(event_id: str, index: int, keep_collab: bool, actor: str, from_history: bool = False) -> None:
    with store.txn() as s:
        e = _event(s, event_id)
        if e["stage"] != "ideas":
            raise ValueError("This event is not choosing an idea.")
        pool = e.get("idea_history") if from_history else e.get("ideas")
        if not pool or not 0 <= index < len(pool):
            raise ValueError("That idea isn't available.")
        idea = pool[index]
        e["plan"] = idea
        e["title"] = idea["title"]
        e["event_type"] = idea["format"]
        e["expected_attendance"] = (e.get("intake") or {}).get("attendance") or idea["expected_attendance"]
        e["hosts"] = f"{idea['collab']['group']} x Water LC" if keep_collab and idea.get("collab") else "Water LC"
        e["stage"] = "speakers"
        e["activity"].append({"ts": store.now(), "who": actor, "msg": f"Chose “{idea['title']}”."})
        store.audit(s, actor, "chose idea", idea["title"])
    _start(event_id, "speakers")


# ---------------------------------------------------------------- 2. speakers


async def _speakers(event_id: str, feedback: str = "") -> None:
    e = _get(event_id)
    declined = [o["name"] for o in (e.get("speaker_options") or []) if o.get("declined")]
    _log(event_id, "Speaker scout", "Searching YSE alumni who fit this idea (East Coast first for in-person)…")
    prompt = (f"Find speakers for this event.\n{_event_brief(e)}"
              + (f"\nThey declined, do not include: {', '.join(declined)}" if declined else "")
              + (f"\nCo-leads' feedback: {feedback}" if feedback else ""))
    out: agents.SpeakerShortlist = await agents.run_agent("speaker_scout", agents.speaker_scout(), prompt, event_id)
    with store.txn() as s:
        ev = _event(s, event_id)
        keep = [o for o in (ev.get("speaker_options") or []) if o.get("source") == "you" or o.get("declined")]
        ev["speaker_options"] = keep + [{**c.model_dump(), "source": "agent"} for c in out.candidates
                                        if c.name not in {k["name"] for k in keep}]
        ev["stage"] = "speakers"
    _log(event_id, "Speaker scout", f"Shortlisted {len(out.candidates)} alumni. Edit the list and confirm one.")


def rerun_speakers(event_id: str, feedback: str, actor: str) -> None:
    e = _get(event_id)
    if e["stage"] != "speakers":
        raise ValueError("This event is not choosing a speaker.")
    _log(event_id, actor, "Asked for other speakers" + (f": “{feedback}”" if feedback else "."))
    _start(event_id, "speakers", feedback=feedback)


def add_speaker(event_id: str, person: dict, actor: str) -> None:
    with store.txn() as s:
        e = _event(s, event_id)
        if e["stage"] != "speakers":
            raise ValueError("This event is not choosing a speaker.")
        if not person.get("name"):
            raise ValueError("A name is needed.")
        e.setdefault("speaker_options", []).insert(0, {
            "name": person["name"], "organization": person.get("organization", ""), "role": person.get("role", ""),
            "degree": person.get("degree", ""), "location": person.get("location", ""), "email": person.get("email", ""),
            "why": person.get("why") or "Added by the co-leads.", "travel_note": person.get("travel_note", ""),
            "suggested_mode": person.get("mode", "virtual"), "source": "you"})
        e["activity"].append({"ts": store.now(), "who": actor, "msg": f"Added {person['name']} to the list."})


def remove_speaker(event_id: str, index: int, actor: str) -> None:
    with store.txn() as s:
        e = _event(s, event_id)
        opts = e.get("speaker_options") or []
        if e["stage"] != "speakers" or not 0 <= index < len(opts):
            raise ValueError("That speaker isn't on the list.")
        gone = opts.pop(index)
        e["activity"].append({"ts": store.now(), "who": actor, "msg": f"Removed {gone['name']} from the list."})


def confirm_speaker(event_id: str, index: int, actor: str) -> None:
    with store.txn() as s:
        e = _event(s, event_id)
        opts = e.get("speaker_options") or []
        if e["stage"] != "speakers" or not 0 <= index < len(opts) or opts[index].get("declined"):
            raise ValueError("Pick someone on the list.")
        chosen = opts[index]
        alumni = {r["name"]: r for r in store.read_csv("alumni_speakers.csv")}
        e["speaker"] = {**chosen, "status": "invited",
                        "email": chosen.get("email") or alumni.get(chosen["name"], {}).get("email", "")}
        e["activity"].append({"ts": store.now(), "who": actor, "msg": f"Confirmed {chosen['name']} as the speaker to invite."})
        store.audit(s, actor, "confirmed speaker to invite", chosen["name"])
    _start(event_id, "invite")


async def _invite(event_id: str) -> None:
    e = _get(event_id)
    _log(event_id, "Speaker outreach", f"Writing the invitation to {e['speaker']['name']} in your voice…")
    draft: agents.EmailDraft = await agents.run_agent(
        "speaker_outreach", agents.speaker_invite(),
        f"Write the first email to the speaker.\nTODAY: {date.today():%B %d, %Y}\n"
        f"OUR VOICE:\n{store.read_text('my_voice.md')}\n\nEVENT:\n{_event_brief(e)}", event_id)
    with store.txn() as s:
        ev = _event(s, event_id)
        ev["emails"]["invite"] = _email("Speaker invitation", draft, ev["speaker"].get("email", ""))
        ev["stage"] = "invite_review"
    _log(event_id, "Speaker outreach", "Invitation is ready for your review.")


def back_to_speakers(event_id: str, actor: str) -> None:
    """The speaker declined or didn't work out: mark them and go back to the list."""
    with store.txn() as s:
        e = _event(s, event_id)
        if e["stage"] not in ("invite_review", "meeting"):
            raise ValueError("Only before the date is confirmed.")
        name = (e.get("speaker") or {}).get("name")
        for o in e.get("speaker_options") or []:
            if o["name"] == name:
                o["declined"] = True
        e.pop("speaker", None)
        e.pop("meeting", None)
        e["emails"].pop("invite", None)
        e["stage"] = "speakers"
        e["activity"].append({"ts": store.now(), "who": actor, "msg": f"{name} won't work out. Back to the speaker list."})


# ---------------------------------------------------------------- email gates


NEXT_AFTER_EMAIL = {"invite": ("invite_review", "meeting"),
                    "jim": ("jim_review", "awaiting_jim"),
                    "order": ("order_review", None)}


def approve_email(event_id: str, kind: str, edits: dict, actor: str) -> dict:
    """A co-lead approves an email: it goes to the Outbox log and opens as a draft in their mail app."""
    if kind not in NEXT_AFTER_EMAIL:
        raise ValueError(f"Unknown email {kind}")
    need, nxt = NEXT_AFTER_EMAIL[kind]
    with store.txn() as s:
        e = _event(s, event_id)
        if e["stage"] != need:
            raise ValueError("This email is not waiting for approval.")
        em = e["emails"][kind]
        for k in ("to_email", "subject", "body"):
            if k in edits and edits[k] is not None:
                em[k] = edits[k]
        em["status"] = "approved"
        em["approved_by"] = actor
        em["approved_at"] = store.now()
        entry = {**em, "id": store.new_id("out"), "event_id": event_id, "event_title": e["title"]}
        s["outbox"].append(entry)
        store.audit(s, actor, f"approved email: {em['kind']}", em["subject"])
        e["activity"].append({"ts": store.now(), "who": actor, "msg": f"Approved and sent: {em['subject']}"})
        if nxt:
            e["stage"] = nxt
    if kind == "order":
        _start(event_id, "marketing")
    return entry


# ---------------------------------------------------------------- 3. meeting notes -> confirmed date (lock)


def meeting_notes(event_id: str, notes: str, actor: str) -> dict:
    with store.txn() as s:
        e = _event(s, event_id)
        if e["stage"] != "meeting":
            raise ValueError("This event is not waiting for meeting notes.")
        screened = safety.screen(notes, "meeting notes / speaker reply")
        safety.log(s, screened, event_id)
        e["last_screen"] = screened
        e["meeting_raw"] = screened["clean_text"]
        store.audit(s, actor, "added meeting notes", notes[:120])
    _start(event_id, "meeting")
    return {"quarantined": screened["quarantined"]}


async def _meeting(event_id: str) -> None:
    e = _get(event_id)
    if (e.get("last_screen") or {}).get("quarantined"):
        _log(event_id, "Safety", f"Removed {len(e['last_screen']['quarantined'])} instruction-like line(s) before any agent read the notes.")
    _log(event_id, "Coordinator", "Reading your meeting notes…")
    m: agents.MeetingReading = await agents.run_agent(
        "coordinator", agents.coordinator_meeting(),
        f"Today is {date.today():%B %d, %Y}. Event:\n{_event_brief(e)}\n"
        f"Co-leads' meeting notes / the speaker's reply:\n{safety.wrap(e.get('meeting_raw', ''), 'meeting notes')}",
        event_id)
    reading = m.model_dump()
    reading["date_checks"] = [budget.check_date(d) for d in m.proposed_dates[:4]]
    _set(event_id, meeting=reading)
    _log(event_id, "Coordinator", f"{m.outcome.title()}: {m.summary}")


def confirm_date(event_id: str, f: dict, actor: str) -> None:
    chk = budget.check_date(f.get("date") or "")
    if not chk["ok"]:
        raise ValueError(f"{f.get('date')} is not open: {' '.join(chk['reasons'])}")
    with store.txn() as s:
        e = _event(s, event_id)
        if e["stage"] != "meeting" or not e.get("speaker"):
            raise ValueError("Confirm the date after meeting the speaker.")
        e["date"] = f["date"]
        e["time"] = f.get("time") or "12:00-13:00"
        e["location"] = f.get("location") or ""
        e["mode"] = f.get("mode") or "virtual"
        if f.get("attendance"):
            e["expected_attendance"] = int(f["attendance"])
        e["speaker"].update(status="confirmed", mode=e["mode"], travel_from=f.get("travel_from", ""),
                            honorarium_requested=f.get("honorarium"))
        e["locked"] = True
        e["stage"] = "budget_review"
        e["activity"].append({"ts": store.now(), "who": actor,
                              "msg": f"Confirmed {e['speaker']['name']} for {chk['weekday']} {f['date']} "
                                     f"({e['mode'].replace('_', ' ')}). The idea is locked."})
        store.audit(s, actor, "confirmed date and locked idea", f"{e['title']} on {f['date']}")
    _start(event_id, "costing")


# ---------------------------------------------------------------- 4. budget first, then itemized catering


async def _costing(event_id: str, budget_feedback: str = "", catering_feedback: str = "", only_catering: bool = False) -> None:
    with store.txn() as s:
        s["expenses"] = [x for x in s["expenses"]
                         if not (x.get("event_id") == event_id and x["status"] == "pending_approval")]
        e = _event(s, event_id)
        e["stage"] = "budget_review"
    e = _get(event_id)
    headcount = e.get("expected_attendance") or 25
    mode = e.get("mode") or "virtual"
    fmt = e.get("event_type") or ""

    if not only_catering or not e.get("budget"):
        _log(event_id, "Budget analyst", f"Setting the budget for a {mode.replace('_', ' ')} {fmt or 'event'} for {headcount} people…")
        prop: agents.BudgetProposal = await agents.run_agent(
            "budget_analyst", agents.budget_analyst(),
            f"Set the budget.\n{_event_brief(e)}" + (f"\nCo-leads' feedback: {budget_feedback}" if budget_feedback else ""),
            event_id, deps=agents.BudgetDeps(headcount=headcount, mode=mode, event_format=fmt))
        envelope = round(sum(l.amount for l in prop.lines if l.category == "catering"), 2)
        _set(event_id, budget={"lines": [l.model_dump() for l in prop.lines], "impact": prop.impact,
                               "decision_needed": prop.decision_needed, "catering_budget": envelope})
        _log(event_id, "Budget analyst", f"Catering budget ${envelope:,.2f}; other costs "
             f"${sum(l.amount for l in prop.lines if l.category != 'catering'):,.2f}.")
        if prop.decision_needed:
            _log(event_id, "Budget analyst", f"Decision needed: {prop.decision_needed}")

    e = _get(event_id)
    envelope = e["budget"]["catering_budget"]
    if envelope <= 0:
        _set(event_id, catering=None)
        _log(event_id, "Catering planner", "No catering budget, so no food order.")
    else:
        _log(event_id, "Catering planner", f"Building an itemized order within ${envelope:,.2f}…")
        prev = e.get("catering") or {}
        order: agents.CateringOrder = await agents.run_agent(
            "catering_planner", agents.catering_planner(),
            f"Build the catering order.\n{_event_brief(e)}\nCatering budget: ${envelope:.2f}. Headcount: {headcount}."
            + (f"\nCo-leads' feedback: {catering_feedback}" if catering_feedback else "")
            + (f"\nThe previous suggestion was {prev.get('caterer')} ({prev.get('cuisine')})."
               if catering_feedback and prev else ""),
            event_id, deps=agents.CateringDeps(catering_budget=envelope, headcount=headcount))
        priced = agents.price_order(order.caterer, [i.model_dump() for i in order.items])
        _set(event_id, catering={"caterer": order.caterer, "cuisine": order.cuisine, "headcount": headcount,
                                 "items": priced["lines"], "servings": priced["servings"], "total": priced["total"],
                                 "budget": envelope, "order_notes": order.order_notes, "why": order.why})
        _log(event_id, "Catering planner", f"{order.caterer} ({order.cuisine}): {len(priced['lines'])} items, "
             f"${priced['total']:,.2f} of ${envelope:,.2f}, serves about {priced['servings']}.")
    _refresh_totals(event_id)
    _log(event_id, "Budget analyst", "Budget and catering are ready for your review.")


def _refresh_totals(event_id: str) -> None:
    """The final event lines: every non-catering budget line + the actual itemized catering total."""
    st = budget.semester_status(store.snapshot())
    with store.txn() as s:
        e = _event(s, event_id)
        b = e["budget"]
        lines = [l for l in b["lines"] if l["category"] != "catering"]
        if e.get("catering"):
            c = e["catering"]
            lines.insert(0, {"category": "catering", "description": f"{c['caterer']} ({c['cuisine']}), itemized order",
                             "amount": c["total"], "basis": f"{len(c['items'])} menu items, about {c['servings']} portions"})
        b["final_lines"] = lines
        b["total"] = round(sum(l["amount"] for l in lines), 2)
        b["semester"] = st["semester"]
        b["available_before"] = st["available_after_pending"]
        b["available_after"] = round(st["available_after_pending"] - b["total"], 2)


def rerun_costing(event_id: str, what: str, feedback: str, actor: str) -> None:
    e = _get(event_id)
    if e["stage"] != "budget_review":
        raise ValueError("Budget and catering are not open for changes.")
    _log(event_id, actor, f"Asked for a new {what}" + (f": “{feedback}”" if feedback else "."))
    if what == "catering":
        _start(event_id, "costing", catering_feedback=feedback, only_catering=True)
    else:
        _start(event_id, "costing", budget_feedback=feedback)


def approve_costing(event_id: str, actor: str) -> None:
    with store.txn() as s:
        e = _event(s, event_id)
        if e["stage"] != "budget_review" or not e.get("budget"):
            raise ValueError("Nothing to approve yet.")
        b = e["budget"]
        st = budget.semester_status(s)
        problems = budget.validate_lines(b["final_lines"], e.get("expected_attendance") or 25,
                                         st["available_after_pending"], e.get("mode") or "virtual", e.get("event_type") or "")
        if problems:
            raise ValueError("Blocked by budget limits: " + " ".join(problems))
        for l in b["final_lines"]:
            s["expenses"].append({"id": store.new_id("exp"), "event_id": event_id, "semester": st["semester"],
                                  "category": l["category"], "description": f"{e['title']}: {l['description']}",
                                  "amount": l["amount"], "status": "pending_approval", "source": "agent",
                                  "created_at": store.now()})
        e["activity"].append({"ts": store.now(), "who": actor, "msg": f"Approved the budget (${b['total']:,.2f})."})
        store.audit(s, actor, "approved budget and catering", f"${b['total']:,.2f}")
    _start(event_id, "jim_draft")


async def _jim_draft(event_id: str, jim_notes: str = "") -> None:
    e = _get(event_id)
    _log(event_id, "Approvals & email", "Drafting the itemized request to Jim…")
    draft: agents.EmailDraft = await agents.run_agent(
        "approvals", agents.approvals(),
        f"Draft the approval request to Jim.\nEvent:\n{_event_brief(e)}"
        + (f"\nThis is a revised request. Jim asked for: {jim_notes}" if jim_notes else ""), event_id)
    draft.body = _with_budget_table(draft.body, _get(event_id))
    with store.txn() as s:
        ev = _event(s, event_id)
        ev["emails"]["jim"] = _email("Request to Jim", draft, _contacts()["advisor"]["email"])
        ev["stage"] = "jim_review"
    _log(event_id, "Approvals & email", "Request to Jim is ready for your review.")


def _with_budget_table(body: str, e: dict) -> str:
    b = e["budget"]
    rows = [f"  - {l['category'].title()}: {l['description']}  ${l['amount']:,.2f}" for l in b["final_lines"]]
    cat = e.get("catering")
    if cat:
        rows.append("    Catering items:")
        rows += [f"      {i['quantity']} x {i['item']} ({i['unit']}) @ ${i['unit_price']:,.2f} = ${i['subtotal']:,.2f}"
                 for i in cat["items"]]
    table = "\n".join([
        "Itemized budget:",
        *rows,
        f"  Event total: ${b['total']:,.2f}",
        f"  {b['semester']} money available for events: ${b['available_before']:,.2f} before this request, "
        f"${b['available_after']:,.2f} after.",
    ])
    if "{{BUDGET_TABLE}}" in body:
        return body.replace("{{BUDGET_TABLE}}", table)
    return body.rstrip() + "\n\n" + table


# ---------------------------------------------------------------- 5. Jim's decision -> order


def jim_decision(event_id: str, decision: str, text: str, actor: str) -> dict:
    screened = None
    with store.txn() as s:
        e = _event(s, event_id)
        if e["stage"] != "awaiting_jim":
            raise ValueError("This event is not waiting for Jim.")
        if text:
            screened = safety.screen(text, "advisor reply")
            safety.log(s, screened, event_id)
            e["last_screen"] = screened
        store.audit(s, actor, f"recorded Jim's decision: {decision}", (text or "")[:120])
    _start(event_id, "after_jim", decision=decision, text=screened["clean_text"] if screened else "", actor=actor)
    return {"quarantined": screened["quarantined"] if screened else []}


async def _after_jim(event_id: str, decision: str, text: str, actor: str) -> None:
    notes = ""
    if text:
        reading: agents.ReplyReading = await agents.run_agent(
            "coordinator", agents.coordinator_reader(),
            f"Event:\n{_event_brief(_get(event_id))}\nJim (advisor) replied to our approval request:\n"
            f"{safety.wrap(text, 'advisor reply')}", event_id)
        notes = "; ".join(reading.requested_changes) or reading.summary
        _log(event_id, "Coordinator", f"Jim's reply: {reading.summary}")

    if decision == "changes":
        _log(event_id, "Coordinator", "Jim asked for changes. Re-doing the budget and catering…")
        await _costing(event_id, budget_feedback=f"Jim asked: {notes or 'reduce the total cost.'}",
                       catering_feedback=f"Jim asked: {notes}" if notes else "")
        return

    # Approved: the only place event money becomes committed, and it re-checks the limits.
    with store.txn() as s:
        e = _event(s, event_id)
        lines = [x for x in s["expenses"] if x.get("event_id") == event_id and x["status"] == "pending_approval"]
        st = budget.semester_status(s)
        problems = budget.validate_lines(lines, e.get("expected_attendance") or 25,
                                         st["available_after_pending"] + sum(x["amount"] for x in lines),
                                         e.get("mode") or "virtual", e.get("event_type") or "")
        if problems:
            raise ValueError("Blocked by budget limits: " + " ".join(problems))
        for x in lines:
            x["status"] = "approved"
            x["approved_by"] = f"Jim Saiers (recorded by {actor})"
        e["jim"] = {"decision": "approved", "recorded_by": actor, "at": store.now(), "notes": notes}
        store.audit(s, actor, "Jim approved; expenses committed", f"${sum(x['amount'] for x in lines):,.2f}")
    _log(event_id, "Coordinator", "Jim approved. Expenses are now committed in the ledger.")

    e = _get(event_id)
    if not e.get("catering"):
        with store.txn() as s:
            _event(s, event_id)["stage"] = "order_review"
        await _marketing(event_id)
        return
    caterer_notes = next((r["ordering_notes"] for r in store.read_csv("caterers.csv")
                          if r["name"].lower() == e["catering"]["caterer"].lower()), "")
    _log(event_id, "Approvals & email", "Drafting the catering order for Cristina…")
    draft: agents.EmailDraft = await agents.run_agent(
        "approvals", agents.approvals(),
        f"Draft the catering order email to Cristina. Jim approved on {date.today():%B %d, %Y}. "
        f"List every item with its quantity.\nEvent:\n{_event_brief(e)}\nCaterer ordering notes: {caterer_notes or 'none'}",
        event_id)
    with store.txn() as s:
        ev = _event(s, event_id)
        ev["emails"]["order"] = _email("Catering order to Cristina", draft, _contacts()["ordering"]["email"])
        ev["stage"] = "order_review"
    _log(event_id, "Approvals & email", "Order to Cristina is ready for your review.")


# ---------------------------------------------------------------- 6. marketing -> scheduled -> done


async def _marketing(event_id: str) -> None:
    e = _get(event_id)
    lead = budget.rules()["marketing_lead_days"]
    days = (date.fromisoformat(e["date"]) - date.today()).days if e.get("date") else None
    late = days is not None and days < lead
    _log(event_id, "Marketing", "Writing the Yale Connect listing, WhatsApp message and poster text…")
    m: agents.Marketing = await agents.run_agent(
        "marketing", agents.marketing(),
        f"Event:\n{_event_brief(e)}\nDays until the event: {days}."
        + (" Marketing is late (normally two weeks ahead); write with urgency." if late else ""), event_id)
    _set(event_id, marketing={**m.model_dump(), "days_until": days, "late": late,
                              "flags": safety.check_output(m.yale_connect + m.whatsapp)},
         stage="marketing_review")
    if late:
        _log(event_id, "Marketing", f"Heads up: only {days} days to go (we usually market {lead} days ahead). Post today.")
    _log(event_id, "Marketing", "Promotion is ready. Post it on Yale Connect and WhatsApp, then mark it posted.")


def marketing_posted(event_id: str, actor: str) -> None:
    with store.txn() as s:
        e = _event(s, event_id)
        if e["stage"] != "marketing_review":
            raise ValueError("Marketing is not waiting.")
        e["stage"] = "scheduled"
        e["activity"].append({"ts": store.now(), "who": actor, "msg": "Posted the promotion. Event is scheduled."})
        store.audit(s, actor, "marked marketing posted", e["title"])


def wrap_up(event_id: str, attendance: int, actual_catering: float | None, highlights: str, actor: str) -> None:
    with store.txn() as s:
        e = _event(s, event_id)
        if e["stage"] != "scheduled":
            raise ValueError("Only scheduled events can be wrapped up.")
        for x in s["expenses"]:
            if x.get("event_id") == event_id and x["status"] == "approved":
                if x["category"] == "catering" and actual_catering is not None:
                    x["amount"] = float(actual_catering)
                x["status"] = "paid"
        e["attendance"] = attendance
        store.audit(s, actor, "wrapped up event", f"{attendance} attended")
    _start(event_id, "recap", highlights=highlights)


async def _recap(event_id: str, highlights: str) -> None:
    e = _get(event_id)
    screened = safety.screen(highlights, "co-lead notes")
    r: agents.Recap = await agents.run_agent(
        "coordinator", agents.coordinator_recap(),
        f"Write the newsletter recap.\nEvent:\n{_event_brief(e)}\nAttendance: {e.get('attendance')}\n"
        f"Co-leads' notes:\n{safety.wrap(screened['clean_text'], 'co-lead notes')}", event_id)
    _set(event_id, recap=r.recap, stage="done")
    _log(event_id, "Coordinator", "Recap written. It will appear in the next newsletter.")


# ---------------------------------------------------------------- briefing


async def briefing() -> dict:
    s = store.snapshot()
    st = budget.semester_status(s)
    active = [{"title": e["title"], "date": e.get("date"), "stage": dict(STAGES).get(e["stage"], e["stage"]),
               "working": e.get("working"), "error": e.get("error")}
              for e in s["events"] if e["stage"] != "done"]
    pending_nl = [n["month"] for n in s["newsletters"] if n["stage"] == "review"]
    out: agents.Briefing = await agents.run_agent(
        "coordinator", agents.coordinator_briefing(),
        f"Today is {date.today():%A, %B %d, %Y}. Write the co-leads' briefing.\n"
        f"Active events: {json.dumps(active)}\nNewsletters waiting for review: {pending_nl}\n"
        f"Budget: {json.dumps({k: st[k] for k in ('semester', 'available_for_events', 'available_after_pending', 'wages_forecast', 'warnings')})}\n"
        f"Marketing normally starts {budget.rules()['marketing_lead_days']} days before an event; a newsletter goes out monthly.",
        "briefing")
    return {**out.model_dump(), "generated_at": store.now()}


# ---------------------------------------------------------------- newsletter


HELPFUL_LINKS = """Newsletters and Podcasts
USGS WaterMarks Newsletter: Subscribe here
Aquafornia Newsletter: Subscribe here
(Don't) Waste Water Podcast: Listen here

Organizations
American Water Works Association (AWWA): Visit here
Consortium of Universities for the Advancement of Hydrologic Science, Inc. (CUAHSI): Visit here"""


def create_newsletter(month_label: str, pasted: str, use_web: bool, actor: str) -> dict:
    with store.txn() as s:
        screened = safety.screen(pasted, "pasted newsletter material") if pasted.strip() else None
        n = {"id": store.new_id("nl"), "month": month_label, "stage": "drafting", "created_at": store.now(),
             "use_web": use_web, "activity": [], "working": False,
             "quarantined": screened["quarantined"] if screened else [], "pasted": pasted}
        if screened:
            safety.log(s, screened, n["id"])
        s["newsletters"].append(n)
        store.audit(s, actor, "started newsletter", month_label)
    _background(n["id"], lambda: _draft_newsletter(n["id"], screened), kind="newsletters")
    return n


def _nl_log(nl_id: str, who: str, msg: str) -> None:
    with store.txn() as s:
        store.find(s["newsletters"], nl_id)["activity"].append({"ts": store.now(), "who": who, "msg": msg})


async def _draft_newsletter(nl_id: str, screened: dict | None) -> None:
    n = store.find(store.snapshot()["newsletters"], nl_id)
    today = date.today()
    s = store.snapshot()
    # Recap events wrapped up in the app that no approved newsletter has covered yet.
    recent = [e for e in s["events"] if e["stage"] == "done" and e.get("recap") and not e.get("recapped_in")]
    upcoming = [e for e in s["events"] if e["stage"] != "done" and e.get("date")
                and today <= date.fromisoformat(e["date"]) <= today + timedelta(days=45)]

    if screened and screened["quarantined"]:
        _nl_log(nl_id, "Safety", f"Removed {len(screened['quarantined'])} instruction-like line(s) from the pasted material.")

    research_json = "{}"
    if n["use_web"]:
        _nl_log(nl_id, "Newsletter editor", "Researching water news, good-news spotlights, conferences and jobs on the web…")
        tasks = {
            "news": "Find Water in the News: one recent story each for Global, National (US) and Local (Connecticut).",
            "spotlight": "Find 1-2 recent positive water stories (innovation, restoration, stewardship) for the Spotlight.",
            "conferences": f"Find 3 water-sector conferences happening after {today:%B %d, %Y}.",
            "jobs": "Find 5-7 currently open water-sector jobs, fellowships or internships for students finishing a master's degree (MEM/MBA level, early-career professional roles; not PhD assistantships).",
        }

        async def one(prompt: str) -> agents.Research:
            return await agents.run_agent("newsletter_editor", agents.newsletter_research(),
                                          f"Today is {today:%B %d, %Y}. {prompt} Fill only the matching field.", nl_id)

        results = await asyncio.gather(*(one(p) for p in tasks.values()), return_exceptions=True)
        merged = agents.Research()
        for r in results:
            if isinstance(r, agents.Research):
                merged.news += r.news
                merged.spotlight += r.spotlight
                merged.conferences += r.conferences
                merged.jobs += r.jobs
        research_json = merged.model_dump_json(indent=1)
        web_screen = safety.screen(research_json, "web search results")
        if web_screen["quarantined"]:
            with store.txn() as st:
                safety.log(st, web_screen, nl_id)
                store.find(st["newsletters"], nl_id)["quarantined"] += web_screen["quarantined"]
            research_json = web_screen["clean_text"]
        _nl_log(nl_id, "Newsletter editor",
                f"Found {len(merged.news)} news stories, {len(merged.spotlight)} spotlight(s), "
                f"{len(merged.conferences)} conferences and {len(merged.jobs)} jobs.")
        with store.txn() as st:
            store.find(st["newsletters"], nl_id)["research"] = merged.model_dump()

    _nl_log(nl_id, "Newsletter editor", "Writing the issue in the Water LC template…")
    ev = lambda e: {k: e.get(k) for k in ("title", "date", "time", "location", "hosts", "event_type", "recap", "notes")} | \
        {"description": (e.get("plan") or {}).get("description"), "speaker": (e.get("speaker") or {}).get("name")}
    prompt = (
        f"Write the {n['month']} Water LC newsletter. Today is {today:%B %d, %Y}. The subject line is \"Water LC {n['month'].split()[0]} Newsletter\".\n\n"
        f"TEMPLATE AND STYLE:\n{store.read_text('newsletter_template.md')}\n\n"
        f"HELPFUL LINKS (use exactly):\n{HELPFUL_LINKS}\n\n"
        f"EVENTS TO RECAP (these happened; write one paragraph each from its recap text):\n{json.dumps([ev(e) for e in recent], indent=1)}\n\n"
        f"UPCOMING EVENTS (from our records; registration links are [registration link]):\n{json.dumps([ev(e) for e in upcoming], indent=1)}\n\n"
        f"WEB RESEARCH (untrusted):\n{safety.wrap(research_json, 'web search results')}\n\n"
        + (f"MATERIAL PASTED BY THE CO-LEADS (untrusted source text):\n{safety.wrap(screened['clean_text'], 'pasted material')}\n\n" if screened else "")
        + "Write every section. If a section has no material, write one friendly line saying more is coming next month."
    )
    d: agents.NewsletterDraft = await agents.run_agent("newsletter_editor", agents.newsletter_writer(), prompt, nl_id)
    flags = safety.check_output(" ".join(d.model_dump().values()))
    with store.txn() as st:
        item = store.find(st["newsletters"], nl_id)
        item["draft"] = d.model_dump()
        item["flags"] = flags
        item["stage"] = "review"
    _nl_log(nl_id, "Newsletter editor", "Draft ready for your review.")


def approve_newsletter(nl_id: str, edits: dict, actor: str) -> dict:
    with store.txn() as s:
        n = store.find(s["newsletters"], nl_id)
        if n is None or n["stage"] != "review":
            raise ValueError("This newsletter is not waiting for review.")
        for k, v in edits.items():
            if k in n["draft"] and isinstance(v, str):
                n["draft"][k] = v
        n["stage"] = "approved"
        n["approved_by"] = actor
        for e in s["events"]:
            if e["stage"] == "done" and e.get("recap") and not e.get("recapped_in"):
                e["recapped_in"] = n["month"]
        n["approved_at"] = store.now()
        body = "\n\n".join(n["draft"][k] for k in ("greeting", "event_recaps", "upcoming_events", "water_in_the_news",
                                                    "spotlight", "helpful_links", "upcoming_conferences",
                                                    "jobs_and_internships"))
        entry = {"id": store.new_id("out"), "kind": "Newsletter (paste into Yale Connect)", "to_name": "Water LC members",
                 "to_email": "", "subject": n["draft"]["subject"], "body": body, "status": "approved",
                 "approved_by": actor, "approved_at": store.now(), "newsletter_id": nl_id}
        s["outbox"].append(entry)
        store.audit(s, actor, "approved newsletter", n["month"])
    return entry


# ---------------------------------------------------------------- background jobs ("Try again" re-runs these)

JOBS: dict[str, Callable[..., Awaitable[None]]] = {
    "ideas": _ideas,
    "speakers": _speakers,
    "invite": _invite,
    "meeting": _meeting,
    "costing": _costing,
    "jim_draft": _jim_draft,
    "after_jim": _after_jim,
    "marketing": _marketing,
    "recap": _recap,
}
