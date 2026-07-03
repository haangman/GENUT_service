import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { PageHeader } from '../../components/PageHeader'
import { listAutoHistory, listJobs } from '../../api/jobs'
import type { AutoHistoryGroup, Job } from '../../types/api'
import { JobTable } from '../jobs/JobTable'

// 접힌 상태에서 프로덕트당 보여줄 최근 job 수
const RECENT_COUNT = 3
// 백엔드 page_size 상한 — 전체 이력은 페이지를 끝까지 걸어 모은다
const FULL_PAGE_SIZE = 200

// 확장 시 그 프로덕트의 auto job 이력 전체를 가져온다(페이지 워크).
async function fetchAllAutoJobs(productId: number): Promise<Job[]> {
  const first = await listJobs({
    product_id: productId,
    origin: 'auto',
    page: 1,
    page_size: FULL_PAGE_SIZE,
  })
  const jobs = [...first.items]
  const totalPages = Math.ceil(first.total / FULL_PAGE_SIZE)
  for (let page = 2; page <= totalPages; page += 1) {
    const next = await listJobs({
      product_id: productId,
      origin: 'auto',
      page,
      page_size: FULL_PAGE_SIZE,
    })
    jobs.push(...next.items)
  }
  // 페이지를 도는 사이 새 job이 끼어들면 경계가 밀려 중복될 수 있어 id로 걸러낸다
  const seen = new Set<number>()
  return jobs.filter((job) => (seen.has(job.id) ? false : (seen.add(job.id), true)))
}

function AutoProductGroup({
  group,
  expanded,
  onToggle,
}: {
  group: AutoHistoryGroup
  expanded: boolean
  onToggle: () => void
}) {
  // 확장된 그룹만 전체 이력을 조회한다(접힌 그룹은 auto-history 응답의 최근 N개로 충분)
  const fullQuery = useQuery({
    queryKey: ['jobs', 'auto', 'byProduct', group.product_id],
    queryFn: () => fetchAllAutoJobs(group.product_id),
    refetchInterval: 2000,
    enabled: expanded,
  })
  // 확장 직후 전체 이력이 로딩되는 동안에는 최근 N개를 그대로 보여준다(깜빡임 방지)
  const jobs = expanded && fullQuery.data ? fullQuery.data : group.jobs
  const hiddenCount = Math.max(0, group.total - group.jobs.length)
  return (
    <section className="space-y-3">
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-center gap-2.5 rounded-lg border border-border bg-surface px-3.5 py-2.5 text-left text-sm transition hover:bg-surface-hover"
      >
        <span className="text-xs text-muted">{expanded ? '▾' : '▸'}</span>
        <span className="font-semibold text-fg">{group.product_name}</span>
        <span className="badge badge-primary">auto</span>
        <span className="font-mono text-xs text-muted">{group.product_code}</span>
        {group.auto_interval_seconds ? (
          <span className="text-xs text-subtle">주기 {group.auto_interval_seconds}s</span>
        ) : null}
        <span className="ml-auto text-xs text-muted">
          전체 {group.total}건
          {!expanded && hiddenCount > 0 ? ` · 외 ${hiddenCount}건 보기` : ''}
        </span>
      </button>
      {/* 프로덕트별로 이미 그룹돼 있으므로 product 컬럼은 숨긴다 */}
      <JobTable jobs={jobs} showKind showProduct={false} emptyMessage="실행 이력이 없습니다." />
    </section>
  )
}

export function AutoJobsPage() {
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
        title="자동 실행 이력"
        description="자동 실행 프로덕트별 job 이력(변경 감지/JJ 스캔/GENUT)을 본다."
      />
      {groups.length === 0 ? (
        <p className="text-sm text-subtle">자동 실행 프로덕트가 없습니다.</p>
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
