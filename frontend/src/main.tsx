import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { getSession } from './api'
import { ToastProvider, useRoute } from './ui'
import { PublicAlumni, PublicEvents, PublicHome, PublicNewsletters } from './pages/Public'
import { Login, MorePage } from './pages/AdminShell'
import { Dashboard } from './pages/Dashboard'
import { EventDetail, EventsList, NewEvent } from './pages/Events'
import { NewsletterDetail, NewsletterList } from './pages/Newsletter'
import { BudgetPage, OutboxPage, SafetyPage, UsagePage } from './pages/Ops'
import './styles.css'

function App() {
  const route = useRoute()
  if (route === '/events') return <PublicEvents />
  if (route === '/newsletters') return <PublicNewsletters />
  if (route === '/alumni') return <PublicAlumni />
  if (route === '/login') return <Login />
  if (route.startsWith('/admin')) {
    if (!getSession()) return <Login />
    const parts = route.split('/').filter(Boolean) // ['admin', 'events', id]
    const [, section, id] = parts
    if (!section) return <Dashboard />
    if (section === 'events') return id === 'new' ? <NewEvent /> : id ? <EventDetail id={id} /> : <EventsList />
    if (section === 'newsletter') return id ? <NewsletterDetail id={id} /> : <NewsletterList />
    if (section === 'budget') return <BudgetPage />
    if (section === 'outbox') return <OutboxPage />
    if (section === 'usage') return <UsagePage />
    if (section === 'safety') return <SafetyPage />
    if (section === 'more') return <MorePage />
    return <Dashboard />
  }
  return <PublicHome />
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ToastProvider><App /></ToastProvider>
  </StrictMode>,
)
