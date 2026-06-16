import { describe, it, expect } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { server } from '../../test/msw/server'
import { renderWithProviders } from '../../test/utils'
import { GenutsPage } from './GenutsPage'

function genut(id = 1, name = 'genut-a') {
  return {
    id,
    name,
    repo_url: 'https://example.com/genut.git',
    repo_ref: 'main',
    ds_assist_send_system_name: 'sys-A',
    ds_assist_user_id: null,
    max_attempts: 10,
    run_command: 'python -m genut',
    enabled: true,
    code_path: null,
    worker_status: 'idle',
    current_job_id: null,
  }
}

describe('GenutsPage', () => {
  it('lists registered GENUT instances', async () => {
    server.use(
      http.get('/api/genuts', () =>
        HttpResponse.json({ items: [genut()], total: 1, page: 1, page_size: 50 }),
      ),
    )
    renderWithProviders(<GenutsPage />)
    expect(await screen.findByText('genut-a')).toBeInTheDocument()
    expect(screen.getByText('sys-A')).toBeInTheDocument()
  })

  it('edits a GENUT and omits the blank credential key on PUT', async () => {
    let putBody: Record<string, unknown> | null = null
    server.use(
      http.get('/api/genuts', () =>
        HttpResponse.json({ items: [genut()], total: 1, page: 1, page_size: 50 }),
      ),
      http.put('/api/genuts/1', async ({ request }) => {
        putBody = (await request.json()) as Record<string, unknown>
        return HttpResponse.json(genut())
      }),
    )
    renderWithProviders(<GenutsPage />)
    await screen.findByText('genut-a')

    await userEvent.click(screen.getByRole('button', { name: '수정' }))
    expect(screen.getByRole('textbox', { name: '이름' })).toHaveValue('genut-a')
    // credential key는 비워둔 채로 저장 → 전송에서 제외되어 기존 값 유지
    await userEvent.click(screen.getByRole('button', { name: '저장' }))

    await waitFor(() => expect(putBody).not.toBeNull())
    expect(putBody!.name).toBe('genut-a')
    expect(putBody!.ds_assist_credential_key).toBeUndefined()
  })
})
