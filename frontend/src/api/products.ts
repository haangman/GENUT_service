import { apiFetch } from '../lib/apiClient'
import type { Job, Page, Product, ProductCreate, TargetFilesResponse } from '../types/api'

export function listProducts(page = 1, pageSize = 50): Promise<Page<Product>> {
  return apiFetch<Page<Product>>('/products', { query: { page, page_size: pageSize } })
}

export function getProduct(id: number): Promise<Product> {
  return apiFetch<Product>(`/products/${id}`)
}

export function createProduct(data: ProductCreate): Promise<Product> {
  return apiFetch<Product>('/products', { method: 'POST', body: data })
}

// 자동 실행 프로덕트 생성(서버가 CMakeLists 스캐폴딩도 만든다).
export function createAutoProduct(data: ProductCreate): Promise<Product> {
  return apiFetch<Product>('/products/auto', { method: 'POST', body: data })
}

// 자동 실행 프로덕트 수정(갱신된 정보/파일 목록으로 스캐폴딩 재생성).
export function updateAutoProduct(id: number, data: ProductCreate): Promise<Product> {
  return apiFetch<Product>(`/products/${id}/auto`, { method: 'PUT', body: data })
}

// 주기와 무관하게 auto 사이클(변경 감지→누락 스캔)을 지금 큐잉한다.
// 이전 사이클이 아직 진행/대기 중이면 서버가 409를 반환한다.
export function runAutoNow(id: number): Promise<Job[]> {
  return apiFetch<Job[]>(`/products/${id}/auto/run`, { method: 'POST' })
}

// 폼 단계 대상 파일 미리보기(로컬 code_path의 compile_commands.json + 기본 필터).
export function previewTargetFiles(body: {
  code_path: string
  compile_db_rel: string
  exclude_globs: string[]
}): Promise<TargetFilesResponse> {
  return apiFetch<TargetFilesResponse>('/products/target-files', { method: 'POST', body })
}

export function updateProduct(id: number, data: ProductCreate): Promise<Product> {
  return apiFetch<Product>(`/products/${id}`, { method: 'PUT', body: data })
}

export function deleteProduct(id: number): Promise<void> {
  return apiFetch<void>(`/products/${id}`, { method: 'DELETE' })
}
