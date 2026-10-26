# Project: Water LC Ops Copilot (MGT 409 Final Project)

## Context
- Course: MGT 409 "AI Foundations for Managers" (Yale SOM, Fall 2026). Requirements: https://zlisto.github.io/mgt_409_fa26/project_requirements.html
- **Due: Monday, Oct 26, 2026, 6:00 PM** (Canvas). Solo project.
- Deliverables: GitHub repo (README + `.env.example`), `report.html` (10–15 pages, self-contained), `slides.html` (reveal.js, ≤10 slides, self-contained), optional 2–3 min demo video.
- Model: course key `PORTKEY_API_KEY` with **gpt-6-luna** only, or own `OPENAI_API_KEY`.
- App must load `.env` from the repo folder first, then the parent folder (graders put `.env` one level above the repo).
- 10-minute rule: graders must have it running from a fresh clone within 10 minutes, or it must be online.

## The user (me)
I co-lead Water LC (Water Learning Community) at Yale. With my co-lead, I organize guest speaker events. Pain points:
- Tracking the budget
- Ordering catering
- Emailing our advisor for budget approval
- Event logistics
- Understanding what members need and whether we are on track
- Sending a monthly newsletter

## Idea (the novelty angle)
One ops copilot that follows an event from idea → budget check → catering → advisor approval → newsletter, with hard budget limits.
Not just an "event planner" or "email drafter" (those risk the overdone-idea cap). Scale story: hundreds of Yale student orgs and learning communities face the same workflow.

## Candidate agents
1. **Event planner:** event request → logistics checklist (room, AV, timeline, speaker communication)
2. **Budget keeper:** reads the budget sheet (CSV) and flags overspending; a hard cap the LLM cannot override
3. **Catering estimator:** RSVPs + dietary needs + menu/price list → quantities and cost
4. **Approval drafter:** itemized advisor email; a human approves before anything is sent
5. **Community pulse:** member surveys + attendance → on track vs. semester goals, what members want next
6. **Newsletter writer:** month's events and recaps → newsletter draft

**MVP for the deadline:** agents 1–4 as one pipeline. Newsletter only if time allows.

## Grading-driven requirements (evidence earns full credit)
- **Tokenomics:** the app should log and display its own token usage per run (input, cached input, output). Cache the system prompts.
- **Safety:** demo at least one defense working. Ideas: prompt injection hidden in pasted member feedback, a budget cap enforced in code, human-in-the-loop before emails.
- **Impact:** time planning a past event by hand vs. with the app. Get a quote from my co-lead.
- Screenshot good runs, bad runs, and defenses as I go.

## Open questions to brainstorm
- What real data do I have (last semester's budget sheet, past event details, catering menu)?
- Web app framework (keep the local setup simple)
- Exact agent orchestration and diagram

## Setup (mirror HW4/HW5: `~/AI-Assignement 5` is the reference)
- Stack: **FastAPI backend** (`backend/`) + **React + Vite + TypeScript frontend** (`frontend/`), agents built with **PydanticAI** (`pydantic-ai-slim[openai]`), `python-dotenv`, Python venv in `.venv/`.
- Model: **gpt-6-luna through Portkey** (`https://api.portkey.ai/v1`), via `OpenAIResponsesModel` (Responses API). gpt-6-luna refuses tool calls on `/v1/chat/completions` while reasoning is on. Copy the pattern from HW5 `backend/model_config.py`, which refuses to start if `PORTKEY_MODEL` is anything else.
- Env vars: `PORTKEY_API_KEY`, `PORTKEY_BASE_URL`, `PORTKEY_MODEL` (see `.env.example`). `.env` is copied from HW5 and gitignored. Load the repo `.env` first, then the parent folder's `.env`.
- Keep HW5 conventions: prompts in `backend/prompts/*.md`, append-only audit trail in `output/`, a human approves every outgoing action, and `AI_prompts.md` logs the prompts used to build the project.

## Decisions so far (Oct 24)
- Budget: $15,000/yr ($7,500/semester), cut from $20,000 in 2025-26. Co-lead wages ($21/hr, max 10 hrs/person/week, ~14 working weeks/semester) come out of the same budget. Catering is planned at $10/person (~$200 for ~20 people), vegetarian/vegan only, different cuisine each event.
- Process: brainstorm event/theme (water sector, 1 hour) → find a Yale/YSE/SOM alum speaker (virtual preferred) → meet the speaker → budget → date (YSE calendar + room) → poster/marketing ~2 weeks before (Yale Connect, WhatsApp) → catering order → Jim Saiers (advisor) approves → Cristina places the order → photos → **monthly** newsletter (past events, jobs/internships, conferences, water news global/US/CT, Water Spotlight of good news). Co-hosting with other YSE learning communities is common.
- Website: a public site plus an admin login that opens the agents. A planned "Water alumni" page lists past co-leads (names added later, only when the user says so).
- Data in `data/`: YSE 2026-27 calendar, caterers, budget rules, 2025-26 past events and wages, and hours by task. **Past co-lead names are anonymized ("Past co-lead A/B"). Do not add names, Yale account codes or vendor contact emails to the repo.**
- Feature idea: estimated water use per prompt run (tokens → energy → water, shown as a low/typical/high range with editable assumptions).

## Build status (Oct 24, evening)
- App built and tested end to end with real gpt-6-luna calls: 8 agents (`backend/agents.py`), pipeline with gates (`backend/workflow.py`), hard limits in code (`backend/budget.py`), 4-layer injection defense (`backend/safety.py`), token/cost/water meter (`backend/usage.py`), public site + admin (`frontend/`, built copy in `frontend/dist`, served by FastAPI).
- Run: `.venv/bin/uvicorn backend.main:app --port 8040` (port 8000 is taken on this Mac by another project). Login Rishabh/Erika, password `waterlc`.
- Verified: an injected line in a speaker reply and in a pasted article was removed before any agent saw it; a $1,500 honorarium request was capped at $300 with a "decision needed" note; Jim "changes" re-costs the event; web search works for the newsletter; prompt caching works; a fresh clone runs with `.env` one folder up.
- Still to do: report.html, slides.html, screenshots, Erika's quote and time saved (impact), GitHub repo, optional demo video.

## Redesigned event flow (Oct 25)
Questions (format / virtual-in person / collab yes-open-no / timing / headcount / notes) → Research scout (web news + interests + done + locked) → strategist gives 3 ideas → Speaker scout (YSE alumni, East Coast first) → invite in the co-leads' voice (`data/my_voice.md`) → meeting notes → confirm date = idea LOCKED → budget (format/mode rules in code) → itemized catering from `data/caterer_menus.csv` (sample prices) → Jim → Cristina → marketing → wrap-up. 10 agents. Learning communities in `data/learning_communities.csv`.

## Submission status (Oct 25, night)
- Public repo: https://github.com/Rishabh200398/water-lc-app. report.html (14 printed pages) and slides.html (10 slides, reveal.js CDN) built by scripts/build_report.py from real logs; repo URL + clone command in both.
- Per the professor (Oct 25): submit ONLY report.html, slides.html and an optional video on Canvas. Nothing else.
- Strategist and catering planner run at low reasoning effort (cost experiment: no measurable quality loss).
