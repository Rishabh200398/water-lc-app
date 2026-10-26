import { useEffect, useState } from 'react'
import { api, fmtTime } from '../api'
import { CopyButton, Md, Working, go, usePoll, useToast } from '../ui'
import { AdminShell } from './AdminShell'

const SECTIONS: [string, string][] = [
  ['subject', 'Subject'], ['greeting', 'Greeting'], ['event_recaps', 'Event Recaps'], ['upcoming_events', 'Upcoming Events'],
  ['water_in_the_news', 'Water in the News'], ['spotlight', 'Spotlight'], ['helpful_links', 'Helpful Links'],
  ['upcoming_conferences', 'Upcoming Conferences'], ['jobs_and_internships', 'Job & Internship Postings'],
]

function nextMonthLabel() {
  const d = new Date()
  d.setDate(1); d.setMonth(d.getMonth() + 1)
  return d.toLocaleDateString('en-US', { month: 'long', year: 'numeric' })
}

export function NewsletterList() {
  const { data } = usePoll<any[]>(() => api('/admin/newsletters'), [], d => (d?.some(n => n.working) ? 3000 : null))
  const [month, setMonth] = useState(nextMonthLabel())
  const [pasted, setPasted] = useState('')
  const [web, setWeb] = useState(true)
  const [busy, setBusy] = useState(false)
  const toast = useToast()
  const start = async () => {
    setBusy(true)
    try {
      const n = await api('/admin/newsletters', 'POST', { month, pasted, use_web: web })
      if (n.quarantined?.length) toast(`🛡️ Removed ${n.quarantined.length} suspicious line(s) from the pasted text`)
      go(`/admin/newsletter/${n.id}`)
    } catch (e: any) { toast(e.message, true) } finally { setBusy(false) }
  }
  return (
    <AdminShell title="Newsletter" subtitle="The Newsletter editor drafts the monthly issue in your template. You review and approve it.">
      <div className="grid side">
        <div className="card stack">
          <h3>📰 Draft a new issue</h3>
          <div className="fields two">
            <div><label>Issue</label><input value={month} onChange={e => setMonth(e.target.value)} /></div>
            <div style={{ display: 'flex', alignItems: 'flex-end' }}><label className="checkbox"><input type="checkbox" checked={web} onChange={e => setWeb(e.target.checked)} /> Research news, jobs &amp; conferences on the web</label></div>
          </div>
          <div>
            <label>Anything to include? (optional)</label>
            <textarea value={pasted} onChange={e => setPasted(e.target.value)} placeholder="Paste job posts, an article, a conference you heard about… Outside text is screened for hidden instructions." />
            <button className="btn ghost small" type="button" onClick={async () => setPasted((await api('/admin/demo/injected_article')).text)}>Load the injection demo article</button>
          </div>
          <button className="btn" disabled={busy || !month.trim()} onClick={start}>{busy ? 'Starting…' : '🌊 Draft the newsletter'}</button>
          <small>Recaps come from events you wrapped up in the app; upcoming events come from the pipeline.</small>
        </div>
        <div className="card">
          <h3>Issues</h3>
          {!data?.length && <p className="muted">No issues yet.</p>}
          {data?.map(n => (
            <a key={n.id} href={`#/admin/newsletter/${n.id}`} className="row between" style={{ padding: '.5rem 0', borderBottom: '1px dashed var(--line)' }}>
              <span>📬 {n.month}</span>
              <span className={`pill ${n.stage === 'approved' ? 'ok' : n.stage === 'review' ? 'warn' : ''}`}>{n.working ? 'drafting…' : n.stage}</span>
            </a>
          ))}
        </div>
      </div>
    </AdminShell>
  )
}

export function NewsletterDetail({ id }: { id: string }) {
  const toast = useToast()
  const { data: n, reload } = usePoll<any>(() => api(`/admin/newsletters/${id}`), [id], d => (d?.working ? 2500 : null))
  const [draft, setDraft] = useState<Record<string, string>>({})
  const [preview, setPreview] = useState(true)
  const [busy, setBusy] = useState(false)
  useEffect(() => { if (n?.draft) setDraft(n.draft) }, [n?.draft])

  if (!n) return <AdminShell title="Loading…"><div className="card empty">Loading…</div></AdminShell>
  const all = SECTIONS.slice(1).map(([k, t]) => `${t === 'Greeting' ? '' : t + '\n'}${draft[k] || ''}`).join('\n\n')
  const approve = async () => {
    setBusy(true)
    try { await api(`/admin/newsletters/${id}/approve`, 'POST', draft); toast('Approved. It’s in the Outbox and on the public site 📬'); reload() }
    catch (e: any) { toast(e.message, true) } finally { setBusy(false) }
  }
  return (
    <AdminShell title={`${n.month} newsletter`} subtitle={n.stage === 'approved' ? `Approved by ${n.approved_by} · ${fmtTime(n.approved_at)}` : 'Review every section, edit anything, then approve.'}
      actions={<a className="btn secondary small" href="#/admin/newsletter">← Newsletters</a>}>
      {n.working && <Working text="The Newsletter editor is researching and writing… (about a minute)" />}
      {n.error && !n.working && <div className="card alert"><h3>Something went wrong</h3><p className="mono">{n.error}</p></div>}
      {n.quarantined?.length > 0 && (
        <div className="quarantine"><strong>🛡️ Removed {n.quarantined.length} instruction-like line(s) before any agent read them:</strong>
          {n.quarantined.map((q: any, i: number) => <div key={i} style={{ marginTop: '.35rem' }}><code>{q.line}</code><br /><small>{q.reasons.join(' · ')}</small></div>)}
        </div>
      )}
      {n.flags?.map((f: string) => <div key={f} className="quarantine">⚠️ {f}</div>)}
      {n.draft && (
        <>
          <div className="row">
            <button className={`btn small ${preview ? '' : 'secondary'}`} onClick={() => setPreview(true)}>Preview</button>
            <button className={`btn small ${!preview ? '' : 'secondary'}`} onClick={() => setPreview(false)}>Edit</button>
            <span className="spacer" />
            <CopyButton text={all} label="Copy whole issue" />
          </div>
          {SECTIONS.map(([k, title]) => (
            <section key={k} className="card">
              <div className="row between"><h3>{title}</h3><CopyButton text={draft[k] || ''} /></div>
              {preview ? <Md text={draft[k] || ''} /> :
                <textarea className={k === 'subject' ? '' : 'tall'} style={k === 'subject' ? { minHeight: 42 } : {}} value={draft[k] || ''} onChange={e => setDraft({ ...draft, [k]: e.target.value })} />}
            </section>
          ))}
          {n.stage === 'review' && <button className="btn success block" disabled={busy} onClick={approve}>✓ Approve newsletter</button>}
        </>
      )}
      <details className="card"><summary>Activity</summary>
        <ul className="feed">{[...(n.activity || [])].reverse().map((a: any, i: number) => <li key={i}><span className={`who ${a.who}`}>{a.who}</span><span>{a.msg}</span><span className="ts">{fmtTime(a.ts)}</span></li>)}</ul>
      </details>
    </AdminShell>
  )
}
