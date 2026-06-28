import { apiFetch } from '../lib/apiClient'
import type { FileContent, NameTestSummary, TargetFileStatus } from '../types/api'

// 이름으로 묶은 전 프로덕트의 테스트 현황 요약(대상 파일 수·총 테스트 수·총 실패 수). 목록 페이지용.
export function getTestStatusSummary(): Promise<NameTestSummary[]> {
  return apiFetch<NameTestSummary[]>('/test-status')
}

// 이름의 모든 변이를 합산한 대상 파일 + 테스트 파일(성공/실패, 파일별 출처·로그 경로 포함).
export function getTestStatusByName(name: string): Promise<TargetFileStatus[]> {
  return apiFetch<TargetFileStatus[]>('/test-status/detail', { query: { name } })
}

// 테스트 코드/로그 파일 1건의 내용. code는 프로덕트 id, path는 프로덕트 root 기준 상대경로.
export function getTestFileContent(code: string, path: string): Promise<FileContent> {
  return apiFetch<FileContent>('/test-status/file', { query: { code, path } })
}
