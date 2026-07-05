import { describe, it, expect, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { Pagination, pageWindow } from './Pagination'

describe('pageWindow', () => {
  it('10페이지 블록 단위로 번호를 만든다', () => {
    expect(pageWindow(1, 50)).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
    expect(pageWindow(10, 50)).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
    expect(pageWindow(13, 50)).toEqual([11, 12, 13, 14, 15, 16, 17, 18, 19, 20])
    expect(pageWindow(45, 47)).toEqual([41, 42, 43, 44, 45, 46, 47]) // 마지막 블록은 잘림
    expect(pageWindow(1, 1)).toEqual([1])
  })
})

describe('Pagination', () => {
  it('페이지가 1개면 아무것도 그리지 않는다', () => {
    const { container } = render(<Pagination page={1} totalPages={1} onChange={vi.fn()} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('번호·화살표로 페이지를 이동하고 현재 페이지를 표시한다', () => {
    const onChange = vi.fn()
    render(<Pagination page={3} totalPages={50} onChange={onChange} />)

    // 현재 페이지 강조(aria-current)
    expect(screen.getByRole('button', { name: '3' })).toHaveAttribute('aria-current', 'page')

    fireEvent.click(screen.getByRole('button', { name: '7' }))
    expect(onChange).toHaveBeenLastCalledWith(7)
    fireEvent.click(screen.getByRole('button', { name: '이전 페이지' }))
    expect(onChange).toHaveBeenLastCalledWith(2)
    fireEvent.click(screen.getByRole('button', { name: '다음 페이지' }))
    expect(onChange).toHaveBeenLastCalledWith(4)
    fireEvent.click(screen.getByRole('button', { name: '첫 페이지' }))
    expect(onChange).toHaveBeenLastCalledWith(1)
    fireEvent.click(screen.getByRole('button', { name: '마지막 페이지' }))
    expect(onChange).toHaveBeenLastCalledWith(50)
  })

  it('양 끝에서는 해당 방향 화살표가 비활성화된다', () => {
    render(<Pagination page={1} totalPages={5} onChange={vi.fn()} />)
    expect(screen.getByRole('button', { name: '첫 페이지' })).toBeDisabled()
    expect(screen.getByRole('button', { name: '이전 페이지' })).toBeDisabled()
    expect(screen.getByRole('button', { name: '다음 페이지' })).toBeEnabled()
    expect(screen.getByRole('button', { name: '마지막 페이지' })).toBeEnabled()
  })
})
