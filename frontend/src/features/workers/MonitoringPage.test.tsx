import { describe, it, expect, vi } from 'vitest'
import { fireEvent, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '../../test/msw/server'
import { renderWithProviders } from '../../test/utils'
import { JobLogs, MonitoringPage } from './MonitoringPage'

function ev(id: number, phase: string, message: string) {
  return { id, job_id: 7, ts: '2026-06-15T00:00:00Z', level: 'info', phase, message, payload: null }
}

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

describe('JobLogs (증분 폴링)', () => {
  it('마지막 id 이후만 받아 누적한다 (since 커서 전진)', async () => {
    const all = [ev(1, 'clone', 'cloning'), ev(2, 'run', 'progress-1'), ev(3, 'run', 'progress-2')]
    const sinceSeen: number[] = []
    server.use(
      http.get('/api/jobs/7/logs', ({ request }) => {
        const since = Number(new URL(request.url).searchParams.get('since') ?? '0')
        sinceSeen.push(since)
        // 폴링마다 한 개씩만 공개 → 증분 누적 동작 검증
        const next = all.filter((e) => e.id > since).slice(0, 1)
        return HttpResponse.json(next)
      }),
    )

    renderWithProviders(<JobLogs jobId={7} status="running" pollMs={20} />)

    // 세 번째 이벤트까지 누적되어 표시됨
    expect(await screen.findByText(/progress-2/)).toBeInTheDocument()
    // 첫 이벤트(clone)도 사라지지 않고 함께 누적
    expect(screen.getByText(/cloning/)).toBeInTheDocument()
    // since가 0을 넘어 전진했음(증분)
    await waitFor(() => expect(Math.max(...sinceSeen)).toBeGreaterThanOrEqual(2))

    // 로그 저장 버튼: 그 순간까지의 로그를 job 이름+날짜시간 파일명으로 저장
    ;(URL as unknown as { createObjectURL: unknown }).createObjectURL = vi.fn(() => 'blob:mock')
    ;(URL as unknown as { revokeObjectURL: unknown }).revokeObjectURL = vi.fn()
    let savedName = ''
    const clickSpy = vi
      .spyOn(HTMLAnchorElement.prototype, 'click')
      .mockImplementation(function (this: HTMLAnchorElement) {
        savedName = this.download
      })
    fireEvent.click(screen.getByRole('button', { name: '로그 저장' }))
    clickSpy.mockRestore()
    expect(savedName).toMatch(/^job_7_\d{8}-\d{6}\.log$/)
  })
})
