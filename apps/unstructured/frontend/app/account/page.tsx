import { useEffect, useState } from 'react'
import { useDefaultUser } from '@/lib/default-user-context'
import { apiClient } from '@/lib/api-client'
import AppLayout from '@/components/layout/AppLayout'
import { User, Building2, Shield, Loader2 } from 'lucide-react'

interface UserProfile {
  id: string
  email: string
  name: string
  roles: string[]
  picture_url?: string
}

interface Workspace {
  id: string
  name: string
  role: string
  created_at: string
}

export default function AccountPage() {
  const { user: bouncerUser } = useDefaultUser()
  const [profile, setProfile] = useState<UserProfile | null>(null)
  const [workspaces, setWorkspaces] = useState<Workspace[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function load() {
      setLoading(true)
      const [profileRes, workspacesRes] = await Promise.all([
        apiClient.get('/api/v1/users/me'),
        apiClient.getWorkspaces(),
      ])
      if (profileRes.data) setProfile(profileRes.data)
      if (workspacesRes.data) setWorkspaces(Array.isArray(workspacesRes.data) ? workspacesRes.data : workspacesRes.data.workspaces ?? [])
      setLoading(false)
    }
    load()
  }, [])

  const displayName = profile?.name || bouncerUser?.displayName || bouncerUser?.samAccountName || 'Unknown'
  const displayEmail = profile?.email || bouncerUser?.email || '—'
  const initials = displayName.charAt(0).toUpperCase()

  return (
    <AppLayout>
      <div className="max-w-4xl mx-auto py-8 px-4">
        <h1 className="text-2xl font-bold text-gray-900 mb-8">Account</h1>

        {loading ? (
          <div className="flex items-center justify-center py-16">
            <Loader2 className="h-8 w-8 animate-spin text-[#C8102E]" />
          </div>
        ) : (
          <div className="space-y-8">
            {/* Profile card */}
            <div className="bg-white rounded-lg border border-gray-200 p-6">
              <div className="flex items-center gap-3 mb-6">
                <User className="h-5 w-5 text-[#C8102E]" />
                <h2 className="text-lg font-semibold text-gray-900">Profile</h2>
              </div>
              <div className="flex items-center gap-5 mb-6">
                {profile?.picture_url ? (
                  <img src={profile.picture_url} alt="Profile" className="w-16 h-16 rounded-full object-cover" />
                ) : (
                  <div className="w-16 h-16 bg-[#F5E6E8] rounded-full flex items-center justify-center">
                    <span className="text-[#C8102E] text-xl font-semibold">{initials}</span>
                  </div>
                )}
                <div>
                  <p className="text-lg font-semibold text-gray-900">{displayName}</p>
                  <p className="text-sm text-gray-500">{displayEmail}</p>
                </div>
              </div>
              <div className="grid sm:grid-cols-2 gap-6">
                <div>
                  <label className="block text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">Department</label>
                  <p className="text-gray-900">{bouncerUser?.department || '—'}</p>
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">Username</label>
                  <p className="text-gray-900">{bouncerUser?.samAccountName || bouncerUser?.upn || '—'}</p>
                </div>
                <div className="sm:col-span-2">
                  <label className="block text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">Roles</label>
                  <div className="flex flex-wrap gap-2">
                    {(profile?.roles?.length ? profile.roles : ['viewer']).map((role) => (
                      <span
                        key={role}
                        className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-[#F5E6E8] text-[#C8102E]"
                      >
                        <Shield className="h-3 w-3" />
                        {role}
                      </span>
                    ))}
                  </div>
                </div>
                {bouncerUser?.groups?.length ? (
                  <div className="sm:col-span-2">
                    <label className="block text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">Groups</label>
                    <div className="flex flex-wrap gap-2">
                      {bouncerUser.groups.map((g) => (
                        <span key={g} className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-700">
                          {g}
                        </span>
                      ))}
                    </div>
                  </div>
                ) : null}
              </div>
            </div>

            {/* Workspaces card */}
            <div className="bg-white rounded-lg border border-gray-200 p-6">
              <div className="flex items-center gap-3 mb-6">
                <Building2 className="h-5 w-5 text-[#C8102E]" />
                <h2 className="text-lg font-semibold text-gray-900">Workspaces</h2>
              </div>
              {workspaces.length === 0 ? (
                <p className="text-gray-500 text-sm">No workspaces found.</p>
              ) : (
                <div className="space-y-3">
                  {workspaces.map((ws) => (
                    <div key={ws.id} className="flex items-center justify-between p-4 border border-gray-200 rounded-lg">
                      <div>
                        <p className="font-medium text-gray-900">{ws.name}</p>
                        <p className="text-xs text-gray-500 mt-0.5">
                          Created {new Date(ws.created_at).toLocaleDateString()}
                        </p>
                      </div>
                      <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
                        {ws.role}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </AppLayout>
  )
}
