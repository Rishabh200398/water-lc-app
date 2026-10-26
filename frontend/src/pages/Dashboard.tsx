import { useState } from 'react'
import { api, fmtDate, money } from '../api'
import { DateBadge, MiniRiver, Working, usePoll, useToast } from '../ui'
import { AdminShell } from './AdminShell'

export type BudgetStatus = {
  semester: string; budget: number; hourly_rate: number; wages_logged: number; hours_logged: number; wages_forecast: number
  forecast_hours: number; weeks_left: number; events_paid: number; events_approved: number; events_pending: number
  available_for_events: number; available_after_pending: number; reserve: number; warnings: string[]
  forecast_hours_per_person_per_week: number; annual_budget: number; last_year?: { annual_budget_usd: number; spent_usd: number; projected_usd: number }
}

export function BudgetMeter({ b }: { b: BudgetStatus }) {
  const parts = [
    { v: b.wages_logged, c: '#0b3954', l: 'Wages paid' },
    { v: b.wages_forecast, c: '#5b8fa8', l: 'Wages forecast' },
    { v: b.events_paid, c: '#087e8b', l: 'Events paid' },
    { v: b.events_approved, c: '#0fa3b1', l: 'Approved' },
    { v: b.events_pending, c: '#e9a23b', l: 'Waiting on Jim' },
    { v: Math.max(b.available_after_pending, 0), c: '#bfe9ef', l: 'Available' },
  ]
  return (
    <div>
      <div className="meter" role="img" aria-label={`${money(b.available_after_pending)} of ${money(b.budget)} available`}>
        {parts.map(p => <div key={p.l} style={{ width: `${(p.v / b.budget) * 100}%`, background: p.c }} title={`${p.l}: ${money(p.v)}`} />)}
      </div>
      <div className="legend">{parts.map(p => <span key={p.l}><i style={{ background: p.c }} />{p.l} {money(p.v)}</span>)}</div>
    </div>
  )
}

type Dash = {
  me: string; budget: BudgetStatus; active_events: any[]; needs_you: any[]; newsletters_in_review: any[]
  usage: { runs: number; input_tokens: number; cached_input_tokens: number; output_tokens: number; cost_usd: number; cache_hit_rate: number; water_ml: { low: number; typical: number; high: number } }
  outbox_count: number; security_count: number; stages: [string, string][]
}

const ACTION: Record<string, string> = {
  intake: 'Answer a few questions', ideas: 'Pick one of 3 ideas', speakers: 'Pick a speaker', invite_review: 'Send the speaker invitation',
  meeting: 'Add meeting notes & confirm the date', budget_review: 'Review budget & catering', jim_review: 'Send the request to Jim',
  awaiting_jim: 'Record Jim’s decision', order_review: 'Send the catering order', marketing_review: 'Post the promotion',
  scheduled: 'Wrap up after the event',
}

export function Dashboard() {
  const { data: d } = usePoll<Dash>(() => api('/admin/dashboard'), [], x => (x?.active_events.some(e => e.working) ? 3000 : null))
  const [brief, setBrief] = useState<any>(null)
  const [briefing, setBriefing] = useState(false)
  const toast = useToast()
  const hour = new Date().getHours()
  const hello = hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening'

  const getBrief = async () => {
    setBriefing(true)
    try { setBrief(await api('/admin/briefing', 'POST')) } catch (e: any) { toast(e.message, true) } finally { setBriefing(false) }
  }

  return (
    <AdminShell title={d ? `${hello}, ${d.me} 🌊` : 'Loading…'} subtitle="Here’s what needs you and how the semester’s money is flowing."
      actions={<a className="btn small" href="#/admin/events/new">＋ New event</a>}>
      {!d ? <div className="card empty">Loading…</div> : <>
        <section className="grid side">
          <div className="card">
            <div className="row between"><h3>💰 {d.budget.semester} budget</h3><a href="#/admin/budget" className="btn ghost small">Details →</a></div>
            <div className="stats" style={{ margin: '.5rem 0 1rem' }}>
              <div className="stat"><span className="v">{money(d.budget.available_after_pending)}</span><span className="l">Available for events</span></div>
              <div className="stat"><span className="v">{money(d.budget.wages_logged + d.budget.wages_forecast)}</span><span className="l">Wages (paid + forecast)</span></div>
              <div className="stat"><span className="v">{money(d.budget.events_paid + d.budget.events_approved)}</span><span className="l">Events committed</span></div>
              <div className="stat"><span className="v">{d.budget.weeks_left}</span><span className="l">Working weeks left</span></div>
            </div>
            <BudgetMeter b={d.budget} />
            {d.budget.warnings.map(w => <p key={w} className="pill warn" style={{ marginTop: '.6rem' }}>⚠️ {w}</p>)}
          </div>
          <div className="card foam">
            <div className="row between"><h3>💧 AI usage</h3><a href="#/admin/usage" className="btn ghost small">Details →</a></div>
            <div className="stats" style={{ gridTemplateColumns: '1fr 1fr' }}>
              <div className="stat"><span className="v">{d.usage.runs}</span><span className="l">Agent runs</span></div>
              <div className="stat"><span className="v">{((d.usage.input_tokens + d.usage.output_tokens) / 1000).toFixed(0)}k</span><span className="l">Tokens</span></div>
              <div className="stat"><span className="v">{Math.round(d.usage.cache_hit_rate * 100)}%</span><span className="l">Input from cache</span></div>
              <div className="stat"><span className="v">~{d.usage.water_ml.typical.toFixed(0)} mL</span><span className="l">Water (est.)</span></div>
            </div>
            <small>Water range {d.usage.water_ml.low.toFixed(0)}–{d.usage.water_ml.high.toFixed(0)} mL · cost ~{money(d.usage.cost_usd, true)}</small>
          </div>
        </section>

        <section className="card">
          <div className="row between">
            <h3>🧭 Coordinator briefing</h3>
            <button className="btn small" onClick={getBrief} disabled={briefing}>{brief ? 'Refresh' : 'Brief me'}</button>
          </div>
          {briefing ? <Working text="The Coordinator is reading every event, the budget and the outbox…" /> : brief ? (
            <div>
              <p><strong>{brief.headline}</strong></p>
              <ol>{brief.todos.map((t: string) => <li key={t}>{t}</li>)}</ol>
              {brief.risks.length > 0 && <p className="muted">Risks: {brief.risks.join(' · ')}</p>}
            </div>
          ) : <p className="muted">Ask the Coordinator for a prioritized to-do list across every event, the budget and the newsletter.</p>}
        </section>

        <section className="stack">
          <h2>Needs you ({d.needs_you.length + d.newsletters_in_review.length})</h2>
          {d.needs_you.length + d.newsletters_in_review.length === 0 && <div className="card empty">All caught up. Nothing is waiting for your approval. 🐟</div>}
          <div className="grid two">
            {d.needs_you.map(e => (
              <a key={e.id} href={`#/admin/events/${e.id}`} className="card-link">
                <div className="card">
                  <div className="row" style={{ flexWrap: 'nowrap', alignItems: 'flex-start' }}>
                    <DateBadge date={e.date} />
                    <div style={{ minWidth: 0, flex: 1 }}>
                      <span className="pill warn">{ACTION[e.stage] || e.stage_label}</span>
                      <h3 style={{ marginTop: '.35rem' }}>{e.title}</h3>
                      <MiniRiver index={e.stage_index} total={d.stages.length} />
                    </div>
                  </div>
                </div>
              </a>
            ))}
            {d.newsletters_in_review.map(n => (
              <a key={n.id} href={`#/admin/newsletter/${n.id}`} className="card-link">
                <div className="card"><span className="pill warn">Review the newsletter</span><h3 style={{ marginTop: '.35rem' }}>📰 {n.month} newsletter</h3></div>
              </a>
            ))}
          </div>
        </section>

        <section className="stack">
          <div className="row between"><h2>In the pipeline</h2><a className="btn ghost small" href="#/admin/events">All events →</a></div>
          <div className="grid two">
            {d.active_events.map(e => (
              <a key={e.id} href={`#/admin/events/${e.id}`} className="card-link">
                <div className="card">
                  <div className="row between"><strong>{e.title}</strong>{e.working ? <span className="pill">working…</span> : <span className="pill">{e.stage_label}</span>}</div>
                  <small>{fmtDate(e.date)}</small>
                  <MiniRiver index={e.stage_index} total={d.stages.length} />
                </div>
              </a>
            ))}
          </div>
        </section>
      </>}
    </AdminShell>
  )
}
