import { useQuery } from '@tanstack/react-query'
import { PageHeader } from '../../components/PageHeader'
import { listAllJobs } from '../../api/jobs'
import { JobTable } from './JobTable'

// 수동(테스트 요청 페이지) 제출 job의 이력 — auto 생성 job은 '자동 실행 이력'에서 본다.
export function ManualJobsPage() {
  // 전체 이력을 페이지 워크로 모두 가져온다(렌더링은 JobTable이 200행씩 청크로 제한).
  // 이력이 커질 수 있어 폴링은 3초 — 취소/재수행은 즉시 무효화로 바로 반영된다.
  const { data } = useQuery({
    queryKey: ['jobs', 'history', 'manual'],
    queryFn: () => listAllJobs({ origin: 'manual' }),
    refetchInterval: 3000,
  })
  return (
    <div className="space-y-6">
      <PageHeader
        title="수동 실행 이력"
        description="테스트 요청 페이지로 제출한 job 이력/로그를 본다."
      />
      {/* showKind: 어떤 GENUT 인스턴스가 실행했는지(배정 전이면 GENUT) 표시 */}
      <JobTable jobs={data ?? []} showKind emptyMessage="job 이력이 없습니다." />
    </div>
  )
}
