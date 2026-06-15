import { describe, it, expect } from 'vitest'
import { screen } from '@testing-library/react'
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

    renderWithProviders(<MonitoringPage />)
    expect(await screen.findByText('worker-a')).toBeInTheDocument()
    expect(await screen.findByText('대기(프로덕트 사용 중)')).toBeInTheDocument()
    expect(await screen.findByText('status=success total=4 pos=2 neg=2')).toBeInTheDocument()
  })
})
