import { apiFetch } from '../lib/apiClient'
import type { Genut, GenutCreate, Page } from '../types/api'

export function listGenuts(page = 1, pageSize = 50): Promise<Page<Genut>> {
  return apiFetch<Page<Genut>>('/genuts', { query: { page, page_size: pageSize } })
}

export function createGenut(data: GenutCreate): Promise<Genut> {
  return apiFetch<Genut>('/genuts', { method: 'POST', body: data })
}

export function deleteGenut(id: number): Promise<void> {
  return apiFetch<void>(`/genuts/${id}`, { method: 'DELETE' })
}
