import { describe, it, expect, beforeEach } from 'vitest'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { server } from '../../test/msw/server'
import { renderWithProviders } from '../../test/utils'
import { FileTreePanel } from './FileTree'
import { useRequestBuilder } from './store'

beforeEach(() => useRequestBuilder.getState().reset())

describe('FileTreePanel', () => {
  it('renders root entries and toggles file selection', async () => {
    server.use(
      http.get('/api/products/1/tree', ({ request }) => {
        const path = new URL(request.url).searchParams.get('path') ?? ''
        if (path === '') {
          return HttpResponse.json({
            entries: [
              { name: 'src', path: 'src', type: 'dir' },
              { name: 'main.cpp', path: 'main.cpp', type: 'file' },
            ],
          })
        }
        return HttpResponse.json({ entries: [] })
      }),
    )
    useRequestBuilder.getState().setProduct(1, 'cpp')
    renderWithProviders(<FileTreePanel productId={1} />)

    const checkbox = await screen.findByRole('checkbox', { name: 'main.cpp' })
    expect(useRequestBuilder.getState().selected).toEqual([])
    await userEvent.click(checkbox)
    expect(useRequestBuilder.getState().selected).toEqual(['main.cpp'])
  })
})
