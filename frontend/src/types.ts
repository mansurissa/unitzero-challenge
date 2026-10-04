export type Role = 'client' | 'operator' | 'admin'

export interface User {
  id: number
  email: string
  name: string
  role: Role
  organisation: string
  is_active: boolean
}

export type Quality = 'good' | 'usable' | 'bad'
export const QUALITIES: Quality[] = ['good', 'usable', 'bad']

export interface Episode {
  id: number
  episode_id: string
  robot_id: string
  task_name: string
  recorded_at: string
  duration_seconds: number
  operator_name: string
  quality: Quality
  /** Id of the request this episode is currently assigned to, or null. */
  assigned_request_id: number | null
}

export interface Assignment {
  id: number
  episode: Episode
  assigned_by: string | null
  assigned_at: string
}

export type Status = 'submitted' | 'in_progress' | 'delivered' | 'accepted' | 'rejected'
export const STATUSES: Status[] = ['submitted', 'in_progress', 'delivered', 'accepted', 'rejected']

export interface DatasetRequest {
  id: number
  client: { id: number; name: string; email: string; organisation: string }
  task_name: string
  episodes_requested: number
  deadline: string
  notes: string
  status: Status
  assigned_count: number
  /** Statuses the current user may move this request to right now (the server enforces this too). */
  allowed_transitions: Status[]
  submitted_at: string
  delivered_at: string | null
  created_at: string
  updated_at: string
}

export interface StatusEvent {
  id: number
  from_status: Status | ''
  to_status: Status
  actor: string | null
  note: string
  created_at: string
}

/** DRF page-number pagination envelope. */
export interface Page<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}
