import { Outlet, useLocation } from 'react-router-dom'
import { LangToggle, ThemeToggle } from '../components/HeaderToggles'
import { useLang } from '../lib/i18n'

// 독립 테스트 현황 서버(serve-status)용 미니 레이아웃 — 네비게이션 없이
// 브랜드 + 페이지 이름 + 테마/언어 토글만 둔다(읽기 전용 단일 페이지).
export function StatusLayout() {
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
            <span className="whitespace-nowrap text-sm font-medium text-muted">
              {t('테스트 파일 현황')}
            </span>
          </div>
          <div className="flex flex-1 items-center justify-end gap-1">
            <LangToggle />
            <ThemeToggle />
          </div>
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
