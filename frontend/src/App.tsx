import { useEffect, useState } from 'react'
import { useAuth } from './auth'
import { LoginPage } from './LoginPage'

type Health = { status: string; db: string }

export default function App() {
  const { user, loading, logout } = useAuth()

  if (loading) return <main className="p-8 text-center text-muted">Loading…</main>
  if (!user) return <LoginPage />

  return (
    <>
      <header className="border-b border-rule">
        <div className="mx-auto flex max-w-3xl items-center gap-4 px-6 py-4">
          <span className="flex-1 text-lg font-medium tracking-wide text-ink-bright">Dataset Request Desk</span>
          <span className="text-sm text-muted">
            {user.name} · <span className="text-ink">{user.role}</span>
          </span>
          <button className="btn-link" onClick={logout}>Log out</button>
        </div>
      </header>
      <main className="mx-auto max-w-3xl px-6 py-12">
        <section className="mb-10">
          <p className="section-label mb-3">Hello</p>
          <p className="text-[0.95rem] leading-[1.85]">
            Signed in as <strong className="font-medium text-ink-bright">{user.email}</strong> with the{' '}
            <strong className="font-medium text-ink-bright">{user.role}</strong> role.
          </p>
        </section>
        <hr className="my-10 border-rule" />
        <section>
          <p className="section-label mb-3">Status</p>
          <BackendStatus />
        </section>
      </main>
    </>
  )
}

function BackendStatus() {
  const [health, setHealth] = useState<Health | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    // /health is proxied to the Django API (vite.config.ts in dev, nginx.conf in Docker).
    fetch('/health')
      .then((r) => r.json())
      .then(setHealth)
      .catch((e) => setError(String(e)))
  }, [])

  return (
    <p className="text-[0.95rem] leading-[1.85]">
      Backend:{' '}
      {error ? <strong className="font-medium text-ink-bright">unreachable ({error})</strong>
        : health ? <strong className="font-medium text-ink-bright">{health.status} · db {health.db}</strong>
        : <span className="text-muted">checking…</span>}
    </p>
  )
}
