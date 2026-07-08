import { describe, it, expect, vi } from 'vitest'
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
    assure_repo_url: null,
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

  it('워커 상태와 요청 큐(수동/자동 구분)를 함께 보여준다', async () => {
    server.use(
      http.get('/api/genuts', () =>
        HttpResponse.json({ items: [], total: 0, page: 1, page_size: 50 }),
      ),
      http.get('/api/workers', () =>
        HttpResponse.json([
          { id: 1, name: 'worker-a', worker_status: 'busy', current_job_id: 5, enabled: true },
        ]),
      ),
      http.get('/api/queue', () =>
        HttpResponse.json([
          {
            job_id: 6,
            product_id: 2,
            submitted_at: '2026-06-15T00:00:00Z',
            waiting_on_product: true,
            origin: 'manual',
          },
          {
            job_id: 7,
            product_id: 3,
            submitted_at: '2026-06-15T00:00:01Z',
            waiting_on_product: false,
            origin: 'auto',
          },
        ]),
      ),
    )

    renderWithProviders(<GenutsPage />)
    // 워커 카드: 이름 + 상태 + 현재 job
    expect(await screen.findByText('worker-a')).toBeInTheDocument()
    expect(screen.getByText('job #5')).toBeInTheDocument()
    // 요청 큐: origin 배지로 수동/자동 구분 + 프로덕트 사용 중 대기 표시
    expect(await screen.findByText('job #6')).toBeInTheDocument()
    expect(screen.getByText('수동')).toBeInTheDocument()
    expect(screen.getByText('자동')).toBeInTheDocument()
    expect(screen.getByText('대기(프로덕트 사용 중)')).toBeInTheDocument()
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

  it('deletes only after the user confirms', async () => {
    let deleted = false
    server.use(
      http.get('/api/genuts', () =>
        HttpResponse.json({ items: [genut()], total: 1, page: 1, page_size: 50 }),
      ),
      http.delete('/api/genuts/1', () => {
        deleted = true
        return new HttpResponse(null, { status: 204 })
      }),
    )
    const confirmSpy = vi.spyOn(window, 'confirm')
    renderWithProviders(<GenutsPage />)
    await screen.findByText('genut-a')

    // 취소 → 요청 없음
    confirmSpy.mockReturnValueOnce(false)
    await userEvent.click(screen.getByRole('button', { name: '삭제' }))
    expect(deleted).toBe(false)

    // 확인 → 삭제
    confirmSpy.mockReturnValueOnce(true)
    await userEvent.click(screen.getByRole('button', { name: '삭제' }))
    await waitFor(() => expect(deleted).toBe(true))
    confirmSpy.mockRestore()
  })
})
