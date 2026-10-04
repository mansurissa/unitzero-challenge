import { useEffect, useState } from 'react'

type Health = { status: string; db: string }

export default function App() {
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
    <main>
      <h1>Dataset Request Desk</h1>
      <p>Hello! The frontend is running.</p>
      <p>
        Backend:{' '}
        {error ? <span className="bad">unreachable ({error})</span>
          : health ? <span className={health.db === 'ok' ? 'ok' : 'bad'}>{health.status} (db: {health.db})</span>
          : <span>checking…</span>}
      </p>
    </main>
  )
}
