
import { useLocation, Link } from 'react-router-dom'
import { useEffect, useState } from 'react'
import {
  Package,
  Database,
  BarChart3,
  Settings,
  Users,
  Home,
  Menu,
  X,
  ChevronDown,
  CreditCard,
  ChevronLeft,
  Bell,
  Search,
  HelpCircle,
  Play,
  UserCircle
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { ComingSoonBadgeInline } from '@/components/ui/coming-soon-badge-inline'
import { resetTour } from '@/components/Tour'
import { useDefaultUser } from '@/lib/default-user-context'

interface AppLayoutProps {
  children: React.ReactNode
}

const navigation = [
  { name: 'Dashboard', href: '/dashboard', icon: Home },
  { name: 'Products', href: '/app/products', icon: Package },
  { name: 'Data Sources', href: '/app/datasources', icon: Database },
  { name: 'Analytics', href: '/app/analytics', icon: BarChart3 },
  { name: 'Team', href: '/app/team', icon: Users, comingSoon: true },
  { name: 'Help', href: '/help', icon: HelpCircle },
  { name: 'Settings', href: '/app/settings', icon: Settings },
]

export default function AppLayout({ children }: AppLayoutProps) {
  const { user } = useDefaultUser()
  const { pathname } = useLocation()
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [userMenuOpen, setUserMenuOpen] = useState(false)

  // Bouncer enforces authentication at the ingress layer — no redirect needed here.

  // Close user menu when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (userMenuOpen) {
        const target = event.target as Element
        if (!target.closest('.user-menu')) {
          setUserMenuOpen(false)
        }
      }
    }

    if (userMenuOpen) {
      document.addEventListener('click', handleClickOutside)
      return () => document.removeEventListener('click', handleClickOutside)
    }
  }, [userMenuOpen])


  return (
    <div className="h-screen flex flex-col overflow-hidden bg-gradient-to-br from-white via-white to-rose-100">
      <div className="flex-1 flex overflow-hidden">
      {/* Mobile sidebar overlay */}
      {sidebarOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div 
            className="fixed inset-0 bg-gray-600 bg-opacity-75" 
            onClick={() => setSidebarOpen(false)} 
          />
        </div>
      )}

      {/* Enhanced Sidebar */}
      <div className={`fixed inset-y-0 left-0 z-50 bg-white shadow-xl transform transition-all duration-300 ease-in-out lg:translate-x-0 lg:static lg:inset-0 ${
        sidebarOpen ? 'translate-x-0' : '-translate-x-full'
      } ${sidebarCollapsed ? 'w-20 lg:w-20' : 'w-64'}`}>
        {/* Enhanced Sidebar header */}
        <div className="flex items-center justify-between h-16 px-4 border-b-2 border-gray-100 bg-white">
          {!sidebarCollapsed && (
            <div>
              <h1 className="text-xl font-bold text-[#C8102E]">
                PrimeData
              </h1>
              <p className="text-xs text-gray-500 mt-0.5">Making Data AI-Ready</p>
            </div>
          )}
          {sidebarCollapsed && (
            <div className="w-8 h-8 bg-[#C8102E] rounded-lg flex items-center justify-center mx-auto">
              <span className="text-white font-bold text-sm">A</span>
            </div>
          )}
          <div className="flex items-center gap-2">
            <button
              onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
              className="hidden lg:flex p-1.5 rounded-md text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors"
              aria-label={sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            >
              <ChevronLeft className={`h-4 w-4 transition-transform ${sidebarCollapsed ? 'rotate-180' : ''}`} />
            </button>
          <button
            onClick={() => setSidebarOpen(false)}
            className="lg:hidden p-2 rounded-md text-gray-400 hover:text-gray-600 hover:bg-gray-100"
          >
              <X className="h-5 w-5" />
          </button>
          </div>
        </div>
        
        {/* Enhanced Navigation */}
        <nav data-tour="navigation-sidebar" className="mt-6 px-3">
          <div className="space-y-1">
            {navigation.map((item) => {
              const isActive = pathname.startsWith(item.href)
              return (
                <Link
                  key={item.name}
                  to={item.href}
                  className={`group flex items-center px-3 py-3 text-sm font-medium rounded-lg transition-all duration-200 ${
                    isActive
                      ? 'bg-[#F5E6E8] text-[#C8102E] border-l-4 border-[#C8102E] shadow-sm'
                      : 'text-gray-700 hover:bg-[#F5E6E8] hover:text-[#C8102E]'
                  }`}
                  onClick={() => setSidebarOpen(false)}
                  title={sidebarCollapsed ? item.name : undefined}
                >
                  <item.icon className={`h-5 w-5 flex-shrink-0 ${
                    isActive ? 'text-[#C8102E]' : 'text-gray-400 group-hover:text-[#C8102E]'
                  } ${sidebarCollapsed ? 'mx-auto' : 'mr-3'}`} />
                  {!sidebarCollapsed && (
                    <div className="flex items-center flex-1 min-w-0">
                      <span className="truncate">{item.name}</span>
                      {item.comingSoon && <ComingSoonBadgeInline />}
                    </div>
                  )}
                </Link>
              )
            })}
          </div>
        </nav>
      </div>

      {/* Main content area */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Enhanced Top header */}
        <header className="bg-white shadow-md border-b-2 border-gray-100">
          <div className="flex items-center justify-between h-16 px-4 sm:px-6 lg:px-8">
            <div className="flex items-center flex-1">
              <button
                onClick={() => setSidebarOpen(true)}
                className="lg:hidden p-2 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors"
              >
                <Menu className="h-6 w-6" />
              </button>
              <h2 className="ml-2 text-xl font-semibold text-gray-900">
                {navigation.find(item => item.href === pathname)?.name || 'PrimeData'}
              </h2>
            </div>
            
            <div className="flex items-center space-x-3">
              {/* Take Tour Button */}
              {pathname === '/dashboard' && (
                <button
                  onClick={() => {
                    resetTour()
                    // Trigger tour by reloading or using a state management approach
                    if (typeof window !== 'undefined') {
                      window.dispatchEvent(new CustomEvent('startTour'))
                    }
                  }}
                  className="hidden md:flex items-center gap-2 px-3 py-2 text-sm font-medium text-[#C8102E] hover:text-[#A00D24] hover:bg-[#F5E6E8] rounded-lg transition-colors border border-[#C8102E] hover:border-[#A00D24]"
                  title="Take Product Tour"
                >
                  <Play className="h-4 w-4" />
                  <span>Take Tour</span>
                </button>
              )}
              
              {/* Search button (placeholder for future) */}
              <button
                className="hidden md:flex p-2 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors"
                aria-label="Search"
              >
                <Search className="h-5 w-5" />
              </button>
              
              {/* Notifications (placeholder) */}
              <button
                className="hidden md:flex relative p-2 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors"
                aria-label="Notifications"
              >
                <Bell className="h-5 w-5" />
                <span className="absolute top-1 right-1 h-2 w-2 bg-red-500 rounded-full"></span>
              </button>
              
              {/* Enhanced User menu */}
              <div className="relative user-menu">
                <button
                  onClick={() => setUserMenuOpen(!userMenuOpen)}
                  className="flex items-center space-x-3 p-2 rounded-lg hover:bg-gray-100 transition-colors border-2 border-transparent hover:border-gray-200"
                >
                  {user?.name ? (
                    <div className="h-9 w-9 rounded-full bg-[#C8102E] flex items-center justify-center ring-2 ring-gray-200">
                      <span className="text-white text-sm font-semibold">
                        {user.name.charAt(0).toUpperCase()}
                      </span>
                    </div>
                  ) : (
                    <div className="h-9 w-9 rounded-full bg-[#C8102E] flex items-center justify-center ring-2 ring-gray-200">
                      <span className="text-white text-sm font-semibold">U</span>
                    </div>
                  )}
                  <div className="hidden sm:block text-left">
                    <p className="text-sm font-semibold text-gray-900">{user?.name}</p>
                    <p className="text-xs text-gray-500">{user?.email}</p>
                  </div>
                  <ChevronDown className={`h-4 w-4 text-gray-400 transition-transform ${userMenuOpen ? 'rotate-180' : ''}`} />
                </button>
                
                {userMenuOpen && (
                    <div className="absolute right-0 mt-2 w-56 bg-white rounded-xl shadow-xl border-2 border-gray-100 z-50 overflow-hidden">
                    <div className="py-2">
                      <div className="px-4 py-3 border-b border-gray-100 bg-[#F5E6E8]">
                        <p className="text-sm font-semibold text-gray-900">{user?.name}</p>
                        <p className="text-xs text-gray-500 truncate">{user?.email}</p>
                      </div>
                      <Link
                        to="/account"
                        onClick={() => setUserMenuOpen(false)}
                        className="flex items-center px-4 py-2.5 text-sm text-gray-700 hover:bg-[#F5E6E8] transition-colors"
                      >
                        <UserCircle className="h-4 w-4 mr-3 text-gray-400" />
                        My Account
                      </Link>
                      <Link
                        to="/app/settings"
                        onClick={() => setUserMenuOpen(false)}
                        className="flex items-center px-4 py-2.5 text-sm text-gray-700 hover:bg-[#F5E6E8] transition-colors"
                      >
                        <Settings className="h-4 w-4 mr-3 text-gray-400" />
                        Settings
                      </Link>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        </header>

        {/* Page content */}
        <main className="flex-1 overflow-auto">
          {children}
        </main>

        {/* Footer */}
        <footer className="bg-white border-t border-gray-200 py-4">
          <div className="container mx-auto px-4 sm:px-6 lg:px-8">
            <div className="text-center text-sm text-gray-500">
            </div>
          </div>
        </footer>
      </div>
      </div>
    </div>
  )
}