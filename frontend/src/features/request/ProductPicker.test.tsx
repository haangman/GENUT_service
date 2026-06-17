import { describe, it, expect } from 'vitest'
import { screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '../../test/msw/server'
import { renderWithProviders } from '../../test/utils'
import { ProductPicker } from './ProductPicker'

describe('ProductPicker', () => {
  it('shows product name with id so same-name products are distinguishable', async () => {
    server.use(
      http.get('/api/products', () =>
        HttpResponse.json({
          items: [
            { id: 1, name: 'dup', test_generation_mode: 'cpp' },
            { id: 2, name: 'dup', test_generation_mode: 'cpp' },
          ],
          total: 2,
          page: 1,
          page_size: 50,
        }),
      ),
    )

    renderWithProviders(<ProductPicker />)
    // 같은 이름(dup)이지만 "이름(아이디)"로 구분되어 두 옵션이 모두 표시된다
    expect(await screen.findByRole('option', { name: 'dup(1)' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'dup(2)' })).toBeInTheDocument()
  })
})
