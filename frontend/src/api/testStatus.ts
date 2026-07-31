import { apiFetch } from '../lib/apiClient'
import type { FileContent, NameTestSummary, Project, TargetFileStatus } from '../types/api'

// 프로젝트의 이름별 테스트 현황 요약(대상 파일 수·총 테스트 수·총 실패 수). 목록 페이지용.
export function getTestStatusSummary(project: Project): Promise<NameTestSummary[]> {
  return apiFetch<NameTestSummary[]>('/test-status', { query: { project } })
}

// (프로젝트, 이름)의 모든 변이를 합산한 대상 파일 + 테스트 파일(성공/실패, 파일별 출처·로그 경로 포함).
export function getTestStatusByName(
  project: Project,
  name: string,
): Promise<TargetFileStatus[]> {
  return apiFetch<TargetFileStatus[]>('/test-status/detail', { query: { project, name } })
}

// 테스트 코드/로그 파일 1건의 내용. code는 프로덕트 id, path는 프로덕트 root 기준 상대경로.
export function getTestFileContent(code: string, path: string): Promise<FileContent> {
  return apiFetch<FileContent>('/test-status/file', { query: { code, path } })
}

// 테스트/실패 테스트 파일 1개를 영구 삭제한다(대응 debug 로그 포함). 실행 중 job 충돌은 409.
// logPath(화면이 아는 대응 로그 경로)를 주면 이름 규칙과 무관하게 그 로그를 확정 삭제한다.
export function deleteTestFile(code: string, path: string, logPath?: string | null): Promise<void> {
  return apiFetch<void>('/test-status/file', {
    method: 'DELETE',
    query: { code, path, log_path: logPath ?? undefined },
  })
}

// (project, name) 그룹의 실패 테스트(_Fail) 전체를 대응 로그와 함께 삭제(성공 테스트 보존).
export function deleteFailedTests(
  project: Project,
  name: string,
): Promise<{ deleted_files: number }> {
  return apiFetch<{ deleted_files: number }>('/test-status/failed', {
    method: 'DELETE',
    query: { project, name },
  })
}

// 대상 파일의 테스트 파일 전체(성공·실패)와 대응 로그 파일을 (project, name) 그룹의
// 모든 프로덕트에서 삭제한다. 폴더·스캐폴딩(CMakeLists 등)은 절대 지우지 않는다.
export function deleteTargetTests(
  project: Project,
  name: string,
  path: string,
): Promise<{ deleted_files: number }> {
  return apiFetch<{ deleted_files: number }>('/test-status/target', {
    method: 'DELETE',
    query: { project, name, path },
  })
}
