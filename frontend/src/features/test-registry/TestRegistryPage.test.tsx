import { describe, it, expect, beforeEach, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { server } from '../../test/msw/server'
import { renderWithProviders } from '../../test/utils'
import { TestRegistryPage } from './TestRegistryPage'

function productsPage(items: Array<{ id: number; name: string }>) {
  return {
    items: items.map((p) => ({
      id: p.id,
      name: p.name,
      product_code: `${p.name}-${p.id}`,
      git_url: 'u',
      git_ref: 'main',
      compile_db_rel: 'build',
      out_tests_rel: 'tests/generated',
      cmake_configure_cmd: 'c',
      cmake_build_cmd: 'b',
      test_run_cmd: 'r',
      test_generation_mode: 'cpp',
      active: true,
      code_path: null,
      patches: [],
    })),
    total: items.length,
    page: 1,
    page_size: 50,
  }
}

beforeEach(() => {
  vi.spyOn(window, 'alert').mockImplementation(() => {})
})

describe('TestRegistryPage', () => {
  it('registers a selected file via POST /api/test-files', async () => {
    let posted: { product_name: string; rel_paths: string[] } | null = null
    server.use(
      http.get('/api/products', () => HttpResponse.json(productsPage([{ id: 1, name: 'AA' }]))),
      http.get('/api/products/1/tree', () =>
        HttpResponse.json({
          entries: [{ name: 'test_a.cpp', path: 'tests/generated/test_a.cpp', type: 'file' }],
        }),
      ),
      http.post('/api/test-files', async ({ request }) => {
        posted = (await request.json()) as { product_name: string; rel_paths: string[] }
        return HttpResponse.json(
          posted.rel_paths.map((rel, i) => ({ id: i + 1, product_name: 'AA', rel_path: rel })),
          { status: 201 },
        )
      }),
    )

    renderWithProviders(<TestRegistryPage />)
    await screen.findByRole('option', { name: 'AA' }, { timeout: 5000 })
    await userEvent.selectOptions(screen.getByLabelText('프로덕트'), 'AA')

    const checkbox = await screen.findByRole('checkbox', { name: 'test_a.cpp' }, { timeout: 5000 })
    await userEvent.click(checkbox)
    await userEvent.click(screen.getByRole('button', { name: '등록' }))

    await waitFor(() => expect(posted).not.toBeNull())
    expect(posted).toEqual({ product_name: 'AA', rel_paths: ['tests/generated/test_a.cpp'] })
  })
})
