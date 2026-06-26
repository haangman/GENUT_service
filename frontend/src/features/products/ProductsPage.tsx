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
    exclude_patterns: (product.exclude_globs ?? []).join('\n'),
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
    const { exclude_patterns, ...rest } = values
    const data: ProductCreate = {
      ...rest,
      code_path: values.code_path.trim() || undefined,
      exclude_globs: exclude_patterns
        .split('\n')
        .map((line) => line.trim())
        .filter(Boolean),
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
        className={`mb-5 ${showForm ? 'btn' : 'btn btn-primary'}`}
        onClick={showForm ? closeForm : openCreate}
      >
        {showForm ? '닫기' : '+ 새 프로덕트'}
      </button>

      {showForm ? (
        <div className="mb-6">
          <h3 className="mb-3 text-sm font-semibold text-fg">
            {editing ? `수정: ${editing.name}` : '새 프로덕트'}
          </h3>
          <ProductForm
            key={editing?.id ?? 'new'}
            defaultValues={editing ? toFormValues(editing) : undefined}
            onSubmit={handleSubmit}
            submitting={saveMut.isPending}
          />
          {saveMut.isError ? (
            <p role="alert" className="mt-2 text-sm text-danger-fg">
              저장에 실패했습니다.
            </p>
          ) : null}
        </div>
      ) : null}

      {isLoading ? <p className="text-sm text-muted">불러오는 중…</p> : null}
      {isError ? (
        <p role="alert" className="text-sm text-danger-fg">
          목록을 불러오지 못했습니다.
        </p>
      ) : null}

      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-surface-2 text-left text-xs font-semibold uppercase tracking-wide text-muted">
              <th className="px-4 py-3">이름</th>
              <th className="px-4 py-3">프로덕트 ID</th>
              <th className="px-4 py-3">모드</th>
              <th className="px-4 py-3">repo</th>
              <th className="px-4 py-3"></th>
            </tr>
          </thead>
          <tbody>
            {data?.items.map((product) => (
              <tr key={product.id} className="border-t border-border transition hover:bg-surface-hover">
                <td className="px-4 py-3 font-medium text-fg">{product.name}</td>
                <td className="px-4 py-3 font-mono text-xs text-muted">{product.product_code}</td>
                <td className="px-4 py-3">
                  <span className="badge badge-neutral">{product.test_generation_mode}</span>
                </td>
                <td className="max-w-[280px] truncate px-4 py-3 text-muted">{product.git_url}</td>
                <td className="space-x-3 whitespace-nowrap px-4 py-3 text-right">
                  <button className="link text-xs" onClick={() => openEdit(product)}>
                    수정
                  </button>
                  <button
                    className="text-xs font-medium text-danger-fg transition hover:opacity-80"
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
    </div>
  )
}
