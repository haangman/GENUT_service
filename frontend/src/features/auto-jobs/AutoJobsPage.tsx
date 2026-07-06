import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { PageHeader } from '../../components/PageHeader'
import { Pagination } from '../../components/Pagination'
import { listAutoHistory, listJobs } from '../../api/jobs'
import { runAutoNow } from '../../api/products'
import { useLang } from '../../lib/i18n'
import type { AutoHistoryGroup } from '../../types/api'
import { JobTable } from '../jobs/JobTable'

// 접힌 상태에서 프로덕트당 보여줄 최근 job 수
const RECENT_COUNT = 3
// 확장(전체 보기) 시 한 페이지에 보여줄 job 수 — 하단 게시판식 페이지네이션으로 이동한다
const PAGE_SIZE = 20

function AutoProductGroup({
  group,
  expanded,
  onToggle,
}: {
  group: AutoHistoryGroup
  expanded: boolean
  onToggle: () => void
}) {
  const { t } = useLang()
  const [page, setPage] = useState(1)
  // 다시 펼칠 때는 1페이지부터 시작한다
  useEffect(() => {
    if (expanded) setPage(1)
  }, [expanded])

  // 확장된 그룹만 페이지 단위로 조회한다(접힌 그룹은 auto-history 응답의 최근 N개로 충분).
  // 전체를 매번 걷지 않고 현재 페이지(20건)만 가져오므로 폴링 비용이 일정하다.
  const pageQuery = useQuery({
    queryKey: ['jobs', 'auto', 'byProduct', group.product_id, page],
    queryFn: () =>
      listJobs({ product_id: group.product_id, origin: 'auto', page, page_size: PAGE_SIZE }),
    refetchInterval: 5000,
    enabled: expanded,
    // 페이지 전환 중에는 직전 페이지를 그대로 보여준다(깜빡임 방지)
    placeholderData: (previous) => previous,
  })
  // 확장 직후 첫 페이지가 로딩되는 동안에는 최근 N개를 그대로 보여준다
  const jobs = expanded && pageQuery.data ? pageQuery.data.items : group.jobs
  const totalPages = pageQuery.data ? Math.ceil(pageQuery.data.total / PAGE_SIZE) : 0
  const hiddenCount = Math.max(0, group.total - group.jobs.length)

  // 주기와 무관한 즉시 실행: 사이클(변경 감지→누락 스캔)을 지금 큐잉한다
  const queryClient = useQueryClient()
  const runMut = useMutation({
    mutationFn: () => runAutoNow(group.product_id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['jobs'] }),
    onError: () =>
      window.alert(t('실행 요청에 실패했습니다. 이미 진행 중인 자동 실행이 있는지 확인하세요.')),
  })
  return (
    <section className="space-y-3">
      {/* 헤더: 토글(접기/펼치기) 버튼과 즉시 실행 버튼을 나란히 둔다(중첩 버튼 방지) */}
      <div className="flex w-full items-center gap-2.5 rounded-lg border border-border bg-surface px-3.5 py-2.5 text-sm transition hover:bg-surface-hover">
        <button
          type="button"
          onClick={onToggle}
          className="flex min-w-0 flex-1 items-center gap-2.5 text-left"
        >
          <span className="text-xs text-muted">{expanded ? '▾' : '▸'}</span>
          <span className="font-semibold text-fg">{group.product_name}</span>
          <span className="badge badge-primary">auto</span>
          <span className="font-mono text-xs text-muted">{group.product_code}</span>
          {group.auto_interval_seconds ? (
            <span className="text-xs text-subtle">{t('주기 {seconds}s', { seconds: group.auto_interval_seconds })}</span>
          ) : null}
          <span className="ml-auto text-xs text-muted">
            {t('전체 {total}건', { total: group.total })}
            {!expanded && hiddenCount > 0 ? t(' · 외 {count}건 보기', { count: hiddenCount }) : ''}
          </span>
        </button>
        <button
          type="button"
          onClick={() => runMut.mutate()}
          disabled={runMut.isPending}
          title={t('주기와 무관하게 지금 실행 (변경 감지 → 누락 테스트 스캔)')}
          className="btn btn-primary btn-sm shrink-0"
        >
          {runMut.isPending ? t('요청 중…') : t('▶ 지금 실행')}
        </button>
      </div>
      {/* 프로덕트별로 이미 그룹돼 있으므로 product 컬럼은 숨긴다 */}
      <JobTable jobs={jobs} showKind showProduct={false} emptyMessage={t('실행 이력이 없습니다.')} />
      {expanded ? <Pagination page={page} totalPages={totalPages} onChange={setPage} /> : null}
    </section>
  )
}

export function AutoJobsPage() {
  const { t } = useLang()
  const [expanded, setExpanded] = useState<Set<number>>(new Set())
  const { data } = useQuery({
    queryKey: ['jobs', 'auto', 'groups'],
    queryFn: () => listAutoHistory(RECENT_COUNT),
    refetchInterval: 2000, // 준비 job 상태/새 사이클 반영을 빠르게
  })
  const groups = data ?? []
  const toggle = (productId: number) =>
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(productId)) {
        next.delete(productId)
      } else {
        next.add(productId)
      }
      return next
    })
  return (
    <div className="space-y-6">
      <PageHeader
        title={t('자동 실행 이력')}
        description={t('자동 실행 프로덕트별 job 이력(변경 감지/스캔/GENUT)을 본다.')}
      />
      {groups.length === 0 ? (
        <p className="text-sm text-subtle">{t('자동 실행 프로덕트가 없습니다.')}</p>
      ) : (
        groups.map((group) => (
          <AutoProductGroup
            key={group.product_id}
            group={group}
            expanded={expanded.has(group.product_id)}
            onToggle={() => toggle(group.product_id)}
          />
        ))
      )}
    </div>
  )
}
