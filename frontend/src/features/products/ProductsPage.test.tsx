import { describe, it, expect, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { server } from '../../test/msw/server'
import { renderWithProviders } from '../../test/utils'
import { ProductsPage } from './ProductsPage'

function product(id: number, name: string, mode = 'cpp', extra: Record<string, unknown> = {}) {
  return {
    id,
    project: 'Ulysses',
    name,
    product_code: `P-${id}`,
    git_url: `https://example.com/${name}.git`,
    git_ref: 'main',
    compile_db_rel: 'build',
    out_tests_rel: 'tests',
    cmake_configure_cmd: 'c',
    cmake_build_cmd: 'b',
    test_run_cmd: 'r',
    test_generation_mode: mode,
    active: true,
    code_path: null,
    auto_run: false,
    auto_interval_seconds: null,
    auto_file_list: [],
    cmake_template: null,
    patches: [],
    ...extra,
  }
}

describe('ProductsPage', () => {
  it('lists products from the API', async () => {
    server.use(
      http.get('/api/products', () =>
        HttpResponse.json({
          items: [product(1, 'alpha', 'c'), product(2, 'beta', 'cpp')],
          total: 2,
          page: 1,
          page_size: 50,
        }),
      ),
    )
    renderWithProviders(<ProductsPage />)
    expect(await screen.findByText('alpha')).toBeInTheDocument()
    expect(await screen.findByText('beta')).toBeInTheDocument()
  })

  it('edits an existing product via PUT with prefilled values', async () => {
    let putBody: Record<string, unknown> | null = null
    server.use(
      http.get('/api/products', () =>
        HttpResponse.json({ items: [product(1, 'alpha', 'c')], total: 1, page: 1, page_size: 50 }),
      ),
      http.put('/api/products/1', async ({ request }) => {
        putBody = (await request.json()) as Record<string, unknown>
        return HttpResponse.json(product(1, 'alpha-edited', 'c'))
      }),
    )
    renderWithProviders(<ProductsPage />)
    await screen.findByText('alpha')

    await userEvent.click(screen.getByRole('button', { name: '수정' }))
    const nameInput = screen.getByRole('textbox', { name: '이름' })
    expect(nameInput).toHaveValue('alpha') // 기존 값으로 채워짐
    await userEvent.clear(nameInput)
    await userEvent.type(nameInput, 'alpha-edited')
    await userEvent.click(screen.getByRole('button', { name: '저장' }))

    await waitFor(() => expect(putBody).not.toBeNull())
    expect(putBody!.name).toBe('alpha-edited')
  })

  it('edits an auto product via PUT /auto with the current file list', async () => {
    let autoPut: Record<string, unknown> | null = null
    const auto = product(1, 'AutoProd', 'cpp', {
      product_code: 'auto-x',
      code_path: '/x',
      auto_run: true,
      auto_interval_seconds: 3600,
      auto_file_list: ['src/aaa.c'],
      cmake_template: 'set(MODULE_TEST_NAME filename_UnitTest)\n',
    })
    server.use(
      http.get('/api/products', () =>
        HttpResponse.json({ items: [auto], total: 1, page: 1, page_size: 50 }),
      ),
      http.post('/api/products/target-files', () =>
        HttpResponse.json({ files: [{ path: 'src/aaa.c', excluded_by_pattern: false }] }),
      ),
      http.put('/api/products/1/auto', async ({ request }) => {
        autoPut = (await request.json()) as Record<string, unknown>
        return HttpResponse.json(auto)
      }),
    )
    renderWithProviders(<ProductsPage />)
    await screen.findByText('AutoProd')

    await userEvent.click(screen.getByRole('button', { name: '수정' }))
    // 자동 모드가 프리필되어 미리보기 목록이 로드된다
    expect(await screen.findByText('src/aaa.c', {}, { timeout: 3000 })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '저장' }))

    await waitFor(() => expect(autoPut).not.toBeNull())
    expect(autoPut!.auto_run).toBe(true)
    expect(autoPut!.auto_file_list).toEqual(['src/aaa.c'])
  })

  it('deletes only after the user confirms, and surfaces server rejections', async () => {
    let deleted = false
    server.use(
      http.get('/api/products', () =>
        HttpResponse.json({ items: [product(1, 'alpha', 'c')], total: 1, page: 1, page_size: 50 }),
      ),
      http.delete('/api/products/1', () => {
        deleted = true
        return new HttpResponse(null, { status: 204 })
      }),
    )
    const confirmSpy = vi.spyOn(window, 'confirm')
    renderWithProviders(<ProductsPage />)
    await screen.findByText('alpha')

    // 취소하면 삭제 요청을 보내지 않는다
    confirmSpy.mockReturnValueOnce(false)
    await userEvent.click(screen.getByRole('button', { name: '삭제' }))
    expect(deleted).toBe(false)

    // 확인하면 삭제한다
    confirmSpy.mockReturnValueOnce(true)
    await userEvent.click(screen.getByRole('button', { name: '삭제' }))
    await waitFor(() => expect(deleted).toBe(true))
    confirmSpy.mockRestore()
  })

  it('alerts with the server detail when delete is rejected', async () => {
    server.use(
      http.get('/api/products', () =>
        HttpResponse.json({ items: [product(1, 'alpha', 'c')], total: 1, page: 1, page_size: 50 }),
      ),
      http.delete('/api/products/1', () =>
        HttpResponse.json(
          { detail: '실행 중이거나 대기 중인 job이 있는 프로덕트는 삭제할 수 없다' },
          { status: 409 },
        ),
      ),
    )
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)
    const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => {})
    renderWithProviders(<ProductsPage />)
    await screen.findByText('alpha')

    await userEvent.click(screen.getByRole('button', { name: '삭제' }))
    await waitFor(() =>
      expect(alertSpy).toHaveBeenCalledWith(
        '실행 중이거나 대기 중인 job이 있는 프로덕트는 삭제할 수 없다',
      ),
    )
    confirmSpy.mockRestore()
    alertSpy.mockRestore()
  })
})
