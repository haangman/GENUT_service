import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { PageHeader } from '../../components/PageHeader'
import { ProductForm } from './ProductForm'
import { createProduct, deleteProduct, listProducts } from '../../api/products'
import type { ProductFormValues } from './productSchema'

export function ProductsPage() {
  const queryClient = useQueryClient()
  const [showForm, setShowForm] = useState(false)

  const { data, isLoading, isError } = useQuery({
    queryKey: ['products'],
    queryFn: () => listProducts(),
  })

  const createMut = useMutation({
    mutationFn: (values: ProductFormValues) =>
      createProduct({
        ...values,
        patches: values.patches.map((patch, index) => ({ ...patch, order_index: index })),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['products'] })
      setShowForm(false)
    },
  })

  const deleteMut = useMutation({
    mutationFn: (id: number) => deleteProduct(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['products'] }),
  })

  return (
    <div>
      <PageHeader title="프로덕트" description="테스트 생성 대상 프로덕트를 등록/관리한다." />

      <button
        className="mb-4 rounded border px-3 py-1.5 text-sm font-medium"
        onClick={() => setShowForm((value) => !value)}
      >
        {showForm ? '닫기' : '새 프로덕트'}
      </button>

      {showForm ? (
        <div className="mb-4">
          <ProductForm onSubmit={(v) => createMut.mutate(v)} submitting={createMut.isPending} />
          {createMut.isError ? (
            <p role="alert" className="mt-2 text-sm text-red-600">
              생성에 실패했습니다.
            </p>
          ) : null}
        </div>
      ) : null}

      {isLoading ? <p className="text-sm text-gray-500">불러오는 중…</p> : null}
      {isError ? (
        <p role="alert" className="text-sm text-red-600">
          목록을 불러오지 못했습니다.
        </p>
      ) : null}

      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b text-left text-gray-500">
            <th className="py-2">이름</th>
            <th>프로덕트 ID</th>
            <th>모드</th>
            <th>repo</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {data?.items.map((product) => (
            <tr key={product.id} className="border-b">
              <td className="py-2 font-medium">{product.name}</td>
              <td>{product.product_code}</td>
              <td>{product.test_generation_mode}</td>
              <td className="text-gray-500">{product.git_url}</td>
              <td>
                <button
                  className="text-xs text-red-600"
                  onClick={() => deleteMut.mutate(product.id)}
                >
                  삭제
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
