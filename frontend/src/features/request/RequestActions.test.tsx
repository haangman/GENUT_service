import { describe, it, expect, beforeEach } from 'vitest'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { server } from '../../test/msw/server'
import { renderWithProviders } from '../../test/utils'
import { RequestActions } from './RequestActions'
import { useRequestBuilder } from './store'

beforeEach(() => useRequestBuilder.getState().reset())

describe('RequestActions', () => {
  it('checks compile_commands, then submits only after a successful check', async () => {
    server.use(
      http.post('/api/products/1/compile-check', () =>
        HttpResponse.json({ included: ['src/a.cpp'], excluded: ['src/b.cpp'] }),
      ),
      http.post('/api/jobs', () =>
        HttpResponse.json({
          id: 7,
          product_id: 1,
          genut_instance_id: null,
          status: 'queued',
          function_name: null,
          file_list: ['src/a.cpp'],
          excluded_files: ['src/b.cpp'],
          attempt: 0,
          submitted_at: '2026-06-15T00:00:00Z',
          started_at: null,
          finished_at: null,
          result_summary: null,
          error: null,
        }),
      ),
    )

    useRequestBuilder.getState().setProduct(1, 'cpp')
    useRequestBuilder.getState().addPaths(['src/a.cpp', 'src/b.cpp'])
    renderWithProviders(<RequestActions />)

    // 검사 전에는 제출 비활성
    expect(screen.getByRole('button', { name: '제출' })).toBeDisabled()

    await userEvent.click(screen.getByRole('button', { name: 'compile_commands 검사' }))
    expect(await screen.findByText('src/a.cpp')).toBeInTheDocument()
    expect(screen.getByText('src/b.cpp')).toBeInTheDocument()

    const submit = screen.getByRole('button', { name: '제출' })
    expect(submit).toBeEnabled()
    await userEvent.click(submit)
    expect(await screen.findByText(/job #7/)).toBeInTheDocument()
  })
})
