import { describe, it, expect } from 'vitest'
import { screen } from '@testing-library/react'
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
})
