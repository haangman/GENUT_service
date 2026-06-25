import { Fragment, useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { PageHeader } from '../../components/PageHeader'
import { listQueue, listWorkers } from '../../api/workers'
import { cancelJob, getJobLogs, listJobs, rerunJob } from '../../api/jobs'
import type { Job, JobEvent } from '../../types/api'

const TERMINAL = new Set(['done', 'failed', 'canceled', 'interrupted'])

// 파일명용 타임스탬프: YYYYMMDD-HHMMSS
function formatStamp(date: Date): string {
  const p = (n: number) => String(n).padStart(2, '0')
  return (
    `${date.getFullYear()}${p(date.getMonth() + 1)}${p(date.getDate())}` +
    `-${p(date.getHours())}${p(date.getMinutes())}${p(date.getSeconds())}`
  )
}

// 로컬 시각 표시: YYYY-MM-DD HH:MM:SS (없으면 '-')
function formatDateTime(iso: string | null): string {
  if (!iso) return '-'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '-'
  const p = (n: number) => String(n).padStart(2, '0')
  return (
    `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ` +
    `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
  )
}

// 총 수행 시간(시작~종료). 종료 전이면 현재까지 경과 + '(진행 중)', 미시작이면 '-'.
export function formatDuration(startIso: string | null, endIso: string | null): string {
  if (!startIso) return '-'
  const start = new Date(startIso).getTime()
  const end = endIso ? new Date(endIso).getTime() : Date.now()
  if (Number.isNaN(start) || Number.isNaN(end) || end < start) return '-'
  const totalSec = Math.floor((end - start) / 1000)
  const h = Math.floor(totalSec / 3600)
  const m = Math.floor((totalSec % 3600) / 60)
  const s = totalSec % 60
  const p = (n: number) => String(n).padStart(2, '0')
  const base = h > 0 ? `${h}:${p(m)}:${p(s)}` : `${m}:${p(s)}`
  return endIso ? base : `${base} (진행 중)`
}

// 결과 컬럼 표시: 짧은 요약만 보여준다. 긴 에러 로그(job.error)는 컬럼에 넣지 않고
// 상태 기반의 간단한 설명으로 대체한다(원문 로그는 행을 펼친 로그 뷰어/다운로드에서 확인).
function jobResultLabel(job: Job): string {
  if (job.result_summary) return job.result_summary
  switch (job.status) {
    case 'done':
      return '완료'
    case 'failed':
      return '실패로 실행이 중단됨.'
    case 'interrupted':
      return '서버 재시작으로 실행이 중단됨.'
    case 'canceled':
      return '강제 종료됨'
    default:
      return ''
  }
}

function WorkerGrid() {
  const { data } = useQuery({
    queryKey: ['workers'],
    queryFn: listWorkers,
    refetchInterval: 3000,
  })
  return (
    <section>
      <h2 className="mb-2 text-sm font-semibold">워커</h2>
      <div className="grid grid-cols-2 gap-2 md:grid-cols-3">
        {(data ?? []).map((worker) => (
          <div key={worker.id} className="rounded border bg-white p-2 text-sm">
            <div className="font-medium">{worker.name}</div>
            <div className="text-gray-500">상태: {worker.worker_status}</div>
            {worker.current_job_id ? (
              <div className="text-gray-500">job #{worker.current_job_id}</div>
            ) : null}
          </div>
        ))}
      </div>
    </section>
  )
}

function QueuePanel() {
  const { data } = useQuery({
    queryKey: ['queue'],
    queryFn: listQueue,
    refetchInterval: 3000,
  })
  return (
    <section>
      <h2 className="mb-2 text-sm font-semibold">요청 큐</h2>
      {(data ?? []).length === 0 ? (
        <p className="text-sm text-gray-400">대기 중인 요청이 없습니다.</p>
      ) : (
        <ul className="space-y-1 text-sm">
          {data?.map((item) => (
            <li key={item.job_id} className="flex gap-2">
              <span>job #{item.job_id}</span>
              <span className="text-gray-500">product {item.product_id}</span>
              {item.waiting_on_product ? (
                <span className="text-amber-700">대기(프로덕트 사용 중)</span>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

// 증분 폴링: 마지막으로 받은 이벤트 id 이후(`?since=`)만 받아 누적한다.
// 작업이 종료(done/failed)되면 마지막 한 번만 더 받아오고 폴링을 멈춘다.
export function JobLogs({
  jobId,
  status,
  pollMs = 1500,
}: {
  jobId: number
  status: string
  pollMs?: number
}) {
  const [events, setEvents] = useState<JobEvent[]>([])
  const cursorRef = useRef(0)
  const preRef = useRef<HTMLPreElement>(null)
  const terminal = TERMINAL.has(status)

  // 재수행: 동일 입력의 새 job을 큐에 추가한다(완료된 job에서만 가능).
  const queryClient = useQueryClient()
  const rerunMut = useMutation({
    mutationFn: () => rerunJob(jobId),
    onSuccess: (job) => {
      queryClient.invalidateQueries({ queryKey: ['jobs', 'history'] })
      queryClient.invalidateQueries({ queryKey: ['queue'] })
      window.alert(`재수행 요청 완료 (새 job #${job.id})`)
    },
    onError: () => window.alert('재수행 요청에 실패했습니다.'),
  })

  // 선택한 job이 바뀌면 누적 로그와 커서를 초기화
  useEffect(() => {
    setEvents([])
    cursorRef.current = 0
  }, [jobId])

  // 폴링 루프 (terminal이 true가 되면 마지막 1회만 받고 재예약하지 않음)
  useEffect(() => {
    let active = true
    let timer: ReturnType<typeof setTimeout> | undefined
    const poll = async () => {
      try {
        const batch = await getJobLogs(jobId, cursorRef.current)
        if (!active) return
        if (batch.length > 0) {
          cursorRef.current = batch[batch.length - 1].id
          setEvents((prev) => [...prev, ...batch])
        }
      } catch {
        /* 일시 오류는 무시하고 다음 tick에서 재시도 */
      }
      if (active && !terminal) {
        timer = setTimeout(poll, pollMs)
      }
    }
    poll()
    return () => {
      active = false
      if (timer) clearTimeout(timer)
    }
  }, [jobId, terminal, pollMs])

  // 새 로그가 들어오면 맨 아래로 스크롤
  useEffect(() => {
    if (preRef.current) preRef.current.scrollTop = preRef.current.scrollHeight
  }, [events])

  // 현재 화면에 쌓인(=그 순간까지의) 로그를 파일로 저장. 출력 중에도 동작.
  const handleSave = () => {
    const text = events.map((event) => `[${event.phase ?? '-'}] ${event.message}`).join('\n')
    const blob = new Blob([text], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `job_${jobId}_${formatStamp(new Date())}.log`
    document.body.appendChild(anchor)
    anchor.click()
    anchor.remove()
    URL.revokeObjectURL(url)
  }

  return (
    <div>
      <div className="mb-1 flex items-center gap-2 text-xs text-gray-500">
        <span>
          job #{jobId} 로그 {terminal ? '(완료)' : '· 실행 중…'}
        </span>
        <button
          type="button"
          onClick={handleSave}
          className="rounded border px-2 py-0.5 text-blue-600"
        >
          로그 저장
        </button>
        {terminal ? (
          <button
            type="button"
            onClick={() => rerunMut.mutate()}
            disabled={rerunMut.isPending}
            className="rounded border px-2 py-0.5 text-blue-600 disabled:opacity-50"
          >
            {rerunMut.isPending ? '재수행 중…' : '재수행'}
          </button>
        ) : null}
      </div>
      <pre
        ref={preRef}
        data-testid="job-log"
        // 로그는 줄바꿈하지 않고(whitespace-pre) 박스 안에서 상하·좌우로 스크롤한다.
        // 테이블은 table-fixed라 이 긴 로그가 데이터 컬럼 폭을 밀지 않는다.
        className="max-h-64 overflow-auto whitespace-pre rounded bg-gray-900 p-2 text-xs text-gray-100"
      >
        {events.map((event) => `[${event.phase ?? '-'}] ${event.message}`).join('\n') ||
          '로그 없음'}
      </pre>
    </div>
  )
}

function JobHistory() {
  const [selectedJobId, setSelectedJobId] = useState<number | null>(null)
  const [canceling, setCanceling] = useState<Set<number>>(new Set())
  const [, setTick] = useState(0) // 1초 틱: 실행 중 job의 총 수행 시간 실시간 갱신용
  const queryClient = useQueryClient()
  const { data } = useQuery({
    queryKey: ['jobs', 'history'],
    queryFn: () => listJobs({ page_size: 50 }),
    refetchInterval: 2000, // 강제 종료 후 상태(canceled) 반영을 빠르게 보이도록
  })
  // 실행 중(시작했고 아직 종료 전)인 job이 있으면 1초마다 리렌더해 총 수행 시간을 실시간 갱신한다.
  const anyRunning = (data?.items ?? []).some((job) => job.started_at && !job.finished_at)
  useEffect(() => {
    if (!anyRunning) return
    const timer = setInterval(() => setTick((t) => t + 1), 1000)
    return () => clearInterval(timer)
  }, [anyRunning])
  const cancelMut = useMutation({
    mutationFn: (jobId: number) => cancelJob(jobId),
    onError: () =>
      window.alert('강제 종료 요청에 실패했습니다. 페이지를 새로고침(Ctrl+Shift+R) 후 다시 시도하세요.'),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ['jobs', 'history'] }),
  })
  const requestCancel = (jobId: number) => {
    setCanceling((prev) => new Set(prev).add(jobId))
    cancelMut.mutate(jobId)
  }
  return (
    <section>
      <h2 className="mb-2 text-sm font-semibold">Job 이력</h2>
      <div className="overflow-x-auto">
        {/* table-fixed + 고정 폭(colgroup): 긴 로그가 열려도 데이터 컬럼이 안 밀린다.
            min-w로 좁은 화면에선 위 overflow-x-auto가 전체 좌우 스크롤을 제공한다. */}
        <table className="w-full min-w-[1120px] table-fixed border-collapse text-sm">
          <colgroup>
            <col className="w-[56px]" />
            <col className="w-[84px]" />
            <col className="w-[90px]" />
            <col className="w-[160px]" />
            <col className="w-[160px]" />
            <col className="w-[160px]" />
            <col className="w-[150px]" />
            <col className="w-[180px]" />
            <col className="w-[80px]" />
          </colgroup>
          <thead>
            <tr className="bg-gray-50 text-left text-xs font-semibold text-gray-600">
              <th className="border border-gray-200 px-3 py-2">#</th>
              <th className="border border-gray-200 px-3 py-2">product</th>
              <th className="border border-gray-200 px-3 py-2">상태</th>
              <th className="border border-gray-200 px-3 py-2">제출 시각</th>
              <th className="border border-gray-200 px-3 py-2">시작 시간</th>
              <th className="border border-gray-200 px-3 py-2">종료 시간</th>
              <th className="border border-gray-200 px-3 py-2">총 수행 시간</th>
              <th className="border border-gray-200 px-3 py-2">결과</th>
              <th className="border border-gray-200 px-3 py-2"></th>
            </tr>
          </thead>
        <tbody>
          {data?.items.map((job) => (
            <Fragment key={job.id}>
              <tr
                className={`cursor-pointer hover:bg-gray-50 ${
                  selectedJobId === job.id ? 'bg-blue-50' : ''
                }`}
                onClick={() => setSelectedJobId((current) => (current === job.id ? null : job.id))}
              >
                <td className="border border-gray-200 px-3 py-2 font-medium text-gray-700">{job.id}</td>
                <td className="border border-gray-200 px-3 py-2">{job.product_id}</td>
                <td className="border border-gray-200 px-3 py-2">{job.status}</td>
                <td className="whitespace-nowrap border border-gray-200 px-3 py-2 text-gray-500">{formatDateTime(job.submitted_at)}</td>
                <td className="whitespace-nowrap border border-gray-200 px-3 py-2 text-gray-500">{formatDateTime(job.started_at)}</td>
                <td className="whitespace-nowrap border border-gray-200 px-3 py-2 text-gray-500">{formatDateTime(job.finished_at)}</td>
                <td className="whitespace-nowrap border border-gray-200 px-3 py-2 text-gray-500">
                  {formatDuration(job.started_at, job.finished_at)}
                </td>
                <td className="border border-gray-200 px-3 py-2 text-gray-500">{jobResultLabel(job)}</td>
                <td className="border border-gray-200 px-3 py-2 text-right">
                  {job.status === 'running' ? (
                    <button
                      type="button"
                      className="rounded border border-red-300 px-2 py-0.5 text-xs text-red-600 hover:bg-red-50 disabled:opacity-50"
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
                <tr className="bg-gray-50">
                  <td colSpan={9} className="border border-gray-200 p-3">
                    <JobLogs jobId={job.id} status={job.status} />
                  </td>
                </tr>
              ) : null}
            </Fragment>
          ))}
        </tbody>
        </table>
      </div>
    </section>
  )
}

export function MonitoringPage() {
  return (
    <div className="space-y-6">
      <PageHeader title="모니터링" description="워커 상태, 요청 큐, job 이력/로그를 본다." />
      <WorkerGrid />
      <QueuePanel />
      <JobHistory />
    </div>
  )
}
