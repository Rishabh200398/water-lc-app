import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { fmtDate } from './api'

// ---------------------------------------------------------------- router (hash based)

export function useRoute(): string {
  const [route, setRoute] = useState(() => window.location.hash.slice(1) || '/')
  const [, setTick] = useState(0)
  useEffect(() => {
    const on = () => {
      setRoute(window.location.hash.slice(1) || '/')
      setTick(t => t + 1) // re-render even when the hash is unchanged (e.g. right after logging in)
      window.scrollTo(0, 0)
    }
    window.addEventListener('hashchange', on)
    return () => window.removeEventListener('hashchange', on)
  }, [])
  return route
}

export const go = (path: string) => {
  if (window.location.hash === '#' + path) window.dispatchEvent(new HashChangeEvent('hashchange')) // same page: re-render anyway
  else window.location.hash = '#' + path
}

// ---------------------------------------------------------------- toast

type ToastT = { msg: string; error?: boolean } | null
const ToastCtx = createContext<(msg: string, error?: boolean) => void>(() => {})

export function ToastProvider({ children }: { children: ReactNode }) {
  const [t, setT] = useState<ToastT>(null)
  const show = useCallback((msg: string, error = false) => {
    setT({ msg, error })
    window.setTimeout(() => setT(null), error ? 6000 : 3200)
  }, [])
  return (
    <ToastCtx.Provider value={show}>
      {children}
      {t && <div className={`toast ${t.error ? 'error' : ''}`} role="status">{t.msg}</div>}
    </ToastCtx.Provider>
  )
}
export const useToast = () => useContext(ToastCtx)

// ---------------------------------------------------------------- water bits

export function Waves() {
  const path = 'M0,40 C150,80 350,0 600,40 C850,80 1050,0 1200,40 L1200,120 L0,120 Z'
  return (
    <div className="waves" aria-hidden="true">
      <svg className="wave3" viewBox="0 0 2400 120" preserveAspectRatio="none" style={{ position: 'absolute', bottom: 8 }}>
        <path d={path} fill="#5fd3e0" /><path d={path} transform="translate(1200,0)" fill="#5fd3e0" />
      </svg>
      <svg className="wave2" viewBox="0 0 2400 120" preserveAspectRatio="none" style={{ position: 'absolute', bottom: 2 }}>
        <path d={path} fill="#0fa3b1" /><path d={path} transform="translate(1200,0)" fill="#0fa3b1" />
      </svg>
      <svg className="wave1" viewBox="0 0 2400 120" preserveAspectRatio="none" style={{ position: 'absolute', bottom: 0 }}>
        <path d={path} fill="#eef8fa" /><path d={path} transform="translate(1200,0)" fill="#eef8fa" />
      </svg>
    </div>
  )
}

export function Drop({ size = 26, className = '' }: { size?: number; className?: string }) {
  return (
    <svg className={className} width={size} height={size} viewBox="0 0 64 64" aria-hidden="true">
      <defs>
        <linearGradient id="dg" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#5fd3e0" /><stop offset="1" stopColor="#087e8b" />
        </linearGradient>
      </defs>
      <path d="M32 4C32 4 12 28 12 40a20 20 0 0 0 40 0C52 28 32 4 32 4z" fill="url(#dg)" />
      <path d="M22 41a10 10 0 0 0 8 10" stroke="#fff" strokeWidth="4" fill="none" strokeLinecap="round" opacity=".8" />
    </svg>
  )
}

export function Working({ text }: { text: string }) {
  return (
    <div className="working" role="status" aria-live="polite">
      <Drop className="drop-spin" />
      <span>{text}</span>
    </div>
  )
}

export function CopyButton({ text, label = 'Copy' }: { text: string; label?: string }) {
  const [done, setDone] = useState(false)
  return (
    <button className="btn secondary small" type="button" onClick={async () => {
      try { await navigator.clipboard.writeText(text) } catch {
        const ta = document.createElement('textarea'); ta.value = text; document.body.appendChild(ta); ta.select()
        document.execCommand('copy'); ta.remove()
      }
      setDone(true); window.setTimeout(() => setDone(false), 1500)
    }}>{done ? 'Copied ✓' : label}</button>
  )
}

export function CopyBlock({ text }: { text: string }) {
  return <div className="copy-block"><CopyButton text={text} />{text}</div>
}

export function DateBadge({ date }: { date?: string | null }) {
  if (!date) return <div className="event-date"><small>TBD</small><b>?</b></div>
  return (
    <div className="event-date">
      <small>{fmtDate(date, { month: 'short' })}</small>
      <b>{fmtDate(date, { day: 'numeric' })}</b>
      <small>{fmtDate(date, { weekday: 'short' })}</small>
    </div>
  )
}

/** Very small markdown: **bold**, ### headings, [text](url), line breaks. */
export function Md({ text }: { text: string }) {
  const lines = (text || '').split('\n')
  const inline = (s: string, k: number) => {
    const parts: ReactNode[] = []
    const re = /\*\*(.+?)\*\*|\[([^\]]+)\]\((https?:[^)]+)\)/g
    let last = 0, m: RegExpExecArray | null, i = 0
    while ((m = re.exec(s))) {
      if (m.index > last) parts.push(s.slice(last, m.index))
      if (m[1]) parts.push(<strong key={`${k}-${i++}`}>{m[1]}</strong>)
      else parts.push(<a key={`${k}-${i++}`} href={m[3]} target="_blank" rel="noreferrer noopener">{m[2]}</a>)
      last = re.lastIndex
    }
    if (last < s.length) parts.push(s.slice(last))
    return parts
  }
  return (
    <div>
      {lines.map((l, k) => {
        const h = l.match(/^#{1,4}\s+(.*)/)
        if (h) return <h4 key={k} style={{ marginTop: '.8rem' }}>{inline(h[1], k)}</h4>
        if (!l.trim()) return <div key={k} style={{ height: '.55rem' }} />
        if (/^\s*[-*]\s+/.test(l)) return <div key={k} style={{ paddingLeft: '1rem', textIndent: '-.8rem' }}>• {inline(l.replace(/^\s*[-*]\s+/, ''), k)}</div>
        return <div key={k}>{inline(l, k)}</div>
      })}
    </div>
  )
}

export function MiniRiver({ index, total }: { index: number; total: number }) {
  return (
    <div className="mini-river" aria-label={`Step ${index + 1} of ${total}`}>
      {Array.from({ length: total }).map((_, i) => <span key={i} className={i < index ? 'done' : i === index ? 'now' : ''} />)}
    </div>
  )
}

export function usePoll<T>(load: () => Promise<T>, deps: unknown[], every?: (data: T | null) => number | null) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [tick, setTick] = useState(0)
  const reload = useCallback(() => setTick(t => t + 1), [])
  useEffect(() => {
    let alive = true
    let timer: number | undefined
    const run = async () => {
      try {
        const d = await load()
        if (!alive) return
        setData(d); setError(null)
        const ms = every?.(d)
        if (ms) timer = window.setTimeout(run, ms)
      } catch (e: any) {
        if (alive) setError(e.message || String(e))
      }
    }
    run()
    return () => { alive = false; if (timer) window.clearTimeout(timer) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick])
  return { data, error, reload, setData }
}
