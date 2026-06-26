import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { PageHeader } from '../../components/PageHeader'
import { getTestStatus, getTestStatusSummary } from '../../api/testStatus'

// 3단계 드릴다운: 프로덕트 목록(대상 파일 수·총 테스트 수) → 프로덕트 상세(대상 파일·테스트 수)
// → 파일 상세(테스트 파일 목록).
export function TestStatusPage() {
  const [productId, setProductId] = useState<number | null>(null)
  const [filePath, setFilePath] = useState<string | null>(null)

  const { data: summary, isLoading: summaryLoading } = useQuery({
    queryKey: ['test-status-summary'],
    queryFn: getTestStatusSummary,
  })
  const products = summary ?? []
  const product = products.find((p) => p.product_id === productId) ?? null

  const { data: status, isLoading, isError } = useQuery({
    queryKey: ['test-status', productId],
    queryFn: () => getTestStatus(productId as number),
    enabled: productId != null,
  })
  const files = status ?? []
  const file = files.find((f) => f.path === filePath) ?? null
  const totalTests = files.reduce((sum, f) => sum + f.test_count, 0)

  return (
    <div>
      <PageHeader
        title="테스트 현황"
        description="프로덕트별 테스트 생성 대상 파일과 생성된 테스트 현황을 본다."
      />

      {productId != null ? (
        <nav className="mb-4 flex items-center gap-1.5 text-sm text-muted">
          <button
            className="link"
            onClick={() => {
              setProductId(null)
              setFilePath(null)
            }}
          >
            프로덕트
          </button>
          <span>/</span>
          {file ? (
            <>
              <button className="link" onClick={() => setFilePath(null)}>
                {product?.name ?? `#${productId}`}
              </button>
              <span>/</span>
              <span className="font-medium text-fg">{file.name}</span>
            </>
          ) : (
            <span className="font-medium text-fg">{product?.name ?? `#${productId}`}</span>
          )}
        </nav>
      ) : null}

      {/* L1: 프로덕트 목록 + 집계 */}
      {productId == null ? (
        <>
          {summaryLoading ? <p className="mb-3 text-sm text-muted">스캔 중…</p> : null}
          <div className="card overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-surface-2 text-left text-xs font-semibold uppercase tracking-wide text-muted">
                  <th className="px-4 py-3">이름</th>
                  <th className="px-4 py-3">프로덕트 ID</th>
                  <th className="px-4 py-3">모드</th>
                  <th className="px-4 py-3 text-right">대상 파일 수</th>
                  <th className="px-4 py-3 text-right">총 테스트 수</th>
                </tr>
              </thead>
              <tbody>
                {products.map((p) => (
                  <tr
                    key={p.product_id}
                    className="cursor-pointer border-t border-border transition hover:bg-surface-hover"
                    onClick={() => {
                      setProductId(p.product_id)
                      setFilePath(null)
                    }}
                  >
                    <td className="px-4 py-3 font-medium text-fg">{p.name}</td>
                    <td className="px-4 py-3 font-mono text-xs text-muted">{p.product_code}</td>
                    <td className="px-4 py-3">
                      <span className="badge badge-neutral">{p.test_generation_mode}</span>
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums text-fg">{p.target_file_count}</td>
                    <td className="px-4 py-3 text-right">
                      <span className={`badge ${p.total_test_count > 0 ? 'badge-primary' : 'badge-neutral'}`}>
                        {p.total_test_count}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!summaryLoading && products.length === 0 ? (
              <p className="px-4 py-6 text-sm text-subtle">등록된 프로덕트가 없습니다.</p>
            ) : null}
          </div>
        </>
      ) : null}

      {/* L2: 대상 파일 목록 + 합계 */}
      {productId != null && file == null ? (
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
              </div>
              <div className="card overflow-hidden">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-surface-2 text-left text-xs font-semibold uppercase tracking-wide text-muted">
                      <th className="px-4 py-3">파일명</th>
                      <th className="px-4 py-3">path</th>
                      <th className="px-4 py-3 text-right">테스트 개수</th>
                    </tr>
                  </thead>
                  <tbody>
                    {files.map((f) => (
                      <tr
                        key={f.path}
                        className="cursor-pointer border-t border-border transition hover:bg-surface-hover"
                        onClick={() => setFilePath(f.path)}
                      >
                        <td className="px-4 py-3 font-medium text-fg">{f.name}</td>
                        <td className="px-4 py-3 font-mono text-xs text-muted">{f.path}</td>
                        <td className="px-4 py-3 text-right">
                          <span className={`badge ${f.test_count > 0 ? 'badge-primary' : 'badge-neutral'}`}>
                            {f.test_count}
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

      {/* L3: 파일별 테스트 파일 목록 */}
      {file != null ? (
        <div className="card overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-surface-2 text-left text-xs font-semibold uppercase tracking-wide text-muted">
                <th className="px-4 py-3">테스트 파일명</th>
                <th className="px-4 py-3">path</th>
              </tr>
            </thead>
            <tbody>
              {file.test_files.map((t) => (
                <tr key={t.path} className="border-t border-border">
                  <td className="px-4 py-3 font-medium text-fg">{t.name}</td>
                  <td className="px-4 py-3 font-mono text-xs text-muted">{t.path}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {file.test_files.length === 0 ? (
            <p className="px-4 py-6 text-sm text-subtle">생성된 테스트 파일이 없습니다.</p>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}
