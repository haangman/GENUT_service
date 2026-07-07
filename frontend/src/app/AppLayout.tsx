import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { useTheme } from '../lib/useTheme'
import { useLang } from '../lib/i18n'

const navItems = [
  { to: '/products', label: '프로덕트 등록' },
  { to: '/genuts', label: 'GENUT 등록' },
  { to: '/request', label: '수동 실행 요청' },
  { to: '/manual-jobs', label: '수동 실행 이력' },
  { to: '/auto-jobs', label: '자동 실행 이력' },
  { to: '/test-status', label: '테스트 파일 현황' },
]

function ThemeToggle() {
  const { isDark, toggle } = useTheme()
  const { t } = useLang()
  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={isDark ? t('라이트 모드로 전환') : t('다크 모드로 전환')}
      title={isDark ? t('라이트 모드') : t('다크 모드')}
      className="btn btn-ghost btn-sm h-9 w-9 !px-0 text-muted hover:text-fg"
    >
      {isDark ? (
        // sun
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <circle cx="12" cy="12" r="4" />
          <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41" />
        </svg>
      ) : (
        // moon
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
        </svg>
      )}
    </button>
  )
}

// 한/영 전환 토글 — 버튼에는 전환될 언어를 표시한다(다크 모드 토글과 같은 관례).
function LangToggle() {
  const { lang, toggle, t } = useLang()
  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={lang === 'ko' ? t('영어로 전환') : t('한국어로 전환')}
      title={lang === 'ko' ? t('영어로 전환') : t('한국어로 전환')}
      className="btn btn-ghost btn-sm h-9 w-9 !px-0 text-xs font-semibold text-muted hover:text-fg"
    >
      {lang === 'ko' ? 'EN' : '한'}
    </button>
  )
}

export function AppLayout() {
  const location = useLocation()
  const { t } = useLang()
  return (
    <div className="min-h-screen bg-bg text-fg">
      <header className="sticky top-0 z-30 border-b border-border bg-bg/80 backdrop-blur-md">
        <div className="mx-auto flex max-w-6xl items-center gap-4 px-4 py-3">
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
      <main className="mx-auto max-w-6xl px-4 py-8">
        <div key={location.pathname} className="animate-fade-in-up">
          <Outlet />
        </div>
      </main>
    </div>
  )
}
