import { apiFetch } from '../lib/apiClient'
import type {
  AutoHistoryGroup,
  Job,
  JobCreate,
  JobEvent,
  JobKind,
  JobOrigin,
  Page,
} from '../types/api'

export function createJob(data: JobCreate): Promise<Job> {
  return apiFetch<Job>('/jobs', { method: 'POST', body: data })
}

export interface ListJobsParams {
  status?: string
  product_id?: number
  origin?: JobOrigin
  kind?: JobKind
  page?: number
  page_size?: number
}

export function listJobs(params: ListJobsParams = {}): Promise<Page<Job>> {
  return apiFetch<Page<Job>>('/jobs', { query: { ...params } })
}

// auto 프로덕트별 자동 실행 job 이력(프로덕트당 최근 perProduct개 + 전체 수)
export function listAutoHistory(perProduct = 3): Promise<AutoHistoryGroup[]> {
  return apiFetch<AutoHistoryGroup[]>('/jobs/auto-history', {
    query: { per_product: perProduct },
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
