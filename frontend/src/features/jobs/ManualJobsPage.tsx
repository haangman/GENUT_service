import { useQuery } from '@tanstack/react-query'
import { PageHeader } from '../../components/PageHeader'
import { listJobs } from '../../api/jobs'
import { JobTable } from './JobTable'

// 수동(테스트 요청 페이지) 제출 job의 이력 — auto 생성 job은 '자동 실행 이력'에서 본다.
export function ManualJobsPage() {
  const { data } = useQuery({
    queryKey: ['jobs', 'history', 'manual'],
    queryFn: () => listJobs({ page_size: 50, origin: 'manual' }),
    refetchInterval: 2000, // 강제 종료 후 상태(canceled) 반영을 빠르게 보이도록
  })
  return (
    <div className="space-y-6">
      <PageHeader
        title="수동 실행 이력"
        description="테스트 요청 페이지로 제출한 job 이력/로그를 본다."
      />
      <JobTable jobs={data?.items ?? []} emptyMessage="job 이력이 없습니다." />
    </div>
  )
}
