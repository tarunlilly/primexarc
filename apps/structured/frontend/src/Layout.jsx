import { useEffect, useRef, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useMsal } from '@azure/msal-react';
import { ChevronDown, Clock, LogOut, User as UserIcon } from 'lucide-react';
import { cn } from '@/lib/utils';
import { BUILD_STAMP } from '@/lib/build-stamp';
import { getCurrentUser, getUserPhoto, fetchMe, getMeCache } from '@/lib/user';

// Layout - persistent header + footer. The `variant` prop controls the
// surface mode via CSS class (red-mode / crimson-mode / [none = white]).
//
// Brand mark is "ARC Evaluator" with the cradle arc glyph leading the wordmark.
// Same font stack throughout (Apple system stack).

const BASE_NAV_ITEMS = [
  { to: '/', label: 'Home' },
  { to: '/assess', label: 'Assess' },
  { to: '/help', label: 'Help Center' },
  { to: '/support', label: 'Support' },
];

export default function Layout({ variant = 'red', children }) {
  const modeClass =
    variant === 'crimson' ? 'crimson-mode' :
    variant === 'red' ? 'red-mode' : '';
  const onTinted = variant === 'red' || variant === 'crimson';

  return (
    <div
      className={cn(
        'relative isolate min-h-screen flex flex-col overflow-x-hidden bg-background text-foreground transition-colors duration-300',
        modeClass,
      )}
    >
      <EdgeVignettes variant={variant} />
      <Header onTinted={onTinted} />
      <main className="relative z-10 flex-1 flex flex-col">{children}</main>
      <Footer onTinted={onTinted} />
    </div>
  );
}

function EdgeVignettes({ variant }) {
  const tintedTop =
    variant === 'crimson'
      ? 'from-[hsl(var(--lilly-dred)/0.72)] via-[hsl(var(--lilly-dred)/0.28)] to-transparent'
      : 'from-[hsl(var(--lilly-dred)/0.64)] via-[hsl(var(--lilly-dred)/0.24)] to-transparent';
  const tintedBottom =
    variant === 'crimson'
      ? 'from-[hsl(var(--lilly-dred)/0.76)] via-[hsl(var(--lilly-dred)/0.3)] to-transparent'
      : 'from-[hsl(var(--lilly-dred)/0.68)] via-[hsl(var(--lilly-dred)/0.26)] to-transparent';
  const neutralTop = 'from-black/12 via-black/5 to-transparent';
  const neutralBottom = 'from-black/14 via-black/6 to-transparent';

  return (
    <>
      <div
        aria-hidden="true"
        className={cn(
          'pointer-events-none absolute inset-x-0 top-0 z-0 h-36 sm:h-44 bg-gradient-to-b',
          variant === 'red' || variant === 'crimson' ? tintedTop : neutralTop,
        )}
      />
      <div
        aria-hidden="true"
        className={cn(
          'pointer-events-none absolute inset-x-0 bottom-0 z-0 h-40 sm:h-48 bg-gradient-to-t',
          variant === 'red' || variant === 'crimson' ? tintedBottom : neutralBottom,
        )}
      />
    </>
  );
}

function CradleArc({ className = '' }) {
  return (
    <svg
      viewBox="8 16 48 28"
      aria-hidden="true"
      className={cn('shrink-0', className)}
      fill="none"
    >
      <path
        d="M12 40 A20 20 0 0 1 52 40"
        stroke="currentColor"
        strokeWidth="5.5"
        strokeLinecap="round"
      />
    </svg>
  );
}

// ─── Header ────────────────────────────────────────────────────────────────
function Header({ onTinted }) {
  const { pathname } = useLocation();
  const [meReady, setMeReady] = useState(false);

  useEffect(() => {
    fetchMe().then(() => setMeReady(true));
  }, []);

  const isSuperuser = getMeCache()?.is_superuser ?? false;
  const NAV_ITEMS = isSuperuser
    ? [...BASE_NAV_ITEMS, { to: '/console', label: 'Console' }]
    : BASE_NAV_ITEMS;

  return (
    <header
      className={cn(
        'sticky top-0 z-50 bg-transparent backdrop-blur-md',
        onTinted ? 'text-white' : 'text-foreground',
      )}
    >
      <div className="container flex items-center justify-between h-16">
        {/* Brand wordmark: cradle arc + ARC Evaluator */}
        <Link to="/" className="group flex items-end gap-2.5">
          <CradleArc
            className={cn(
              'h-6 w-8 transition-opacity group-hover:opacity-80',
              onTinted ? 'text-white' : 'text-primary',
            )}
          />
          <span
            className={cn(
              'font-nav text-[22px] tracking-[-0.04em] transition-opacity group-hover:opacity-80 leading-none',
              onTinted ? 'text-white' : 'text-primary',
            )}
          >
            <span className="font-normal italic">ARC</span>
            <span className="font-light ml-1">Evaluator</span>
          </span>
        </Link>

        {/* Right cluster: nav + user menu */}
        <div className="flex items-center gap-7">
          <nav className="flex items-center gap-7">
            {NAV_ITEMS.map((item) => {
              const active =
                item.to === '/'
                  ? pathname === '/'
                  : pathname.startsWith(item.to);
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
              );
            })}
          </nav>
          <UserMenu onTinted={onTinted} />
        </div>
      </div>
    </header>
  );
}

// ─── User menu ─────────────────────────────────────────────────────────────
// Compact avatar + name + chevron. Click reveals dropdown with profile link
// and sign-out.
function UserMenu({ onTinted }) {
  const [open, setOpen] = useState(false);
  const [photoUrl, setPhotoUrl] = useState(null);
  const ref = useRef(null);
  const navigate = useNavigate();
  const { instance } = useMsal();
  const user = getCurrentUser();

  useEffect(() => {
    getUserPhoto(instance).then(url => setPhotoUrl(url));
  }, []);

  useEffect(() => {
    return () => { if (photoUrl) URL.revokeObjectURL(photoUrl); };
  }, [photoUrl]);

  // Close on outside click / Escape
  useEffect(() => {
    if (!open) return;
    const onClick = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    };
    const onKey = (e) => { if (e.key === 'Escape') setOpen(false); };
    document.addEventListener('mousedown', onClick);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onClick);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  if (!user) return null;

  const handleSignOut = () => {
    setOpen(false);
    instance.logoutRedirect({ postLogoutRedirectUri: '/' });
  };

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
        {photoUrl ? (
          <img
            src={photoUrl}
            alt={user.initials}
            className="h-8 w-8 rounded-full object-cover"
          />
        ) : (
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
        )}
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
          className={cn(
            'absolute right-0 mt-2 w-64 rounded-xl border shadow-xl overflow-hidden animate-fade-in z-50',
            // Force light styling regardless of mode for readable contrast
            'bg-card border-border text-card-foreground',
          )}
        >
          <div className="px-4 py-3 border-b border-border flex items-center gap-3">
            {photoUrl ? (
              <img
                src={photoUrl}
                alt={user.initials}
                className="h-10 w-10 rounded-full object-cover flex-shrink-0"
              />
            ) : (
              <span className="inline-flex items-center justify-center h-10 w-10 rounded-full font-nav text-[13px] font-semibold bg-primary text-primary-foreground flex-shrink-0">
                {user.initials}
              </span>
            )}
            <div className="min-w-0">
              <p className="font-semibold text-foreground truncate">{user.name}</p>
              <p className="font-nav text-[12px] text-muted-foreground truncate">
                {user.email}
              </p>
              <p className="font-nav text-[11px] font-medium text-primary mt-1.5 uppercase tracking-wider">
                {user.role ?? 'Lilly Employee'}
              </p>
            </div>
          </div>
          <MenuItem
            icon={Clock}
            label="History"
            onClick={() => { setOpen(false); navigate('/history'); }}
          />
          <MenuItem
            icon={UserIcon}
            label="Account"
            onClick={() => { setOpen(false); navigate('/account'); }}
          />
          <div className="border-t border-border" />
          <MenuItem
            icon={LogOut}
            label="Sign out"
            onClick={handleSignOut}
          />
        </div>
      )}
    </div>
  );
}

function MenuItem({ icon: Icon, label, onClick }) {
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
  );
}

// ─── Footer ────────────────────────────────────────────────────────────────
function Footer({ onTinted }) {
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
            <CradleArc className="h-3.5 w-6" />
            <span><span className="font-normal">ARC</span><span className="font-light ml-1">Evaluator</span></span>
          </span>
          <span className="leading-none">· {BUILD_STAMP} · Internal Lilly Tool</span>
        </span>
        <div className="flex items-center gap-6 font-nav text-[12px]">
          <Link to="/support" className="hover:underline underline-offset-4">
            Report an Issue
          </Link>
          <a
            href="mailto:ai-readiness@lilly.com"
            className="hover:underline underline-offset-4"
          >
            ai-readiness@lilly.com
          </a>
        </div>
      </div>
    </footer>
  );
}
