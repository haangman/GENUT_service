import { useQuery } from '@tanstack/react-query'
import { PageHeader } from '../../components/PageHeader'
import { listQueue, listWorkers } from '../../api/workers'
import { listJobs } from '../../api/jobs'
import { JobTable } from '../jobs/JobTable'

function workerBadgeClass(status: string): string {
  switch (status) {
    case 'idle':
      return 'badge badge-success'
    case 'busy':
      return 'badge badge-primary'
    case 'error':
      return 'badge badge-danger'
    default:
      return 'badge badge-neutral'
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
      <h2 className="mb-3 text-sm font-semibold text-fg">워커</h2>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-4">
        {(data ?? []).map((worker) => (
          <div key={worker.id} className="card p-3.5 text-sm">
            <div className="flex items-center justify-between gap-2">
              <span className="truncate font-semibold text-fg">{worker.name}</span>
              <span className={workerBadgeClass(worker.worker_status)}>{worker.worker_status}</span>
            </div>
            {worker.current_job_id ? (
              <div className="mt-1.5 font-mono text-xs text-muted">job #{worker.current_job_id}</div>
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
      <h2 className="mb-3 text-sm font-semibold text-fg">요청 큐</h2>
      {(data ?? []).length === 0 ? (
        <p className="text-sm text-subtle">대기 중인 요청이 없습니다.</p>
      ) : (
        <ul className="space-y-2 text-sm">
          {data?.map((item) => (
            <li
              key={item.job_id}
              className="flex items-center gap-3 rounded-lg border border-border bg-surface px-3 py-2"
            >
              <span className="font-semibold text-fg">job #{item.job_id}</span>
              <span className="text-muted">product {item.product_id}</span>
              {item.waiting_on_product ? (
                <span className="badge badge-warn ml-auto">대기(프로덕트 사용 중)</span>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

function JobHistory() {
  const { data } = useQuery({
    queryKey: ['jobs', 'history', 'manual'],
    // 수동(테스트 요청 페이지) job만 — auto 생성 job은 '자동 실행 이력' 페이지에서 본다
    queryFn: () => listJobs({ page_size: 50, origin: 'manual' }),
    refetchInterval: 2000, // 강제 종료 후 상태(canceled) 반영을 빠르게 보이도록
  })
  return (
    <section>
      <h2 className="mb-3 text-sm font-semibold text-fg">Job 이력</h2>
      <JobTable jobs={data?.items ?? []} />
    </section>
  )
}

export function MonitoringPage() {
  return (
    <div className="space-y-8">
      <PageHeader title="모니터링" description="워커 상태, 요청 큐, job 이력/로그를 본다." />
      <WorkerGrid />
      <QueuePanel />
      <JobHistory />
    </div>
  )
}
