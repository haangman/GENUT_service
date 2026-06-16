import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { PageHeader } from '../../components/PageHeader'
import { listQueue, listWorkers } from '../../api/workers'
import { getJobLogs, listJobs } from '../../api/jobs'
import type { JobEvent } from '../../types/api'

const TERMINAL = new Set(['done', 'failed'])

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

  return (
    <div className="mt-2">
      <div className="mb-1 flex items-center gap-2 text-xs text-gray-500">
        <span>
          job #{jobId} 로그 {terminal ? '(완료)' : '· 실행 중…'}
        </span>
        <a
          href={`/api/jobs/${jobId}/log/download`}
          download={`job_${jobId}.log`}
          className="text-blue-600 underline"
        >
          로그 파일 다운로드
        </a>
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
  const { data } = useQuery({
    queryKey: ['jobs', 'history'],
    queryFn: () => listJobs({ page_size: 50 }),
    refetchInterval: 5000,
  })
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
          </tr>
        </thead>
        <tbody>
          {data?.items.map((job) => (
            <tr
              key={job.id}
              className="cursor-pointer border-b hover:bg-gray-50"
              onClick={() => setSelectedJobId(job.id)}
            >
              <td className="py-2">{job.id}</td>
              <td>{job.product_id}</td>
              <td>{job.status}</td>
              <td className="text-gray-500">{job.result_summary ?? job.error ?? ''}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {selectedJobId ? (
        <JobLogs
          jobId={selectedJobId}
          status={data?.items.find((job) => job.id === selectedJobId)?.status ?? 'running'}
        />
      ) : null}
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
