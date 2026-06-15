import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { PageHeader } from '../../components/PageHeader'
import { listQueue, listWorkers } from '../../api/workers'
import { getJobLogs, listJobs } from '../../api/jobs'

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

function JobLogs({ jobId }: { jobId: number }) {
  const { data } = useQuery({
    queryKey: ['jobLogs', jobId],
    queryFn: () => getJobLogs(jobId),
    refetchInterval: 2000,
  })
  return (
    <pre className="mt-2 max-h-64 overflow-auto rounded bg-gray-900 p-2 text-xs text-gray-100">
      {(data ?? []).map((event) => `[${event.phase ?? '-'}] ${event.message}`).join('\n') ||
        '로그 없음'}
    </pre>
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
      {selectedJobId ? <JobLogs jobId={selectedJobId} /> : null}
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
