import { useState } from 'react'
import { keepPreviousData, useMutation, useQuery } from '@tanstack/react-query'
import { Link, useSearchParams } from 'react-router-dom'
import { PageHeader } from '../../components/PageHeader'
import { ProjectSelect } from '../../components/ProjectSelect'
import {
  deleteTargetTests,
  deleteTestFile,
  getTestStatusByName,
  getTestStatusSummary,
} from '../../api/testStatus'
import { ApiError } from '../../lib/apiClient'
import { formatDateTime } from '../jobs/jobFormat'
import { useLang } from '../../lib/i18n'
import { DEFAULT_PROJECT, PROJECTS } from '../../lib/projects'
import type { Project, TargetFileStatus, TestFileInfo } from '../../types/api'

// 스냅샷 폴링 주기 — 서버는 미리 계산된 스냅샷을 반환하므로 요청이 가볍다
const REFETCH_MS = 30_000

// 코드/로그 뷰어(전용 라우트)로 가는 링크. tab=code면 codePath, tab=log면 logPath를 본다.
function viewHref(t: TestFileInfo, tab: 'code' | 'log'): string {
  const params = new URLSearchParams({
    code: t.product_codes[0] ?? '',
    codePath: t.path,
    name: t.name,
    tab,
  })
  if (t.log_path) params.set('logPath', t.log_path)
  return `/test-status/view?${params.toString()}`
}

// 테스트 파일 목록 표(성공/실패 공용). 실패는 색으로 구분하고, 각 행에 코드/로그 버튼을 둔다.
function TestFileTable({
  title,
  files,
  variant,
  emptyText,
  onDelete,
  deletingPath,
}: {
  title: string
  files: TestFileInfo[]
  variant: 'success' | 'failed'
  emptyText: string
  // 개별 테스트 파일 삭제(확인 창은 호출부에서). deletingPath는 진행 중 표시용.
  onDelete: (tf: TestFileInfo) => void
  deletingPath: string | null
}) {
  const { t } = useLang()
  const failed = variant === 'failed'
  return (
    <div className="card overflow-x-auto">
      <div className="flex items-center gap-2 px-4 py-3">
        <h3 className="text-sm font-semibold text-fg">{t(title)}</h3>
        <span className={`badge ${failed ? 'badge-danger' : 'badge-success'}`}>{files.length}</span>
      </div>
      <table className="w-full text-sm">
        <thead>
          <tr
            className={`text-left text-xs font-semibold uppercase tracking-wide ${
              failed ? 'bg-danger-soft text-danger-fg' : 'bg-surface-2 text-muted'
            }`}
          >
            <th className="px-4 py-3">{t('테스트 파일명')}</th>
            <th className="px-4 py-3">path</th>
            {!failed ? <th className="px-4 py-3 text-right">{t('테스트 케이스 수')}</th> : null}
            <th className="px-4 py-3 text-right">{t('보기')}</th>
          </tr>
        </thead>
        <tbody>
          {files.map((tf) => (
            <tr key={tf.path} className="border-t border-border">
              <td className={`px-4 py-3 font-medium ${failed ? 'text-danger-fg' : 'text-fg'}`}>{tf.name}</td>
              <td className="break-all px-4 py-3 font-mono text-xs text-muted">{tf.path}</td>
              {!failed ? (
                <td className="px-4 py-3 text-right">
                  <span className="badge badge-neutral">{tf.case_count ?? 0}</span>
                </td>
              ) : null}
              <td className="px-4 py-3">
                <div className="flex justify-end gap-2">
                  <Link className="btn btn-sm btn-ghost" to={viewHref(tf, 'code')}>
                    {t('코드')}
                  </Link>
                  {tf.log_path ? (
                    <Link className="btn btn-sm btn-ghost" to={viewHref(tf, 'log')}>
                      {t('로그')}
                    </Link>
                  ) : (
                    <button className="btn btn-sm btn-ghost" disabled>
                      {t('로그')}
                    </button>
                  )}
                  <button
                    type="button"
                    className="btn btn-sm"
                    disabled={deletingPath === tf.path}
                    onClick={() => onDelete(tf)}
                  >
                    {deletingPath === tf.path ? t('삭제 중…') : t('삭제')}
                  </button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {files.length === 0 ? <p className="px-4 py-6 text-sm text-subtle">{t(emptyText)}</p> : null}
    </div>
  )
}

// 3단계 드릴다운(이름 기준): 프로덕트(이름) 목록 → 이름 상세(대상 파일·테스트/실패 수)
// → 파일 상세(성공/실패 테스트 파일 목록 + 코드/로그 뷰어 링크). 드릴다운 상태는 URL 쿼리에 둔다.
export function TestStatusPage() {
  const { t } = useLang()
  const [searchParams, setSearchParams] = useSearchParams()
  // 프로젝트도 드릴다운(name/file)과 같은 URL 쿼리에 둔다 — 미지정/알 수 없는 값은 기본 프로젝트
  const projectParam = searchParams.get('project')
  const project: Project = PROJECTS.includes(projectParam as Project)
    ? (projectParam as Project)
    : DEFAULT_PROJECT
  const selectedName = searchParams.get('name')
  const filePath = searchParams.get('file')

  const goToRoot = () => setSearchParams({ project })
  const goToName = (name: string) => setSearchParams({ project, name })
  const goToFile = (name: string, path: string) => setSearchParams({ project, name, file: path })
  // 프로젝트 전환: 다른 프로젝트의 name/file은 무효이므로 드릴다운을 함께 클리어한다
  const changeProject = (next: Project) => setSearchParams({ project: next })

  // placeholderData: 재조회 중에도 이전 표를 계속 보여준다("스캔 중…"은 최초 로딩만).
  const {
    data: summary,
    isLoading: summaryLoading,
    isFetching: summaryFetching,
    refetch: refetchSummary,
  } = useQuery({
    queryKey: ['test-status-summary', project],
    queryFn: () => getTestStatusSummary(project),
    refetchInterval: REFETCH_MS,
    placeholderData: keepPreviousData,
  })
  const names = summary ?? []

  const {
    data: status,
    isLoading,
    isError,
    isFetching: detailFetching,
    refetch: refetchDetail,
  } = useQuery({
    queryKey: ['test-status', project, selectedName],
    queryFn: () => getTestStatusByName(project, selectedName as string),
    enabled: selectedName != null,
    refetchInterval: REFETCH_MS,
    placeholderData: keepPreviousData,
  })
  const files = status ?? []
  const file = files.find((f) => f.path === filePath) ?? null
  const totalTests = files.reduce((sum, f) => sum + f.test_count, 0)
  const totalCases = files.reduce((sum, f) => sum + f.case_count, 0)
  const totalFails = files.reduce((sum, f) => sum + f.fail_count, 0)

  // 스냅샷 생성 시각(가장 최신) — 실시간 폴백 스캔만 있으면 null
  const generatedTimes = names
    .map((g) => g.generated_at)
    .filter((v): v is string => Boolean(v))
  const generatedAt = generatedTimes.length
    ? generatedTimes.reduce((a, b) => (a > b ? a : b))
    : null
  const refreshing = summaryFetching || detailFetching
  const refresh = () => {
    refetchSummary()
    if (selectedName != null) refetchDetail()
  }

  // 테스트 삭제(개별 파일 / 대상 파일 단위). 성공 시 상세·요약을 즉시 재조회한다.
  const [deletingPath, setDeletingPath] = useState<string | null>(null)
  const alertDeleteError = (error: unknown) => {
    const detail =
      error instanceof ApiError ? (error.body as { detail?: string } | null)?.detail : undefined
    window.alert(detail ? t(detail) : t('삭제에 실패했습니다.'))
  }
  const afterDelete = () => {
    refetchDetail()
    refetchSummary()
  }
  const fileDeleteMut = useMutation({
    // 합산 화면이라 한 파일이 여러 프로덕트에 있을 수 있다 — 출처 전체에서 지운다
    mutationFn: async (tf: TestFileInfo) => {
      for (const code of tf.product_codes) await deleteTestFile(code, tf.path)
    },
    onSuccess: afterDelete,
    onError: alertDeleteError,
    onSettled: () => setDeletingPath(null),
  })
  const requestFileDelete = (tf: TestFileInfo) => {
    if (!window.confirm(t('{name} 테스트 파일을 삭제할까요?', { name: tf.name }))) return
    setDeletingPath(tf.path)
    fileDeleteMut.mutate(tf)
  }
  const targetDeleteMut = useMutation({
    mutationFn: (target: TargetFileStatus) =>
      deleteTargetTests(project, selectedName as string, target.path),
    onSuccess: afterDelete,
    onError: alertDeleteError,
    onSettled: () => setDeletingPath(null),
  })
  const requestTargetDelete = (target: TargetFileStatus) => {
    const count = target.test_count + target.fail_count
    if (
      !window.confirm(
        t('{name}의 테스트 {count}개(실패 포함)를 모두 삭제할까요?', {
          name: target.name,
          count,
        }),
      )
    )
      return
    setDeletingPath(target.path)
    targetDeleteMut.mutate(target)
  }

  return (
    <div>
      <PageHeader
        title={t('테스트 파일 현황')}
        description={t('프로덕트별 테스트 생성 대상 파일과 생성된 테스트(성공/실패) 현황을 본다. 같은 이름의 프로덕트는 합산해서 보여준다.')}
      />

      {/* 프로젝트 필터 + 스냅샷 신선도 + 수동 새로고침 — 데이터는 백그라운드 스냅샷이라 즉시 뜬다 */}
      <div className="mb-4 flex flex-wrap items-center gap-3 text-xs text-muted">
        <ProjectSelect value={project} onChange={changeProject} id="test-status-project" />
        <button type="button" className="btn btn-sm" onClick={refresh} disabled={refreshing}>
          {refreshing ? t('갱신 중…') : t('새로고침')}
        </button>
        {generatedAt ? (
          <span>{t('마지막 갱신 {time}', { time: formatDateTime(generatedAt) })}</span>
        ) : null}
      </div>

      {selectedName != null ? (
        <nav className="mb-4 flex items-center gap-1.5 text-sm text-muted">
          <button className="link" onClick={goToRoot}>
            {t('프로덕트')}
          </button>
          <span>/</span>
          {file ? (
            <>
              <button className="link" onClick={() => goToName(selectedName)}>
                {selectedName}
              </button>
              <span>/</span>
              <span className="font-medium text-fg">{file.name}</span>
            </>
          ) : (
            <span className="font-medium text-fg">{selectedName}</span>
          )}
        </nav>
      ) : null}

      {/* L1: 이름별 목록 + 집계 */}
      {selectedName == null ? (
        <>
          {summaryLoading ? <p className="mb-3 text-sm text-muted">{t('스캔 중…')}</p> : null}
          <div className="card overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-surface-2 text-left text-xs font-semibold uppercase tracking-wide text-muted">
                  <th className="px-4 py-3">{t('이름')}</th>
                  <th className="px-4 py-3">{t('등록 ID')}</th>
                  <th className="px-4 py-3">{t('모드')}</th>
                  <th className="px-4 py-3 text-right">{t('대상 파일 수')}</th>
                  <th className="px-4 py-3 text-right">{t('총 테스트파일 수')}</th>
                  <th className="px-4 py-3 text-right">{t('총 테스트 케이스 수')}</th>
                  <th className="px-4 py-3 text-right">{t('실패 수')}</th>
                </tr>
              </thead>
              <tbody>
                {names.map((g) => (
                  <tr
                    key={g.name}
                    className="cursor-pointer border-t border-border transition hover:bg-surface-hover"
                    onClick={() => goToName(g.name)}
                  >
                    <td className="px-4 py-3 font-medium text-fg">{g.name}</td>
                    <td
                      className="max-w-[220px] truncate px-4 py-3 font-mono text-xs text-muted"
                      title={g.product_codes.join(', ')}
                    >
                      {g.product_codes.join(', ')}
                    </td>
                    <td className="px-4 py-3">
                      <span className="badge badge-neutral">{g.test_generation_mode}</span>
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums text-fg">{g.target_file_count}</td>
                    <td className="px-4 py-3 text-right">
                      <span className={`badge ${g.total_test_count > 0 ? 'badge-primary' : 'badge-neutral'}`}>
                        {g.total_test_count}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <span className={`badge ${g.total_case_count > 0 ? 'badge-primary' : 'badge-neutral'}`}>
                        {g.total_case_count}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <span className={`badge ${g.total_fail_count > 0 ? 'badge-danger' : 'badge-neutral'}`}>
                        {g.total_fail_count}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!summaryLoading && names.length === 0 ? (
              <p className="px-4 py-6 text-sm text-subtle">{t('등록된 프로덕트가 없습니다.')}</p>
            ) : null}
          </div>
        </>
      ) : null}

      {/* L2: 대상 파일 목록 + 합계 + 출처 */}
      {selectedName != null && file == null ? (
        <>
          {isLoading ? <p className="text-sm text-muted">{t('스캔 중…')}</p> : null}
          {isError ? (
            <p role="alert" className="text-sm text-danger-fg">
              {t('현황을 불러오지 못했습니다.')}
            </p>
          ) : null}
          {!isLoading && !isError ? (
            <>
              <div className="mb-3 flex gap-2 text-sm">
                <span className="badge badge-neutral">{t('대상 파일 {count}', { count: files.length })}</span>
                <span className={`badge ${totalTests > 0 ? 'badge-primary' : 'badge-neutral'}`}>
                  {t('총 테스트파일 {count}', { count: totalTests })}
                </span>
                <span className={`badge ${totalCases > 0 ? 'badge-primary' : 'badge-neutral'}`}>
                  {t('총 테스트 케이스 {count}', { count: totalCases })}
                </span>
                <span className={`badge ${totalFails > 0 ? 'badge-danger' : 'badge-neutral'}`}>
                  {t('총 실패 {count}', { count: totalFails })}
                </span>
              </div>
              <div className="card overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-surface-2 text-left text-xs font-semibold uppercase tracking-wide text-muted">
                      <th className="px-4 py-3">{t('파일명')}</th>
                      <th className="px-4 py-3">path</th>
                      <th className="px-4 py-3 text-right">{t('테스트 파일 수')}</th>
                      <th className="px-4 py-3 text-right">{t('테스트 케이스 수')}</th>
                      <th className="px-4 py-3 text-right">{t('실패 수')}</th>
                      <th className="px-4 py-3"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {files.map((f) => (
                      <tr
                        key={f.path}
                        className="cursor-pointer border-t border-border transition hover:bg-surface-hover"
                        onClick={() => goToFile(selectedName, f.path)}
                      >
                        <td className="px-4 py-3 font-medium text-fg">{f.name}</td>
                        <td className="break-all px-4 py-3 font-mono text-xs text-muted">{f.path}</td>
                        <td className="px-4 py-3 text-right">
                          <span className={`badge ${f.test_count > 0 ? 'badge-primary' : 'badge-neutral'}`}>
                            {f.test_count}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-right">
                          <span className={`badge ${f.case_count > 0 ? 'badge-primary' : 'badge-neutral'}`}>
                            {f.case_count}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-right">
                          <span className={`badge ${f.fail_count > 0 ? 'badge-danger' : 'badge-neutral'}`}>
                            {f.fail_count}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-right">
                          {/* 대상 파일의 테스트 전체(성공·실패·로그) 일괄 삭제 — 행 클릭(드릴다운)과 분리 */}
                          <button
                            type="button"
                            className="btn btn-sm"
                            disabled={
                              deletingPath === f.path || f.test_count + f.fail_count === 0
                            }
                            onClick={(event) => {
                              event.stopPropagation()
                              requestTargetDelete(f)
                            }}
                          >
                            {deletingPath === f.path ? t('삭제 중…') : t('테스트 삭제')}
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {files.length === 0 ? (
                  <p className="px-4 py-6 text-sm text-subtle">{t('테스트 생성 대상 파일이 없습니다.')}</p>
                ) : null}
              </div>
            </>
          ) : null}
        </>
      ) : null}

      {/* L3: 파일별 테스트 파일 목록(성공/실패 분리) + 코드/로그 뷰어 링크 */}
      {file != null ? (
        <div className="space-y-4">
          <TestFileTable
            title="생성 성공"
            files={file.test_files}
            variant="success"
            emptyText="생성에 성공한 테스트 파일이 없습니다."
            onDelete={requestFileDelete}
            deletingPath={deletingPath}
          />
          <TestFileTable
            title="생성 실패"
            files={file.failed_test_files}
            variant="failed"
            emptyText="실패한 테스트 파일이 없습니다."
            onDelete={requestFileDelete}
            deletingPath={deletingPath}
          />
        </div>
      ) : null}
    </div>
  )
}
