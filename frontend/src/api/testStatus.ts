import { apiFetch } from '../lib/apiClient'
import type { NameTestSummary, TargetFileStatus } from '../types/api'

// 이름으로 묶은 전 프로덕트의 테스트 현황 요약(대상 파일 수·총 테스트 수). 목록 페이지용.
export function getTestStatusSummary(): Promise<NameTestSummary[]> {
  return apiFetch<NameTestSummary[]>('/test-status')
}

// 이름의 모든 변이를 합산한 대상 파일 + 테스트 파일(파일별 출처 product_codes 포함).
export function getTestStatusByName(name: string): Promise<TargetFileStatus[]> {
  return apiFetch<TargetFileStatus[]>('/test-status/detail', { query: { name } })
}
