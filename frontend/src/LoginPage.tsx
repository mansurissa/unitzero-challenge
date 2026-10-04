import { useState, type FormEvent } from 'react'
import { ApiError } from './api'
import { useAuth } from './auth'

export function LoginPage() {
  const { login } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await login(email, password)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Login failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="mx-auto mt-24 max-w-sm px-6">
      <h1 className="mb-8 text-2xl font-medium tracking-wide text-ink-bright">
        Dataset Request Desk<span className="ml-0.5 inline-block h-[1.1em] w-[0.55em] translate-y-[0.18em] animate-pulse bg-ink-bright" aria-hidden />
      </h1>
      <form onSubmit={submit} className="card flex flex-col gap-5">
        <p className="section-label">Sign in</p>
        <label className="flex flex-col gap-1 text-xs uppercase tracking-wider text-muted">
          Email
          <input className="input" type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoFocus required />
        </label>
        <label className="flex flex-col gap-1 text-xs uppercase tracking-wider text-muted">
          Password
          <input className="input" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        </label>
        {error && <p className="border border-ink bg-paper px-3 py-2 text-sm text-ink">{error}</p>}
        <button type="submit" className="btn-primary" disabled={busy}>{busy ? 'Signing in…' : 'Sign in →'}</button>
      </form>
    </main>
  )
}
