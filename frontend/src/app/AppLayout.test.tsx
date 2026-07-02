import { describe, it, expect, afterEach } from 'vitest'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { AppLayout } from './AppLayout'
import { renderWithProviders } from '../test/utils'

afterEach(() => document.documentElement.classList.remove('dark'))

describe('AppLayout', () => {
  it('renders navigation links', () => {
    renderWithProviders(<AppLayout />)
    expect(screen.getByText('테스트 요청')).toBeInTheDocument()
    expect(screen.getByText('프로덕트')).toBeInTheDocument()
    expect(screen.getByText('GENUT')).toBeInTheDocument()
    expect(screen.getByText('모니터링')).toBeInTheDocument()
    expect(screen.getByText('자동 실행 이력')).toBeInTheDocument()
  })

  it('toggles dark mode on the document element', async () => {
    document.documentElement.classList.remove('dark')
    renderWithProviders(<AppLayout />)

    await userEvent.click(screen.getByRole('button', { name: '다크 모드로 전환' }))
    expect(document.documentElement.classList.contains('dark')).toBe(true)

    // 토글 후 라벨이 라이트 모드 전환으로 바뀐다
    await userEvent.click(screen.getByRole('button', { name: '라이트 모드로 전환' }))
    expect(document.documentElement.classList.contains('dark')).toBe(false)
  })
})
