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

export interface PullCodeResult {
  path: string
  detail: string
  // 폼 로그창용 부가 정보(최근 커밋 등)
  log: string
}

// 코드 저장 경로로 git 코드를 받아온다(없으면 clone, 있으면 제자리 업데이트).
// 폼 값 기반이라 저장 전 신규 등록 중에도 동작한다. patches는 체크아웃 후 순서대로 적용된다.
export function pullCode(body: {
  git_url: string
  git_ref: string
  // reset(원격 강제 일치) | rebase(로컬 커밋 유지) — 미지정 시 서버 기본 reset
  git_update_mode?: 'reset' | 'rebase'
  code_path: string
  out_tests_rel?: string
  patches?: { name: string; content: string; order_index: number }[]
}): Promise<PullCodeResult> {
  return apiFetch<PullCodeResult>('/products/pull-code', { method: 'POST', body })
}

export interface GerritPatchResult {
  name: string
  content: string
  ref: string
  subject: string
}

// Gerrit change 주소/번호로 diff를 가져온다(Git URL로 change ref fetch — clone과 같은 인증).
// code_path 체크아웃이 필요하다(먼저 다운로드).
export function fetchGerritPatch(body: {
  git_url: string
  code_path: string
  change: string
}): Promise<GerritPatchResult> {
  return apiFetch<GerritPatchResult>('/products/fetch-gerrit-patch', { method: 'POST', body })
}

export interface RunCommandResult {
  exit_code: number
  output: string
  duration_seconds: number
}

// 폼의 명령(CMAKE_CONFIGURE_CMD 등)을 code_path에서 시험 실행한다.
// 명령 자체의 실패(비0 exit)는 HTTP 오류가 아니라 exit_code로 온다.
export function runCommand(body: {
  command: string
  code_path: string
}): Promise<RunCommandResult> {
  return apiFetch<RunCommandResult>('/products/run-command', { method: 'POST', body })
}

export function updateProduct(id: number, data: ProductCreate): Promise<Product> {
  return apiFetch<Product>(`/products/${id}`, { method: 'PUT', body: data })
}

export function deleteProduct(id: number): Promise<void> {
  return apiFetch<void>(`/products/${id}`, { method: 'DELETE' })
}
