import { describe, it, expect } from 'vitest'
import { screen } from '@testing-library/react'
import { AppLayout } from './AppLayout'
import { renderWithProviders } from '../test/utils'

describe('AppLayout', () => {
  it('renders navigation links', () => {
    renderWithProviders(<AppLayout />)
    expect(screen.getByText('테스트 요청')).toBeInTheDocument()
    expect(screen.getByText('프로덕트')).toBeInTheDocument()
    expect(screen.getByText('GENUT')).toBeInTheDocument()
    expect(screen.getByText('모니터링')).toBeInTheDocument()
  })
})
