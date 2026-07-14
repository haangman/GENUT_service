import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { LangToggle, ThemeToggle } from '../components/HeaderToggles'
import { useLang } from '../lib/i18n'

const navItems = [
  { to: '/products', label: '프로덕트 등록' },
  { to: '/genuts', label: 'GENUT 등록' },
  { to: '/request', label: '수동 실행 요청' },
  { to: '/manual-jobs', label: '수동 실행 이력' },
  { to: '/auto-jobs', label: '자동 실행 이력' },
  { to: '/test-status', label: '테스트 파일 현황' },
  { to: '/terminal', label: '터미널' },
]

export function AppLayout() {
  const location = useLocation()
  const { t } = useLang()
  return (
    <div className="min-h-screen bg-bg text-fg">
      <header className="sticky top-0 z-30 border-b border-border bg-bg/80 backdrop-blur-md">
        <div className="flex w-full items-center gap-4 px-4 py-3 xl:px-6 2xl:px-8">
          <div className="flex shrink-0 items-center gap-2.5">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-primary-fg shadow-card">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M13 2 4.5 13.5H11l-1 8.5L19.5 10H13l0-8z" />
              </svg>
            </span>
            <span className="text-base font-bold tracking-tight text-fg">GENUT SERVICE</span>
          </div>
          <nav className="flex flex-1 items-center gap-1 overflow-x-auto">
            {navItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  `whitespace-nowrap rounded-lg px-3 py-1.5 text-sm font-medium transition ${
                    isActive
                      ? 'bg-primary text-primary-fg shadow-card'
                      : 'text-muted hover:bg-surface-hover hover:text-fg'
                  }`
                }
              >
                {t(item.label)}
              </NavLink>
            ))}
          </nav>
          <LangToggle />
          <ThemeToggle />
        </div>
      </header>
      <main className="w-full px-4 py-8 xl:px-6 2xl:px-8">
        <div key={location.pathname} className="animate-fade-in-up">
          <Outlet />
        </div>
      </main>
    </div>
  )
}
