import { describe, it, expect, beforeEach } from 'vitest'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { server } from '../../test/msw/server'
import { renderWithProviders } from '../../test/utils'
import { ProductPicker } from './ProductPicker'
import { useRequestBuilder } from './store'

describe('ProductPicker', () => {
  beforeEach(() => {
    // zustand 스토어는 모듈 전역이라 테스트 간 상태가 새지 않게 초기화한다
    useRequestBuilder.setState({ project: 'Ulysses', productId: null, selected: [] })
  })

  it('shows product name with product_code so same-name products are distinguishable', async () => {
    server.use(
      http.get('/api/products', () =>
        HttpResponse.json({
          items: [
            { id: 1, project: 'Ulysses', name: 'AA', product_code: 'aa_0', test_generation_mode: 'cpp' },
            { id: 2, project: 'Ulysses', name: 'AA', product_code: 'aa_1', test_generation_mode: 'cpp' },
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

  it('filters products by the selected project and resets the selection on change', async () => {
    server.use(
      http.get('/api/products', () =>
        HttpResponse.json({
          items: [
            { id: 1, project: 'Ulysses', name: 'AA', product_code: 'aa_u', test_generation_mode: 'cpp' },
            { id: 2, project: 'Thetis', name: 'AA', product_code: 'aa_t', test_generation_mode: 'cpp' },
          ],
          total: 2,
          page: 1,
          page_size: 50,
        }),
      ),
    )

    renderWithProviders(<ProductPicker />)
    // 기본 프로젝트(Ulysses)의 프로덕트만 노출된다
    expect(await screen.findByRole('option', { name: 'AA(aa_u)' })).toBeInTheDocument()
    expect(screen.queryByRole('option', { name: 'AA(aa_t)' })).not.toBeInTheDocument()

    // 프로덕트를 고른 뒤 프로젝트를 바꾸면 목록이 전환되고 선택이 리셋된다
    await userEvent.selectOptions(screen.getByLabelText('프로덕트'), '1')
    expect(useRequestBuilder.getState().productId).toBe(1)
    await userEvent.selectOptions(screen.getByLabelText('프로젝트'), 'Thetis')
    expect(await screen.findByRole('option', { name: 'AA(aa_t)' })).toBeInTheDocument()
    expect(screen.queryByRole('option', { name: 'AA(aa_u)' })).not.toBeInTheDocument()
    expect(useRequestBuilder.getState().productId).toBeNull()
  })
})
