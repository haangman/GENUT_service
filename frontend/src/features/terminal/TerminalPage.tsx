import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { PageHeader } from '../../components/PageHeader'
import { getTerminalInfo } from '../../api/terminal'
import { useLang } from '../../lib/i18n'
import { TerminalTab } from './TerminalTab'

interface Tab {
  id: number
  title: string
}

// 서비스 실행 환경의 인터랙티브 터미널. 탭마다 독립 셸을 열고, 탭을 추가/닫을 수 있다.
// 라우트 전환에도 세션이 유지되도록 AppLayout에서 항상 마운트하고, 현재 경로가
// 터미널일 때만 visible=true로 표시한다(숨김 시 언마운트하지 않아 WebSocket·스크롤백 보존).
export function TerminalPage({ visible = true }: { visible?: boolean }) {
  const { t } = useLang()
  const { data: info, isLoading } = useQuery({
    queryKey: ['terminal-info'],
    queryFn: getTerminalInfo,
  })

  const nextId = useRef(1)
  const [tabs, setTabs] = useState<Tab[]>([])
  const [activeId, setActiveId] = useState<number | null>(null)

  const addTab = () => {
    const id = nextId.current++
    setTabs((prev) => [...prev, { id, title: `${t('터미널')} ${id}` }])
    setActiveId(id)
  }

  const closeTab = (id: number) => {
    setTabs((prev) => {
      const next = prev.filter((tab) => tab.id !== id)
      setActiveId((current) => {
        if (current !== id) return current
        // 닫은 탭이 활성이면 마지막 탭으로 이동(없으면 null)
        return next.length ? next[next.length - 1].id : null
      })
      return next
    })
  }

  // 터미널 페이지가 보이고 사용 가능한데 탭이 없으면 첫 탭을 자동으로 연다.
  // (앱 로드 시점이 아니라 페이지를 처음 보게 됐을 때 열리도록 visible에 의존한다)
  useEffect(() => {
    if (visible && info?.available && tabs.length === 0) addTab()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visible, info?.available])

  return (
    <div style={{ display: visible ? 'block' : 'none' }}>
      <PageHeader
        title={t('터미널')}
        description={t('GENUT SERVICE가 실행 중인 환경의 셸에서 명령을 실행·디버깅한다.')}
      />

      {isLoading ? <p className="text-sm text-muted">{t('불러오는 중…')}</p> : null}

      {info && !info.available ? (
        <div className="card p-5">
          <p className="text-sm font-medium text-fg">{t('터미널을 사용할 수 없습니다.')}</p>
          <p className="mt-1 text-sm text-muted">{info.reason}</p>
        </div>
      ) : null}

      {info?.available ? (
        <div className="space-y-3">
          {/* 탭바: 각 탭 선택/닫기 + 새 터미널 */}
          <div className="flex flex-wrap items-center gap-1.5">
            {tabs.map((tab) => (
              <div
                key={tab.id}
                className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm transition ${
                  tab.id === activeId
                    ? 'bg-primary text-primary-fg shadow-card'
                    : 'bg-surface text-muted hover:bg-surface-hover hover:text-fg'
                }`}
              >
                <button type="button" onClick={() => setActiveId(tab.id)}>
                  {tab.title}
                </button>
                <button
                  type="button"
                  aria-label={t('탭 닫기 {title}', { title: tab.title })}
                  className="opacity-70 transition hover:opacity-100"
                  onClick={() => closeTab(tab.id)}
                >
                  ✕
                </button>
              </div>
            ))}
            <button type="button" className="btn btn-sm" onClick={addTab}>
              {t('+ 새 터미널')}
            </button>
          </div>

          {tabs.length === 0 ? (
            <p className="text-sm text-subtle">{t('열린 터미널이 없습니다. 새 터미널을 여세요.')}</p>
          ) : (
            tabs.map((tab) => (
              // 페이지가 숨겨져 있으면 모든 탭을 hidden 처리(보일 때 활성 탭에서 fit 재실행)
              <TerminalTab key={tab.id} hidden={!visible || tab.id !== activeId} />
            ))
          )}
        </div>
      ) : null}
    </div>
  )
}
