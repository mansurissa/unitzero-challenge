import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ApiError, get } from './api'
import { QualityTag } from './components'
import { QUALITIES, type Episode, type Page, type Quality } from './types'

const PAGE_SIZE = 50

export function EpisodesPage() {
  const [taskNames, setTaskNames] = useState<string[]>([])
  const [taskName, setTaskName] = useState('')
  const [quality, setQuality] = useState<Quality | ''>('')
  const [robotId, setRobotId] = useState('')
  const [page, setPage] = useState(1)
  const [data, setData] = useState<Page<Episode> | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    get<string[]>('/api/episodes/task-names').then(setTaskNames).catch(() => {})
  }, [])

  // Any filter change goes back to page 1.
  useEffect(() => {
    setPage(1)
  }, [taskName, quality, robotId])

  useEffect(() => {
    const params = new URLSearchParams({ page: String(page) })
    if (taskName) params.set('task_name', taskName)
    if (quality) params.set('quality', quality)
    if (robotId.trim()) params.set('robot_id', robotId.trim())
    setError(null)
    get<Page<Episode>>(`/api/episodes?${params}`)
      .then(setData)
      .catch((err) => setError(err instanceof ApiError ? err.message : 'Failed to load episodes'))
  }, [taskName, quality, robotId, page])

  const lastPage = data ? Math.max(1, Math.ceil(data.count / PAGE_SIZE)) : 1

  return (
    <>
      <p className="section-label mb-4">Episodes</p>

      <div className="mb-6 flex flex-wrap items-end gap-4">
        <label className="flex flex-col gap-1 text-xs uppercase tracking-wider text-muted">
          Task
          <select className="input w-56" value={taskName} onChange={(e) => setTaskName(e.target.value)}>
            <option value="">any</option>
            {taskNames.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-xs uppercase tracking-wider text-muted">
          Quality
          <select className="input w-40" value={quality} onChange={(e) => setQuality(e.target.value as Quality | '')}>
            <option value="">any</option>
            {QUALITIES.map((q) => <option key={q} value={q}>{q}</option>)}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-xs uppercase tracking-wider text-muted">
          Robot
          <input className="input w-40" placeholder="arm-01" value={robotId} onChange={(e) => setRobotId(e.target.value)} />
        </label>
        <span className="pb-2 text-sm text-muted">{data ? `${data.count} episode${data.count === 1 ? '' : 's'}` : '…'}</span>
      </div>

      {error && <p className="mb-4 border border-ink bg-paper px-3 py-2 text-sm">{error}</p>}

      {data && data.results.length === 0 ? (
        <p className="text-muted">No episodes match.</p>
      ) : (
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="border-b border-ink text-left text-xs uppercase tracking-wider text-muted">
              <th className="py-2 pr-4 font-medium">Episode</th>
              <th className="py-2 pr-4 font-medium">Robot</th>
              <th className="py-2 pr-4 font-medium">Task</th>
              <th className="py-2 pr-4 font-medium">Recorded</th>
              <th className="py-2 pr-4 text-right font-medium">Duration</th>
              <th className="py-2 pr-4 font-medium">Operator</th>
              <th className="py-2 pr-4 font-medium">Quality</th>
              <th className="py-2 font-medium">Assigned to</th>
            </tr>
          </thead>
          <tbody>
            {data?.results.map((e) => (
              <tr key={e.id} className="border-b border-rule">
                <td className="py-2 pr-4 font-medium text-ink-bright">{e.episode_id}</td>
                <td className="py-2 pr-4">{e.robot_id}</td>
                <td className="py-2 pr-4">{e.task_name}</td>
                <td className="py-2 pr-4 whitespace-nowrap">{new Date(e.recorded_at).toLocaleString()}</td>
                <td className="py-2 pr-4 text-right">{e.duration_seconds}s</td>
                <td className="py-2 pr-4">{e.operator_name || <span className="text-muted">—</span>}</td>
                <td className="py-2 pr-4"><QualityTag quality={e.quality} /></td>
                <td className="py-2">{e.assigned_request_id ? <Link className="btn-link" to={`/requests/${e.assigned_request_id}`}>#{e.assigned_request_id}</Link> : <span className="text-muted">—</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {data && data.count > PAGE_SIZE && (
        <div className="mt-4 flex items-center gap-4 text-sm">
          <button className="btn-link disabled:no-underline disabled:opacity-40" disabled={!data.previous} onClick={() => setPage((p) => p - 1)}>← previous</button>
          <span className="text-muted">page {page} of {lastPage}</span>
          <button className="btn-link disabled:no-underline disabled:opacity-40" disabled={!data.next} onClick={() => setPage((p) => p + 1)}>next →</button>
        </div>
      )}
    </>
  )
}
