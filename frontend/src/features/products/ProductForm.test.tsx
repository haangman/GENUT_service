import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
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
  patches: [],
}

describe('ProductForm', () => {
  it('shows validation errors and does not submit when empty', async () => {
    const onSubmit = vi.fn()
    render(<ProductForm onSubmit={onSubmit} />)
    await userEvent.click(screen.getByRole('button', { name: '저장' }))
    expect(await screen.findByText('이름을 입력하세요')).toBeInTheDocument()
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('submits valid values including patches', async () => {
    const onSubmit = vi.fn()
    render(
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
    render(<ProductForm onSubmit={vi.fn()} />)
    await userEvent.click(screen.getByRole('button', { name: '패치 추가' }))
    expect(screen.getByLabelText('패치 1 이름')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '삭제' }))
    expect(screen.queryByLabelText('패치 1 이름')).not.toBeInTheDocument()
  })
})
