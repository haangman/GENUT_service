import { useQuery } from '@tanstack/react-query'
import { listProducts } from '../../api/products'
import { useRequestBuilder } from './store'

export function ProductPicker() {
  const { data } = useQuery({ queryKey: ['products'], queryFn: () => listProducts() })
  const productId = useRequestBuilder((state) => state.productId)
  const setProduct = useRequestBuilder((state) => state.setProduct)
  const products = data?.items ?? []

  return (
    <div>
      <label htmlFor="product-picker" className="label">
        프로덕트
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
          프로덕트 선택…
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
