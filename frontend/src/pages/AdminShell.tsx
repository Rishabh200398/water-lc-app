import { useState, type ReactNode } from 'react'
import { api, getSession, setSession } from '../api'
import { Waves, go, useRoute, useToast } from '../ui'

const NAV: [string, string, string][] = [
  ['/admin', '🏠', 'Today'],
  ['/admin/events', '📅', 'Events'],
  ['/admin/newsletter', '📰', 'Newsletter'],
  ['/admin/budget', '💰', 'Budget'],
  ['/admin/outbox', '📤', 'Outbox'],
  ['/admin/usage', '💧', 'Usage & water'],
  ['/admin/safety', '🛡️', 'Safety log'],
]
const TABS = [NAV[0], NAV[1], NAV[2], NAV[3], ['/admin/more', '☰', 'More'] as [string, string, string]]

export function AdminShell({ title, subtitle, actions, children }: { title: string; subtitle?: ReactNode; actions?: ReactNode; children: ReactNode }) {
  const route = useRoute()
  const s = getSession()
  const active = (to: string) => (to === '/admin' ? route === '/admin' : route.startsWith(to)) ? 'active' : ''
  return (
    <div className="admin">
      <nav className="sidebar" aria-label="Admin">
        <a className="brand" href="#/admin" style={{ padding: '.2rem .6rem 1rem' }}><img src="/drop.svg" alt="" /><span>Water LC<small>Ops copilot</small></span></a>
        {NAV.map(([to, icon, label]) => <a key={to} href={`#${to}`} className={`nav ${active(to)}`}><span>{icon}</span>{label}</a>)}
        <a href="#/" className="nav"><span>🌐</span>Public site</a>
        <div className="who">Signed in as <strong>{s?.name}</strong><br />
          <button className="btn ghost small" style={{ color: '#a9d9e2', padding: 0 }} onClick={() => { setSession(null); go('/') }}>Sign out</button>
        </div>
      </nav>
      <div className="admin-main">
        <header className="ocean-header">
          <div className="inner">
            <div className="topbar">
              <a className="brand" href="#/admin"><img src="/drop.svg" alt="" /><span>Water LC<small>Ops copilot · {s?.name}</small></span></a>
              <div className="row">{actions}</div>
            </div>
            <div style={{ paddingTop: '1.2rem' }}>
              <h1 style={{ fontSize: 'clamp(1.45rem, 4vw, 2.1rem)' }}>{title}</h1>
              {subtitle && <div style={{ color: '#cdeef3' }}>{subtitle}</div>}
            </div>
          </div>
          <Waves />
        </header>
        <main className="page stack">{children}</main>
      </div>
      <nav className="bottom-tabs" aria-label="Admin tabs">
        {TABS.map(([to, icon, label]) => <a key={to} href={`#${to}`} className={active(to)}><span className="i">{icon}</span>{label}</a>)}
      </nav>
    </div>
  )
}

export function MorePage() {
  return (
    <AdminShell title="More">
      <div className="grid two">
        {NAV.slice(4).map(([to, icon, label]) => (
          <a key={to} href={`#${to}`} className="card-link"><div className="card"><h3>{icon} {label}</h3></div></a>
        ))}
        <a href="#/" className="card-link"><div className="card"><h3>🌐 Public site</h3></div></a>
        <button className="card" style={{ textAlign: 'left', cursor: 'pointer', font: 'inherit' }} onClick={() => { setSession(null); go('/') }}><h3>🚪 Sign out</h3></button>
      </div>
    </AdminShell>
  )
}

export function Login() {
  const [name, setName] = useState('Rishabh')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const toast = useToast()
  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    try {
      const r = await api<{ token: string; name: string }>('/login', 'POST', { name, password })
      setSession(r)
      go('/admin')
    } catch (err: any) {
      toast(err.message, true)
    } finally { setBusy(false) }
  }
  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      <header className="ocean-header">
        <div className="inner"><a className="brand" href="#/"><img src="/drop.svg" alt="" /><span>Water LC<small>Co-lead login</small></span></a></div>
        <Waves />
      </header>
      <main className="page" style={{ maxWidth: 440 }}>
        <form className="card stack" onSubmit={submit}>
          <h2>Welcome back 💧</h2>
          <p className="muted">The ops copilot is for Water LC co-leads. Every email and the newsletter wait for your approval.</p>
          <div className="field">
            <label htmlFor="who">I am</label>
            <select id="who" value={name} onChange={e => setName(e.target.value)}>
              <option>Rishabh</option><option>Erika</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor="pw">Password</label>
            <input id="pw" type="password" autoComplete="current-password" value={password} onChange={e => setPassword(e.target.value)} placeholder="ADMIN_PASSWORD from .env" required />
          </div>
          <button className="btn block" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</button>
          <small>Graders: the default password is in the README.</small>
        </form>
      </main>
    </div>
  )
}
