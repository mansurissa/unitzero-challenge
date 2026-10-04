import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { ApiError, get, post } from './api'
import { useAuth } from './auth'
import { ErrorNote, StatusTag, formatDate, labelClass, tdClass, thClass } from './components'
import { STATUSES, type DatasetRequest, type Page, type Status } from './types'

export function RequestsPage() {
  const { user } = useAuth()
  const isClient = user!.role === 'client'
  const [rows, setRows] = useState<DatasetRequest[] | null>(null)
  const [status, setStatus] = useState<Status | ''>('')
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      const page = await get<Page<DatasetRequest>>(`/api/requests${status ? `?status=${status}` : ''}`)
      setRows(page.results)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to load requests')
    }
  }, [status])

  useEffect(() => {
    load()
  }, [load])

  return (
    <>
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <p className="section-label">{isClient ? 'My requests' : 'All requests'}</p>
        <label className={labelClass}>
          Status
          <select className="input w-44" value={status} onChange={(e) => setStatus(e.target.value as Status | '')}>
            <option value="">any</option>
            {STATUSES.map((s) => <option key={s} value={s}>{s.replace('_', ' ')}</option>)}
          </select>
        </label>
      </div>

      {isClient && <NewRequestForm onCreated={load} />}
      <ErrorNote message={error} />

      {rows === null ? (
        <p className="text-muted">Loading…</p>
      ) : rows.length === 0 ? (
        <p className="text-muted">{isClient ? 'You have no requests yet. Create one above.' : 'No requests match.'}</p>
      ) : (
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="border-b border-ink">
              <th className={thClass}>#</th>
              {!isClient && <th className={thClass}>Client</th>}
              <th className={thClass}>Task</th>
              <th className={`${thClass} text-right`}>Episodes</th>
              <th className={thClass}>Deadline</th>
              <th className={thClass}>Status</th>
              <th className={thClass}>Created</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className="border-b border-rule">
                <td className={tdClass}><Link className="font-medium text-ink-bright hover:underline" to={`/requests/${r.id}`}>#{r.id}</Link></td>
                {!isClient && <td className={tdClass}>{r.client.organisation || r.client.name}</td>}
                <td className={tdClass}>{r.task_name}</td>
                <td className={`${tdClass} text-right`}>{r.assigned_count} / {r.episodes_requested}</td>
                <td className={tdClass}>{r.deadline}</td>
                <td className={tdClass}><StatusTag status={r.status} /></td>
                <td className={`${tdClass} text-muted`}>{formatDate(r.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  )
}

function NewRequestForm({ onCreated }: { onCreated: () => void }) {
  const [open, setOpen] = useState(false)
  const [taskName, setTaskName] = useState('')
  const [count, setCount] = useState(10)
  const [deadline, setDeadline] = useState('')
  const [notes, setNotes] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await post('/api/requests', { task_name: taskName, episodes_requested: count, deadline, notes })
      setTaskName(''); setCount(10); setDeadline(''); setNotes(''); setOpen(false)
      onCreated()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Failed to create request')
    } finally {
      setBusy(false)
    }
  }

  if (!open) return <p className="mb-6"><button className="btn-primary" onClick={() => setOpen(true)}>+ New request</button></p>

  return (
    <form onSubmit={submit} className="card mb-8 flex flex-col gap-4">
      <p className="section-label">New request</p>
      <div className="grid gap-4 sm:grid-cols-3">
        <label className={labelClass}>Task name<input className="input" value={taskName} onChange={(e) => setTaskName(e.target.value)} placeholder="pick cup" required /></label>
        <label className={labelClass}>Episodes requested<input className="input" type="number" min={1} value={count} onChange={(e) => setCount(Number(e.target.value))} required /></label>
        <label className={labelClass}>Deadline<input className="input" type="date" value={deadline} onChange={(e) => setDeadline(e.target.value)} required /></label>
      </div>
      <label className={labelClass}>Notes<textarea className="input" rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} /></label>
      <ErrorNote message={error} />
      <div className="flex gap-3">
        <button type="submit" className="btn-primary" disabled={busy}>{busy ? 'Submitting…' : 'Submit request'}</button>
        <button type="button" className="btn-link" onClick={() => setOpen(false)}>Cancel</button>
      </div>
    </form>
  )
}
