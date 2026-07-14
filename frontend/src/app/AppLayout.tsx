import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { LangToggle, ThemeToggle } from '../components/HeaderToggles'
import { useLang } from '../lib/i18n'
import { TerminalPage } from '../features/terminal/TerminalPage'

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
  // 터미널은 라우트 전환에도 세션이 유지되도록 여기서 항상 마운트하고, 터미널 경로일
  // 때만 보인다. 다른 페이지는 Outlet으로 렌더된다(터미널 경로에선 Outlet이 비어 있음).
  const isTerminal = location.pathname === '/terminal'
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
        {/* 터미널 경로에선 Outlet 영역을 숨기고, 항상 마운트된 터미널을 보여준다 */}
        <div key={location.pathname} className="animate-fade-in-up" hidden={isTerminal}>
          <Outlet />
        </div>
        <TerminalPage visible={isTerminal} />
      </main>
    </div>
  )
}
