import { PageHeader } from '../../components/PageHeader'
import { FileTreePanel } from './FileTree'
import { ProductPicker } from './ProductPicker'
import { SelectedFilesPanel } from './SelectedFilesPanel'
import { useRequestBuilder } from './store'

export function RequestPage() {
  const productId = useRequestBuilder((state) => state.productId)

  return (
    <div>
      <PageHeader
        title="테스트 요청"
        description="프로덕트를 선택하고 소스 파일을 구성해 GENUT 테스트 생성을 요청한다."
      />
      <ProductPicker />
      {productId ? (
        <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2">
          <FileTreePanel productId={productId} />
          <SelectedFilesPanel />
        </div>
      ) : (
        <p className="mt-4 text-sm text-gray-500">프로덕트를 선택하세요.</p>
      )}
    </div>
  )
}
