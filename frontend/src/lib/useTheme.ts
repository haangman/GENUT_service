import { useEffect, useState } from 'react'

export type Theme = 'light' | 'dark'

// 초기 테마는 <html>의 dark 클래스(index.html의 무깜빡임 스크립트가 미리 설정)에서 읽는다.
function currentTheme(): Theme {
  if (typeof document === 'undefined') return 'light'
  return document.documentElement.classList.contains('dark') ? 'dark' : 'light'
}

/** 라이트/다크 테마 상태와 토글. <html>.dark 클래스 + localStorage('theme')에 반영한다. */
export function useTheme() {
  const [theme, setTheme] = useState<Theme>(currentTheme)

  useEffect(() => {
    const isDark = theme === 'dark'
    document.documentElement.classList.toggle('dark', isDark)
    try {
      localStorage.setItem('theme', theme)
    } catch {
      /* 저장 불가(프라이빗 모드 등)는 무시 */
    }
  }, [theme])

  return {
    theme,
    isDark: theme === 'dark',
    toggle: () => setTheme((t) => (t === 'dark' ? 'light' : 'dark')),
  }
}
