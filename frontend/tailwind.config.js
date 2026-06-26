/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"Plus Jakarta Sans"', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
      // 모든 색은 CSS 변수(라이트/다크) 기반 시맨틱 토큰 → 다크모드는 변수 교체로 자동 전환.
      colors: {
        bg: 'var(--bg)',
        surface: 'var(--surface)',
        'surface-2': 'var(--surface-2)',
        'surface-hover': 'var(--surface-hover)',
        border: 'var(--border)',
        'border-strong': 'var(--border-strong)',
        fg: 'var(--fg)',
        muted: 'var(--muted)',
        subtle: 'var(--subtle)',
        ring: 'var(--ring)',
        primary: {
          DEFAULT: 'var(--primary)',
          hover: 'var(--primary-hover)',
          fg: 'var(--primary-fg)',
          soft: 'var(--primary-soft)',
        },
        success: { DEFAULT: 'var(--success)', soft: 'var(--success-soft)', fg: 'var(--success-fg)' },
        warn: { DEFAULT: 'var(--warn)', soft: 'var(--warn-soft)', fg: 'var(--warn-fg)' },
        danger: { DEFAULT: 'var(--danger)', soft: 'var(--danger-soft)', fg: 'var(--danger-fg)' },
      },
      borderColor: { DEFAULT: 'var(--border)' },
      boxShadow: {
        card: 'var(--shadow-card)',
        pop: 'var(--shadow-pop)',
      },
      borderRadius: { xl: '0.875rem', '2xl': '1.125rem' },
      keyframes: {
        'fade-in-up': {
          '0%': { opacity: '0', transform: 'translateY(6px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
      },
      animation: { 'fade-in-up': 'fade-in-up 0.35s cubic-bezier(0.22, 1, 0.36, 1) both' },
    },
  },
  plugins: [],
}
