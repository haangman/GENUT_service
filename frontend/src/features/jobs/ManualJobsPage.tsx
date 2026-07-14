import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { PageHeader } from '../../components/PageHeader'
import { Pagination } from '../../components/Pagination'
import { ProjectSelect } from '../../components/ProjectSelect'
import { listJobs } from '../../api/jobs'
import { useLang } from '../../lib/i18n'
import { DEFAULT_PROJECT } from '../../lib/projects'
import type { Project } from '../../types/api'
import { JobTable } from './JobTable'

// 한 페이지에 보여줄 job 수 — 하단 게시판식 페이지네이션으로 이동한다
const PAGE_SIZE = 20

// 수동 실행 요청 페이지로 제출한 job의 이력 — auto 생성 job은 '자동 실행 이력'에서 본다.
export function ManualJobsPage() {
  const { t } = useLang()
  const [project, setProject] = useState<Project>(DEFAULT_PROJECT)
  const [page, setPage] = useState(1)
  // 프로젝트 전환 시 1페이지부터 다시 본다
  const changeProject = (next: Project) => {
    setProject(next)
    setPage(1)
  }
  // 현재 페이지(20건)만 조회하므로 이력이 커져도 폴링 비용이 일정하다.
  // 취소/재수행은 즉시 무효화로 바로 반영된다.
  const { data } = useQuery({
    queryKey: ['jobs', 'history', 'manual', project, page],
    queryFn: () => listJobs({ origin: 'manual', project, page, page_size: PAGE_SIZE }),
    refetchInterval: 3000,
    // 페이지 전환 중에는 직전 페이지를 그대로 보여준다(깜빡임 방지)
    placeholderData: (previous) => previous,
  })
  const totalPages = data ? Math.ceil(data.total / PAGE_SIZE) : 0
  return (
    <div className="space-y-6">
      <PageHeader
        title={t('수동 실행 이력')}
        description={t('수동 실행 요청 페이지로 제출한 job 이력/로그를 본다.')}
      />
      <ProjectSelect value={project} onChange={changeProject} id="manual-jobs-project" />
      {/* showKind: 어떤 GENUT 인스턴스가 실행했는지(배정 전이면 GENUT) 표시 */}
      <JobTable jobs={data?.items ?? []} showKind emptyMessage={t('job 이력이 없습니다.')} />
      <Pagination page={page} totalPages={totalPages} onChange={setPage} />
    </div>
  )
}
