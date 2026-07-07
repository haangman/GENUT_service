import { describe, it, expect } from 'vitest'
import { screen } from '@testing-library/react'
import { StatusLayout } from './StatusLayout'
import { renderWithProviders } from '../test/utils'

describe('StatusLayout', () => {
  it('renders the brand, the page name and the toggles without the main nav', () => {
    renderWithProviders(<StatusLayout />)
    expect(screen.getByText('GENUT SERVICE')).toBeInTheDocument()
    expect(screen.getByText('테스트 파일 현황')).toBeInTheDocument()
    // 테마/언어 토글은 존재
    expect(screen.getByRole('button', { name: '영어로 전환' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '다크 모드로 전환' })).toBeInTheDocument()
    // 메인 네비게이션 항목은 없다(독립 단일 페이지)
    expect(screen.queryByText('프로덕트 등록')).not.toBeInTheDocument()
    expect(screen.queryByText('수동 실행 요청')).not.toBeInTheDocument()
  })
})
