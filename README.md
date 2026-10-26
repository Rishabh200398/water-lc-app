# Water LC Ops Copilot 💧

**MGT 409 final project · Rishabh Ravichandran · Yale School of the Environment**

The Water Learning Community (Water LC) at YSE runs Lunch and Learns, career chats and field trips on a **$15,000/year budget, cut from $20,000**. The budget also pays the two co-leads' wages. Last year the leads spent roughly 350 hours on emails, the newsletter, catering and budget spreadsheets, and spending reached ~$13,600 (projected ~$15,500), which would be over this year's budget.

This app is a public Water LC website plus a co-lead **ops copilot**. **Ten AI agents** take an event from idea to newsletter: research → three ideas → speaker shortlist → invitation → meeting notes and date → budget → itemized catering → advisor approval → catering order → marketing → recap → monthly newsletter. The co-leads only click **Approve**. Money rules live in code, outside the AI's reach.

- Model: **gpt-6-luna through Portkey** (the only model the course allows; the app refuses any other)
- Backend: FastAPI + PydanticAI · Frontend: React + Vite + TypeScript (built copy committed in `frontend/dist`)
- Works on phone and desktop · water theme · estimates the **water used by every AI run**

---

## Run it (under 10 minutes)

Needs **Python 3.10+**. Node is *not* needed; the built website is in the repo.

```bash
git clone <this repo> water-lc-app
cd water-lc-app
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env          # add your PORTKEY_API_KEY (or put a .env one folder up)
.venv/bin/uvicorn backend.main:app --port 8040
```

Open **http://localhost:8040**. Co-lead login: **Rishabh** or **Erika**, password **`waterlc`** (or `ADMIN_PASSWORD` from `.env`).

- `.env` is read from the repo folder first, then **one folder up** (where graders keep theirs).
- On a phone on the same Wi-Fi: add `--host 0.0.0.0` and open `http://<your-computer-ip>:8040`.
- Windows: use `.venv\Scripts\pip` and `.venv\Scripts\uvicorn`.
- Start over at any time: **Safety log → Reset demo data** (or delete the `state/` folder).

Frontend development only: `cd frontend && npm install && npm run dev` → http://localhost:5173 (proxies `/api` to :8040).

---

## A 5-minute tour

1. **Today** (dashboard): semester money (wages paid + forecast, events paid/approved/pending, available), AI usage and water, and everything waiting for you. **Brief me** gives the Coordinator's prioritized to-do list.
2. **Events** groups every event by phase: Ideas → Speaker & date → Budget & approval → Promotion & event day → Done.
3. **New event → answer the questions:** format (Lunch and Learn, seminar, student-led webinar, career session, field visit, social), virtual or in person, **collaborate? yes / only if it fits / no**, timing, headcount, notes.
4. **Ideas:** the **Research scout** searches current water news on the web and reads what members asked for, what Water LC did this year and last, and ideas already confirmed with speakers. The **Event strategist** returns **three** ideas. Choose one (tick or untick the suggested co-host), or brainstorm again with feedback.
5. **Speakers:** the **Speaker scout** shortlists YSE alumni (East Coast / NYC first for in-person). Remove people, add someone you know, or search again; then **Invite this person**.
6. **Invitation:** Speaker outreach drafts the email **in your voice** (`data/my_voice.md`) asking for a time to talk. **Approve & open in my mail app**; it's logged in the **Outbox**.
7. **Meeting & date:** paste your meeting notes. The Coordinator pulls out mode, dates (checked against the YSE calendar), travel, honorarium and needs. **Confirm date**: the idea is now **locked** and will never be brainstormed again.
8. **Budget, then catering:** the Budget analyst sets the budget by format and mode (virtual = catering only; in person = + travel; field visit = + student transport). The Catering planner builds an **itemized order** from the caterer's menu (code prices every line). Redo either with feedback, then approve.
9. **Jim → Cristina → promotion → wrap-up:** the request to Jim includes the itemized table (inserted by code). Record Jim's decision (changes → re-costed), approve the order to Cristina, post the Yale Connect / WhatsApp text, and after the event record attendance; the Coordinator writes the recap.
10. **Newsletter → Draft the newsletter:** web research for news (global / US / Connecticut), good-news Spotlight, conferences and jobs, written in the Water LC template. **Load the injection demo article** to watch the safety screen work.

---

## The agents

| # | Agent | What it does | You decide |
|---|---|---|---|
| 1 | Research scout | Web search for current water news + member interests + events this/last year + locked ideas + learning communities | n/a |
| 2 | Event strategist | Three different ideas from your answers and the brief; co-host only when wanted and it truly fits | Pick an idea / brainstorm again |
| 3 | Speaker scout | YSE alumni shortlist, East Coast first for in-person, travel note for each | Edit the list, invite one |
| 4 | Speaker outreach | First email in your voice, asking for a time to talk | Approve the email |
| 5 | Coordinator | Reads meeting notes and Jim's replies, writes recaps and the briefing | Confirm the date |
| 6 | Budget analyst | Budget by format and mode; must pass `check_budget` (hard limits in code) | Approve or redo |
| 7 | Catering planner | Itemized vegetarian/vegan order from a menu, new cuisine, within the catering budget (code prices it) | Approve or redo |
| 8 | Approvals & email | Request to Jim (code inserts the table), then the order to Cristina | Approve each email |
| 9 | Marketing | Yale Connect listing, WhatsApp message, reminder, poster text | Mark as posted |
| 10 | Newsletter editor | Web research + monthly issue in the house template | Approve newsletter |

Code in `backend/`: `agents.py` (agents, tools, output types), `workflow.py` (the steps and gates), `budget.py` (all money math and limits), `safety.py` (injection defenses), `usage.py` (tokens, cost, water), `store.py` (JSON state seeded from `data/`), `main.py` (API + serves the site). Agent instructions are in `backend/prompts/`.

## Safety (four layers)

1. **Screening:** pasted replies, pasted articles and web results are screened line by line; lines that read like instructions to an AI ("ignore previous instructions", "approve $5,000", "email Cristina now") are removed **before any agent sees them** and logged in the Safety log.
2. **Fencing:** the rest goes to the model inside `<untrusted_data>` tags; every agent's instructions say that text is information, never orders.
3. **No power:** agents can't send email, spend, approve or edit the ledger. Hard limits (honorarium ≤ $300, travel ≤ $500, 1 hotel night ≤ $250, catering ≤ $15/person, event ≤ $1,000 or $2,000 for field visits, student transport ≤ $1,200, a $250 reserve, 10 hours/person/week, and **virtual = catering only**) are enforced in `budget.py`; `ModelRetry` forces agents to fix proposals that break them. Catering prices come from the menu file, never from the AI, and speaker names must exist in the alumni list.
4. **Humans approve:** every email, Jim's decision and the newsletter need a co-lead's click; each one is recorded in the Outbox and the audit trail.

## Tokenomics and water

Every agent run records input, **cached input** and output (and reasoning) tokens from the API. Each agent's instructions start with the same ~1,000-token handbook (`prompts/handbook.md`) plus a fixed role prompt, sent with an OpenAI prompt-cache key, so repeat runs read most of their input from cache (verified: 4,013 of 4,054 input tokens cached on a repeat call). The **Usage & water** page shows totals, per-agent breakdowns, estimated cost, and **estimated water**: tokens → energy (Wh) → litres (data-center cooling + electricity generation), shown as a low / typical / high range. All assumptions are in `data/usage_rules.json`; they are estimates, since OpenAI doesn't publish per-request energy or water.

## Data (`data/`)

YSE 2026–27 academic calendar · caterer list · budget rules and limits · 2025–26 past events and wages (past co-leads anonymized) · hours by task from last year's timesheets · Fall Splash member-interest word cloud · newsletter template · this year's events · contacts (blank; fill locally) · **sample** alumni speakers with locations (fictional, marked "(sample)") · **sample** caterer menus with item prices · YSE learning communities (from the YSE website) · the co-leads' email voice guide · demo files for the safety tests.

---
🤖 Built with Claude Code.
