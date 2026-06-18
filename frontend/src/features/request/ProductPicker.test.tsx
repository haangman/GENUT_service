import { describe, it, expect } from 'vitest'
import { screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '../../test/msw/server'
import { renderWithProviders } from '../../test/utils'
import { ProductPicker } from './ProductPicker'

describe('ProductPicker', () => {
  it('shows product name with product_code so same-name products are distinguishable', async () => {
    server.use(
      http.get('/api/products', () =>
        HttpResponse.json({
          items: [
            { id: 1, name: 'AA', product_code: 'aa_0', test_generation_mode: 'cpp' },
            { id: 2, name: 'AA', product_code: 'aa_1', test_generation_mode: 'cpp' },
          ],
          total: 2,
          page: 1,
          page_size: 50,
        }),
      ),
    )

    renderWithProviders(<ProductPicker />)
    // 같은 이름(AA)이지만 "이름(프로덕트 코드)"로 구분되어 두 옵션이 모두 표시된다
    expect(await screen.findByRole('option', { name: 'AA(aa_0)' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'AA(aa_1)' })).toBeInTheDocument()
  })
})
