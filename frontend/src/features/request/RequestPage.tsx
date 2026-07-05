import { useEffect } from 'react'
import { PageHeader } from '../../components/PageHeader'
import { FileTreePanel } from './FileTree'
import { ProductPicker } from './ProductPicker'
import { RequestActions } from './RequestActions'
import { SelectedFilesPanel } from './SelectedFilesPanel'
import { useRequestBuilder } from './store'

export function RequestPage() {
  const productId = useRequestBuilder((state) => state.productId)
  const lastSubmittedJobId = useRequestBuilder((state) => state.lastSubmittedJobId)

  // 페이지를 떠날 때 요청 빌더를 초기화한다 → 테스트 요청 탭으로 다시 들어오면 항상 초기 모습.
  useEffect(() => () => useRequestBuilder.getState().reset(), [])

  return (
    <div>
      <PageHeader
        title="수동 실행 요청"
        description="프로덕트를 선택하고 소스 파일을 구성해 GENUT 테스트 생성을 요청한다."
      />
      {lastSubmittedJobId ? (
        <p className="mb-5 rounded-lg border border-success bg-success-soft px-4 py-2.5 text-sm font-medium text-success-fg">
          요청이 접수되었습니다. job #{lastSubmittedJobId}
        </p>
      ) : null}
      <ProductPicker />
      {productId ? (
        <>
          <div className="mt-5 grid grid-cols-1 gap-4 md:grid-cols-2">
            <FileTreePanel productId={productId} />
            <SelectedFilesPanel />
          </div>
          <RequestActions />
        </>
      ) : (
        <p className="mt-5 text-sm text-muted">프로덕트를 선택하세요.</p>
      )}
    </div>
  )
}
