import { describe, it, expect, vi, afterEach } from 'vitest'
import { fireEvent, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '../../test/msw/server'
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

describe('JobTable (대상 컬럼)', () => {
  it('로그를 열지 않아도 대상 파일·함수를 행에서 바로 확인할 수 있다', () => {
    const jobs = [
      makeJob(1, { file_list: ['src/parser.c'], function_name: 'parse_line' }),
      makeJob(2, { file_list: ['src/math/vector2d.cpp'], function_name: null }),
      makeJob(3, { file_list: ['src/main.c', 'src/a.c', 'src/b.c'], function_name: null }),
      makeJob(4, { kind: 'auto_scan', file_list: [], function_name: null }),
    ]
    renderWithProviders(<JobTable jobs={jobs} showKind />)

    expect(screen.getByRole('columnheader', { name: '대상' })).toBeInTheDocument()
    // 함수 지정 job은 함수명까지, 파일 전체 job은 파일명만
    expect(screen.getByText('parser.c :: parse_line')).toBeInTheDocument()
    expect(screen.getByText('vector2d.cpp')).toBeInTheDocument()
    expect(screen.getByText('main.c 외 2개')).toBeInTheDocument()
    // 대상 파일이 없는 준비 job은 '-'
    expect(screen.getAllByText('-').length).toBeGreaterThan(0)
  })

  it('잘린 파일명의 전체 경로는 툴팁으로 남는다', () => {
    renderWithProviders(
      <JobTable jobs={[makeJob(5, { file_list: ['src/deep/nested/parser.c'], function_name: 'fn' })]} />,
    )
    expect(screen.getByText('parser.c :: fn')).toHaveAttribute('title', 'src/deep/nested/parser.c')
  })
})

describe('JobTable (job 삭제)', () => {
  afterEach(() => vi.restoreAllMocks())

  it('종결 job 행에만 삭제 버튼이 보이고, confirm 수락 시 DELETE를 호출한다', async () => {
    let deletedId: string | null = null
    server.use(
      http.delete('/api/jobs/:id', ({ params }) => {
        deletedId = params.id as string
        return new HttpResponse(null, { status: 204 })
      }),
    )
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    const jobs = [makeJob(11, { status: 'done' }), makeJob(12, { status: 'running', finished_at: null })]
    renderWithProviders(<JobTable jobs={jobs} />)

    // 실행 중 행은 강제 종료만, 종결 행은 삭제만 보인다
    const deleteButtons = screen.getAllByRole('button', { name: '삭제' })
    expect(deleteButtons).toHaveLength(1)
    expect(screen.getByRole('button', { name: '강제 종료' })).toBeInTheDocument()

    fireEvent.click(deleteButtons[0])
    expect(window.confirm).toHaveBeenCalled()
    await waitFor(() => expect(deletedId).toBe('11'))
  })

  it('confirm 거절 시 DELETE를 호출하지 않는다', () => {
    let called = false
    server.use(
      http.delete('/api/jobs/:id', () => {
        called = true
        return new HttpResponse(null, { status: 204 })
      }),
    )
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    renderWithProviders(<JobTable jobs={[makeJob(21, { status: 'failed' })]} />)

    fireEvent.click(screen.getByRole('button', { name: '삭제' }))
    expect(called).toBe(false)
  })

  it('삭제 실패 시 서버 사유를 알림으로 보여준다', async () => {
    server.use(
      http.delete('/api/jobs/:id', () =>
        HttpResponse.json({ detail: '완료된 job만 삭제할 수 있다' }, { status: 409 }),
      ),
    )
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => {})
    renderWithProviders(<JobTable jobs={[makeJob(31, { status: 'canceled' })]} />)

    fireEvent.click(screen.getByRole('button', { name: '삭제' }))
    await waitFor(() =>
      expect(alertSpy).toHaveBeenCalledWith(expect.stringContaining('완료된 job만')),
    )
  })
})
