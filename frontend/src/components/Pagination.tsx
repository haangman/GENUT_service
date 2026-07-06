import { useLang } from '../lib/i18n'

// 게시판식 페이지네이션: « ‹ 1 2 3 … 10 › » — 페이지 번호는 10개 블록 단위로 보여준다.
const BLOCK = 10

// 현재 페이지가 속한 블록의 페이지 번호 목록 (예: 13/50페이지 → 11..20)
export function pageWindow(page: number, totalPages: number): number[] {
  const start = Math.floor((page - 1) / BLOCK) * BLOCK + 1
  const end = Math.min(start + BLOCK - 1, totalPages)
  return Array.from({ length: Math.max(0, end - start + 1) }, (_, index) => start + index)
}

export function Pagination({
  page,
  totalPages,
  onChange,
}: {
  page: number
  totalPages: number
  onChange: (page: number) => void
}) {
  const { t } = useLang()
  if (totalPages <= 1) return null
  const go = (target: number) => onChange(Math.min(Math.max(1, target), totalPages))
  const base = 'btn btn-sm min-w-[32px] px-2'
  return (
    <nav
      aria-label={t('페이지 이동')}
      className="flex flex-wrap items-center justify-center gap-1 text-sm"
    >
      <button type="button" className={base} onClick={() => go(1)} disabled={page === 1} aria-label={t('첫 페이지')}>
        «
      </button>
      <button
        type="button"
        className={base}
        onClick={() => go(page - 1)}
        disabled={page === 1}
        aria-label={t('이전 페이지')}
      >
        ‹
      </button>
      {pageWindow(page, totalPages).map((target) => (
        <button
          key={target}
          type="button"
          onClick={() => go(target)}
          aria-current={target === page ? 'page' : undefined}
          className={target === page ? 'btn btn-primary btn-sm min-w-[32px] px-2' : base}
        >
          {target}
        </button>
      ))}
      <button
        type="button"
        className={base}
        onClick={() => go(page + 1)}
        disabled={page === totalPages}
        aria-label={t('다음 페이지')}
      >
        ›
      </button>
      <button
        type="button"
        className={base}
        onClick={() => go(totalPages)}
        disabled={page === totalPages}
        aria-label={t('마지막 페이지')}
      >
        »
      </button>
    </nav>
  )
}
