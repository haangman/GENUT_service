import { describe, it, expect } from 'vitest'
import { screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '../../test/msw/server'
import { renderWithProviders } from '../../test/utils'
import { GenutsPage } from './GenutsPage'

describe('GenutsPage', () => {
  it('lists registered GENUT instances', async () => {
    server.use(
      http.get('/api/genuts', () =>
        HttpResponse.json({
          items: [
            {
              id: 1,
              name: 'genut-a',
              repo_url: 'https://example.com/genut.git',
              repo_ref: 'main',
              ds_assist_send_system_name: 'sys-A',
              max_attempts: 10,
              run_command: 'python -m genut',
              enabled: true,
              worker_status: 'idle',
              current_job_id: null,
            },
          ],
          total: 1,
          page: 1,
          page_size: 50,
        }),
      ),
    )
    renderWithProviders(<GenutsPage />)
    expect(await screen.findByText('genut-a')).toBeInTheDocument()
    expect(screen.getByText('sys-A')).toBeInTheDocument()
  })
})
