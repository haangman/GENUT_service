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
})
