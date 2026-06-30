import { describe, it, expect, vi } from 'vitest'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { server } from '../../test/msw/server'
import { renderWithProviders } from '../../test/utils'
import { ProductForm } from './ProductForm'
import type { ProductFormValues } from './productSchema'

const VALID: ProductFormValues = {
  name: 'demo',
  product_code: 'P-1',
  git_url: 'https://example.com/repo.git',
  git_ref: 'main',
  compile_db_rel: 'build',
  out_tests_rel: 'tests',
  cmake_configure_cmd: 'cmake -S . -B build',
  cmake_build_cmd: 'cmake --build build',
  test_run_cmd: 'ctest',
  test_generation_mode: 'cpp',
  code_path: '',
  exclude_patterns: '',
  patches: [],
  auto_run: false,
  auto_interval_value: 24,
  auto_interval_unit: 'hours',
  cmake_template: 'set(MODULE_TEST_NAME filename_UnitTest)\n',
}

describe('ProductForm', () => {
  it('shows validation errors and does not submit when empty', async () => {
    const onSubmit = vi.fn()
    renderWithProviders(<ProductForm onSubmit={onSubmit} />)
    await userEvent.click(screen.getByRole('button', { name: '저장' }))
    expect(await screen.findByText('이름을 입력하세요')).toBeInTheDocument()
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('submits valid values including patches', async () => {
    const onSubmit = vi.fn()
    renderWithProviders(
      <ProductForm
        onSubmit={onSubmit}
        defaultValues={{ ...VALID, patches: [{ name: 'p0', content: 'diff0' }] }}
      />,
    )
    await userEvent.click(screen.getByRole('button', { name: '저장' }))
    expect(onSubmit).toHaveBeenCalledTimes(1)
    const values = onSubmit.mock.calls[0][0]
    expect(values.name).toBe('demo')
    expect(values.patches).toHaveLength(1)
    expect(values.patches[0].name).toBe('p0')
  })

  it('adds and removes patch rows', async () => {
    renderWithProviders(<ProductForm onSubmit={vi.fn()} />)
    await userEvent.click(screen.getByRole('button', { name: '패치 추가' }))
    expect(screen.getByLabelText('패치 1 이름')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '삭제' }))
    expect(screen.queryByLabelText('패치 1 이름')).not.toBeInTheDocument()
  })

  it('auto mode reveals interval/template, lists target files, and requires auto prefix', async () => {
    server.use(
      http.post('/api/products/target-files', () =>
        HttpResponse.json({
          files: [
            { path: 'src/aaa.c', excluded_by_pattern: false },
            { path: 'src/bbb.c', excluded_by_pattern: true },
          ],
        }),
      ),
    )
    const onSubmit = vi.fn()
    renderWithProviders(
      <ProductForm
        onSubmit={onSubmit}
        defaultValues={{ ...VALID, code_path: '/x', compile_db_rel: 'build' }}
      />,
    )

    await userEvent.click(screen.getByRole('checkbox'))
    // 주기 입력 + 템플릿 편집기 노출
    expect(screen.getByLabelText('자동 수행 주기')).toBeInTheDocument()
    expect(screen.getByLabelText(/CMakeLists.txt 양식/)).toBeInTheDocument()

    // 디바운스 후 미리보기 목록(패턴 제외 표시 포함)
    expect(await screen.findByText('src/aaa.c', {}, { timeout: 3000 })).toBeInTheDocument()
    expect(screen.getByText('src/bbb.c')).toBeInTheDocument()
    expect(screen.getByText(/제외됨 \(패턴\)/)).toBeInTheDocument()

    // product_code가 auto로 시작하지 않으면 저장 차단
    await userEvent.click(screen.getByRole('button', { name: '저장' }))
    expect(
      await screen.findByText("자동 실행 모드의 ID는 'auto'로 시작해야 합니다"),
    ).toBeInTheDocument()
    expect(onSubmit).not.toHaveBeenCalled()
  })
})
