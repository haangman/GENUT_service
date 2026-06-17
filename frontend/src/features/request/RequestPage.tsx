import { PageHeader } from '../../components/PageHeader'
import { FileTreePanel } from './FileTree'
import { ProductPicker } from './ProductPicker'
import { RequestActions } from './RequestActions'
import { SelectedFilesPanel } from './SelectedFilesPanel'
import { useRequestBuilder } from './store'

export function RequestPage() {
  const productId = useRequestBuilder((state) => state.productId)
  const lastSubmittedJobId = useRequestBuilder((state) => state.lastSubmittedJobId)

  return (
    <div>
      <PageHeader
        title="테스트 요청"
        description="프로덕트를 선택하고 소스 파일을 구성해 GENUT 테스트 생성을 요청한다."
      />
      {lastSubmittedJobId ? (
        <p className="mt-4 rounded border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-700">
          요청이 접수되었습니다. job #{lastSubmittedJobId}
        </p>
      ) : null}
      <ProductPicker />
      {productId ? (
        <>
          <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2">
            <FileTreePanel productId={productId} />
            <SelectedFilesPanel />
          </div>
          <RequestActions />
        </>
      ) : (
        <p className="mt-4 text-sm text-gray-500">프로덕트를 선택하세요.</p>
      )}
    </div>
  )
}
