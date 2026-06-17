import { apiFetch } from '../lib/apiClient'
import type { Job, JobCreate, JobEvent, Page } from '../types/api'

export function createJob(data: JobCreate): Promise<Job> {
  return apiFetch<Job>('/jobs', { method: 'POST', body: data })
}

export interface ListJobsParams {
  status?: string
  product_id?: number
  page?: number
  page_size?: number
}

export function listJobs(params: ListJobsParams = {}): Promise<Page<Job>> {
  return apiFetch<Page<Job>>('/jobs', { query: { ...params } })
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
