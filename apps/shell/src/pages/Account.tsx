import { ExternalLink } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { useUser } from '@/lib/user-context'
import { getStructuredUrl, getUnstructuredUrl } from '@/lib/config'

export default function Account() {
  const user = useUser()

  return (
    <section className="container py-12 animate-card-rise max-w-2xl">
      {/* Profile header */}
      <div className="flex items-center gap-5 mb-10">
        <span className="inline-flex items-center justify-center h-16 w-16 rounded-full font-nav text-xl font-semibold bg-primary text-primary-foreground">
          {user.initials}
        </span>
        <div>
          <h1 className="font-display text-3xl font-light text-primary">{user.name}</h1>
          <p className="text-muted-foreground text-sm">{user.email}</p>
        </div>
      </div>

      <div className="space-y-6">
        {/* User info */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Profile</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <InfoRow label="Email" value={user.email} />
            {user.department && <InfoRow label="Department" value={user.department} />}
            {user.groups && user.groups.length > 0 && (
              <div>
                <p className="text-xs text-muted-foreground uppercase tracking-wider font-bold mb-1">Groups</p>
                <div className="flex flex-wrap gap-1.5">
                  {user.groups.map(g => (
                    <span key={g} className="px-2 py-0.5 rounded-sm bg-muted text-xs font-medium text-muted-foreground">
                      {g}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        {/* App links */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Applications</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <AppLink label="Structured (ARC)" href={getStructuredUrl()} />
            <AppLink label="Unstructured (PrimeData)" href={getUnstructuredUrl()} />
          </CardContent>
        </Card>
      </div>
    </section>
  )
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs text-muted-foreground uppercase tracking-wider font-bold mb-0.5">{label}</p>
      <p className="text-sm text-foreground">{value}</p>
    </div>
  )
}

function AppLink({ label, href }: { label: string; href: string }) {
  return (
    <a
      href={href}
      className="flex items-center justify-between px-3 py-2.5 rounded-lg hover:bg-muted transition-colors group"
    >
      <span className="text-sm font-medium text-foreground">{label}</span>
      <ExternalLink className="h-4 w-4 text-muted-foreground group-hover:text-foreground transition-colors" />
    </a>
  )
}
