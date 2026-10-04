export type Role = 'client' | 'operator' | 'admin'

export interface User {
  id: number
  email: string
  name: string
  role: Role
  organisation: string
  is_active: boolean
}
