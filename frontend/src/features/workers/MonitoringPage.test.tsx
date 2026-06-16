import { describe, it, expect } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
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

    renderWithProviders(<MonitoringPage />)
    expect(await screen.findByText('worker-a')).toBeInTheDocument()
    expect(await screen.findByText('대기(프로덕트 사용 중)')).toBeInTheDocument()
    expect(await screen.findByText('status=success total=4 pos=2 neg=2')).toBeInTheDocument()
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
  })
})
