import { useEffect, useRef, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { ChevronDown, User as UserIcon } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useUser } from '@/lib/user-context'
import { BUILD_STAMP } from '@/lib/config'

const NAV_ITEMS = [
  { to: '/', label: 'Home' },
  { to: '/help', label: 'Help Center' },
  { to: '/support', label: 'Support' },
]

interface HeaderProps {
  onTinted: boolean
}

export default function Header({ onTinted }: HeaderProps) {
  const { pathname } = useLocation()
  const user = useUser()

  return (
    <header
      className={cn(
        'sticky top-0 z-50 bg-transparent backdrop-blur-md',
        onTinted ? 'text-white' : 'text-foreground',
      )}
    >
      <div className="container flex items-center justify-between h-16">
        {/* Brand wordmark */}
        <Link to="/" className="group flex items-end gap-2.5">
          <span
            className={cn(
              'font-nav text-[22px] tracking-[-0.04em] transition-opacity group-hover:opacity-80 leading-none',
              onTinted ? 'text-white' : 'text-primary',
            )}
          >
            <span className="font-semibold">Prime</span>
            <span className="font-light">Xarc</span>
          </span>
        </Link>

        {/* Right cluster: nav + user menu */}
        <div className="flex items-center gap-7">
          <nav className="flex items-center gap-7">
            {NAV_ITEMS.map((item) => {
              const active =
                item.to === '/'
                  ? pathname === '/'
                  : pathname.startsWith(item.to)
              return (
                <Link
                  key={item.to}
                  to={item.to}
                  className={cn(
                    'font-nav text-[13px] font-medium transition-opacity',
                    onTinted
                      ? active
                        ? 'text-white'
                        : 'text-white/65 hover:text-white'
                      : active
                        ? 'text-primary'
                        : 'text-muted-foreground hover:text-primary',
                  )}
                >
                  {item.label}
                </Link>
              )
            })}
          </nav>
          <UserMenu onTinted={onTinted} user={user} />
        </div>
      </div>
    </header>
  )
}

// ─── User menu ─────────────────────────────────────────────────────────────

interface UserMenuProps {
  onTinted: boolean
  user: { name: string; email: string; initials: string }
}

function UserMenu({ onTinted, user }: UserMenuProps) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', onClick)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onClick)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
        className={cn(
          'flex items-center gap-2.5 rounded-full pl-1 pr-2.5 py-1 transition-colors',
          onTinted
            ? 'hover:bg-white/10 text-white'
            : 'hover:bg-muted text-foreground',
        )}
      >
        <span
          className={cn(
            'inline-flex items-center justify-center h-8 w-8 rounded-full font-nav text-[12px] font-semibold',
            onTinted
              ? 'bg-white text-primary'
              : 'bg-primary text-primary-foreground',
          )}
        >
          {user.initials}
        </span>
        <span className="font-nav text-[13px] font-medium hidden sm:inline">
          {user.name.split(' ')[0]}
        </span>
        <ChevronDown
          className={cn(
            'h-3.5 w-3.5 transition-transform hidden sm:block',
            open && 'rotate-180',
          )}
        />
      </button>

      {open && (
        <div
          role="menu"
          className="absolute right-0 mt-2 w-64 rounded-xl border shadow-xl overflow-hidden animate-fade-in z-50 bg-card border-border text-card-foreground"
        >
          <div className="px-4 py-3 border-b border-border flex items-center gap-3">
            <span className="inline-flex items-center justify-center h-10 w-10 rounded-full font-nav text-[13px] font-semibold bg-primary text-primary-foreground flex-shrink-0">
              {user.initials}
            </span>
            <div className="min-w-0">
              <p className="font-semibold text-foreground truncate">{user.name}</p>
              <p className="font-nav text-[12px] text-muted-foreground truncate">
                {user.email}
              </p>
              <p className="font-nav text-[11px] font-medium text-primary mt-1.5 uppercase tracking-wider">
                Lilly Employee
              </p>
            </div>
          </div>
          <MenuItem
            icon={UserIcon}
            label="Account"
            onClick={() => { setOpen(false); window.location.href = '/account' }}
          />
        </div>
      )}
    </div>
  )
}

interface MenuItemProps {
  icon: React.ComponentType<{ className?: string }>
  label: string
  onClick: () => void
}

function MenuItem({ icon: Icon, label, onClick }: MenuItemProps) {
  return (
    <button
      type="button"
      role="menuitem"
      onClick={onClick}
      className="w-full px-4 py-2.5 flex items-center gap-3 text-left text-sm hover:bg-muted/60 transition-colors"
    >
      <Icon className="h-4 w-4 text-muted-foreground" />
      <span className="text-foreground">{label}</span>
    </button>
  )
}

// ─── Footer ────────────────────────────────────────────────────────────────

interface FooterProps {
  onTinted: boolean
}

export function Footer({ onTinted }: FooterProps) {
  return (
    <footer className="relative z-10 mt-auto bg-transparent">
      <div
        className={cn(
          'container py-6 flex flex-wrap items-center justify-between gap-3',
          onTinted ? 'text-white/60' : 'text-muted-foreground',
        )}
      >
        <span className="font-nav text-[12px] flex flex-wrap items-center gap-2">
          <span className="inline-flex items-end gap-1.5 leading-none">
            <span><span className="font-semibold">Prime</span><span className="font-light">Xarc</span></span>
          </span>
          <span className="leading-none">· {BUILD_STAMP} · Internal Lilly Tool</span>
        </span>
        <div className="flex items-center gap-6 font-nav text-[12px]">
          <Link to="/support" className="hover:underline underline-offset-4">
            Report an Issue
          </Link>
        </div>
      </div>
    </footer>
  )
}
