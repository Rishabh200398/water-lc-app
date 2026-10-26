import { useEffect, useState } from 'react'
import { api, fmtDate, fmtTime, mailto, money } from '../api'
import { CopyBlock, DateBadge, MiniRiver, Working, go, usePoll, useToast } from '../ui'
import { AdminShell } from './AdminShell'

type Stage = [string, string]

// ================================================================ shared bits

const PHASES: { key: string; label: string; icon: string; stages: string[] }[] = [
  { key: 'ideas', label: 'Ideas', icon: '💡', stages: ['intake', 'ideas'] },
  { key: 'speaker', label: 'Speaker & date', icon: '🎤', stages: ['speakers', 'invite_review', 'meeting'] },
  { key: 'money', label: 'Budget & approval', icon: '💰', stages: ['budget_review', 'jim_review', 'awaiting_jim', 'order_review'] },
  { key: 'promo', label: 'Promotion & event day', icon: '📣', stages: ['marketing_review', 'scheduled'] },
]

const NEXT: Record<string, string> = {
  intake: 'Answer a few questions', ideas: 'Pick one of 3 ideas', speakers: 'Pick a speaker', invite_review: 'Send the invitation',
  meeting: 'Add meeting notes & confirm date', budget_review: 'Review budget & catering', jim_review: 'Send the request to Jim',
  awaiting_jim: 'Record Jim’s decision', order_review: 'Send the catering order', marketing_review: 'Post the promotion',
  scheduled: 'Wrap up after the event', done: 'Done',
}

const FORMAT_OPTIONS: [string, string, string][] = [
  ['lunch and learn', '🥪', 'Lunch and Learn'], ['seminar', '🎓', 'Seminar'], ['student-led webinar', '💻', 'Student-led webinar'],
  ['career session', '🧭', 'Career session'], ['field visit', '🚐', 'Field visit'], ['social', '🎉', 'Social / community'],
  ['', '✨', 'Not sure: suggest'],
]

const modeLabel = (m?: string) => (m === 'in_person' ? 'In person' : m === 'virtual' ? 'Virtual' : m === 'either' ? 'Either' : '')

function Radio<T extends string>({ name, value, options, onChange }: { name: string; value: T; options: [T, string, string?][]; onChange: (v: T) => void }) {
  return (
    <div className="radio-cards" role="radiogroup" aria-label={name}>
      {options.map(([v, label, icon]) => (
        <label key={v || 'none'} className={`radio-card ${value === v ? 'on' : ''}`}>
          <input type="radio" name={name} checked={value === v} onChange={() => onChange(v)} />
          {icon && <span className="ri">{icon}</span>}<span>{label}</span>
        </label>
      ))}
    </div>
  )
}

function Chips({ items, onPick }: { items: string[]; onPick: (s: string) => void }) {
  return <div className="chips" style={{ margin: '.5rem 0' }}>{items.map(n => <button key={n} type="button" className="chip" onClick={() => onPick(n)}>{n}</button>)}</div>
}

function Section({ step, title, sub, children, tone = '' }: { step?: string; title: string; sub?: string; children: React.ReactNode; tone?: string }) {
  return (
    <section className={`card ${tone}`}>
      <div className="step-head">{step && <span className="step-no">{step}</span>}<div><h3 style={{ margin: 0 }}>{title}</h3>{sub && <small>{sub}</small>}</div></div>
      <div style={{ marginTop: '.8rem' }}>{children}</div>
    </section>
  )
}

// ================================================================ events list (grouped by phase)

function EventCard({ e, stages }: { e: any; stages: Stage[] }) {
  return (
    <a href={`#/admin/events/${e.id}`} className="card-link">
      <div className="card event-card">
        <div className="row" style={{ flexWrap: 'nowrap', alignItems: 'flex-start' }}>
          <DateBadge date={e.locked || e.stage === 'done' ? e.date : null} />
          <div style={{ flex: 1, minWidth: 0 }}>
            <strong className="clamp2">{e.title}</strong>
            <div className="row" style={{ gap: '.3rem', margin: '.35rem 0' }}>
              {e.event_type && <span className="pill">{e.event_type}</span>}
              {e.mode && <span className="pill">{modeLabel(e.mode)}</span>}
              {e.hosts && e.hosts !== 'Water LC' && <span className="pill dark">🤝 {e.hosts.replace(' x Water LC', '')}</span>}
              {e.locked && <span className="pill ok">🔒 confirmed</span>}
            </div>
            <div className="meta">
              {e.speaker?.name && <span>🎤 {e.speaker.name}</span>}
              {e.budget?.total != null && <span>💰 {money(e.budget.total)}</span>}
              {!e.locked && e.date && <span>📅 planned {fmtDate(e.date)}</span>}
            </div>
            <MiniRiver index={e.stage_index} total={stages.length} />
            {e.working ? <span className="pill">⏳ agents working…</span> :
              e.error ? <span className="pill alert">Needs a retry</span> :
                <span className={`pill ${e.needs_you ? 'warn' : ''}`}>Next: {NEXT[e.stage]}</span>}
          </div>
        </div>
      </div>
    </a>
  )
}

export function EventsList() {
  const { data } = usePoll<{ events: any[]; stages: Stage[] }>(() => api('/admin/events'), [],
    d => (d?.events.some(e => e.working) ? 3000 : null))
  const [showDone, setShowDone] = useState(false)
  const events = data?.events || []
  const done = events.filter(e => e.stage === 'done').reverse()
  return (
    <AdminShell title="Events" subtitle="From idea to recap. The agents do the work; you decide at every step."
      actions={<a className="btn small" href="#/admin/events/new">＋ New event</a>}>
      {data && (
        <div className="stats phase-stats">
          {PHASES.map(p => (
            <a key={p.key} href={`#phase-${p.key}`} onClick={ev => { ev.preventDefault(); document.getElementById(`phase-${p.key}`)?.scrollIntoView({ behavior: 'smooth' }) }} className="stat card" style={{ padding: '.8rem 1rem' }}>
              <span className="v">{events.filter(e => p.stages.includes(e.stage)).length}</span>
              <span className="l">{p.icon} {p.label}</span>
            </a>
          ))}
        </div>
      )}
      {PHASES.map(p => {
        const list = events.filter(e => p.stages.includes(e.stage))
        return (
          <section key={p.key} id={`phase-${p.key}`} className="stack">
            <h2 className="phase-title">{p.icon} {p.label} <span className="muted">({list.length})</span></h2>
            {list.length ? <div className="grid two">{list.map(e => <EventCard key={e.id} e={e} stages={data!.stages} />)}</div>
              : <div className="card empty" style={{ padding: '1rem' }}>Nothing here right now.</div>}
          </section>
        )
      })}
      <section className="stack">
        <div className="row between">
          <h2 className="phase-title">✅ Done <span className="muted">({done.length})</span></h2>
          <button className="btn ghost small" onClick={() => setShowDone(!showDone)}>{showDone ? 'Hide' : 'Show'}</button>
        </div>
        {showDone && (
          <div className="card table-wrap">
            <table>
              <thead><tr><th>Date</th><th>Event</th><th>Hosts</th><th className="num">Attended</th></tr></thead>
              <tbody>{done.map(e => (
                <tr key={e.id} style={{ cursor: 'pointer' }} onClick={() => go(`/admin/events/${e.id}`)}>
                  <td>{fmtDate(e.date)}</td><td>{e.title}</td><td><small>{e.hosts}</small></td><td className="num">{e.attendance ?? '—'}</td>
                </tr>))}</tbody>
            </table>
          </div>
        )}
      </section>
    </AdminShell>
  )
}

// ================================================================ step 1: the questions

type IntakeT = { format: string; mode: string; collab: string; timing: string; attendance: string; notes: string }

function IntakeForm({ initial, busy, submitLabel, onSubmit }: { initial?: any; busy: boolean; submitLabel: string; onSubmit: (i: any) => void }) {
  const [f, setF] = useState<IntakeT>({
    format: initial?.format ?? 'lunch and learn', mode: initial?.mode ?? 'either', collab: initial?.collab ?? 'open',
    timing: initial?.timing ?? '', attendance: String(initial?.attendance ?? 25), notes: initial?.notes ?? '',
  })
  const set = (k: keyof IntakeT) => (v: string) => setF({ ...f, [k]: v })
  return (
    <form className="stack" onSubmit={ev => { ev.preventDefault(); onSubmit({ ...f, attendance: f.attendance ? Number(f.attendance) : null }) }}>
      <div>
        <label>1. What kind of event?</label>
        <Radio name="format" value={f.format} onChange={set('format')} options={FORMAT_OPTIONS.map(([v, i, l]) => [v, l, i])} />
        <small>{f.format === 'field visit' ? 'Budget will include student transport and any entry fees.' :
          f.format === 'student-led webinar' ? 'Students present, so no honorarium.' :
            'Virtual speakers cost only catering; in-person adds travel (East Coast preferred).'}</small>
      </div>
      <div>
        <label>2. Speaker: virtual or in person?</label>
        <Radio name="mode" value={f.mode} onChange={set('mode')} options={[['virtual', 'Virtual (cheapest)', '💻'], ['in_person', 'In person (East Coast / NYC preferred)', '🚆'], ['either', 'Either', '🤷']]} />
      </div>
      <div>
        <label>3. Collaborate with another learning community or group?</label>
        <Radio name="collab" value={f.collab} onChange={set('collab')} options={[['yes', 'Yes, find a co-host', '🤝'], ['open', 'Only if it truly fits', '🔍'], ['no', 'No, Water LC only', '💧']]} />
      </div>
      <div className="fields two">
        <div><label htmlFor="timing">4. When?</label><input id="timing" value={f.timing} onChange={e => set('timing')(e.target.value)} placeholder="e.g. early November, or on 2026-11-06" /></div>
        <div><label htmlFor="att">5. About how many people?</label><input id="att" type="number" min={5} max={200} value={f.attendance} onChange={e => set('attendance')(e.target.value)} /></div>
      </div>
      <div>
        <label htmlFor="notes">6. Anything else? (topics, constraints, a speaker in mind)</label>
        <textarea id="notes" style={{ minHeight: 80 }} value={f.notes} onChange={e => set('notes')(e.target.value)} placeholder="e.g. members keep asking about PFAS; keep it under $300" />
      </div>
      <button className="btn" disabled={busy}>{submitLabel}</button>
      <small>The Research scout checks current water news, what members asked for, what we’ve already done and ideas already confirmed, then the Event strategist brainstorms three ideas.</small>
    </form>
  )
}

export function NewEvent() {
  const [busy, setBusy] = useState(false)
  const toast = useToast()
  return (
    <AdminShell title="New event" subtitle="A few quick questions, then the agents research and brainstorm three ideas.">
      <Section step="1" title="Tell the strategist what you have in mind">
        <IntakeForm busy={busy} submitLabel="🔍 Research & brainstorm 3 ideas" onSubmit={async intake => {
          setBusy(true)
          try { const ev = await api('/admin/events', 'POST', intake); go(`/admin/events/${ev.id}`) }
          catch (err: any) { toast(err.message, true) } finally { setBusy(false) }
        }} />
      </Section>
    </AdminShell>
  )
}

// ================================================================ step 2: ideas

function ResearchBrief({ r }: { r: any }) {
  return (
    <details className="card foam">
      <summary>🔎 What the Research scout found ({r.news_hooks?.length || 0} news hooks · {fmtTime(r.generated_at)})</summary>
      <div className="grid two" style={{ marginTop: '.8rem' }}>
        <div>
          <h4>Current news</h4>
          <ul>{r.news_hooks?.map((h: any) => <li key={h.url}><a href={h.url} target="_blank" rel="noreferrer noopener">{h.headline}</a> <small>({h.source})</small><br /><small>{h.why_it_matters}</small></li>)}</ul>
        </div>
        <div>
          <h4>Members want</h4><div className="chips">{r.top_student_interests?.map((t: string) => <span key={t} className="chip">{t}</span>)}</div>
          <h4 style={{ marginTop: '.8rem' }}>Gaps</h4><ul>{r.gaps?.map((g: string) => <li key={g}>{g}</li>)}</ul>
          {r.do_not_repeat?.length > 0 && <><h4>🔒 Already confirmed (won’t repeat)</h4><ul>{r.do_not_repeat.map((g: string) => <li key={g}>{g}</li>)}</ul></>}
          {r.collab_candidates?.length > 0 && <><h4>Possible co-hosts</h4><p><small>{r.collab_candidates.join(' · ')}</small></p></>}
        </div>
      </div>
    </details>
  )
}

function IdeaCard({ idea, onChoose, busy }: { idea: any; onChoose: (keepCollab: boolean) => void; busy: boolean }) {
  const [collab, setCollab] = useState(!!idea.collab)
  return (
    <div className="card idea-card">
      <span className="pill">{idea.format}</span>
      <h3 style={{ marginTop: '.5rem' }}>{idea.title}</h3>
      <p>{idea.description}</p>
      <p><small><strong>Why now:</strong> {idea.why_now}</small></p>
      <ul className="tight">{idea.learning_goals.map((g: string) => <li key={g}><small>{g}</small></li>)}</ul>
      <p><small>👥 ~{idea.expected_attendance} people · 💰 {idea.cost_drivers}</small></p>
      <p><small>🎤 {idea.speaker_profile}</small></p>
      {idea.collab && (
        <label className="checkbox" style={{ marginBottom: '.6rem' }}>
          <input type="checkbox" checked={collab} onChange={e => setCollab(e.target.checked)} />
          <span><small>Co-host with <strong>{idea.collab.group}</strong>: {idea.collab.why}</small></span>
        </label>
      )}
      <div className="spacer" />
      <button className="btn success block" disabled={busy} onClick={() => onChoose(collab)}>✓ Choose this idea</button>
    </div>
  )
}

function IdeasStep({ e, busy, act }: { e: any; busy: boolean; act: any }) {
  const [feedback, setFeedback] = useState('')
  const [fresh, setFresh] = useState(false)
  const [editing, setEditing] = useState(false)
  const history: any[] = e.idea_history || []
  return (
    <>
      {e.research && <ResearchBrief r={e.research} />}
      <Section step="2" title="Pick an idea" sub="Three different ideas from the strategist. Choose one, or ask for new ones below.">
        <div className="ideas-grid">{(e.ideas || []).map((idea: any, i: number) => (
          <IdeaCard key={idea.title} idea={idea} busy={busy} onChoose={keep => act('/choose-idea', { index: i, keep_collab: keep })} />
        ))}</div>
      </Section>
      <Section title="🔄 Not quite right? Brainstorm again" sub="The strategist won’t repeat any idea you’ve already seen or confirmed.">
        <textarea style={{ minHeight: 70 }} value={feedback} onChange={ev => setFeedback(ev.target.value)} placeholder="e.g. more hands-on, or focused on careers in utilities" />
        <Chips items={['More career-focused', 'Hands-on or outdoors', 'Lower cost', 'A panel instead of one speaker', 'Something on Long Island Sound', 'Tie it to current news']}
          onPick={n => setFeedback(f => (f ? `${f}; ${n.toLowerCase()}` : n))} />
        <div className="row">
          <button className="btn secondary" disabled={busy} onClick={() => act('/ideas', { feedback, fresh_research: fresh })}>🔄 Brainstorm 3 new ideas</button>
          <label className="checkbox"><input type="checkbox" checked={fresh} onChange={ev => setFresh(ev.target.checked)} /> <small>Also refresh the news research</small></label>
          <button className="btn ghost small" onClick={() => setEditing(!editing)}>✏️ Change my answers</button>
        </div>
        {editing && <div style={{ marginTop: '1rem' }}><IntakeForm initial={e.intake} busy={busy} submitLabel="Save answers & brainstorm again" onSubmit={intake => act('/ideas', { intake, fresh_research: true })} /></div>}
        {history.length > 0 && (
          <details style={{ marginTop: '1rem' }}><summary>Earlier ideas ({history.length})</summary>
            {history.map((p, i) => (
              <div key={i} className="row between list-row">
                <div style={{ minWidth: 0 }}><strong>{p.title}</strong><br /><small>{p.format} · {p.theme}</small></div>
                <button className="btn ghost small nowrap" disabled={busy} onClick={() => act('/choose-idea', { index: i, keep_collab: true, from_history: true })}>Use this one</button>
              </div>
            ))}
          </details>
        )}
      </Section>
    </>
  )
}

// ================================================================ step 3: speakers

function SpeakerCard({ o, i, busy, act }: { o: any; i: number; busy: boolean; act: any }) {
  return (
    <div className={`card speaker-card ${o.declined ? 'faded' : ''}`}>
      <div className="row between" style={{ flexWrap: 'nowrap', alignItems: 'flex-start' }}>
        <div style={{ minWidth: 0 }}>
          <strong>{o.name}</strong>
          <div><small>{[o.role, o.organization].filter(Boolean).join(', ')}{o.degree ? ` · YSE ${o.degree}` : ''}</small></div>
        </div>
        <span className={`pill ${o.source === 'you' ? 'dark' : ''}`}>{o.source === 'you' ? 'Added by you' : 'AI pick'}</span>
      </div>
      <div className="meta" style={{ margin: '.5rem 0' }}>
        {o.location && <span>📍 {o.location}</span>}
        <span>{o.suggested_mode === 'in_person' ? '🚆 In person' : '💻 Virtual'}</span>
      </div>
      {o.travel_note && <p><small>🧭 {o.travel_note}</small></p>}
      <p><small>{o.why}</small></p>
      {o.declined ? <span className="pill alert">Declined / didn’t work out</span> : (
        <div className="row">
          <button className="btn success small" disabled={busy} onClick={() => act('/speakers/confirm', { index: i })}>✓ Invite this person</button>
          <button className="btn ghost small" disabled={busy} onClick={() => act('/speakers/remove', { index: i }, undefined, false)}>Remove</button>
        </div>
      )}
    </div>
  )
}

function SpeakersStep({ e, busy, act }: { e: any; busy: boolean; act: any }) {
  const [feedback, setFeedback] = useState('')
  const [p, setP] = useState({ name: '', organization: '', role: '', degree: '', location: '', email: '', mode: 'virtual' })
  const opts: any[] = e.speaker_options || []
  return (
    <>
      <Section step="3" title="Pick a speaker" sub="YSE alumni who fit the idea. In-person picks are East Coast / NYC first to keep travel cheap. Remove, add or re-run, then invite one.">
        {!opts.length && <p className="muted">No one on the list yet.</p>}
        <div className="grid two">{opts.map((o, i) => <SpeakerCard key={o.name + i} o={o} i={i} busy={busy} act={act} />)}</div>
      </Section>
      <div className="grid two">
        <Section title="🔄 Find other speakers">
          <textarea style={{ minHeight: 70 }} value={feedback} onChange={ev => setFeedback(ev.target.value)} placeholder="e.g. someone from a utility, or based in New York" />
          <Chips items={['Based near NYC', 'From a utility', 'From consulting', 'From a nonprofit', 'Recent graduate']} onPick={n => setFeedback(f => (f ? `${f}; ${n.toLowerCase()}` : n))} />
          <button className="btn secondary" disabled={busy} onClick={() => act('/speakers/rerun', { feedback })}>🔄 Search again</button>
        </Section>
        <Section title="➕ Add someone you know">
          <div className="fields two">
            <div><label>Name</label><input value={p.name} onChange={ev => setP({ ...p, name: ev.target.value })} /></div>
            <div><label>Organization</label><input value={p.organization} onChange={ev => setP({ ...p, organization: ev.target.value })} /></div>
            <div><label>Role</label><input value={p.role} onChange={ev => setP({ ...p, role: ev.target.value })} /></div>
            <div><label>YSE degree</label><input value={p.degree} onChange={ev => setP({ ...p, degree: ev.target.value })} placeholder="MEM 2019" /></div>
            <div><label>Location</label><input value={p.location} onChange={ev => setP({ ...p, location: ev.target.value })} placeholder="New York NY" /></div>
            <div><label>Email</label><input value={p.email} onChange={ev => setP({ ...p, email: ev.target.value })} /></div>
          </div>
          <button className="btn secondary small" style={{ marginTop: '.6rem' }} disabled={busy || !p.name.trim()}
            onClick={() => { act('/speakers/add', p, undefined, false); setP({ name: '', organization: '', role: '', degree: '', location: '', email: '', mode: 'virtual' }) }}>Add to list</button>
        </Section>
      </div>
    </>
  )
}

// ================================================================ step 4–5: invitation, meeting & date

function EmailEditor({ email, onApprove, busy }: { email: any; onApprove: (edits: any) => void; busy: boolean }) {
  const [to, setTo] = useState(email.to_email || '')
  const [subject, setSubject] = useState(email.subject)
  const [body, setBody] = useState(email.body)
  useEffect(() => { setTo(email.to_email || ''); setSubject(email.subject); setBody(email.body) }, [email.id])
  return (
    <div className="stack">
      <div className="email">
        <div className="head">
          <div className="fields two">
            <div><label>To ({email.to_name})</label><input value={to} onChange={e => setTo(e.target.value)} placeholder="name@example.org" /></div>
            <div><label>Subject</label><input value={subject} onChange={e => setSubject(e.target.value)} /></div>
          </div>
        </div>
        <textarea aria-label="Email body" value={body} onChange={e => setBody(e.target.value)} />
      </div>
      {email.flags?.map((f: string) => <div key={f} className="quarantine">⚠️ {f}</div>)}
      <div className="row">
        <button className="btn success" disabled={busy} onClick={() => onApprove({ to_email: to, subject, body })}>✓ Approve &amp; open in my mail app</button>
        <small>Logged in the Outbox and opened as a draft. You press Send.</small>
      </div>
    </div>
  )
}

function Quarantine({ items }: { items?: any[] }) {
  if (!items?.length) return null
  return (
    <div className="quarantine">
      <strong>🛡️ Removed before any agent read it ({items.length}):</strong>
      {items.map((q, i) => <div key={i} style={{ marginTop: '.35rem' }}><code>{q.line}</code><br /><small>{q.reasons.join(' · ')}</small></div>)}
    </div>
  )
}

function MeetingStep({ e, busy, act }: { e: any; busy: boolean; act: any }) {
  const toast = useToast()
  const m = e.meeting
  const [notes, setNotes] = useState(e.meeting_raw || '')
  const okDates: string[] = (m?.date_checks || []).filter((c: any) => c.ok).map((c: any) => c.date)
  const [f, setF] = useState({
    date: okDates[0] || e.date || '', time: m?.proposed_time || '12:00-13:00', location: e.location || '',
    mode: m?.mode && m.mode !== 'unknown' ? m.mode : (e.speaker?.suggested_mode || 'virtual'),
    travel_from: m?.travel_from || e.speaker?.location || '', attendance: String(e.expected_attendance || 25),
  })
  useEffect(() => {
    if (!m) return
    setF(x => ({ ...x, date: okDates[0] || x.date, time: m.proposed_time || x.time,
      mode: m.mode && m.mode !== 'unknown' ? m.mode : x.mode, travel_from: m.travel_from || x.travel_from }))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [m?.summary])
  return (
    <>
      <Section step="5" title={`Meeting notes with ${e.speaker?.name}`} sub="Paste your notes from the call (or their reply). The Coordinator pulls out dates, mode, travel and needs.">
        <textarea className="tall" value={notes} onChange={ev => setNotes(ev.target.value)}
          placeholder="e.g. Call on Oct 27. Happy to come in person by Metro-North. Nov 6 works, Nov 5 backup. No honorarium. Needs HDMI." />
        <div className="row" style={{ marginTop: '.6rem' }}>
          <button className="btn" disabled={busy || !notes.trim()} onClick={() => act('/meeting-notes', { notes }, (r: any) => r.quarantined?.length && toast(`🛡️ Removed ${r.quarantined.length} suspicious line(s)`))}>📝 Read my notes</button>
          <button className="btn ghost small" disabled={busy} onClick={() => { if (confirm(`Mark ${e.speaker?.name} as not working out and go back to the speaker list?`)) act('/speakers/back', {}, undefined, false) }}>They declined: pick someone else</button>
        </div>
      </Section>
      {m && (
        <Section title="📅 Confirm the date" sub="Confirming locks this idea with this speaker: the strategist will never brainstorm it again." tone="foam">
          <p><span className={`pill ${m.outcome === 'confirmed' || m.outcome === 'interested' ? 'ok' : 'warn'}`}>{m.outcome}</span> {m.summary}</p>
          <div className="meta" style={{ marginBottom: '.6rem' }}>
            {m.costs_mentioned?.length > 0 && <span>💵 {m.costs_mentioned.join('; ')}</span>}
            {m.honorarium_requested != null && <span>🎁 Honorarium asked: {money(m.honorarium_requested)}</span>}
            {m.needs?.length > 0 && <span>🧰 {m.needs.join(', ')}</span>}
          </div>
          {m.date_checks?.length > 0 && <p><small>Dates mentioned: {m.date_checks.map((c: any) => `${fmtDate(c.date)} ${c.ok ? '✓ open' : '✗ ' + c.reasons.join(' ')}`).join(' · ')}</small></p>}
          <div className="fields three">
            <div><label>Date</label><input type="date" value={f.date} onChange={ev => setF({ ...f, date: ev.target.value })} /></div>
            <div><label>Time</label><input value={f.time} onChange={ev => setF({ ...f, time: ev.target.value })} /></div>
            <div><label>Room</label><input value={f.location} onChange={ev => setF({ ...f, location: ev.target.value })} placeholder="e.g. Kroon 321" /></div>
            <div><label>Speaker joins</label><select value={f.mode} onChange={ev => setF({ ...f, mode: ev.target.value })}><option value="virtual">Virtually</option><option value="in_person">In person</option></select></div>
            <div><label>Travelling from</label><input value={f.travel_from} onChange={ev => setF({ ...f, travel_from: ev.target.value })} disabled={f.mode === 'virtual'} /></div>
            <div><label>Expected attendance</label><input type="number" value={f.attendance} onChange={ev => setF({ ...f, attendance: ev.target.value })} /></div>
          </div>
          <button className="btn success" style={{ marginTop: '.8rem' }} disabled={busy || !f.date}
            onClick={() => act('/confirm-date', { ...f, attendance: Number(f.attendance) || null, honorarium: m.honorarium_requested ?? null })}>🔒 Confirm date &amp; set the budget</button>
        </Section>
      )}
    </>
  )
}

// ================================================================ step 6: budget, then catering

function BudgetCard({ e, limits, busy, act }: { e: any; limits: any; busy: boolean; act?: any }) {
  const b = e.budget
  const [fb, setFb] = useState('')
  if (!b) return null
  return (
    <Section step={act ? '6a' : undefined} title="💰 Budget" sub={`${e.mode === 'virtual' ? 'Virtual speaker: catering only.' : e.event_type === 'field visit' ? 'Field visit: includes student transport.' : 'In-person speaker: catering + travel (+ honorarium if requested).'}`}>
      {b.decision_needed && <div className="card warn" style={{ marginBottom: '.7rem' }}><strong>⚖️ Decision needed:</strong> {b.decision_needed}</div>}
      <div className="table-wrap"><table>
        <thead><tr><th>Category</th><th>Item</th><th className="num">Amount</th></tr></thead>
        <tbody>{(b.final_lines || b.lines).map((l: any, i: number) => (
          <tr key={i}><td><span className="pill">{l.category}</span></td><td>{l.description}<br /><small>{l.basis}</small></td><td className="num">{money(l.amount, true)}</td></tr>))}
          {b.total != null && <tr><td /><td><strong>Event total</strong></td><td className="num"><strong>{money(b.total, true)}</strong></td></tr>}
        </tbody>
      </table></div>
      <p style={{ marginTop: '.6rem' }}><small>{b.impact} Catering budget set at {money(b.catering_budget, true)}. Semester money for events: {money(b.available_before)} → {money(b.available_after)}.</small></p>
      <p><small>Hard limits (code): honorarium ≤ {money(limits.honorarium_max_usd)}, travel ≤ {money(limits.travel_max_usd)}, catering ≤ {money(limits.catering_max_per_person_usd)}/person, event ≤ {money(limits.event_max_total_usd)} ({money(limits.field_visit_max_total_usd)} field visits).</small></p>
      {act && (
        <details><summary>🔄 Redo the budget</summary>
          <textarea style={{ minHeight: 60, marginTop: '.5rem' }} value={fb} onChange={ev => setFb(ev.target.value)} placeholder="e.g. keep catering to $200; add $40 for supplies" />
          <button className="btn secondary small" disabled={busy} onClick={() => act('/costing/rerun', { what: 'budget', feedback: fb })}>Redo budget (and catering)</button>
        </details>
      )}
    </Section>
  )
}

function CateringCard({ e, busy, act }: { e: any; busy: boolean; act?: any }) {
  const c = e.catering
  const [fb, setFb] = useState('')
  if (!c) return e.budget ? <Section title="🥗 Catering"><p className="muted">No catering for this event.</p></Section> : null
  return (
    <Section step={act ? '6b' : undefined} title={`🥗 Catering: ${c.caterer} (${c.cuisine})`} sub={`For ${c.headcount} people · ≈ ${c.servings} portions across dishes · vegetarian/vegan`}>
      <div className="table-wrap"><table>
        <thead><tr><th>Item</th><th>Unit</th><th className="num">Qty</th><th className="num">Price</th><th className="num">Subtotal</th></tr></thead>
        <tbody>
          {c.items.map((i: any) => <tr key={i.item}><td>{i.item} <small className={`pill ${i.diet === 'vegan' ? 'ok' : ''}`} style={{ fontSize: '.68rem' }}>{i.diet}</small></td><td><small>{i.unit} (serves {i.serves})</small></td><td className="num">{i.quantity}</td><td className="num">{money(i.unit_price, true)}</td><td className="num">{money(i.subtotal, true)}</td></tr>)}
          <tr><td colSpan={4}><strong>Total</strong> <small>(budget {money(c.budget, true)})</small></td><td className="num"><strong>{money(c.total, true)}</strong></td></tr>
        </tbody>
      </table></div>
      <p style={{ marginTop: '.6rem' }}><small><strong>Why:</strong> {c.why}</small></p>
      <p><small><strong>For Cristina:</strong> {c.order_notes}</small></p>
      <p><small className="muted">Menu prices are samples in data/caterer_menus.csv: confirm with the caterer.</small></p>
      {act && (
        <details><summary>🔄 Don’t like it? Get a different recommendation</summary>
          <textarea style={{ minHeight: 60, marginTop: '.5rem' }} value={fb} onChange={ev => setFb(ev.target.value)} placeholder="e.g. a different cuisine, more vegan items, finger food" />
          <Chips items={['Different cuisine', 'More vegan items', 'Finger food / easy to eat', 'Spend less']} onPick={n => setFb(f => (f ? `${f}; ${n.toLowerCase()}` : n))} />
          <button className="btn secondary small" disabled={busy} onClick={() => act('/costing/rerun', { what: 'catering', feedback: fb })}>Redo catering</button>
        </details>
      )}
    </Section>
  )
}

// ================================================================ later steps

function JimDecision({ busy, act }: { busy: boolean; act: any }) {
  const [text, setText] = useState('')
  return (
    <Section step="8" title="⏳ Waiting for Jim" sub="Record his decision. If he asked for changes, paste his reply and the budget and catering are redone.">
      <textarea value={text} onChange={ev => setText(ev.target.value)} placeholder="Optional: paste Jim's reply" />
      <div className="row" style={{ marginTop: '.6rem' }}>
        <button className="btn success" disabled={busy} onClick={() => act('/jim', { decision: 'approved', text })}>✓ Jim approved</button>
        <button className="btn secondary" disabled={busy} onClick={() => act('/jim', { decision: 'changes', text })}>Jim asked for changes</button>
      </div>
    </Section>
  )
}

function MarketingPanel({ e, busy, act }: { e: any; busy: boolean; act: any }) {
  const m = e.marketing
  return (
    <Section step="10" title="📣 Promote the event">
      <div className="stack">
        {m.late && <div className="card warn">⏰ Only <strong>{m.days_until} days</strong> to go. We usually market two weeks ahead, so post today.</div>}
        <div><label>Yale Connect listing</label><CopyBlock text={m.yale_connect} /></div>
        <div><label>WhatsApp message</label><CopyBlock text={m.whatsapp} /></div>
        <div><label>Day-before reminder</label><CopyBlock text={m.reminder} /></div>
        <div><label>Poster text</label><CopyBlock text={`${m.poster_headline}\n${m.poster_subhead}\n\n${m.poster_bullets.map((b: string) => `• ${b}`).join('\n')}`} /></div>
        <button className="btn success" disabled={busy} onClick={() => act('/marketing-posted', {}, undefined, false)}>✓ Posted on Yale Connect &amp; WhatsApp</button>
      </div>
    </Section>
  )
}

function WrapUp({ e, busy, act }: { e: any; busy: boolean; act: any }) {
  const [att, setAtt] = useState(String(e.expected_attendance || ''))
  const [cost, setCost] = useState(String(e.catering?.total || ''))
  const [notes, setNotes] = useState('')
  return (
    <Section step="11" title="📸 After the event" sub="Don’t forget photos! Record how it went; the Coordinator writes the newsletter recap and the ledger marks costs paid.">
      <div className="fields two">
        <div><label>Attendance</label><input type="number" value={att} onChange={ev => setAtt(ev.target.value)} /></div>
        <div><label>Actual catering cost ($)</label><input type="number" step="0.01" value={cost} onChange={ev => setCost(ev.target.value)} /></div>
      </div>
      <div className="field"><label>Highlights</label><textarea value={notes} onChange={ev => setNotes(ev.target.value)} placeholder="Great questions about…, the speaker shared…" /></div>
      <button className="btn success" disabled={busy || !att} onClick={() => act('/wrap-up', { attendance: Number(att), actual_catering: cost ? Number(cost) : null, highlights: notes })}>✓ Wrap up &amp; write recap</button>
    </Section>
  )
}

function StagePanel({ e, busy, act, approveEmail, limits }: { e: any; busy: boolean; act: any; approveEmail: any; limits: any }) {
  switch (e.stage) {
    case 'intake': return (
      <Section step="1" title="A few questions first" sub="Your answers steer the research and the ideas.">
        <IntakeForm initial={e.intake} busy={busy} submitLabel="🔍 Research & brainstorm 3 ideas" onSubmit={intake => act('/ideas', { intake })} />
      </Section>)
    case 'ideas': return <IdeasStep e={e} busy={busy} act={act} />
    case 'speakers': return <SpeakersStep e={e} busy={busy} act={act} />
    case 'invite_review': return (
      <Section step="4" title={`✉️ Invite ${e.speaker?.name}`} sub="Written in your voice, asking for a time to talk. Edit anything, then approve.">
        <EmailEditor email={e.emails.invite} busy={busy} onApprove={approveEmail('invite')} />
        <button className="btn ghost small" style={{ marginTop: '.6rem' }} disabled={busy} onClick={() => act('/speakers/back', {}, undefined, false)}>← Pick a different speaker</button>
      </Section>)
    case 'meeting': return <MeetingStep e={e} busy={busy} act={act} />
    case 'budget_review': return (
      <>
        <BudgetCard e={e} limits={limits} busy={busy} act={act} />
        <CateringCard e={e} busy={busy} act={act} />
        <section className="card ok">
          <div className="row between">
            <div><strong>Event total {money(e.budget?.total, true)}</strong><br /><small>Approving adds these lines as “waiting on Jim” in the ledger and drafts the request to Jim.</small></div>
            <button className="btn success" disabled={busy} onClick={() => act('/costing/approve')}>✓ Approve &amp; draft request to Jim</button>
          </div>
        </section>
      </>)
    case 'jim_review': return (
      <>
        <Section step="7" title="✉️ Request to Jim" sub="The budget table and catering items are inserted by code, not written by the AI.">
          <EmailEditor email={e.emails.jim} busy={busy} onApprove={approveEmail('jim')} />
        </Section>
        <BudgetCard e={e} limits={limits} busy={busy} />
        <CateringCard e={e} busy={busy} />
      </>)
    case 'awaiting_jim': return <><JimDecision busy={busy} act={act} /><BudgetCard e={e} limits={limits} busy={busy} /></>
    case 'order_review': return e.emails.order ? (
      <Section step="9" title="✉️ Catering order to Cristina" sub="Jim approved. The expenses are committed in the ledger.">
        <EmailEditor email={e.emails.order} busy={busy} onApprove={approveEmail('order')} />
      </Section>) : null
    case 'marketing_review': return <MarketingPanel e={e} busy={busy} act={act} />
    case 'scheduled': return <WrapUp e={e} busy={busy} act={act} />
    case 'done': return (
      <Section title="✅ Done" tone="ok">
        {e.recap ? <><p>{e.recap}</p><small>{e.recapped_in ? `In the ${e.recapped_in} newsletter.` : 'Will appear in the next newsletter.'}</small></> : <p className="muted">{e.notes}</p>}
        {e.attendance && <p><span className="pill ok">{e.attendance} attended</span></p>}
      </Section>)
    default: return null
  }
}

function Summary({ e }: { e: any }) {
  const rows: [string, React.ReactNode][] = [
    ['Format', e.event_type || e.intake?.format || '—'],
    ['Speaker joins', modeLabel(e.mode) || modeLabel(e.intake?.mode) || '—'],
    ['Hosts', e.hosts || 'Water LC'],
    ['Date', e.locked ? `${fmtDate(e.date)} · ${e.time?.replace('-', '–') || ''}` : e.date ? `Planned ${fmtDate(e.date)}` : 'Not set yet'],
    ['Room', e.location || '—'],
    ['Speaker', e.speaker?.name ? `${e.speaker.name} (${e.speaker.status})` : '—'],
    ['People', e.expected_attendance || '—'],
    ['Budget', e.budget?.total != null ? money(e.budget.total, true) : '—'],
  ]
  return (
    <div className="card">
      <h3>📋 At a glance {e.locked && <span className="pill ok">🔒 locked</span>}</h3>
      <table><tbody>{rows.map(([k, v]) => <tr key={k}><td className="muted" style={{ width: '40%' }}>{k}</td><td>{v}</td></tr>)}</tbody></table>
    </div>
  )
}

function Rethink({ e, busy, act }: { e: any; busy: boolean; act: any }) {
  const [fb, setFb] = useState('')
  const sent = Object.values(e.emails || {}).filter((m: any) => m.status === 'approved').map((m: any) => m.kind)
  return (
    <details className="card" style={{ padding: 0 }}>
      <summary style={{ padding: '.85rem 1.15rem' }}>🔄 Rethink the idea (allowed until the date is confirmed)</summary>
      <div style={{ padding: '0 1.15rem 1rem' }}>
        <p className="muted">Goes back to step 2 with three new ideas and clears the speaker list and drafts for this idea.</p>
        {sent.length > 0 && <div className="quarantine" style={{ marginBottom: '.6rem' }}>Already sent: {sent.join(', ')}. You may want to let them know.</div>}
        <textarea style={{ minHeight: 60 }} value={fb} onChange={ev => setFb(ev.target.value)} placeholder="What would you like instead?" />
        <button className="btn secondary small" style={{ marginTop: '.5rem' }} disabled={busy}
          onClick={() => { if (confirm('Go back to brainstorming? The current speaker list and drafts for this idea are cleared.')) act('/ideas', { feedback: fb }) }}>🔄 Brainstorm new ideas</button>
      </div>
    </details>
  )
}

export function EventDetail({ id }: { id: string }) {
  const toast = useToast()
  const [busy, setBusy] = useState(false)
  const { data, reload, setData } = usePoll<{ event: any; stages: Stage[]; contacts: any; limits: any }>(
    () => api(`/admin/events/${id}`), [id], d => (d?.event.working ? 2000 : null))
  const e = data?.event

  // act(path, body, after?, startsAgent = true)
  const act = async (path: string, body: any = {}, after?: (r: any) => void, startsAgent = true) => {
    setBusy(true)
    try {
      const r = await api(`/admin/events/${id}${path}`, 'POST', body)
      after?.(r)
      if (data && startsAgent) setData({ ...data, event: { ...data.event, working: true } })
      window.setTimeout(reload, startsAgent ? 400 : 50)
      if (startsAgent) window.scrollTo({ top: 0, behavior: 'smooth' })
    } catch (err: any) { toast(err.message, true) } finally { setBusy(false) }
  }
  const approveEmail = (kind: string) => (edits: any) =>
    act(`/emails/${kind}/approve`, edits, r => { window.location.href = mailto(r.to_email, r.subject, r.body); toast('Logged in the Outbox and opened in your mail app ✉️') }, kind === 'order')

  if (!e) return <AdminShell title="Loading…"><div className="card empty">Loading…</div></AdminShell>
  const stages = data!.stages
  const rethinkable = ['speakers', 'invite_review', 'meeting'].includes(e.stage) && !e.locked

  return (
    <AdminShell title={e.title} subtitle={<span>Next: <strong>{NEXT[e.stage]}</strong></span>}
      actions={<a className="btn secondary small" href="#/admin/events">← Events</a>}>
      <div className="card" style={{ padding: '.7rem .8rem' }}>
        <div className="river">{stages.map(([k, label], i) => (
          <div key={k} className={`st ${i < e.stage_index ? 'done' : i === e.stage_index ? 'now' : ''}`}><span className="dot" />{label}</div>
        ))}</div>
      </div>
      {e.working && <Working text="The agents are working… this page updates by itself." />}
      {e.error && !e.working && (
        <div className="card alert"><h3>Something went wrong</h3><p className="mono">{e.error}</p>
          <button className="btn small" onClick={() => act('/retry')}>Try again</button></div>
      )}
      <Quarantine items={e.last_screen?.quarantined} />
      {!e.working && rethinkable && <Rethink e={e} busy={busy} act={act} />}

      <div className="grid side">
        <div className="stack">
          {!e.working && <StagePanel e={e} busy={busy} act={act} approveEmail={approveEmail} limits={data!.limits} />}
          {e.plan && e.stage !== 'ideas' && (
            <details className="card"><summary>💡 The idea: {e.plan.title}</summary>
              <p style={{ marginTop: '.6rem' }}>{e.plan.description}</p>
              <p><small><strong>Why now:</strong> {e.plan.why_now}</small></p>
              <ul>{e.plan.learning_goals.map((g: string) => <li key={g}>{g}</li>)}</ul>
            </details>
          )}
        </div>
        <div className="stack">
          <Summary e={e} />
          <details className="card">
            <summary>🌊 Activity ({e.activity?.length || 0})</summary>
            <ul className="feed" style={{ marginTop: '.5rem' }}>{[...(e.activity || [])].reverse().map((a: any, i: number) => (
              <li key={i}><span className={`who ${a.who}`}>{a.who}</span><span>{a.msg}</span><span className="ts">{fmtTime(a.ts)}</span></li>
            ))}</ul>
          </details>
          <button className="btn ghost small" onClick={async () => {
            if (!confirm('Delete this event? Pending budget lines are removed too.')) return
            await api(`/admin/events/${id}`, 'DELETE'); go('/admin/events')
          }}>🗑 Delete event</button>
        </div>
      </div>
    </AdminShell>
  )
}
