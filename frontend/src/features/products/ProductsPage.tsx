import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { PageHeader } from '../../components/PageHeader'
import { ProductForm } from './ProductForm'
import { createProduct, deleteProduct, listProducts, updateProduct } from '../../api/products'
import type { ProductFormValues } from './productSchema'
import type { Product, ProductCreate } from '../../types/api'

function toFormValues(product: Product): Partial<ProductFormValues> {
  return {
    name: product.name,
    product_code: product.product_code,
    git_url: product.git_url,
    git_ref: product.git_ref,
    compile_db_rel: product.compile_db_rel,
    out_tests_rel: product.out_tests_rel,
    cmake_configure_cmd: product.cmake_configure_cmd,
    cmake_build_cmd: product.cmake_build_cmd,
    test_run_cmd: product.test_run_cmd,
    test_generation_mode: product.test_generation_mode,
    code_path: product.code_path ?? '',
    patches: product.patches.map((patch) => ({ name: patch.name, content: patch.content })),
  }
}

export function ProductsPage() {
  const queryClient = useQueryClient()
  const [showForm, setShowForm] = useState(false)
  const [editing, setEditing] = useState<Product | null>(null)

  const { data, isLoading, isError } = useQuery({
    queryKey: ['products'],
    queryFn: () => listProducts(),
  })

  const saveMut = useMutation({
    mutationFn: ({ id, data }: { id: number | null; data: ProductCreate }) =>
      id == null ? createProduct(data) : updateProduct(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['products'] })
      setShowForm(false)
      setEditing(null)
    },
  })

  const deleteMut = useMutation({
    mutationFn: (id: number) => deleteProduct(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['products'] }),
  })

  const handleSubmit = (values: ProductFormValues) => {
    const data: ProductCreate = {
      ...values,
      code_path: values.code_path.trim() || undefined,
      patches: values.patches.map((patch, index) => ({ ...patch, order_index: index })),
    }
    saveMut.mutate({ id: editing?.id ?? null, data })
  }

  const openCreate = () => {
    setEditing(null)
    setShowForm(true)
  }
  const openEdit = (product: Product) => {
    setEditing(product)
    setShowForm(true)
  }
  const closeForm = () => {
    setShowForm(false)
    setEditing(null)
  }

  return (
    <div>
      <PageHeader title="프로덕트" description="테스트 생성 대상 프로덕트를 등록/관리한다." />

      <button
        className="mb-4 rounded border px-3 py-1.5 text-sm font-medium"
        onClick={showForm ? closeForm : openCreate}
      >
        {showForm ? '닫기' : '새 프로덕트'}
      </button>

      {showForm ? (
        <div className="mb-4">
          <h3 className="mb-2 text-sm font-semibold">
            {editing ? `수정: ${editing.name}` : '새 프로덕트'}
          </h3>
          <ProductForm
            key={editing?.id ?? 'new'}
            defaultValues={editing ? toFormValues(editing) : undefined}
            onSubmit={handleSubmit}
            submitting={saveMut.isPending}
          />
          {saveMut.isError ? (
            <p role="alert" className="mt-2 text-sm text-red-600">
              저장에 실패했습니다.
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
              <td className="space-x-2 whitespace-nowrap">
                <button className="text-xs text-blue-600" onClick={() => openEdit(product)}>
                  수정
                </button>
                <button className="text-xs text-red-600" onClick={() => deleteMut.mutate(product.id)}>
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
