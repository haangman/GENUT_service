import { apiFetch } from '../lib/apiClient'
import type { QueueItem, Worker } from '../types/api'

export function listWorkers(): Promise<Worker[]> {
  return apiFetch<Worker[]>('/workers')
}

export function listQueue(): Promise<QueueItem[]> {
  return apiFetch<QueueItem[]>('/queue')
}
