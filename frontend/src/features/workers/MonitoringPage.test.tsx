import { describe, it, expect } from 'vitest'
import { fireEvent, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '../../test/msw/server'
import { renderWithProviders } from '../../test/utils'
import { MonitoringPage } from './MonitoringPage'

describe('MonitoringPage', () => {
  it('renders workers, queue, and job history from the API', async () => {
    server.use(
      http.get('/api/workers', () =>
        HttpResponse.json([
          { id: 1, name: 'worker-a', worker_status: 'busy', current_job_id: 5, enabled: true },
        ]),
      ),
      http.get('/api/queue', () =>
        HttpResponse.json([
          { job_id: 6, product_id: 2, submitted_at: '2026-06-15T00:00:00Z', waiting_on_product: true },
        ]),
      ),
      http.get('/api/jobs', () =>
        HttpResponse.json({
          items: [
            {
              id: 5,
              product_id: 2,
              genut_instance_id: 1,
              status: 'done',
              function_name: null,
              file_list: [],
              excluded_files: [],
              attempt: 0,
              submitted_at: '2026-06-15T00:00:00Z',
              started_at: null,
              finished_at: null,
              result_summary: 'status=success total=4 pos=2 neg=2',
              error: null,
            },
          ],
          total: 1,
          page: 1,
          page_size: 50,
        }),
      ),
    )

    server.use(http.get('/api/jobs/5/logs', () => HttpResponse.json([])))

    renderWithProviders(<MonitoringPage />)
    expect(await screen.findByText('worker-a')).toBeInTheDocument()
    expect(await screen.findByText('대기(프로덕트 사용 중)')).toBeInTheDocument()
    const resultCell = await screen.findByText('status=success total=4 pos=2 neg=2')

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
      http.get('/api/workers', () => HttpResponse.json([])),
      http.get('/api/queue', () => HttpResponse.json([])),
      http.get('/api/jobs', () =>
        HttpResponse.json({
          items: [
            {
              id: 9,
              product_id: 4,
              genut_instance_id: 1,
              status: 'done',
              function_name: null,
              file_list: [],
              excluded_files: [],
              attempt: 0,
              submitted_at: '2026-06-15T00:00:00Z',
              started_at: '2026-06-15T00:00:00Z',
              finished_at: '2026-06-15T00:01:30Z',
              result_summary: 'status=success total=4 pos=2 neg=2',
              error: null,
            },
          ],
          total: 1,
          page: 1,
          page_size: 50,
        }),
      ),
    )

    renderWithProviders(<MonitoringPage />)
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
      http.get('/api/workers', () => HttpResponse.json([])),
      http.get('/api/queue', () => HttpResponse.json([])),
      http.get('/api/jobs', () =>
        HttpResponse.json({
          items: [
            {
              id: 11,
              product_id: 2,
              genut_instance_id: 1,
              status: 'failed',
              function_name: null,
              file_list: [],
              excluded_files: [],
              attempt: 0,
              submitted_at: '2026-06-15T00:00:00Z',
              started_at: '2026-06-15T00:00:00Z',
              finished_at: '2026-06-15T00:01:00Z',
              result_summary: null,
              error: longError,
            },
          ],
          total: 1,
          page: 1,
          page_size: 50,
        }),
      ),
    )

    renderWithProviders(<MonitoringPage />)
    expect(await screen.findByText('실패로 실행이 중단됨.')).toBeInTheDocument()
    // 긴 에러 로그 원문은 결과 컬럼에 노출되지 않는다
    expect(screen.queryByText(/traceback/)).toBeNull()
  })

  it('interrupted job은 결과 컬럼에 서버 재시작 안내를 보여준다', async () => {
    server.use(
      http.get('/api/workers', () => HttpResponse.json([])),
      http.get('/api/queue', () => HttpResponse.json([])),
      http.get('/api/jobs', () =>
        HttpResponse.json({
          items: [
            {
              id: 12,
              product_id: 2,
              genut_instance_id: 1,
              status: 'interrupted',
              function_name: null,
              file_list: [],
              excluded_files: [],
              attempt: 0,
              submitted_at: '2026-06-15T00:00:00Z',
              started_at: '2026-06-15T00:00:00Z',
              finished_at: '2026-06-15T00:00:30Z',
              result_summary: null,
              error: '서버 재시작으로 실행이 중단됨',
            },
          ],
          total: 1,
          page: 1,
          page_size: 50,
        }),
      ),
    )

    renderWithProviders(<MonitoringPage />)
    expect(await screen.findByText('서버 재시작으로 실행이 중단됨.')).toBeInTheDocument()
  })

  it('shows a force-kill button for running jobs and posts cancel', async () => {
    let canceled = false
    const runningJob = {
      id: 8,
      product_id: 3,
      genut_instance_id: 1,
      status: 'running',
      function_name: null,
      file_list: [],
      excluded_files: [],
      attempt: 0,
      submitted_at: '2026-06-15T00:00:00Z',
      started_at: null,
      finished_at: null,
      result_summary: null,
      error: null,
    }
    server.use(
      http.get('/api/workers', () => HttpResponse.json([])),
      http.get('/api/queue', () => HttpResponse.json([])),
      http.get('/api/jobs', () =>
        HttpResponse.json({ items: [runningJob], total: 1, page: 1, page_size: 50 }),
      ),
      http.post('/api/jobs/8/cancel', () => {
        canceled = true
        return HttpResponse.json({ ...runningJob })
      }),
    )

    renderWithProviders(<MonitoringPage />)
    const btn = await screen.findByRole('button', { name: '강제 종료' })
    fireEvent.click(btn)
    await waitFor(() => expect(canceled).toBe(true))
  })
})
