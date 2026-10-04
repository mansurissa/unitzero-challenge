import { Navigate, NavLink, Route, Routes } from 'react-router-dom'
import { useAuth } from './auth'
import { EpisodesPage } from './EpisodesPage'
import { LoginPage } from './LoginPage'
import { RequestDetailPage } from './RequestDetailPage'
import { RequestsPage } from './RequestsPage'

export default function App() {
  const { user, loading, logout } = useAuth()

  if (loading) return <main className="p-8 text-center text-muted">Loading…</main>
  if (!user) return <LoginPage />

  const isOps = user.role !== 'client'
  const navClass = ({ isActive }: { isActive: boolean }) => `text-sm ${isActive ? 'text-ink-bright underline' : 'text-muted hover:text-ink'}`

  return (
    <>
      <header className="border-b border-rule">
        <div className="mx-auto flex max-w-5xl items-center gap-6 px-6 py-4">
          <span className="text-lg font-medium tracking-wide text-ink-bright">Dataset Request Desk</span>
          <nav className="flex flex-1 gap-5">
            <NavLink to="/" end className={navClass}>Requests</NavLink>
            {isOps && <NavLink to="/episodes" className={navClass}>Episodes</NavLink>}
          </nav>
          <span className="text-sm text-muted">
            {user.name} · <span className="text-ink">{user.role}</span>
          </span>
          <button className="btn-link" onClick={logout}>Log out</button>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-6 py-10">
        <Routes>
          <Route path="/" element={<RequestsPage />} />
          <Route path="/requests/:id" element={<RequestDetailPage />} />
          {isOps && <Route path="/episodes" element={<EpisodesPage />} />}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </>
  )
}
