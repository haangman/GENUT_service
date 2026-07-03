import { describe, it, expect } from 'vitest'
import { fireEvent, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '../../test/msw/server'
import { renderWithProviders } from '../../test/utils'
import { ManualJobsPage } from './ManualJobsPage'

function job(overrides: Record<string, unknown> = {}) {
  return {
    id: 5,
    product_id: 2,
    genut_instance_id: 1,
    status: 'done',
    kind: 'genut',
    origin: 'manual',
    function_name: null,
    file_list: [],
    excluded_files: [],
    attempt: 0,
    submitted_at: '2026-06-15T00:00:00Z',
    started_at: null,
    finished_at: null,
    result_summary: null,
    error: null,
    ...overrides,
  }
}

describe('ManualJobsPage', () => {
  it('수동 job만 요청해 이력을 표시하고, 행 클릭 시 로그 패널이 열린다', async () => {
    const originsSeen: (string | null)[] = []
    server.use(
      http.get('/api/jobs', ({ request }) => {
        originsSeen.push(new URL(request.url).searchParams.get('origin'))
        return HttpResponse.json({
          items: [job({ result_summary: 'status=success total=4 pos=2 neg=2' })],
          total: 1,
          page: 1,
          page_size: 50,
        })
      }),
      http.get('/api/jobs/5/logs', () => HttpResponse.json([])),
    )

    renderWithProviders(<ManualJobsPage />)
    const resultCell = await screen.findByText('status=success total=4 pos=2 neg=2')

    // 수동 job만 조회한다(auto job은 '자동 실행 이력' 페이지 전용)
    expect(originsSeen.every((origin) => origin === 'manual')).toBe(true)

    // 고정 폭 테이블 + min-width: 좁은 화면에선 래퍼(overflow-x-auto)가 전체 좌우 스크롤을 준다.
    const table = resultCell.closest('table')
    expect(table?.className).toContain('table-fixed')
    expect(table?.className).toContain('min-w-[1120px]')

    // 행을 클릭하면 바로 그 행 아래에 로그 패널이 펼쳐진다(인라인)
    fireEvent.click(resultCell)
    expect(await screen.findByText(/job #5 로그/)).toBeInTheDocument()
  })

  it('shows start time, end time, and total duration for jobs', async () => {
    server.use(
      http.get('/api/jobs', () =>
        HttpResponse.json({
          items: [
            job({
              id: 9,
              product_id: 4,
              started_at: '2026-06-15T00:00:00Z',
              finished_at: '2026-06-15T00:01:30Z',
              result_summary: 'status=success total=4 pos=2 neg=2',
            }),
          ],
          total: 1,
          page: 1,
          page_size: 50,
        }),
      ),
    )

    renderWithProviders(<ManualJobsPage />)
    // 총 수행 시간 = 90초 → "1:30" (두 시각의 차이라 타임존과 무관). 데이터 로드까지 대기.
    expect(await screen.findByText('1:30')).toBeInTheDocument()
    // 컬럼 헤더가 표시된다
    expect(screen.getByText('제출 시각')).toBeInTheDocument()
    expect(screen.getByText('시작 시간')).toBeInTheDocument()
    expect(screen.getByText('종료 시간')).toBeInTheDocument()
    expect(screen.getByText('총 수행 시간')).toBeInTheDocument()
  })

  it('결과 컬럼에 긴 에러 로그 대신 간단한 설명을 보여준다', async () => {
    const longError = 'E'.repeat(800) + ' traceback (most recent call last) ...'
    server.use(
      http.get('/api/jobs', () =>
        HttpResponse.json({
          items: [
            job({
              id: 11,
              status: 'failed',
              started_at: '2026-06-15T00:00:00Z',
              finished_at: '2026-06-15T00:01:00Z',
              error: longError,
            }),
          ],
          total: 1,
          page: 1,
          page_size: 50,
        }),
      ),
    )

    renderWithProviders(<ManualJobsPage />)
    expect(await screen.findByText('실패로 실행이 중단됨.')).toBeInTheDocument()
    // 긴 에러 로그 원문은 결과 컬럼에 노출되지 않는다
    expect(screen.queryByText(/traceback/)).toBeNull()
  })

  it('interrupted job은 결과 컬럼에 서버 재시작 안내를 보여준다', async () => {
    server.use(
      http.get('/api/jobs', () =>
        HttpResponse.json({
          items: [
            job({
              id: 12,
              status: 'interrupted',
              started_at: '2026-06-15T00:00:00Z',
              finished_at: '2026-06-15T00:00:30Z',
              error: '서버 재시작으로 실행이 중단됨',
            }),
          ],
          total: 1,
          page: 1,
          page_size: 50,
        }),
      ),
    )

    renderWithProviders(<ManualJobsPage />)
    expect(await screen.findByText('서버 재시작으로 실행이 중단됨.')).toBeInTheDocument()
  })

  it('shows a force-kill button for running jobs and posts cancel', async () => {
    let canceled = false
    const runningJob = job({ id: 8, product_id: 3, status: 'running' })
    server.use(
      http.get('/api/jobs', () =>
        HttpResponse.json({ items: [runningJob], total: 1, page: 1, page_size: 50 }),
      ),
      http.post('/api/jobs/8/cancel', () => {
        canceled = true
        return HttpResponse.json({ ...runningJob })
      }),
    )

    renderWithProviders(<ManualJobsPage />)
    const btn = await screen.findByRole('button', { name: '강제 종료' })
    fireEvent.click(btn)
    await waitFor(() => expect(canceled).toBe(true))
  })
})
