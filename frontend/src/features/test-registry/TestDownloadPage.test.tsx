import { describe, it, expect, beforeEach, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { server } from '../../test/msw/server'
import { renderWithProviders } from '../../test/utils'
import { TestDownloadPage } from './TestDownloadPage'

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

describe('TestDownloadPage', () => {
  it('lists registered files and downloads selected ones as zip', async () => {
    let posted: { product_id: number; rel_paths: string[] } | null = null
    server.use(
      http.get('/api/products', () => HttpResponse.json(productsPage([{ id: 1, name: 'AA' }]))),
      http.get('/api/test-files', () =>
        HttpResponse.json([
          { id: 1, product_name: 'AA', rel_path: 'tests/generated/test_a.cpp' },
          { id: 2, product_name: 'AA', rel_path: 'tests/generated/test_b.cpp' },
        ]),
      ),
      http.post('/api/test-files/download', async ({ request }) => {
        posted = (await request.json()) as { product_id: number; rel_paths: string[] }
        return new HttpResponse('PK', { headers: { 'Content-Type': 'application/zip' } })
      }),
    )
    ;(URL as unknown as { createObjectURL: unknown }).createObjectURL = vi.fn(() => 'blob:mock')
    ;(URL as unknown as { revokeObjectURL: unknown }).revokeObjectURL = vi.fn()
    const clickSpy = vi
      .spyOn(HTMLAnchorElement.prototype, 'click')
      .mockImplementation(() => {})

    renderWithProviders(<TestDownloadPage />)
    await screen.findByRole('option', { name: 'AA' }, { timeout: 5000 })
    await userEvent.selectOptions(screen.getByLabelText('프로덕트'), 'AA')

    const row = await screen.findByRole(
      'checkbox',
      { name: 'tests/generated/test_a.cpp' },
      { timeout: 5000 },
    )
    await userEvent.click(row)
    await userEvent.click(screen.getByRole('button', { name: '다운로드 (zip)' }))

    await waitFor(() => expect(posted).not.toBeNull())
    expect(posted).toEqual({ product_id: 1, rel_paths: ['tests/generated/test_a.cpp'] })
    clickSpy.mockRestore()
  })

  it('removes selected files via DELETE /api/test-files', async () => {
    let deleted: { product_name: string; rel_paths: string[] } | null = null
    server.use(
      http.get('/api/products', () => HttpResponse.json(productsPage([{ id: 1, name: 'AA' }]))),
      http.get('/api/test-files', () =>
        HttpResponse.json([{ id: 1, product_name: 'AA', rel_path: 'tests/generated/test_a.cpp' }]),
      ),
      http.delete('/api/test-files', async ({ request }) => {
        deleted = (await request.json()) as { product_name: string; rel_paths: string[] }
        return HttpResponse.json({ removed: 1 })
      }),
    )

    renderWithProviders(<TestDownloadPage />)
    await screen.findByRole('option', { name: 'AA' }, { timeout: 5000 })
    await userEvent.selectOptions(screen.getByLabelText('프로덕트'), 'AA')

    const row = await screen.findByRole(
      'checkbox',
      { name: 'tests/generated/test_a.cpp' },
      { timeout: 5000 },
    )
    await userEvent.click(row)
    await userEvent.click(screen.getByRole('button', { name: '선택 삭제' }))

    await waitFor(() => expect(deleted).not.toBeNull())
    expect(deleted).toEqual({ product_name: 'AA', rel_paths: ['tests/generated/test_a.cpp'] })
  })
})
