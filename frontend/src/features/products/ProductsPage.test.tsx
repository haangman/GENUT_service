import { describe, it, expect } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { server } from '../../test/msw/server'
import { renderWithProviders } from '../../test/utils'
import { ProductsPage } from './ProductsPage'

function product(id: number, name: string, mode = 'cpp') {
  return {
    id,
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
    patches: [],
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
})
