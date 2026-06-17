import { describe, it, expect, beforeEach } from 'vitest'
import { screen } from '@testing-library/react'
import { renderWithProviders } from '../../test/utils'
import { RequestPage } from './RequestPage'
import { useRequestBuilder } from './store'

beforeEach(() => useRequestBuilder.getState().reset())

describe('RequestPage', () => {
  it('prompts to select a product when none is chosen', async () => {
    renderWithProviders(<RequestPage />)
    expect(await screen.findByText('프로덕트를 선택하세요.')).toBeInTheDocument()
  })

  it('shows the submission banner on the initial screen after a request', async () => {
    useRequestBuilder.getState().completeSubmission(42)
    renderWithProviders(<RequestPage />)
    // 초기 화면(프로덕트 미선택)으로 복귀하면서 접수 안내가 함께 표시된다
    expect(await screen.findByText('요청이 접수되었습니다. job #42')).toBeInTheDocument()
    expect(screen.getByText('프로덕트를 선택하세요.')).toBeInTheDocument()
  })

  it('resets the builder when leaving the page (tab navigation)', () => {
    useRequestBuilder.getState().setProduct(1, 'cpp')
    useRequestBuilder.getState().addPaths(['src/a.cpp'])
    useRequestBuilder.getState().completeSubmission(9)
    const { unmount } = renderWithProviders(<RequestPage />)
    unmount()
    const state = useRequestBuilder.getState()
    expect(state.productId).toBeNull()
    expect(state.selected).toEqual([])
    expect(state.lastSubmittedJobId).toBeNull()
  })
})
