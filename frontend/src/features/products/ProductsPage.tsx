import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { PageHeader } from '../../components/PageHeader'
import { ProductForm } from './ProductForm'
import {
  createAutoProduct,
  createProduct,
  deleteProduct,
  listProducts,
  updateAutoProduct,
  updateProduct,
} from '../../api/products'
import { ApiError } from '../../lib/apiClient'
import { useLang } from '../../lib/i18n'
import {
  DEFAULT_CMAKE_TEMPLATE,
  INTERVAL_UNIT_SECONDS,
  type ProductFormValues,
} from './productSchema'
import type { Product, ProductCreate } from '../../types/api'

function secondsToInterval(seconds: number | null): {
  value: number
  unit: ProductFormValues['auto_interval_unit']
} {
  if (!seconds) return { value: 24, unit: 'hours' }
  if (seconds % 86400 === 0) return { value: seconds / 86400, unit: 'days' }
  if (seconds % 3600 === 0) return { value: seconds / 3600, unit: 'hours' }
  return { value: Math.max(1, Math.round(seconds / 60)), unit: 'minutes' }
}

function toFormValues(product: Product): Partial<ProductFormValues> {
  const interval = secondsToInterval(product.auto_interval_seconds)
  return {
    project: product.project,
    name: product.name,
    product_code: product.product_code,
    git_url: product.git_url,
    git_ref: product.git_ref,
    git_update_mode: product.git_update_mode,
    compile_db_rel: product.compile_db_rel,
    out_tests_rel: product.out_tests_rel,
    cmake_configure_cmd: product.cmake_configure_cmd,
    cmake_build_cmd: product.cmake_build_cmd,
    test_run_cmd: product.test_run_cmd,
    test_generation_mode: product.test_generation_mode,
    code_path: product.code_path ?? '',
    exclude_patterns: (product.exclude_globs ?? []).join('\n'),
    patches: product.patches.map((patch) => ({ name: patch.name, content: patch.content })),
    auto_run: product.auto_run,
    auto_interval_value: interval.value,
    auto_interval_unit: interval.unit,
    cmake_template: product.cmake_template ?? DEFAULT_CMAKE_TEMPLATE,
  }
}

export function ProductsPage() {
  const { t } = useLang()
  const queryClient = useQueryClient()
  const [showForm, setShowForm] = useState(false)
  const [editing, setEditing] = useState<Product | null>(null)

  const { data, isLoading, isError } = useQuery({
    queryKey: ['products'],
    queryFn: () => listProducts(),
  })

  const onSaved = () => {
    queryClient.invalidateQueries({ queryKey: ['products'] })
    setShowForm(false)
    setEditing(null)
  }

  const saveMut = useMutation({
    mutationFn: ({ id, data }: { id: number | null; data: ProductCreate }) =>
      id == null ? createProduct(data) : updateProduct(id, data),
    onSuccess: onSaved,
  })

  // 자동 실행 프로덕트는 전용 엔드포인트(스캐폴딩 포함)로 생성/수정한다.
  const autoMut = useMutation({
    mutationFn: ({ id, data }: { id: number | null; data: ProductCreate }) =>
      id == null ? createAutoProduct(data) : updateAutoProduct(id, data),
    onSuccess: onSaved,
  })

  const deleteMut = useMutation({
    mutationFn: (id: number) => deleteProduct(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['products'] }),
    // 서버 거부(예: 실행 중 job 409)를 조용히 삼키지 않는다 — 사유를 그대로 보여준다
    onError: (error: unknown) => {
      const detail =
        error instanceof ApiError ? (error.body as { detail?: string } | null)?.detail : undefined
      window.alert(detail ? t(detail) : t('삭제에 실패했습니다.'))
    },
  })

  const confirmDelete = (product: Product) => {
    if (
      !window.confirm(
        t('{name} 프로덕트를 삭제할까요? 관련 job 이력도 함께 삭제됩니다.', { name: product.name }),
      )
    )
      return
    deleteMut.mutate(product.id)
  }

  const saving = saveMut.isPending || autoMut.isPending
  const saveError = saveMut.isError || autoMut.isError

  const handleSubmit = (values: ProductFormValues, autoFileList: string[]) => {
    const { exclude_patterns, auto_interval_value, auto_interval_unit, auto_run, cmake_template, ...rest } =
      values
    const base: ProductCreate = {
      ...rest,
      code_path: values.code_path.trim() || undefined,
      exclude_globs: exclude_patterns
        .split('\n')
        .map((line) => line.trim())
        .filter(Boolean),
      auto_run,
      patches: values.patches.map((patch, index) => ({ ...patch, order_index: index })),
    }
    // 자동 실행 모드 → 신규/수정 모두 전용 엔드포인트로(스캐폴딩 포함)
    if (auto_run) {
      autoMut.mutate({
        id: editing?.id ?? null,
        data: {
          ...base,
          auto_run: true,
          auto_interval_seconds: Math.round(
            auto_interval_value * INTERVAL_UNIT_SECONDS[auto_interval_unit],
          ),
          auto_file_list: autoFileList,
          cmake_template,
        },
      })
      return
    }
    saveMut.mutate({ id: editing?.id ?? null, data: base })
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
      <PageHeader title={t('프로덕트 등록')} description={t('테스트 생성 대상 프로덕트를 등록/관리한다.')} />

      <button
        className={`mb-5 ${showForm ? 'btn' : 'btn btn-primary'}`}
        onClick={showForm ? closeForm : openCreate}
      >
        {showForm ? t('닫기') : t('+ 새 프로덕트')}
      </button>

      {showForm ? (
        <div className="mb-6">
          <h3 className="mb-3 text-sm font-semibold text-fg">
            {editing ? t('수정: {name}', { name: editing.name }) : t('새 프로덕트')}
          </h3>
          <ProductForm
            key={editing?.id ?? 'new'}
            defaultValues={editing ? toFormValues(editing) : undefined}
            initialAutoFiles={editing?.auto_file_list}
            onSubmit={handleSubmit}
            submitting={saving}
          />
          {saveError ? (
            <p role="alert" className="mt-2 text-sm text-danger-fg">
              {t('저장에 실패했습니다.')}
            </p>
          ) : null}
        </div>
      ) : null}

      {isLoading ? <p className="text-sm text-muted">{t('불러오는 중…')}</p> : null}
      {isError ? (
        <p role="alert" className="text-sm text-danger-fg">
          {t('목록을 불러오지 못했습니다.')}
        </p>
      ) : null}

      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-surface-2 text-left text-xs font-semibold uppercase tracking-wide text-muted">
              <th className="px-4 py-3">{t('프로젝트')}</th>
              <th className="px-4 py-3">{t('이름')}</th>
              <th className="px-4 py-3">{t('프로덕트 ID')}</th>
              <th className="px-4 py-3">{t('모드')}</th>
              <th className="px-4 py-3">repo</th>
              <th className="px-4 py-3"></th>
            </tr>
          </thead>
          <tbody>
            {data?.items.map((product) => (
              <tr key={product.id} className="border-t border-border transition hover:bg-surface-hover">
                <td className="px-4 py-3">
                  <span className="badge badge-neutral">{product.project}</span>
                </td>
                <td className="px-4 py-3 font-medium text-fg">{product.name}</td>
                <td className="px-4 py-3 font-mono text-xs text-muted">{product.product_code}</td>
                <td className="space-x-1.5 px-4 py-3">
                  <span className="badge badge-neutral">{product.test_generation_mode}</span>
                  {product.auto_run ? (
                    <span
                      className="badge badge-primary"
                      title={
                        product.auto_interval_seconds
                          ? t('주기 {seconds}s', { seconds: product.auto_interval_seconds })
                          : undefined
                      }
                    >
                      auto
                    </span>
                  ) : null}
                </td>
                <td className="max-w-[280px] truncate px-4 py-3 text-muted">{product.git_url}</td>
                <td className="space-x-3 whitespace-nowrap px-4 py-3 text-right">
                  <button className="link text-xs" onClick={() => openEdit(product)}>
                    {t('수정')}
                  </button>
                  <button
                    className="text-xs font-medium text-danger-fg transition hover:opacity-80"
                    onClick={() => confirmDelete(product)}
                  >
                    {t('삭제')}
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
