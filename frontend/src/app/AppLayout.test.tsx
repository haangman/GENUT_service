import { describe, it, expect, afterEach } from 'vitest'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { AppLayout } from './AppLayout'
import { renderWithProviders } from '../test/utils'

afterEach(() => {
  document.documentElement.classList.remove('dark')
  // 언어 토글 테스트가 남긴 선택이 다른 테스트로 새지 않게 한다
  localStorage.removeItem('lang')
})

describe('AppLayout', () => {
  it('renders navigation links', () => {
    renderWithProviders(<AppLayout />)
    expect(screen.getByText('수동 실행 요청')).toBeInTheDocument()
    expect(screen.getByText('프로덕트 등록')).toBeInTheDocument()
    expect(screen.getByText('GENUT 등록')).toBeInTheDocument()
    expect(screen.getByText('수동 실행 이력')).toBeInTheDocument()
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

  it('toggles the UI language between Korean and English', async () => {
    renderWithProviders(<AppLayout />)

    // 기본은 한국어 → EN 버튼을 누르면 영문으로 전환
    await userEvent.click(screen.getByRole('button', { name: '영어로 전환' }))
    expect(screen.getByText('Product Registration')).toBeInTheDocument()
    expect(screen.getByText('Manual Run Request')).toBeInTheDocument()
    expect(localStorage.getItem('lang')).toBe('en')

    // 다시 누르면 한국어로 복귀
    await userEvent.click(screen.getByRole('button', { name: 'Switch to Korean' }))
    expect(screen.getByText('프로덕트 등록')).toBeInTheDocument()
    expect(localStorage.getItem('lang')).toBe('ko')
  })
})
