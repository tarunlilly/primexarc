
import React, { createContext, useContext, useEffect, useState, ReactNode } from 'react'
import { getCachedUser, getResolvedUser, type BouncerUser } from './bouncer-auth'

interface DefaultUser {
  email: string
  name: string
  role: string
}

interface DefaultUserContextType {
  user: DefaultUser
}

const DefaultUserContext = createContext<DefaultUserContextType | undefined>(undefined)

export const DEFAULT_USER: DefaultUser = {
  email: 'anonymous@lilly.com',
  name: 'Anonymous User',
  role: 'viewer',
}

function bouncerUserToDefaultUser(u: BouncerUser): DefaultUser {
  return {
    email: u.email,
    name: u.name,
    role: 'admin', // Role is enforced at the ingress via lilly.com/security_groups ADGroups
  }
}

export function DefaultUserProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<DefaultUser | null>(() => {
    const resolved = getResolvedUser()
    return resolved ? bouncerUserToDefaultUser(resolved) : null
  })

  useEffect(() => {
    getCachedUser().then((bouncerUser) => {
      setUser(bouncerUserToDefaultUser(bouncerUser))
    })
  }, [])

  // Block rendering until the authenticated user is loaded
  if (!user) {
    return null
  }

  return (
    <DefaultUserContext.Provider value={{ user }}>
      {children}
    </DefaultUserContext.Provider>
  )
}

export function useDefaultUser() {
  const context = useContext(DefaultUserContext)
  if (context === undefined) {
    throw new Error('useDefaultUser must be used within a DefaultUserProvider')
  }
  return context
}
