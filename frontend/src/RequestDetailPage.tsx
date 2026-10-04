import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ApiError, del, get, post } from './api'
import { useAuth } from './auth'
import { ErrorNote, QualityTag, StatusTag, formatDateTime, labelClass, tdClass, thClass } from './components'
import type { Assignment, DatasetRequest, Episode, Page, Quality, Status, StatusEvent } from './types'

const TRANSITION_LABELS: Record<Status, string> = {
  submitted: 'Submit',
  in_progress: 'Start work',
  delivered: 'Mark delivered',
  accepted: 'Accept delivery',
  rejected: 'Reject delivery',
}

export function RequestDetailPage() {
  const { id } = useParams()
  const { user } = useAuth()
  const isOps = user!.role !== 'client'

  const [request, setRequest] = useState<DatasetRequest | null>(null)
  const [assignments, setAssignments] = useState<Assignment[]>([])
  const [history, setHistory] = useState<StatusEvent[]>([])
  const [error, setError] = useState<string | null>(null)
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    try {
      const [r, a, h] = await Promise.all([
        get<DatasetRequest>(`/api/requests/${id}`),
        get<Assignment[]>(`/api/requests/${id}/assignments`),
        get<StatusEvent[]>(`/api/requests/${id}/history`),
      ])
      setRequest(r); setAssignments(a); setHistory(h)
    } catch (err) {
      setError(err instanceof ApiError && err.status === 404 ? 'Request not found.' : err instanceof ApiError ? err.message : 'Failed to load')
    }
  }, [id])

  useEffect(() => {
    load()
  }, [load])

  /** Run an API call, then refresh everything; any rule violation from the server shows as the error note. */
  async function act(fn: () => Promise<unknown>) {
    setBusy(true)
    setError(null)
    try {
      await fn()
      await load()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Action failed')
    } finally {
      setBusy(false)
    }
  }

  if (!request) return error ? <ErrorNote message={error} /> : <p className="text-muted">Loading…</p>

  const canAssign = isOps && request.status === 'in_progress'

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
            <button key={to} className="btn-primary" disabled={busy}
              onClick={() => act(() => post(`/api/requests/${id}/transition`, { status: to, note }).then(() => setNote('')))}>
              {TRANSITION_LABELS[to]}
            </button>
          ))}
        </div>
      )}
      <ErrorNote message={error} />

      <p className="section-label mb-3 mt-10">Assigned episodes ({assignments.length})</p>
      {assignments.length === 0 ? (
        <p className="text-muted">No episodes assigned yet.</p>
      ) : (
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="border-b border-ink">
              <th className={thClass}>Episode</th><th className={thClass}>Robot</th><th className={thClass}>Task</th>
              <th className={thClass}>Recorded</th><th className={`${thClass} text-right`}>Duration</th><th className={thClass}>Quality</th>
              <th className={thClass}>Assigned by</th>{canAssign && <th className={thClass} />}
            </tr>
          </thead>
          <tbody>
            {assignments.map((a) => (
              <tr key={a.id} className="border-b border-rule">
                <td className={`${tdClass} font-medium text-ink-bright`}>{a.episode.episode_id}</td>
                <td className={tdClass}>{a.episode.robot_id}</td>
                <td className={tdClass}>{a.episode.task_name}</td>
                <td className={`${tdClass} whitespace-nowrap`}>{formatDateTime(a.episode.recorded_at)}</td>
                <td className={`${tdClass} text-right`}>{a.episode.duration_seconds}s</td>
                <td className={tdClass}><QualityTag quality={a.episode.quality} /></td>
                <td className={`${tdClass} text-muted`}>{a.assigned_by}</td>
                {canAssign && (
                  <td className={tdClass}>
                    <button className="btn-link" disabled={busy} onClick={() => act(() => del(`/api/requests/${id}/assignments/${a.episode.episode_id}`))}>remove</button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {canAssign && (
        <EpisodePicker request={request} busy={busy} onAssign={(code) => act(() => post(`/api/requests/${id}/assignments`, { episode_id: code }))} />
      )}
      {isOps && !canAssign && (
        <p className="mt-3 text-sm text-muted">Episodes can be assigned or removed while the request is <em>in progress</em>.</p>
      )}

      <p className="section-label mb-3 mt-10">History</p>
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b border-ink">
            <th className={thClass}>When</th><th className={thClass}>Change</th><th className={thClass}>By</th><th className={thClass}>Note</th>
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

/** Operator's search box for episodes to attach. Defaults to the request's task and to unassigned episodes only. */
function EpisodePicker({ request, busy, onAssign }: { request: DatasetRequest; busy: boolean; onAssign: (code: string) => void }) {
  const [taskName, setTaskName] = useState(request.task_name)
  const [quality, setQuality] = useState<Quality | ''>('')
  const [onlyAvailable, setOnlyAvailable] = useState(true)
  const [taskNames, setTaskNames] = useState<string[]>([])
  const [page, setPage] = useState<Page<Episode> | null>(null)

  useEffect(() => {
    get<string[]>('/api/episodes/task-names').then(setTaskNames).catch(() => {})
  }, [])

  useEffect(() => {
    const params = new URLSearchParams()
    if (taskName) params.set('task_name', taskName)
    if (quality) params.set('quality', quality)
    if (onlyAvailable) params.set('available', '1')
    get<Page<Episode>>(`/api/episodes?${params}`).then(setPage).catch(() => {})
  }, [taskName, quality, onlyAvailable, request.assigned_count])  // refetch after each assign/unassign

  return (
    <section className="card mt-6">
      <p className="section-label mb-4">Find episodes to assign</p>
      <div className="mb-4 flex flex-wrap items-end gap-4">
        <label className={labelClass}>Task
          <select className="input w-56" value={taskName} onChange={(e) => setTaskName(e.target.value)}>
            <option value="">any</option>
            {taskNames.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        </label>
        <label className={labelClass}>Quality
          <select className="input w-44" value={quality} onChange={(e) => setQuality(e.target.value as Quality | '')}>
            <option value="">good or usable</option>
            <option value="good">good</option>
            <option value="usable">usable</option>
          </select>
        </label>
        <label className="flex items-center gap-2 pb-2 text-sm text-muted">
          <input type="checkbox" checked={onlyAvailable} onChange={(e) => setOnlyAvailable(e.target.checked)} /> unassigned only
        </label>
        <span className="pb-2 text-sm text-muted">
          {page ? `${page.count} match${page.count === 1 ? '' : 'es'}${page.count > page.results.length ? `, showing ${page.results.length}` : ''}` : '…'}
        </span>
      </div>
      {page && page.results.length === 0 ? (
        <p className="text-muted">No episodes match.</p>
      ) : (
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="border-b border-ink">
              <th className={thClass}>Episode</th><th className={thClass}>Robot</th><th className={thClass}>Task</th>
              <th className={thClass}>Recorded</th><th className={`${thClass} text-right`}>Duration</th><th className={thClass}>Quality</th>
              <th className={thClass}>Assigned to</th><th className={thClass} />
            </tr>
          </thead>
          <tbody>
            {page?.results.map((e) => {
              const assignable = e.quality !== 'bad' && e.assigned_request_id === null
              return (
                <tr key={e.id} className="border-b border-rule">
                  <td className={`${tdClass} font-medium text-ink-bright`}>{e.episode_id}</td>
                  <td className={tdClass}>{e.robot_id}</td>
                  <td className={tdClass}>{e.task_name}</td>
                  <td className={`${tdClass} whitespace-nowrap`}>{formatDateTime(e.recorded_at)}</td>
                  <td className={`${tdClass} text-right`}>{e.duration_seconds}s</td>
                  <td className={tdClass}><QualityTag quality={e.quality} /></td>
                  <td className={tdClass}>{e.assigned_request_id ? <Link className="btn-link" to={`/requests/${e.assigned_request_id}`}>#{e.assigned_request_id}</Link> : <span className="text-muted">—</span>}</td>
                  <td className={tdClass}><button className="btn-primary px-2 py-1 text-xs" disabled={!assignable || busy} onClick={() => onAssign(e.episode_id)}>Assign</button></td>
                </tr>
              )
            })}
          </tbody>
        </table>
      )}
    </section>
  )
}
