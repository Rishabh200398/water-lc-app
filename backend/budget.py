"""Budget keeper: all money math and every hard limit, in plain code.

Agents can *read* these numbers through tools and *propose* cost lines, but only this
module decides whether a proposal fits. Nothing here calls the LLM, so no prompt (or
injected text) can change a limit or the arithmetic.

Semester money = budget - wages (logged + forecast) - event spending (approved + paid).
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import store

CATEGORIES = ["catering", "honorarium", "travel", "lodging", "supplies", "transport", "other"]


def rules() -> dict[str, Any]:
    return store.read_json("budget_rules.json")


# ---------------------------------------------------------------- calendar


def calendar_blocks() -> list[dict[str, Any]]:
    out = []
    for r in store.read_csv("yse_calendar_2026_27.csv"):
        out.append({"start": date.fromisoformat(r["start_date"]), "end": date.fromisoformat(r["end_date"]),
                    "label": r["label"], "blocks": r["blocks_events"] == "yes", "term": r["term"]})
    return out


def check_date(d: str) -> dict[str, Any]:
    """Is this date usable for a Water LC event? Weekdays only, not in a blocked YSE period."""
    try:
        day = date.fromisoformat(d)
    except ValueError:
        return {"date": d, "ok": False, "reasons": ["Not a valid YYYY-MM-DD date."]}
    reasons = []
    if day.weekday() >= 5:
        reasons.append(f"{day:%A} is a weekend.")
    for b in calendar_blocks():
        if b["blocks"] and b["start"] <= day <= b["end"]:
            reasons.append(f"YSE calendar: {b['label']}.")
    if day < date.today():
        reasons.append("Date is in the past.")
    notes = [b["label"] for b in calendar_blocks() if not b["blocks"] and b["start"] <= day <= b["end"]]
    return {"date": d, "weekday": day.strftime("%A"), "ok": not reasons, "reasons": reasons, "notes": notes}


def open_dates(start: str, end: str, limit: int = 15) -> list[str]:
    """Open weekdays (Tue-Thu first, the best lunch days) between start and end."""
    s, e = date.fromisoformat(start), date.fromisoformat(end)
    days, d = [], max(s, date.today() + timedelta(days=1))
    while d <= e:
        if check_date(d.isoformat())["ok"]:
            days.append(d)
        d += timedelta(days=1)
    days.sort(key=lambda x: (x.weekday() not in (1, 2, 3), x))
    return [x.isoformat() for x in days[:limit]]


def semester_for(d: date) -> dict[str, Any]:
    for sem in rules()["semesters"]:
        if date.fromisoformat(sem["start"]) <= d <= date.fromisoformat(sem["end"]):
            return sem
    return rules()["semesters"][0]


def working_weeks(sem: dict[str, Any], after: date | None = None) -> list[date]:
    """Mondays of weeks with at least 3 open weekdays (recess and exam weeks drop out)."""
    start, end = date.fromisoformat(sem["start"]), date.fromisoformat(sem["end"])
    monday = start - timedelta(days=start.weekday())
    weeks = []
    while monday <= end:
        open_days = 0
        for i in range(5):
            day = monday + timedelta(days=i)
            if start <= day <= end and not any(
                b["blocks"] and b["start"] <= day <= b["end"] for b in calendar_blocks()
            ):
                open_days += 1
        if open_days >= 3 and (after is None or monday > after):
            weeks.append(monday)
        monday += timedelta(days=7)
    return weeks


# ---------------------------------------------------------------- status


def semester_status(s: dict[str, Any], semester_name: str | None = None, today: date | None = None) -> dict[str, Any]:
    r = rules()
    today = today or date.today()
    sem = next((x for x in r["semesters"] if x["name"] == semester_name), None) or semester_for(today)
    w = r["wages"]
    rate = w["hourly_rate_usd"]
    sem_start, sem_end = date.fromisoformat(sem["start"]), date.fromisoformat(sem["end"])

    logged = [h for h in s["hours"] if sem_start <= date.fromisoformat(h["week_start"]) <= sem_end]
    logged_hours = sum(h["hours"] for h in logged)
    last_logged = max((date.fromisoformat(h["week_start"]) for h in logged), default=None)
    after = max(filter(None, [last_logged, today - timedelta(days=today.weekday() + 1)]))
    weeks_left = len(working_weeks(sem, after=after))
    expected = w.get("forecast_hours_per_person_per_week", sum(w["typical_hours_per_person_per_week"]) / 2)
    people = len(w["co_leads"])
    forecast_hours = weeks_left * expected * people

    exp = [e for e in s["expenses"] if e["semester"] == sem["name"]]
    paid = sum(e["amount"] for e in exp if e["status"] == "paid")
    approved = sum(e["amount"] for e in exp if e["status"] == "approved")
    pending = sum(e["amount"] for e in exp if e["status"] == "pending_approval")

    wages_logged = logged_hours * rate
    wages_forecast = forecast_hours * rate
    committed = wages_logged + wages_forecast + paid + approved
    available = sem["budget_usd"] - committed
    reserve = r["limits"]["keep_reserve_usd"]

    # Over-10-hours weeks
    over = []
    by_week: dict[tuple[str, str], float] = {}
    for h in logged:
        key = (h["week_start"], h["person"])
        by_week[key] = by_week.get(key, 0) + h["hours"]
    for (wk, person), hrs in by_week.items():
        if hrs > w["max_hours_per_person_per_week"]:
            over.append({"week_start": wk, "person": person, "hours": hrs})

    warnings = []
    if available - pending < reserve:
        warnings.append(f"Less than the ${reserve:,.0f} reserve would be left after pending requests.")
    if over:
        warnings.append(f"{len(over)} logged week(s) exceed {w['max_hours_per_person_per_week']} hours per person.")

    return {
        "semester": sem["name"],
        "budget": sem["budget_usd"],
        "hourly_rate": rate,
        "wages_logged": round(wages_logged, 2),
        "hours_logged": logged_hours,
        "wages_forecast": round(wages_forecast, 2),
        "forecast_hours": forecast_hours,
        "forecast_hours_per_person_per_week": expected,
        "weeks_left": weeks_left,
        "events_paid": round(paid, 2),
        "events_approved": round(approved, 2),
        "events_pending": round(pending, 2),
        "available_for_events": round(available, 2),
        "available_after_pending": round(available - pending, 2),
        "reserve": reserve,
        "over_hours": over,
        "warnings": warnings,
        "annual_budget": r["annual_budget_usd"],
        "last_year": r.get("history", {}).get("2025_26"),
    }


# ---------------------------------------------------------------- hard limits


def validate_lines(lines: list[dict[str, Any]], headcount: int, available: float,
                   mode: str = "in_person", event_format: str = "") -> list[str]:
    """Every rule an event budget must pass. Returns the problems (empty list = OK).

    mode: "virtual" or "in_person" (the speaker's). event_format: e.g. "field visit".
    """
    lim = rules()["limits"]
    problems = []
    field_visit = event_format == "field visit"
    totals: dict[str, float] = {}
    for ln in lines:
        cat, amt = ln.get("category"), ln.get("amount")
        if cat not in CATEGORIES:
            problems.append(f"Unknown category {cat!r}; use one of {', '.join(CATEGORIES)}.")
            continue
        if not isinstance(amt, (int, float)) or amt < 0:
            problems.append(f"{cat}: amount must be a number of dollars, 0 or more.")
            continue
        totals[cat] = totals.get(cat, 0) + amt
    if mode == "virtual" and not field_visit:
        for cat in ("honorarium", "travel", "lodging"):
            if totals.get(cat, 0) > 0:
                problems.append(f"Virtual event: no {cat}. A virtual talk is catering only.")
    if event_format == "student-led webinar" and totals.get("honorarium", 0) > 0:
        problems.append("Student-led webinar: no honorarium.")
    if totals.get("transport", 0) > 0 and not field_visit:
        problems.append("Student transport is only for field visits; put speaker travel under 'travel'.")
    if field_visit and totals.get("transport", 0) > lim["student_transport_max_usd"]:
        problems.append(f"Student transport ${totals['transport']:,.0f} is over the ${lim['student_transport_max_usd']:,} limit.")
    if totals.get("honorarium", 0) > lim["honorarium_max_usd"]:
        problems.append(f"Honorarium ${totals['honorarium']:,.0f} is over the ${lim['honorarium_max_usd']:,} limit.")
    if totals.get("travel", 0) > lim["travel_max_usd"]:
        problems.append(f"Travel ${totals['travel']:,.0f} is over the ${lim['travel_max_usd']:,} limit.")
    max_lodging = lim["lodging_max_per_night_usd"] * lim["lodging_max_nights"]
    if totals.get("lodging", 0) > max_lodging:
        problems.append(f"Lodging ${totals['lodging']:,.0f} is over the ${max_lodging:,} limit "
                        f"({lim['lodging_max_nights']} night at ${lim['lodging_max_per_night_usd']})."
                        )
    if headcount > 0 and totals.get("catering", 0) / headcount > lim["catering_max_per_person_usd"]:
        problems.append(f"Catering is ${totals['catering'] / headcount:,.2f} per person; the limit is "
                        f"${lim['catering_max_per_person_usd']}.")
    total = sum(totals.values())
    event_max = lim["field_visit_max_total_usd"] if field_visit else lim["event_max_total_usd"]
    if total > event_max:
        problems.append(f"Event total ${total:,.0f} is over the ${event_max:,} per-event limit"
                        f"{' for field visits' if field_visit else ''}.")
    if total > available - lim["keep_reserve_usd"]:
        problems.append(f"Event total ${total:,.0f} would leave less than the ${lim['keep_reserve_usd']} reserve "
                        f"(${available:,.0f} available this semester).")
    return problems


def catering_quote(headcount: int, per_person: float | None = None) -> dict[str, Any]:
    r = rules()
    rate = per_person if per_person is not None else r["catering"]["planning_rate_per_person_usd"]
    return {"headcount": headcount, "per_person": rate, "total": round(headcount * rate, 2),
            "max_per_person": r["limits"]["catering_max_per_person_usd"]}


def log_hours(s: dict[str, Any], week_start: str, person: str, hours: float) -> dict[str, Any]:
    r = rules()["wages"]
    if person not in r["co_leads"]:
        raise ValueError(f"{person} is not a co-lead.")
    if hours <= 0:
        raise ValueError("Hours must be more than 0.")
    already = sum(h["hours"] for h in s["hours"] if h["week_start"] == week_start and h["person"] == person)
    if already + hours > r["max_hours_per_person_per_week"]:
        raise ValueError(f"{person} would have {already + hours:g} hours that week; the limit is "
                         f"{r['max_hours_per_person_per_week']}.")
    entry = {"id": store.new_id("hrs"), "week_start": week_start, "person": person, "hours": hours,
             "source": "logged"}
    s["hours"].append(entry)
    return entry
