import { describe, it, expect } from 'vitest'
import { fireEvent, screen } from '@testing-library/react'
import { renderWithProviders } from '../../test/utils'
import type { Job } from '../../types/api'
import { JobTable } from './JobTable'

function makeJob(id: number, overrides: Partial<Job> = {}): Job {
  return {
    id,
    product_id: 1,
    product_name: 'prod-a',
    genut_instance_id: null,
    genut_name: null,
    status: 'done',
    kind: 'genut',
    origin: 'auto',
    function_name: null,
    file_list: ['src/aaa.c'],
    excluded_files: [],
    attempt: 0,
    submitted_at: '2026-06-15T00:00:00Z',
    started_at: '2026-06-15T00:00:00Z',
    finished_at: '2026-06-15T00:01:00Z',
    result_summary: `summary-${id}`,
    error: null,
    ...overrides,
  }
}

describe('JobTable (대량 이력 청크 렌더링)', () => {
  it('행을 200개 단위로 렌더링하고 더 보기로 늘려간다', () => {
    const jobs = Array.from({ length: 450 }, (_, index) => makeJob(10_000 - index))
    renderWithProviders(<JobTable jobs={jobs} />)

    // 처음에는 청크(200)만 DOM에 올린다 — 수천 행을 통째로 그리면 페이지가 버벅인다
    expect(screen.getByText('summary-10000')).toBeInTheDocument()
    expect(screen.getByText('summary-9801')).toBeInTheDocument() // 200번째
    expect(screen.queryByText('summary-9800')).toBeNull() // 201번째는 아직 미렌더

    const more = screen.getByRole('button', { name: '더 보기 (200/450)' })
    fireEvent.click(more)
    expect(screen.getByText('summary-9800')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '더 보기 (400/450)' })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '더 보기 (400/450)' }))
    expect(screen.getByText('summary-9551')).toBeInTheDocument() // 마지막 행(450번째)
    expect(screen.queryByRole('button', { name: /더 보기/ })).toBeNull() // 전부 표시됨
  })

  it('청크 이하의 목록은 더 보기 없이 전부 렌더링한다', () => {
    const jobs = Array.from({ length: 3 }, (_, index) => makeJob(100 - index))
    renderWithProviders(<JobTable jobs={jobs} />)
    expect(screen.getByText('summary-98')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /더 보기/ })).toBeNull()
  })
})
