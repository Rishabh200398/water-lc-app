"""Water LC app backend (FastAPI).

Public routes need no login; /api/admin/* routes need the admin password (ADMIN_PASSWORD in
.env, default "waterlc"). The built React app in frontend/dist is served at "/", so one
command runs everything:

    .venv/bin/uvicorn backend.main:app --port 8040          (from the repo root)

Add --host 0.0.0.0 to open it from a phone on the same Wi-Fi.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # allow "backend.main" and "main"

from fastapi import Depends, FastAPI, Header, HTTPException  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel  # noqa: E402

import agents  # noqa: E402
import budget  # noqa: E402
import model_config  # noqa: E402  (loads .env)
import safety  # noqa: E402
import store  # noqa: E402
import usage  # noqa: E402
import workflow  # noqa: E402

app = FastAPI(title="Water LC app")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["*"], allow_headers=["*"])

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "waterlc")
_SECRET = (os.getenv("SESSION_SECRET") or ADMIN_PASSWORD + "-water-lc-session").encode()
CO_LEADS = budget.rules()["wages"]["co_leads"]


# ---------------------------------------------------------------- auth


def _token(name: str) -> str:
    sig = hmac.new(_SECRET, name.encode(), hashlib.sha256).digest()
    return f"{name}.{base64.urlsafe_b64encode(sig).decode().rstrip('=')}"


def admin(authorization: str = Header(default="")) -> str:
    """Returns the co-lead's name from a valid token, or 401."""
    token = authorization.removeprefix("Bearer ").strip()
    name = token.split(".", 1)[0]
    if not token or name not in CO_LEADS or not hmac.compare_digest(_token(name), token):
        raise HTTPException(401, "Please log in as a co-lead.")
    return name


class Login(BaseModel):
    name: str
    password: str


@app.post("/api/login")
def login(body: Login) -> dict:
    if body.name not in CO_LEADS:
        raise HTTPException(400, f"Choose one of: {', '.join(CO_LEADS)}")
    if not hmac.compare_digest(body.password, ADMIN_PASSWORD):
        raise HTTPException(401, "Wrong password.")
    return {"token": _token(body.name), "name": body.name}


def _guard(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except (ValueError, KeyError) as e:
        raise HTTPException(400, str(e).strip("'"))


# ---------------------------------------------------------------- public


@app.get("/api/health")
def health() -> dict:
    ok, detail = model_config.model_ready()
    return {"ok": True, "model_ready": ok, "model": detail, "today": date.today().isoformat()}


@app.get("/api/public")
def public() -> dict:
    s = store.snapshot()
    today = date.today().isoformat()

    def card(e: dict) -> dict:
        plan = e.get("plan") or {}
        return {"id": e["id"], "title": e["title"], "date": e.get("date"), "time": e.get("time"),
                "location": e.get("location"), "hosts": e.get("hosts"), "event_type": e.get("event_type"),
                "description": plan.get("description") or e.get("notes", ""), "recap": e.get("recap"),
                "speaker": (e.get("speaker") or {}).get("name") if (e.get("speaker") or {}).get("status") == "confirmed" else None}

    events = [e for e in s["events"] if e.get("date")]
    upcoming = sorted([card(e) for e in events if e["date"] >= today and e["stage"] != "done"], key=lambda x: x["date"])
    past = sorted([card(e) for e in events if e["stage"] == "done" or e["date"] < today], key=lambda x: x["date"], reverse=True)
    newsletters = [{"id": n["id"], "month": n["month"], "approved_at": n.get("approved_at"), **n["draft"]}
                   for n in s["newsletters"] if n["stage"] == "approved"]
    interests = [r["topic"] for r in store.read_csv("member_interests_fall_2026.csv") if int(r["priority"]) <= 3]
    return {"upcoming": upcoming, "past": past, "newsletters": list(reversed(newsletters)),
            "alumni": [], "interests": interests, "co_leads": CO_LEADS}


# ---------------------------------------------------------------- dashboard


def _event_view(e: dict) -> dict:
    stages = [k for k, _ in workflow.STAGES]
    return {**e, "stage_label": dict(workflow.STAGES).get(e["stage"], e["stage"]),
            "stage_index": stages.index(e["stage"]) if e["stage"] in stages else 0,
            "needs_you": e["stage"] in workflow.WAITING_ON_YOU and not e.get("working")}


@app.get("/api/admin/dashboard")
def dashboard(who: str = Depends(admin)) -> dict:
    s = store.snapshot()
    events = [_event_view(e) for e in s["events"]]
    active = [e for e in events if e["stage"] != "done"]
    u = usage.summary(s)
    return {
        "me": who,
        "budget": budget.semester_status(s),
        "active_events": sorted(active, key=lambda e: e.get("date") or "9999"),
        "needs_you": [e for e in active if e["needs_you"]],
        "newsletters_in_review": [n for n in s["newsletters"] if n["stage"] == "review"],
        "usage": {k: u[k] for k in ("runs", "input_tokens", "cached_input_tokens", "output_tokens", "cost_usd",
                                    "cache_hit_rate", "water_ml")},
        "outbox_count": len(s["outbox"]),
        "security_count": len(s["security_log"]),
        "stages": workflow.STAGES,
    }


@app.post("/api/admin/briefing")
async def make_briefing(who: str = Depends(admin)) -> dict:
    try:
        return await workflow.briefing()
    except Exception as e:  # show a readable message instead of a bare 500
        msg = str(e) if e.__class__.__name__ == "AIUnavailable" else f"The briefing failed: {type(e).__name__}. Please try again."
        raise HTTPException(503, msg)


# ---------------------------------------------------------------- events


class Intake(BaseModel):
    format: str = ""
    mode: str = "either"
    collab: str = "open"
    timing: str = ""
    attendance: int | None = None
    notes: str = ""


class FindIdeas(BaseModel):
    intake: Intake | None = None
    feedback: str = ""
    fresh_research: bool = False


@app.get("/api/admin/events")
def list_events(who: str = Depends(admin)) -> dict:
    s = store.snapshot()
    return {"events": [_event_view(e) for e in sorted(s["events"], key=lambda e: e.get("date") or "9999")],
            "stages": workflow.STAGES}


@app.get("/api/admin/events/{event_id}")
def get_event(event_id: str, who: str = Depends(admin)) -> dict:
    e = store.find(store.snapshot()["events"], event_id)
    if e is None:
        raise HTTPException(404, "No such event.")
    return {"event": _event_view(e), "stages": workflow.STAGES, "contacts": store.read_json("contacts.json"),
            "limits": budget.rules()["limits"], "formats": agents.FORMATS}


@app.post("/api/admin/events")
async def new_event(body: Intake, who: str = Depends(admin)) -> dict:
    return workflow.create_event(body.model_dump(), who)


@app.post("/api/admin/events/{event_id}/ideas")
async def find_ideas(event_id: str, body: FindIdeas, who: str = Depends(admin)) -> dict:
    _guard(workflow.find_ideas, event_id, body.intake.model_dump() if body.intake else None,
           body.feedback.strip(), body.fresh_research, who)
    return {"ok": True}


class Choose(BaseModel):
    index: int
    keep_collab: bool = True
    from_history: bool = False


@app.post("/api/admin/events/{event_id}/choose-idea")
async def choose_idea(event_id: str, body: Choose, who: str = Depends(admin)) -> dict:
    _guard(workflow.choose_idea, event_id, body.index, body.keep_collab, who, body.from_history)
    return {"ok": True}


class Feedback(BaseModel):
    feedback: str = ""


@app.post("/api/admin/events/{event_id}/speakers/rerun")
async def rerun_speakers(event_id: str, body: Feedback, who: str = Depends(admin)) -> dict:
    _guard(workflow.rerun_speakers, event_id, body.feedback.strip(), who)
    return {"ok": True}


class Person(BaseModel):
    name: str
    organization: str = ""
    role: str = ""
    degree: str = ""
    location: str = ""
    email: str = ""
    mode: str = "virtual"
    why: str = ""


@app.post("/api/admin/events/{event_id}/speakers/add")
def add_speaker(event_id: str, body: Person, who: str = Depends(admin)) -> dict:
    _guard(workflow.add_speaker, event_id, body.model_dump(), who)
    return {"ok": True}


class Index(BaseModel):
    index: int


@app.post("/api/admin/events/{event_id}/speakers/remove")
def remove_speaker(event_id: str, body: Index, who: str = Depends(admin)) -> dict:
    _guard(workflow.remove_speaker, event_id, body.index, who)
    return {"ok": True}


@app.post("/api/admin/events/{event_id}/speakers/confirm")
async def confirm_speaker(event_id: str, body: Index, who: str = Depends(admin)) -> dict:
    _guard(workflow.confirm_speaker, event_id, body.index, who)
    return {"ok": True}


@app.post("/api/admin/events/{event_id}/speakers/back")
def back_to_speakers(event_id: str, who: str = Depends(admin)) -> dict:
    _guard(workflow.back_to_speakers, event_id, who)
    return {"ok": True}


class EmailEdits(BaseModel):
    to_email: str | None = None
    subject: str | None = None
    body: str | None = None


@app.post("/api/admin/events/{event_id}/emails/{kind}/approve")
async def approve_email(event_id: str, kind: str, body: EmailEdits, who: str = Depends(admin)) -> dict:
    return _guard(workflow.approve_email, event_id, kind, body.model_dump(), who)


class Notes(BaseModel):
    notes: str


@app.post("/api/admin/events/{event_id}/meeting-notes")
async def meeting_notes(event_id: str, body: Notes, who: str = Depends(admin)) -> dict:
    if not body.notes.strip():
        raise HTTPException(400, "Paste your notes or the speaker's reply first.")
    return _guard(workflow.meeting_notes, event_id, body.notes, who)


class ConfirmDate(BaseModel):
    date: str
    time: str = "12:00-13:00"
    location: str = ""
    mode: str = "virtual"
    travel_from: str = ""
    honorarium: float | None = None
    attendance: int | None = None


@app.post("/api/admin/events/{event_id}/confirm-date")
async def confirm_date(event_id: str, body: ConfirmDate, who: str = Depends(admin)) -> dict:
    _guard(workflow.confirm_date, event_id, body.model_dump(), who)
    return {"ok": True}


class Rerun(BaseModel):
    what: str  # "budget" or "catering"
    feedback: str = ""


@app.post("/api/admin/events/{event_id}/costing/rerun")
async def rerun_costing(event_id: str, body: Rerun, who: str = Depends(admin)) -> dict:
    if body.what not in ("budget", "catering"):
        raise HTTPException(400, "what must be 'budget' or 'catering'")
    _guard(workflow.rerun_costing, event_id, body.what, body.feedback.strip(), who)
    return {"ok": True}


@app.post("/api/admin/events/{event_id}/costing/approve")
async def approve_costing(event_id: str, who: str = Depends(admin)) -> dict:
    _guard(workflow.approve_costing, event_id, who)
    return {"ok": True}


class JimDecision(BaseModel):
    decision: str
    text: str = ""


@app.post("/api/admin/events/{event_id}/jim")
async def jim(event_id: str, body: JimDecision, who: str = Depends(admin)) -> dict:
    if body.decision not in ("approved", "changes"):
        raise HTTPException(400, "decision must be 'approved' or 'changes'")
    return _guard(workflow.jim_decision, event_id, body.decision, body.text, who)


@app.post("/api/admin/events/{event_id}/marketing-posted")
def marketing_posted(event_id: str, who: str = Depends(admin)) -> dict:
    _guard(workflow.marketing_posted, event_id, who)
    return {"ok": True}


class WrapUp(BaseModel):
    attendance: int
    actual_catering: float | None = None
    highlights: str = ""


@app.post("/api/admin/events/{event_id}/wrap-up")
async def wrap_up(event_id: str, body: WrapUp, who: str = Depends(admin)) -> dict:
    _guard(workflow.wrap_up, event_id, body.attendance, body.actual_catering, body.highlights, who)
    return {"ok": True}


@app.post("/api/admin/events/{event_id}/retry")
async def retry(event_id: str, who: str = Depends(admin)) -> dict:
    _guard(workflow.retry, event_id)
    return {"ok": True}


@app.delete("/api/admin/events/{event_id}")
def delete_event(event_id: str, who: str = Depends(admin)) -> dict:
    with store.txn() as s:
        e = store.find(s["events"], event_id)
        if e is None:
            raise HTTPException(404, "No such event.")
        s["events"].remove(e)
        s["expenses"] = [x for x in s["expenses"] if not (x.get("event_id") == event_id and x["status"] == "pending_approval")]
        store.audit(s, who, "deleted event", e["title"])
    return {"ok": True}


# ---------------------------------------------------------------- budget


@app.get("/api/admin/budget")
def get_budget(who: str = Depends(admin)) -> dict:
    s = store.snapshot()
    titles = {e["id"]: e["title"] for e in s["events"]}
    return {"status": budget.semester_status(s), "limits": budget.rules()["limits"],
            "expenses": [{**x, "event_title": titles.get(x.get("event_id"))} for x in reversed(s["expenses"])],
            "hours": sorted(s["hours"], key=lambda h: h["week_start"], reverse=True),
            "co_leads": CO_LEADS, "max_hours": budget.rules()["wages"]["max_hours_per_person_per_week"],
            "categories": budget.CATEGORIES}


class Hours(BaseModel):
    week_start: str
    person: str
    hours: float


@app.post("/api/admin/budget/hours")
def add_hours(body: Hours, who: str = Depends(admin)) -> dict:
    with store.txn() as s:
        try:
            entry = budget.log_hours(s, body.week_start, body.person, body.hours)
        except ValueError as e:
            raise HTTPException(400, str(e))
        store.audit(s, who, "logged hours", f"{body.person} {body.hours}h week of {body.week_start}")
    return entry


class Expense(BaseModel):
    description: str
    category: str
    amount: float
    status: str = "paid"


@app.post("/api/admin/budget/expenses")
def add_expense(body: Expense, who: str = Depends(admin)) -> dict:
    if body.category not in budget.CATEGORIES or body.status not in ("paid", "approved") or body.amount <= 0:
        raise HTTPException(400, "Check the category, status (paid/approved) and amount.")
    with store.txn() as s:
        st = budget.semester_status(s)
        if body.amount > st["available_after_pending"]:
            raise HTTPException(400, f"${body.amount:,.2f} is more than the ${st['available_after_pending']:,.2f} available.")
        entry = {"id": store.new_id("exp"), "event_id": None, "semester": st["semester"], "category": body.category,
                 "description": body.description, "amount": body.amount, "status": body.status, "source": f"added by {who}",
                 "created_at": store.now()}
        s["expenses"].append(entry)
        store.audit(s, who, "added expense", f"{body.description} ${body.amount:,.2f}")
    return entry


@app.delete("/api/admin/budget/expenses/{exp_id}")
def delete_expense(exp_id: str, who: str = Depends(admin)) -> dict:
    with store.txn() as s:
        x = store.find(s["expenses"], exp_id)
        if x is None:
            raise HTTPException(404, "No such expense.")
        s["expenses"].remove(x)
        store.audit(s, who, "deleted expense", x["description"])
    return {"ok": True}


# ---------------------------------------------------------------- newsletters


class NewNewsletter(BaseModel):
    month: str
    pasted: str = ""
    use_web: bool = True


@app.get("/api/admin/newsletters")
def list_newsletters(who: str = Depends(admin)) -> list:
    return list(reversed(store.snapshot()["newsletters"]))


@app.get("/api/admin/newsletters/{nl_id}")
def get_newsletter(nl_id: str, who: str = Depends(admin)) -> dict:
    n = store.find(store.snapshot()["newsletters"], nl_id)
    if n is None:
        raise HTTPException(404, "No such newsletter.")
    return n


@app.post("/api/admin/newsletters")
async def new_newsletter(body: NewNewsletter, who: str = Depends(admin)) -> dict:
    return workflow.create_newsletter(body.month, body.pasted, body.use_web, who)


@app.post("/api/admin/newsletters/{nl_id}/approve")
def approve_newsletter(nl_id: str, body: dict, who: str = Depends(admin)) -> dict:
    return _guard(workflow.approve_newsletter, nl_id, body, who)


@app.delete("/api/admin/newsletters/{nl_id}")
def delete_newsletter(nl_id: str, who: str = Depends(admin)) -> dict:
    with store.txn() as s:
        n = store.find(s["newsletters"], nl_id)
        if n is None:
            raise HTTPException(404, "No such newsletter.")
        s["newsletters"].remove(n)
    return {"ok": True}


# ---------------------------------------------------------------- outbox, usage, security, demo


@app.get("/api/admin/outbox")
def outbox(who: str = Depends(admin)) -> list:
    return list(reversed(store.snapshot()["outbox"]))


@app.get("/api/admin/usage")
def get_usage(who: str = Depends(admin)) -> dict:
    return usage.summary(store.snapshot())


@app.get("/api/admin/security")
def security(who: str = Depends(admin)) -> dict:
    s = store.snapshot()
    return {"log": list(reversed(s["security_log"])), "audit": list(reversed(s["audit"][-100:]))}


class ScreenText(BaseModel):
    text: str


@app.post("/api/admin/security/screen")
def screen_text(body: ScreenText, who: str = Depends(admin)) -> dict:
    """Try the injection screen on any text without running an agent."""
    return safety.screen(body.text, "manual test")


@app.get("/api/admin/demo/{name}")
def demo_file(name: str, who: str = Depends(admin)) -> dict:
    files = {"injected_article": "injected_article.txt", "speaker_reply_accept": "speaker_reply_accept.txt"}
    if name not in files:
        raise HTTPException(404, "Unknown demo file.")
    return {"text": (store.DATA / "demo" / files[name]).read_text()}


@app.post("/api/admin/reset")
def reset(who: str = Depends(admin)) -> dict:
    store.reset()
    with store.txn() as s:
        store.audit(s, who, "reset demo data")
    return {"ok": True}


# ---------------------------------------------------------------- the React app

DIST = store.ROOT / "frontend" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        f = DIST / path
        if path and f.is_file():
            return FileResponse(f)
        return FileResponse(DIST / "index.html")
