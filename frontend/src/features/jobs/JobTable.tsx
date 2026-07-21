import { Fragment, memo, useCallback, useEffect, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { cancelJob, deleteJob } from '../../api/jobs'
import { ApiError } from '../../lib/apiClient'
import { useLang } from '../../lib/i18n'
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

// 한 번에 렌더링하는 행 수. 수천 건 이력을 통째로 DOM에 올리면 로그 토글/폴링마다
// 페이지 전체가 버벅이므로, 청크로 잘라 '더 보기'로 늘려간다(데이터 자체는 전부 로드됨).
const RENDER_CHUNK = 200

const cell = 'whitespace-nowrap px-3 py-2.5 text-muted'

// 삭제 가능한 종결 상태 — 실행/대기 중 job은 워커·스케줄러 소유라 삭제 불가(서버도 409)
const TERMINAL_STATUSES = new Set(['done', 'failed', 'canceled', 'interrupted'])

// 행 1개 — memo로 감싸 로그 토글(selected)·1초 틱이 관련 행만 다시 그리게 한다.
// (React Query의 structural sharing이 변하지 않은 job 객체 참조를 유지해 준다)
const JobRow = memo(function JobRow({
  job,
  showKind,
  showProduct,
  selected,
  canceling,
  deleting,
  runningTick,
  onToggle,
  onCancel,
  onDelete,
}: {
  job: Job
  showKind: boolean
  showProduct: boolean
  selected: boolean
  canceling: boolean
  deleting: boolean
  runningTick: number // 실행 중 행만 1초마다 변해 경과 시간을 갱신한다(그 외 행은 0 고정)
  onToggle: (jobId: number) => void
  onCancel: (jobId: number) => void
  onDelete: (jobId: number) => void
}) {
  void runningTick // 값은 리렌더 트리거로만 쓰인다
  const { t } = useLang()
  return (
    <tr
      className={`group cursor-pointer border-t border-border transition hover:bg-surface-hover ${
        selected ? 'bg-primary-soft' : ''
      }`}
      onClick={() => onToggle(job.id)}
    >
      <td className="px-3 py-2.5 font-semibold text-fg">{job.id}</td>
      {showProduct ? (
        <td
          className="truncate px-3 py-2.5 text-muted"
          title={`${job.product_name ?? ''} (#${job.product_id})`}
        >
          {job.product_name ?? '?'} <span className="text-subtle">#{job.product_id}</span>
        </td>
      ) : null}
      {showKind ? (
        <td className="px-3 py-2.5">
          <span className={jobKindBadgeClass(job.kind)}>{t(jobKindLabel(job))}</span>
        </td>
      ) : null}
      <td className="px-3 py-2.5">
        <span className={jobBadgeClass(job.status)}>{job.status}</span>
      </td>
      <td className={cell}>{formatDateTime(job.submitted_at)}</td>
      <td className={cell}>{formatDateTime(job.started_at)}</td>
      <td className={cell}>{formatDateTime(job.finished_at)}</td>
      <td className={cell}>{formatDuration(job.started_at, job.finished_at, t('진행 중'))}</td>
      {/* 결과는 잘라내지 않고 줄바꿈으로 전체를 보여준다 */}
      <td className="break-words px-3 py-2.5 text-muted">{t(jobResultLabel(job))}</td>
      {/* 액션 컬럼은 오른쪽에 고정(sticky) — 테이블이 화면보다 넓어 가로 스크롤이 생겨도
          강제 종료 버튼이 항상 보인다. 배경을 채워 밑의 내용이 비치지 않게 한다. */}
      <td
        className={`sticky right-0 px-3 py-2.5 text-right ${
          selected ? 'bg-primary-soft' : 'bg-surface group-hover:bg-surface-hover'
        }`}
      >
        {job.status === 'running' ? (
          <button
            type="button"
            className="btn btn-danger btn-sm"
            disabled={canceling}
            onClick={(event) => {
              event.stopPropagation()
              onCancel(job.id)
            }}
          >
            {canceling ? t('종료 중…') : t('강제 종료')}
          </button>
        ) : TERMINAL_STATUSES.has(job.status) ? (
          // 종결 job은 이력에서 영구 삭제할 수 있다(이벤트·로그 포함)
          <button
            type="button"
            className="btn btn-sm"
            disabled={deleting}
            onClick={(event) => {
              event.stopPropagation()
              onDelete(job.id)
            }}
          >
            {deleting ? t('삭제 중…') : t('삭제')}
          </button>
        ) : null}
      </td>
    </tr>
  )
})

// job 이력 테이블: 행 클릭 → 바로 아래에 로그 패널 전개, 실행 중 job은 강제 종료 버튼.
// 수동/자동 실행 이력 페이지가 공용으로 사용한다.
// showKind: 종류(GENUT 이름/스캔/변경 감지) badge 컬럼을 추가한다.
// showProduct: product 컬럼 표시 여부 — 프로덕트별로 이미 그룹된 화면에서는 끈다.
export function JobTable({
  jobs,
  showKind = false,
  showProduct = true,
  emptyMessage,
}: {
  jobs: Job[]
  showKind?: boolean
  showProduct?: boolean
  emptyMessage?: string
}) {
  const [selectedJobId, setSelectedJobId] = useState<number | null>(null)
  const [canceling, setCanceling] = useState<Set<number>>(new Set())
  const [visibleCount, setVisibleCount] = useState(RENDER_CHUNK)
  const [tick, setTick] = useState(0) // 1초 틱: 실행 중 job의 총 수행 시간 실시간 갱신용
  const { t } = useLang()
  const queryClient = useQueryClient()

  const visibleJobs = jobs.length > visibleCount ? jobs.slice(0, visibleCount) : jobs
  // 화면에 보이는 실행 중 job이 있을 때만 1초 틱을 돌린다.
  const anyRunning = visibleJobs.some((job) => job.started_at && !job.finished_at)
  useEffect(() => {
    if (!anyRunning) return
    const timer = setInterval(() => setTick((t) => t + 1), 1000)
    return () => clearInterval(timer)
  }, [anyRunning])

  const cancelMut = useMutation({
    mutationFn: (jobId: number) => cancelJob(jobId),
    onError: () =>
      window.alert(t('강제 종료 요청에 실패했습니다. 페이지를 새로고침(Ctrl+Shift+R) 후 다시 시도하세요.')),
    // ['jobs'] prefix 무효화: 이 테이블을 쓰는 모든 페이지의 job 쿼리를 갱신
    onSettled: () => queryClient.invalidateQueries({ queryKey: ['jobs'] }),
  })
  const { mutate: cancelMutate } = cancelMut
  const requestCancel = useCallback(
    (jobId: number) => {
      setCanceling((prev) => new Set(prev).add(jobId))
      cancelMutate(jobId)
    },
    [cancelMutate],
  )

  // 종결 job 삭제 — 이벤트·로그 파일까지 영구 삭제(서버 DELETE /jobs/{id})
  const [deleting, setDeleting] = useState<Set<number>>(new Set())
  const deleteMut = useMutation({
    mutationFn: (jobId: number) => deleteJob(jobId),
    onSuccess: (_data, jobId) => {
      // 삭제한 job의 로그 패널이 열려 있었다면 닫는다
      setSelectedJobId((current) => (current === jobId ? null : current))
    },
    onError: (error) => {
      const detail =
        error instanceof ApiError ? (error.body as { detail?: string } | null)?.detail : undefined
      window.alert(detail ? t(detail) : t('삭제에 실패했습니다.'))
    },
    onSettled: (_data, _error, jobId) => {
      setDeleting((prev) => {
        const next = new Set(prev)
        next.delete(jobId)
        return next
      })
      queryClient.invalidateQueries({ queryKey: ['jobs'] })
    },
  })
  const { mutate: deleteMutate } = deleteMut
  const requestDelete = useCallback(
    (jobId: number) => {
      if (!window.confirm(t('job #{id}을 삭제할까요? 로그도 함께 삭제됩니다.', { id: jobId })))
        return
      setDeleting((prev) => new Set(prev).add(jobId))
      deleteMutate(jobId)
    },
    [deleteMutate, t],
  )
  const toggleSelected = useCallback((jobId: number) => {
    setSelectedJobId((current) => (current === jobId ? null : jobId))
  }, [])

  if (jobs.length === 0 && emptyMessage) {
    return <p className="text-sm text-subtle">{emptyMessage}</p>
  }
  const columnCount = 8 + (showProduct ? 1 : 0) + (showKind ? 1 : 0)
  return (
    <div className="card overflow-x-auto">
      {/* table-fixed + 고정 폭(colgroup): 긴 로그가 열려도 데이터 컬럼이 안 밀린다.
          결과 컬럼만 폭을 지정하지 않아 남는 공간을 차지하며 줄바꿈으로 전체 내용을 보여준다.
          제품(이름+id) 컬럼이 있으면 폭이 컨테이너를 넘을 수 있는데, 액션 컬럼을 sticky로
          고정해 가로 스크롤이 생겨도 강제 종료 버튼은 항상 보인다. */}
      <table
        className={`w-full ${showProduct ? 'min-w-[1200px]' : 'min-w-[1120px]'} table-fixed text-sm`}
      >
        <colgroup>
          <col className="w-[56px]" />
          {showProduct ? <col className="w-[150px]" /> : null}
          {showKind ? <col className="w-[100px]" /> : null}
          <col className="w-[96px]" />
          <col className="w-[160px]" />
          <col className="w-[160px]" />
          <col className="w-[160px]" />
          <col className="w-[140px]" />
          <col />
          <col className="w-[80px]" />
        </colgroup>
        <thead>
          <tr className="bg-surface-2 text-left text-xs font-semibold uppercase tracking-wide text-muted">
            <th className="px-3 py-2.5">#</th>
            {showProduct ? <th className="px-3 py-2.5">{t('제품')}</th> : null}
            {showKind ? <th className="px-3 py-2.5">{t('종류')}</th> : null}
            <th className="px-3 py-2.5">{t('상태')}</th>
            <th className="px-3 py-2.5">{t('제출 시각')}</th>
            <th className="px-3 py-2.5">{t('시작 시간')}</th>
            <th className="px-3 py-2.5">{t('종료 시간')}</th>
            <th className="px-3 py-2.5">{t('총 수행 시간')}</th>
            <th className="px-3 py-2.5">{t('결과')}</th>
            <th className="sticky right-0 bg-surface-2 px-3 py-2.5"></th>
          </tr>
        </thead>
        <tbody>
          {visibleJobs.map((job) => (
            <Fragment key={job.id}>
              <JobRow
                job={job}
                showKind={showKind}
                showProduct={showProduct}
                selected={selectedJobId === job.id}
                canceling={canceling.has(job.id)}
                deleting={deleting.has(job.id)}
                runningTick={job.started_at && !job.finished_at ? tick : 0}
                onToggle={toggleSelected}
                onCancel={requestCancel}
                onDelete={requestDelete}
              />
              {selectedJobId === job.id ? (
                <tr className="bg-surface-2">
                  <td colSpan={columnCount} className="border-t border-border p-3">
                    <JobLogs jobId={job.id} status={job.status} />
                  </td>
                </tr>
              ) : null}
            </Fragment>
          ))}
        </tbody>
      </table>
      {jobs.length > visibleJobs.length ? (
        <div className="border-t border-border p-3 text-center">
          <button
            type="button"
            className="btn btn-sm"
            onClick={() => setVisibleCount((count) => count + RENDER_CHUNK)}
          >
            {t('더 보기 ({visible}/{total})', {
              visible: visibleJobs.length.toLocaleString(),
              total: jobs.length.toLocaleString(),
            })}
          </button>
        </div>
      ) : null}
    </div>
  )
}
