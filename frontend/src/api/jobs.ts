import { apiFetch } from '../lib/apiClient'
import type {
  AutoHistoryGroup,
  Job,
  JobCreate,
  JobEvent,
  JobKind,
  JobOrigin,
  Page,
  Project,
} from '../types/api'

export function createJob(data: JobCreate): Promise<Job> {
  return apiFetch<Job>('/jobs', { method: 'POST', body: data })
}

export interface ListJobsParams {
  status?: string
  product_id?: number
  origin?: JobOrigin
  kind?: JobKind
  // 프로젝트 필터(프로덕트 경유). 미지정이면 전체.
  project?: Project
  page?: number
  page_size?: number
}

export function listJobs(params: ListJobsParams = {}): Promise<Page<Job>> {
  return apiFetch<Page<Job>>('/jobs', { query: { ...params } })
}

// 페이지 상한(200)을 넘는 목록을 끝까지 걸어 전부 모은다.
// 페이지를 도는 사이 새 job이 끼어들면 경계가 밀려 중복될 수 있어 id로 걸러낸다.
export async function listAllJobs(
  params: Omit<ListJobsParams, 'page' | 'page_size'> = {},
): Promise<Job[]> {
  const pageSize = 200
  const first = await listJobs({ ...params, page: 1, page_size: pageSize })
  const jobs = [...first.items]
  const totalPages = Math.ceil(first.total / pageSize)
  for (let page = 2; page <= totalPages; page += 1) {
    const next = await listJobs({ ...params, page, page_size: pageSize })
    jobs.push(...next.items)
  }
  const seen = new Set<number>()
  return jobs.filter((job) => (seen.has(job.id) ? false : (seen.add(job.id), true)))
}

// auto 프로덕트별 자동 실행 job 이력(프로덕트당 최근 perProduct개 + 전체 수)
export function listAutoHistory(
  perProduct = 3,
  project?: Project,
): Promise<AutoHistoryGroup[]> {
  return apiFetch<AutoHistoryGroup[]>('/jobs/auto-history', {
    query: { per_product: perProduct, project },
  })
}

export function getJob(id: number): Promise<Job> {
  return apiFetch<Job>(`/jobs/${id}`)
}

export function getJobLogs(id: number, since = 0): Promise<JobEvent[]> {
  return apiFetch<JobEvent[]>(`/jobs/${id}/logs`, { query: { since } })
}

export function cancelJob(id: number): Promise<Job> {
  return apiFetch<Job>(`/jobs/${id}/cancel`, { method: 'POST' })
}

export function rerunJob(id: number): Promise<Job> {
  return apiFetch<Job>(`/jobs/${id}/rerun`, { method: 'POST' })
}

// 종결된 job을 이벤트·로그 파일과 함께 영구 삭제한다(실행/대기 중이면 409).
export function deleteJob(id: number): Promise<void> {
  return apiFetch<void>(`/jobs/${id}`, { method: 'DELETE' })
}
