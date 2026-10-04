// Thin fetch wrapper. Auth is a session cookie; writes carry the CSRF token Django put in the csrftoken cookie.

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

function cookie(name: string): string | undefined {
  return document.cookie
    .split('; ')
    .find((row) => row.startsWith(name + '='))
    ?.split('=')[1]
}

function messageFrom(body: unknown, status: number): string {
  if (body && typeof body === 'object') {
    const b = body as Record<string, unknown>
    if (typeof b.detail === 'string') return b.detail
    // DRF field errors look like {"field": ["message"]}
    const parts = Object.entries(b).map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(' ') : String(v)}`)
    if (parts.length) return parts.join('; ')
  }
  return `Request failed (${status})`
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json', ...(init.headers as Record<string, string>) }
  if (init.body) headers['Content-Type'] = 'application/json'
  if (init.method && init.method !== 'GET') headers['X-CSRFToken'] = cookie('csrftoken') ?? ''

  const response = await fetch(path, { credentials: 'same-origin', ...init, headers })
  if (response.status === 204) return undefined as T
  const body = await response.json().catch(() => null)
  if (!response.ok) throw new ApiError(response.status, messageFrom(body, response.status))
  return body as T
}

export const get = <T>(path: string) => api<T>(path)
export const post = <T>(path: string, data?: unknown) =>
  api<T>(path, { method: 'POST', body: data === undefined ? undefined : JSON.stringify(data) })
export const del = <T>(path: string) => api<T>(path, { method: 'DELETE' })
