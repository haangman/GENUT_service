import { Fragment, useEffect, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { cancelJob } from '../../api/jobs'
import type { Job } from '../../types/api'
import { JobLogs } from './JobLogs'
import {
  formatDateTime,
  formatDuration,
  jobBadgeClass,
  jobKindBadgeClass,
  jobKindLabel,
  jobResultLabel,
} from './jobFormat'

// job 이력 테이블: 행 클릭 → 바로 아래에 로그 패널 전개, 실행 중 job은 강제 종료 버튼.
// 모니터링(Job 이력)과 자동 실행 이력 페이지가 공용으로 사용한다.
// showKind: 종류(GENUT/JJ 스캔/변경 감지) badge 컬럼을 추가한다(자동 실행 이력 전용).
export function JobTable({
  jobs,
  showKind = false,
  emptyMessage,
}: {
  jobs: Job[]
  showKind?: boolean
  emptyMessage?: string
}) {
  const [selectedJobId, setSelectedJobId] = useState<number | null>(null)
  const [canceling, setCanceling] = useState<Set<number>>(new Set())
  const [, setTick] = useState(0) // 1초 틱: 실행 중 job의 총 수행 시간 실시간 갱신용
  const queryClient = useQueryClient()
  // 실행 중(시작했고 아직 종료 전)인 job이 있으면 1초마다 리렌더해 총 수행 시간을 실시간 갱신한다.
  const anyRunning = jobs.some((job) => job.started_at && !job.finished_at)
  useEffect(() => {
    if (!anyRunning) return
    const timer = setInterval(() => setTick((t) => t + 1), 1000)
    return () => clearInterval(timer)
  }, [anyRunning])
  const cancelMut = useMutation({
    mutationFn: (jobId: number) => cancelJob(jobId),
    onError: () =>
      window.alert('강제 종료 요청에 실패했습니다. 페이지를 새로고침(Ctrl+Shift+R) 후 다시 시도하세요.'),
    // ['jobs'] prefix 무효화: 이 테이블을 쓰는 모든 페이지의 job 쿼리를 갱신
    onSettled: () => queryClient.invalidateQueries({ queryKey: ['jobs'] }),
  })
  const requestCancel = (jobId: number) => {
    setCanceling((prev) => new Set(prev).add(jobId))
    cancelMut.mutate(jobId)
  }
  const cell = 'whitespace-nowrap px-3 py-2.5 text-muted'
  if (jobs.length === 0 && emptyMessage) {
    return <p className="text-sm text-subtle">{emptyMessage}</p>
  }
  return (
    <div className="card overflow-x-auto">
      {/* table-fixed + 고정 폭(colgroup): 긴 로그가 열려도 데이터 컬럼이 안 밀린다.
          min-w로 좁은 화면에선 위 overflow-x-auto가 전체 좌우 스크롤을 제공한다. */}
      <table className={`w-full ${showKind ? 'min-w-[1220px]' : 'min-w-[1120px]'} table-fixed text-sm`}>
        <colgroup>
          <col className="w-[56px]" />
          <col className="w-[84px]" />
          {showKind ? <col className="w-[100px]" /> : null}
          <col className="w-[96px]" />
          <col className="w-[160px]" />
          <col className="w-[160px]" />
          <col className="w-[160px]" />
          <col className="w-[150px]" />
          <col className="w-[180px]" />
          <col className="w-[80px]" />
        </colgroup>
        <thead>
          <tr className="bg-surface-2 text-left text-xs font-semibold uppercase tracking-wide text-muted">
            <th className="px-3 py-2.5">#</th>
            <th className="px-3 py-2.5">product</th>
            {showKind ? <th className="px-3 py-2.5">종류</th> : null}
            <th className="px-3 py-2.5">상태</th>
            <th className="px-3 py-2.5">제출 시각</th>
            <th className="px-3 py-2.5">시작 시간</th>
            <th className="px-3 py-2.5">종료 시간</th>
            <th className="px-3 py-2.5">총 수행 시간</th>
            <th className="px-3 py-2.5">결과</th>
            <th className="px-3 py-2.5"></th>
          </tr>
        </thead>
        <tbody>
          {jobs.map((job) => (
            <Fragment key={job.id}>
              <tr
                className={`cursor-pointer border-t border-border transition hover:bg-surface-hover ${
                  selectedJobId === job.id ? 'bg-primary-soft' : ''
                }`}
                onClick={() => setSelectedJobId((current) => (current === job.id ? null : job.id))}
              >
                <td className="px-3 py-2.5 font-semibold text-fg">{job.id}</td>
                <td className="px-3 py-2.5 text-muted">{job.product_id}</td>
                {showKind ? (
                  <td className="px-3 py-2.5">
                    <span className={jobKindBadgeClass(job.kind)}>{jobKindLabel(job.kind)}</span>
                  </td>
                ) : null}
                <td className="px-3 py-2.5">
                  <span className={jobBadgeClass(job.status)}>{job.status}</span>
                </td>
                <td className={cell}>{formatDateTime(job.submitted_at)}</td>
                <td className={cell}>{formatDateTime(job.started_at)}</td>
                <td className={cell}>{formatDateTime(job.finished_at)}</td>
                <td className={cell}>{formatDuration(job.started_at, job.finished_at)}</td>
                <td className="truncate px-3 py-2.5 text-muted">{jobResultLabel(job)}</td>
                <td className="px-3 py-2.5 text-right">
                  {job.status === 'running' ? (
                    <button
                      type="button"
                      className="btn btn-danger btn-sm"
                      disabled={canceling.has(job.id)}
                      onClick={(event) => {
                        event.stopPropagation()
                        requestCancel(job.id)
                      }}
                    >
                      {canceling.has(job.id) ? '종료 중…' : '강제 종료'}
                    </button>
                  ) : null}
                </td>
              </tr>
              {selectedJobId === job.id ? (
                <tr className="bg-surface-2">
                  <td colSpan={showKind ? 10 : 9} className="border-t border-border p-3">
                    <JobLogs jobId={job.id} status={job.status} />
                  </td>
                </tr>
              ) : null}
            </Fragment>
          ))}
        </tbody>
      </table>
    </div>
  )
}
