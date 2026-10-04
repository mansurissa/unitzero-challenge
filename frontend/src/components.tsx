import type { Quality, Status } from './types'

/** Monochrome, like the rest of the theme: weight and border carry the meaning, not colour. */
export function StatusTag({ status }: { status: Status }) {
  const style =
    status === 'accepted' ? 'border-ink bg-ink text-paper'
    : status === 'rejected' ? 'border-ink text-ink line-through'
    : status === 'delivered' ? 'border-ink text-ink font-medium'
    : status === 'in_progress' ? 'border-ink text-ink border-dashed'
    : 'border-rule text-muted'
  return <span className={`inline-block whitespace-nowrap border px-1.5 text-xs ${style}`}>{status.replace('_', ' ')}</span>
}

export function QualityTag({ quality }: { quality: Quality }) {
  const style = quality === 'good' ? 'border-ink bg-ink text-paper' : quality === 'usable' ? 'border-ink text-ink' : 'border-rule text-muted line-through'
  return <span className={`inline-block border px-1.5 text-xs ${style}`}>{quality}</span>
}

export function ErrorNote({ message }: { message: string | null }) {
  if (!message) return null
  return <p className="my-4 border border-ink bg-paper px-3 py-2 text-sm">{message}</p>
}

export const formatDateTime = (iso: string | null) => (iso ? new Date(iso).toLocaleString() : '—')
export const formatDate = (iso: string | null) => (iso ? new Date(iso).toLocaleDateString() : '—')

export const labelClass = 'flex flex-col gap-1 text-xs uppercase tracking-wider text-muted'
export const thClass = 'py-2 pr-4 text-left text-xs font-medium uppercase tracking-wider text-muted'
export const tdClass = 'py-2 pr-4 align-top'
