import { apiFetch } from '../lib/apiClient'
import type { TargetFileStatus } from '../types/api'

// 프로덕트의 테스트 대상 파일 + 매칭된 생성 테스트 현황을 실시간으로 받아온다.
export function getTestStatus(productId: number): Promise<TargetFileStatus[]> {
  return apiFetch<TargetFileStatus[]>(`/products/${productId}/test-status`)
}
