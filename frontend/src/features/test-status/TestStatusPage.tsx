import { useQuery } from '@tanstack/react-query'
import { Link, useSearchParams } from 'react-router-dom'
import { PageHeader } from '../../components/PageHeader'
import { getTestStatusByName, getTestStatusSummary } from '../../api/testStatus'
import type { TestFileInfo } from '../../types/api'

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
}: {
  title: string
  files: TestFileInfo[]
  variant: 'success' | 'failed'
  emptyText: string
}) {
  const failed = variant === 'failed'
  return (
    <div className="card overflow-x-auto">
      <div className="flex items-center gap-2 px-4 py-3">
        <h3 className="text-sm font-semibold text-fg">{title}</h3>
        <span className={`badge ${failed ? 'badge-danger' : 'badge-success'}`}>{files.length}</span>
      </div>
      <table className="w-full text-sm">
        <thead>
          <tr
            className={`text-left text-xs font-semibold uppercase tracking-wide ${
              failed ? 'bg-danger-soft text-danger-fg' : 'bg-surface-2 text-muted'
            }`}
          >
            <th className="px-4 py-3">테스트 파일명</th>
            <th className="px-4 py-3">path</th>
            <th className="px-4 py-3 text-right">보기</th>
          </tr>
        </thead>
        <tbody>
          {files.map((t) => (
            <tr key={t.path} className="border-t border-border">
              <td className={`px-4 py-3 font-medium ${failed ? 'text-danger-fg' : 'text-fg'}`}>{t.name}</td>
              <td className="break-all px-4 py-3 font-mono text-xs text-muted">{t.path}</td>
              <td className="px-4 py-3">
                <div className="flex justify-end gap-2">
                  <Link className="btn btn-sm btn-ghost" to={viewHref(t, 'code')}>
                    코드
                  </Link>
                  {t.log_path ? (
                    <Link className="btn btn-sm btn-ghost" to={viewHref(t, 'log')}>
                      로그
                    </Link>
                  ) : (
                    <button className="btn btn-sm btn-ghost" disabled>
                      로그
                    </button>
                  )}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {files.length === 0 ? <p className="px-4 py-6 text-sm text-subtle">{emptyText}</p> : null}
    </div>
  )
}

// 3단계 드릴다운(이름 기준): 프로덕트(이름) 목록 → 이름 상세(대상 파일·테스트/실패 수)
// → 파일 상세(성공/실패 테스트 파일 목록 + 코드/로그 뷰어 링크). 드릴다운 상태는 URL 쿼리에 둔다.
export function TestStatusPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const selectedName = searchParams.get('name')
  const filePath = searchParams.get('file')

  const goToRoot = () => setSearchParams({})
  const goToName = (name: string) => setSearchParams({ name })
  const goToFile = (name: string, path: string) => setSearchParams({ name, file: path })

  const { data: summary, isLoading: summaryLoading } = useQuery({
    queryKey: ['test-status-summary'],
    queryFn: getTestStatusSummary,
  })
  const names = summary ?? []

  const { data: status, isLoading, isError } = useQuery({
    queryKey: ['test-status', selectedName],
    queryFn: () => getTestStatusByName(selectedName as string),
    enabled: selectedName != null,
  })
  const files = status ?? []
  const file = files.find((f) => f.path === filePath) ?? null
  const totalTests = files.reduce((sum, f) => sum + f.test_count, 0)
  const totalFails = files.reduce((sum, f) => sum + f.fail_count, 0)

  return (
    <div>
      <PageHeader
        title="테스트 현황"
        description="프로덕트별 테스트 생성 대상 파일과 생성된 테스트(성공/실패) 현황을 본다. 같은 이름의 프로덕트는 합산해서 보여준다."
      />

      {selectedName != null ? (
        <nav className="mb-4 flex items-center gap-1.5 text-sm text-muted">
          <button className="link" onClick={goToRoot}>
            프로덕트
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
          {summaryLoading ? <p className="mb-3 text-sm text-muted">스캔 중…</p> : null}
          <div className="card overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-surface-2 text-left text-xs font-semibold uppercase tracking-wide text-muted">
                  <th className="px-4 py-3">이름</th>
                  <th className="px-4 py-3">등록 ID</th>
                  <th className="px-4 py-3">모드</th>
                  <th className="px-4 py-3 text-right">대상 파일 수</th>
                  <th className="px-4 py-3 text-right">총 테스트 수</th>
                  <th className="px-4 py-3 text-right">실패 테스트 수</th>
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
                      <span className={`badge ${g.total_fail_count > 0 ? 'badge-danger' : 'badge-neutral'}`}>
                        {g.total_fail_count}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!summaryLoading && names.length === 0 ? (
              <p className="px-4 py-6 text-sm text-subtle">등록된 프로덕트가 없습니다.</p>
            ) : null}
          </div>
        </>
      ) : null}

      {/* L2: 대상 파일 목록 + 합계 + 출처 */}
      {selectedName != null && file == null ? (
        <>
          {isLoading ? <p className="text-sm text-muted">스캔 중…</p> : null}
          {isError ? (
            <p role="alert" className="text-sm text-danger-fg">
              현황을 불러오지 못했습니다.
            </p>
          ) : null}
          {!isLoading && !isError ? (
            <>
              <div className="mb-3 flex gap-2 text-sm">
                <span className="badge badge-neutral">대상 파일 {files.length}</span>
                <span className={`badge ${totalTests > 0 ? 'badge-primary' : 'badge-neutral'}`}>
                  총 테스트 {totalTests}
                </span>
                <span className={`badge ${totalFails > 0 ? 'badge-danger' : 'badge-neutral'}`}>
                  총 실패 {totalFails}
                </span>
              </div>
              <div className="card overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-surface-2 text-left text-xs font-semibold uppercase tracking-wide text-muted">
                      <th className="px-4 py-3">파일명</th>
                      <th className="px-4 py-3">path</th>
                      <th className="px-4 py-3 text-right">테스트 개수</th>
                      <th className="px-4 py-3 text-right">실패 개수</th>
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
                          <span className={`badge ${f.fail_count > 0 ? 'badge-danger' : 'badge-neutral'}`}>
                            {f.fail_count}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {files.length === 0 ? (
                  <p className="px-4 py-6 text-sm text-subtle">테스트 생성 대상 파일이 없습니다.</p>
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
          />
          <TestFileTable
            title="생성 실패"
            files={file.failed_test_files}
            variant="failed"
            emptyText="실패한 테스트 파일이 없습니다."
          />
        </div>
      ) : null}
    </div>
  )
}
