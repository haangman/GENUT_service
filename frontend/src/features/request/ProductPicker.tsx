import { useQuery } from '@tanstack/react-query'
import { listProducts } from '../../api/products'
import { useRequestBuilder } from './store'
import { useLang } from '../../lib/i18n'
import { ProjectSelect } from '../../components/ProjectSelect'

export function ProductPicker() {
  const { t } = useLang()
  const { data } = useQuery({ queryKey: ['products'], queryFn: () => listProducts() })
  const project = useRequestBuilder((state) => state.project)
  const setProject = useRequestBuilder((state) => state.setProject)
  const productId = useRequestBuilder((state) => state.productId)
  const setProduct = useRequestBuilder((state) => state.setProduct)
  // 선택된 프로젝트의 프로덕트만 노출한다(전량 로드 후 클라이언트 필터)
  const products = (data?.items ?? []).filter((p) => p.project === project)

  return (
    <div className="space-y-3">
      <ProjectSelect value={project} onChange={setProject} id="request-project" />
      <label htmlFor="product-picker" className="label">
        {t('프로덕트')}
      </label>
      <select
        id="product-picker"
        className="input max-w-xs"
        value={productId ?? ''}
        onChange={(event) => {
          const id = Number(event.target.value)
          const product = products.find((p) => p.id === id)
          if (product) setProduct(product.id, product.test_generation_mode)
        }}
      >
        <option value="" disabled>
          {t('프로덕트 선택…')}
        </option>
        {products.map((product) => (
          <option key={product.id} value={product.id}>
            {product.name}({product.product_code})
          </option>
        ))}
      </select>
    </div>
  )
}
