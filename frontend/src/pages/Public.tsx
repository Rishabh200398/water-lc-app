import { useEffect, useState } from 'react'
import { api, fmtDate } from '../api'
import { DateBadge, Md, Waves, useRoute } from '../ui'

type Card = { id: string; title: string; date: string; time: string; location: string; hosts: string; event_type: string; description: string; recap?: string; speaker?: string }
type Newsletter = { id: string; month: string; subject: string; greeting: string; event_recaps: string; upcoming_events: string; water_in_the_news: string; spotlight: string; helpful_links: string; upcoming_conferences: string; jobs_and_internships: string }
type PublicData = { upcoming: Card[]; past: Card[]; newsletters: Newsletter[]; interests: string[]; co_leads: string[] }

function PublicHeader({ children }: { children?: React.ReactNode }) {
  const route = useRoute()
  const link = (to: string, label: string) => (
    <a href={`#${to}`} className={route === to ? 'active' : ''}>{label}</a>
  )
  return (
    <header className="ocean-header">
      <div className="inner">
        <div className="topbar">
          <a className="brand" href="#/"><img src="/drop.svg" alt="" /><span>Water LC<small>Yale School of the Environment</small></span></a>
          <nav className="nav-links" aria-label="Main">
            {link('/', 'Home')}
            {link('/events', 'Events')}
            {link('/newsletters', 'Newsletters')}
            {link('/alumni', 'Alumni')}
            <a href="#/admin">Co-lead login</a>
          </nav>
        </div>
        {children}
      </div>
      <Waves />
    </header>
  )
}

function usePublic() {
  const [d, setD] = useState<PublicData | null>(null)
  useEffect(() => { api<PublicData>('/public').then(setD).catch(() => setD({ upcoming: [], past: [], newsletters: [], interests: [], co_leads: [] })) }, [])
  return d
}

function EventCard({ e, showRecap = false }: { e: Card; showRecap?: boolean }) {
  return (
    <div className="card">
      <div className="row" style={{ alignItems: 'flex-start', flexWrap: 'nowrap' }}>
        <DateBadge date={e.date} />
        <div style={{ minWidth: 0 }}>
          <h3 style={{ marginBottom: '.2rem' }}>{e.title}</h3>
          <div className="row" style={{ gap: '.35rem', marginBottom: '.4rem' }}>
            {e.event_type && <span className="pill">{e.event_type}</span>}
            {e.hosts && e.hosts !== 'Water LC' && <span className="pill dark">{e.hosts}</span>}
          </div>
          <small>{[e.time && e.time.replace('-', '–'), e.location].filter(Boolean).join(' · ') || 'Details coming soon'}</small>
          {e.speaker && <p style={{ marginTop: '.4rem' }}>With <strong>{e.speaker}</strong></p>}
          {showRecap && e.recap ? <p style={{ marginTop: '.5rem' }}>{e.recap}</p> : e.description && <p style={{ marginTop: '.5rem' }}>{e.description}</p>}
        </div>
      </div>
    </div>
  )
}

export function PublicHome() {
  const d = usePublic()
  return (
    <>
      <PublicHeader>
        <div className="hero">
          <div className="eyebrow">Water Learning Community</div>
          <h1>Making waves in water careers, science and policy</h1>
          <p>Lunch and Learns with water professionals, career chats, field trips and a monthly newsletter for YSE students who care about water.</p>
          <div className="row" style={{ marginTop: '1rem' }}>
            <a className="btn" href="#/events">See upcoming events</a>
            <a className="btn secondary" href="#/newsletters">Read the newsletter</a>
          </div>
        </div>
      </PublicHeader>
      <main className="page stack">
        <section className="grid side">
          <div className="stack">
            <h2>Coming up</h2>
            {!d ? <div className="card empty">Loading…</div> :
              d.upcoming.length ? d.upcoming.slice(0, 4).map(e => <EventCard key={e.id} e={e} />) :
                <div className="card empty">New events are being planned. Check back soon!</div>}
          </div>
          <div className="stack">
            <div className="card foam">
              <h3>💧 What members asked for</h3>
              <p className="muted">From the Fall Splash word cloud. We plan around it.</p>
              <div className="chips">{d?.interests.map((t, i) => <span key={t} className={`chip ${i < 3 ? 'big' : ''}`}>{t}</span>)}</div>
            </div>
            <div className="card">
              <h3>🌊 Who we are</h3>
              <p>Water LC connects YSE students with the water sector: water quality, coastal resilience, freshwater management, water law and finance.</p>
              <p className="muted">Co-leads: {d?.co_leads.join(' & ')} · Advisor: Prof. Jim Saiers</p>
            </div>
          </div>
        </section>
        <section className="stack">
          <h2>Recent events</h2>
          <div className="grid two">{d?.past.slice(0, 6).map(e => <EventCard key={e.id} e={e} showRecap />)}</div>
        </section>
      </main>
      <footer className="footer">Water Learning Community · Yale School of the Environment</footer>
    </>
  )
}

export function PublicEvents() {
  const d = usePublic()
  return (
    <>
      <PublicHeader><div className="hero"><h1>Events</h1><p>Lunch and Learns, career chats, field trips and socials.</p></div></PublicHeader>
      <main className="page stack">
        <h2>Upcoming</h2>
        <div className="grid two">{d?.upcoming.map(e => <EventCard key={e.id} e={e} />)}</div>
        {d && !d.upcoming.length && <div className="card empty">Nothing scheduled yet.</div>}
        <h2 style={{ marginTop: '2rem' }}>Past events</h2>
        <div className="grid two">{d?.past.map(e => <EventCard key={e.id} e={e} showRecap />)}</div>
      </main>
    </>
  )
}

export function PublicNewsletters() {
  const d = usePublic()
  const [open, setOpen] = useState<string | null>(null)
  const n = d?.newsletters.find(x => x.id === open) || d?.newsletters[0]
  const sections: [keyof Newsletter, string][] = [
    ['greeting', ''], ['event_recaps', 'Event Recaps'], ['upcoming_events', 'Upcoming Events'],
    ['water_in_the_news', 'Water in the News'], ['spotlight', 'Spotlight'], ['helpful_links', 'Helpful Links'],
    ['upcoming_conferences', 'Upcoming Conferences'], ['jobs_and_internships', 'Job & Internship Postings'],
  ]
  return (
    <>
      <PublicHeader><div className="hero"><h1>Newsletters</h1><p>Monthly news, events, jobs and good news from the water world.</p></div></PublicHeader>
      <main className="page">
        {!d ? <div className="card empty">Loading…</div> : !d.newsletters.length ? (
          <div className="card empty">The first issue made in the app will appear here once the co-leads approve it.</div>
        ) : (
          <div className="grid side">
            <article className="card stack">
              <h2>{n!.subject}</h2>
              {sections.map(([k, title]) => (
                <section key={k}>
                  {title && <h3 style={{ color: 'var(--ocean)' }}>{title}</h3>}
                  <Md text={n![k]} />
                </section>
              ))}
            </article>
            <aside className="card">
              <h3>Past issues</h3>
              {d.newsletters.map(x => (
                <button key={x.id} className="btn ghost block" style={{ justifyContent: 'flex-start' }} onClick={() => setOpen(x.id)}>📬 {x.month}</button>
              ))}
            </aside>
          </div>
        )}
      </main>
    </>
  )
}

export function PublicAlumni() {
  return (
    <>
      <PublicHeader><div className="hero"><h1>Water alumni</h1><p>The people who led Water LC before us, and alumni working across the water sector.</p></div></PublicHeader>
      <main className="page">
        <div className="card empty">
          <h3>Coming soon</h3>
          <p>Past co-leads and water alumni will be listed here. If you're a Water LC alum, we'd love to hear from you!</p>
          <small>Last updated {fmtDate(new Date().toISOString(), { month: 'long', year: 'numeric' })}</small>
        </div>
      </main>
    </>
  )
}
