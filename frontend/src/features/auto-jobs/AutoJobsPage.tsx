import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { PageHeader } from '../../components/PageHeader'
import { listAutoHistory, listJobs } from '../../api/jobs'
import { runAutoNow } from '../../api/products'
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
  // 확장된 그룹만 전체 이력을 조회한다(접힌 그룹은 auto-history 응답의 최근 N개로 충분).
  // 전체 이력은 수천 건 × 여러 페이지 요청이라 폴링을 5초로 완화한다 — 상태 변화가
  // 잦은 최근 항목은 접힘 그룹 쿼리(2초)와 취소/재수행의 즉시 무효화가 커버한다.
  const fullQuery = useQuery({
    queryKey: ['jobs', 'auto', 'byProduct', group.product_id],
    queryFn: () => fetchAllAutoJobs(group.product_id),
    refetchInterval: 5000,
    enabled: expanded,
  })
  // 확장 직후 전체 이력이 로딩되는 동안에는 최근 N개를 그대로 보여준다(깜빡임 방지)
  const jobs = expanded && fullQuery.data ? fullQuery.data : group.jobs
  const hiddenCount = Math.max(0, group.total - group.jobs.length)

  // 주기와 무관한 즉시 실행: 사이클(변경 감지→누락 스캔)을 지금 큐잉한다
  const queryClient = useQueryClient()
  const runMut = useMutation({
    mutationFn: () => runAutoNow(group.product_id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['jobs'] }),
    onError: () =>
      window.alert('실행 요청에 실패했습니다. 이미 진행 중인 자동 실행이 있는지 확인하세요.'),
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
            <span className="text-xs text-subtle">주기 {group.auto_interval_seconds}s</span>
          ) : null}
          <span className="ml-auto text-xs text-muted">
            전체 {group.total}건
            {!expanded && hiddenCount > 0 ? ` · 외 ${hiddenCount}건 보기` : ''}
          </span>
        </button>
        <button
          type="button"
          onClick={() => runMut.mutate()}
          disabled={runMut.isPending}
          title="주기와 무관하게 지금 실행 (변경 감지 → 누락 테스트 스캔)"
          className="btn btn-primary btn-sm shrink-0"
        >
          {runMut.isPending ? '요청 중…' : '▶ 지금 실행'}
        </button>
      </div>
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
