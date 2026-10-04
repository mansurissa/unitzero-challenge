import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ApiError, get, post } from './api'
import { ErrorNote, StatusTag, formatDateTime, tdClass, thClass } from './components'
import type { DatasetRequest, Status, StatusEvent } from './types'

const TRANSITION_LABELS: Record<Status, string> = {
  submitted: 'Submit',
  in_progress: 'Start work',
  delivered: 'Mark delivered',
  accepted: 'Accept delivery',
  rejected: 'Reject delivery',
}

export function RequestDetailPage() {
  const { id } = useParams()
  const [request, setRequest] = useState<DatasetRequest | null>(null)
  const [history, setHistory] = useState<StatusEvent[]>([])
  const [error, setError] = useState<string | null>(null)
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    try {
      const [r, h] = await Promise.all([get<DatasetRequest>(`/api/requests/${id}`), get<StatusEvent[]>(`/api/requests/${id}/history`)])
      setRequest(r)
      setHistory(h)
    } catch (err) {
      setError(err instanceof ApiError && err.status === 404 ? 'Request not found.' : err instanceof ApiError ? err.message : 'Failed to load')
    }
  }, [id])

  useEffect(() => {
    load()
  }, [load])

  async function move(to: Status) {
    setBusy(true)
    setError(null)
    try {
      await post(`/api/requests/${id}/transition`, { status: to, note })
      setNote('')
      await load()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Action failed')
    } finally {
      setBusy(false)
    }
  }

  if (!request) return error ? <ErrorNote message={error} /> : <p className="text-muted">Loading…</p>

  return (
    <>
      <p className="mb-4"><Link className="btn-link" to="/">← All requests</Link></p>
      <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
        <h1 className="text-xl font-medium text-ink-bright">Request #{request.id} · {request.task_name}</h1>
        <StatusTag status={request.status} />
      </div>

      <dl className="card mb-6 grid gap-x-8 gap-y-4 text-sm sm:grid-cols-2 lg:grid-cols-3">
        <Field label="Client">{request.client.organisation || request.client.name} <span className="text-muted">({request.client.email})</span></Field>
        <Field label="Episodes">{request.assigned_count} assigned of {request.episodes_requested} requested</Field>
        <Field label="Deadline">{request.deadline}</Field>
        <Field label="Submitted">{formatDateTime(request.submitted_at)}</Field>
        <Field label="Delivered">{formatDateTime(request.delivered_at)}</Field>
        {request.notes && <Field label="Notes">{request.notes}</Field>}
      </dl>

      {request.allowed_transitions.length > 0 && (
        <div className="card mb-6 flex flex-wrap items-center gap-3">
          <input className="input flex-1 min-w-48" placeholder="Note (optional)" value={note} onChange={(e) => setNote(e.target.value)} />
          {request.allowed_transitions.map((to) => (
            <button key={to} className="btn-primary" disabled={busy} onClick={() => move(to)}>{TRANSITION_LABELS[to]}</button>
          ))}
        </div>
      )}
      <ErrorNote message={error} />

      <p className="section-label mb-3 mt-10">History</p>
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b border-ink">
            <th className={thClass}>When</th>
            <th className={thClass}>Change</th>
            <th className={thClass}>By</th>
            <th className={thClass}>Note</th>
          </tr>
        </thead>
        <tbody>
          {history.map((e) => (
            <tr key={e.id} className="border-b border-rule">
              <td className={`${tdClass} whitespace-nowrap`}>{formatDateTime(e.created_at)}</td>
              <td className={tdClass}>{e.from_status && <><StatusTag status={e.from_status} /> → </>}<StatusTag status={e.to_status} /></td>
              <td className={tdClass}>{e.actor ?? '—'}</td>
              <td className={`${tdClass} text-muted`}>{e.note}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wider text-muted">{label}</dt>
      <dd className="mt-0.5">{children}</dd>
    </div>
  )
}
