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
export function TerminalPage() {
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

  // 사용 가능하고 탭이 하나도 없으면 첫 탭을 자동으로 연다
  useEffect(() => {
    if (info?.available && tabs.length === 0) addTab()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [info?.available])

  return (
    <div>
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
              <TerminalTab key={tab.id} hidden={tab.id !== activeId} />
            ))
          )}
        </div>
      ) : null}
    </div>
  )
}
