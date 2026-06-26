import { apiFetch } from '../lib/apiClient'
import type { ProductTestSummary, TargetFileStatus } from '../types/api'

// 전 프로덕트의 테스트 현황 요약(대상 파일 수·총 테스트 수). 목록 페이지용.
export function getTestStatusSummary(): Promise<ProductTestSummary[]> {
  return apiFetch<ProductTestSummary[]>('/test-status')
}

// 프로덕트의 테스트 대상 파일 + 매칭된 생성 테스트 현황을 실시간으로 받아온다.
export function getTestStatus(productId: number): Promise<TargetFileStatus[]> {
  return apiFetch<TargetFileStatus[]>(`/products/${productId}/test-status`)
}
