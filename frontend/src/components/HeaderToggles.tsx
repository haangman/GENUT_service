import { useTheme } from '../lib/useTheme'
import { useLang } from '../lib/i18n'

// 헤더 공용 토글들 — 메인 레이아웃(AppLayout)과 독립 현황 레이아웃(StatusLayout)이 공유한다.

export function ThemeToggle() {
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
export function LangToggle() {
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
