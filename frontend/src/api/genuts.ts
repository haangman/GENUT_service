import { apiFetch } from '../lib/apiClient'
import type { Genut, GenutCreate, Page } from '../types/api'

export function listGenuts(page = 1, pageSize = 50): Promise<Page<Genut>> {
  return apiFetch<Page<Genut>>('/genuts', { query: { page, page_size: pageSize } })
}

export function createGenut(data: GenutCreate): Promise<Genut> {
  return apiFetch<Genut>('/genuts', { method: 'POST', body: data })
}

// 수정. credential key를 생략하면 서버가 기존 값을 유지한다.
export function updateGenut(id: number, data: Record<string, unknown>): Promise<Genut> {
  return apiFetch<Genut>(`/genuts/${id}`, { method: 'PUT', body: data })
}

export function deleteGenut(id: number): Promise<void> {
  return apiFetch<void>(`/genuts/${id}`, { method: 'DELETE' })
}
