import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { getCachedUser, getResolvedUser, type BouncerUser } from './bouncer-auth'

export interface ShellUser {
  email: string
  name: string
  initials: string
  department?: string
  groups?: string[]
}

interface UserContextType {
  user: ShellUser
}

const UserContext = createContext<UserContextType | undefined>(undefined)

function deriveInitials(name: string): string {
  const parts = name.trim().split(/\s+/)
  if (parts.length === 0) return '?'
  if (parts.length === 1) return parts[0][0].toUpperCase()
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
}

function bouncerToShellUser(u: BouncerUser): ShellUser {
  return {
    email: u.email,
    name: u.name,
    initials: deriveInitials(u.name),
    department: u.department,
    groups: u.groups,
  }
}

export function UserProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<ShellUser | null>(() => {
    const resolved = getResolvedUser()
    return resolved ? bouncerToShellUser(resolved) : null
  })

  useEffect(() => {
    getCachedUser().then((bouncerUser) => {
      setUser(bouncerToShellUser(bouncerUser))
    })
  }, [])

  // Block rendering until the authenticated user is loaded
  if (!user) {
    return null
  }

  return (
    <UserContext.Provider value={{ user }}>
      {children}
    </UserContext.Provider>
  )
}

export function useUser(): ShellUser {
  const context = useContext(UserContext)
  if (context === undefined) {
    throw new Error('useUser must be used within a UserProvider')
  }
  return context.user
}
