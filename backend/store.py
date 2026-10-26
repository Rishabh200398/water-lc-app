"""The app's memory: one JSON file (state/app_state.json), seeded from data/ on first run.

Everything the app knows about this year lives here: events and where each one is in the
pipeline, the expense ledger, logged co-lead hours, the outbox, newsletters, token usage
and the security log. "Reset demo data" deletes the file so the next read reseeds it.
"""

from __future__ import annotations

import csv
import json
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
STATE_DIR = ROOT / "state"
STATE_FILE = STATE_DIR / "app_state.json"

_lock = threading.RLock()
_state: dict[str, Any] | None = None


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def read_csv(name: str) -> list[dict[str, str]]:
    with open(DATA / name, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def read_json(name: str) -> Any:
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def read_text(name: str) -> str:
    return (DATA / name).read_text(encoding="utf-8")


# ---------------------------------------------------------------- seeding


def _seed() -> dict[str, Any]:
    events = []
    for row in read_csv("events_2026_27.csv"):
        held = row["status"] == "held"
        events.append({
            "id": new_id("evt"),
            "title": row["event"],
            "event_type": row["event_type"],
            "date": row["date"],
            "time": row["time"] or ("12:00-13:00" if "lunch" in row["event_type"] else ""),
            "location": row["location"],
            "hosts": row["hosts"],
            "speaker_role": row["speaker_role"],
            "notes": row["notes"],
            "stage": "done" if held else "intake",
            "intake": None if held else {
                "format": "lunch and learn", "mode": "either", "collab": "open",
                "timing": f"on {row['date']}" if row["date"] else "", "attendance": 25,
                "notes": row["notes"]},
            "expected_attendance": None if held else 25,
            "emails": {},
            "seeded": True,
            "recapped_in": "September/October newsletter" if held else None,
            "created_at": now(),
            "activity": [],
            "working": False,
        })
    # Sample Fall 2026 ledger so the dashboard isn't empty. Clearly marked; edit or delete.
    career_chat = next((e for e in events if e["title"].startswith("Career Chat #1")), None)
    splash = next((e for e in events if e["title"].startswith("Fall Splash")), None)
    expenses = [
        {"id": new_id("exp"), "event_id": splash["id"] if splash else None, "semester": "Fall 2026",
         "category": "catering", "description": "Fall Splash snacks and watercolor supplies (sample)",
         "amount": 95.0, "status": "paid", "source": "sample", "created_at": now()},
        {"id": new_id("exp"), "event_id": career_chat["id"] if career_chat else None, "semester": "Fall 2026",
         "category": "catering", "description": "Career Chat #1 lunch (placeholder)",
         "amount": 200.0, "status": "paid", "source": "sample", "created_at": now()},
    ]
    # Sample hours: 4 hours per co-lead per working week from Sep 1 to Oct 16 (7 weeks).
    hours = []
    for week in ["2026-08-31", "2026-09-07", "2026-09-14", "2026-09-21", "2026-09-28",
                 "2026-10-05", "2026-10-12"]:
        for person in ("Rishabh", "Erika"):
            hours.append({"id": new_id("hrs"), "week_start": week, "person": person,
                          "hours": 4.0, "source": "sample"})
    return {
        "version": 1,
        "created_at": now(),
        "events": events,
        "expenses": expenses,
        "hours": hours,
        "outbox": [],
        "newsletters": [],
        "usage": [],
        "security_log": [],
        "audit": [{"ts": now(), "actor": "system", "action": "seeded",
                   "detail": "Seeded from data/ (sample ledger entries are marked 'sample')."}],
    }


def _load() -> dict[str, Any]:
    global _state
    if _state is None:
        if STATE_FILE.exists():
            _state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        else:
            _state = _seed()
            _save()
    return _state


def _save() -> None:
    STATE_DIR.mkdir(exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(_state, indent=2), encoding="utf-8")
    tmp.replace(STATE_FILE)


class Txn:
    """`with store.txn() as s:` gives the state under a lock and saves it afterwards."""

    def __enter__(self) -> dict[str, Any]:
        _lock.acquire()
        return _load()

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            if exc_type is None:
                _save()
        finally:
            _lock.release()


def txn() -> Txn:
    return Txn()


def snapshot() -> dict[str, Any]:
    """A deep copy for reading without holding the lock."""
    with _lock:
        return json.loads(json.dumps(_load()))


def reset() -> None:
    global _state
    with _lock:
        if STATE_FILE.exists():
            STATE_FILE.unlink()
        _state = None
        _load()


def audit(s: dict[str, Any], actor: str, action: str, detail: str = "") -> None:
    s["audit"].append({"ts": now(), "actor": actor, "action": action, "detail": detail})


def find(items: list[dict], item_id: str) -> dict | None:
    return next((x for x in items if x["id"] == item_id), None)
