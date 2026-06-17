import { Fragment, useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { PageHeader } from '../../components/PageHeader'
import { listQueue, listWorkers } from '../../api/workers'
import { cancelJob, getJobLogs, listJobs } from '../../api/jobs'
import type { JobEvent } from '../../types/api'

const TERMINAL = new Set(['done', 'failed', 'canceled'])

// 파일명용 타임스탬프: YYYYMMDD-HHMMSS
function formatStamp(date: Date): string {
  const p = (n: number) => String(n).padStart(2, '0')
  return (
    `${date.getFullYear()}${p(date.getMonth() + 1)}${p(date.getDate())}` +
    `-${p(date.getHours())}${p(date.getMinutes())}${p(date.getSeconds())}`
  )
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
      </div>
      <pre
        ref={preRef}
        className="max-h-64 overflow-auto rounded bg-gray-900 p-2 text-xs text-gray-100"
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
  const queryClient = useQueryClient()
  const { data } = useQuery({
    queryKey: ['jobs', 'history'],
    queryFn: () => listJobs({ page_size: 50 }),
    refetchInterval: 2000, // 강제 종료 후 상태(canceled) 반영을 빠르게 보이도록
  })
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
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b text-left text-gray-500">
            <th className="py-2">#</th>
            <th>product</th>
            <th>상태</th>
            <th>결과</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {data?.items.map((job) => (
            <Fragment key={job.id}>
              <tr
                className="cursor-pointer border-b hover:bg-gray-50"
                onClick={() => setSelectedJobId((current) => (current === job.id ? null : job.id))}
              >
                <td className="py-2">{job.id}</td>
                <td>{job.product_id}</td>
                <td>{job.status}</td>
                <td className="text-gray-500">{job.result_summary ?? job.error ?? ''}</td>
                <td className="text-right">
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
                <tr className="border-b bg-gray-50">
                  <td colSpan={5} className="p-2">
                    <JobLogs jobId={job.id} status={job.status} />
                  </td>
                </tr>
              ) : null}
            </Fragment>
          ))}
        </tbody>
      </table>
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
