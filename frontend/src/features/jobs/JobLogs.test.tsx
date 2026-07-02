import { describe, it, expect, vi } from 'vitest'
import { fireEvent, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '../../test/msw/server'
import { renderWithProviders } from '../../test/utils'
import { JobLogs } from './JobLogs'

function ev(id: number, phase: string, message: string) {
  return { id, job_id: 7, ts: '2026-06-15T00:00:00Z', level: 'info', phase, message, payload: null }
}

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

  it('완료된 job에서 재수행 버튼을 누르면 rerun 엔드포인트를 호출한다', async () => {
    let reran = false
    server.use(
      http.get('/api/jobs/7/logs', () => HttpResponse.json([])),
      http.post('/api/jobs/7/rerun', () => {
        reran = true
        return HttpResponse.json({ id: 99 })
      }),
    )
    const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => {})

    renderWithProviders(<JobLogs jobId={7} status="done" />)
    fireEvent.click(await screen.findByRole('button', { name: '재수행' }))
    await waitFor(() => expect(reran).toBe(true))
    alertSpy.mockRestore()
  })

  it('실행 중인 job에는 재수행 버튼이 없다', async () => {
    server.use(http.get('/api/jobs/7/logs', () => HttpResponse.json([])))
    renderWithProviders(<JobLogs jobId={7} status="running" pollMs={1000} />)
    expect(await screen.findByRole('button', { name: '로그 저장' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '재수행' })).toBeNull()
  })

  it('로그 패널은 박스 안에서 상하·좌우로 스크롤된다 (줄바꿈하지 않음)', async () => {
    server.use(
      http.get('/api/jobs/7/logs', () =>
        HttpResponse.json([ev(1, 'run', 'C:/very/long/path/'.repeat(30))]),
      ),
    )
    renderWithProviders(<JobLogs jobId={7} status="done" />)
    const log = await screen.findByTestId('job-log')
    // 줄바꿈하지 않고(whitespace-pre) 박스 내부에서 양방향 스크롤(overflow-auto + max-h)한다.
    // (테이블은 table-fixed라 이 긴 로그가 데이터 컬럼을 밀지 않는다.)
    expect(log.className).toContain('max-h-64')
    expect(log.className).toContain('overflow-auto')
    expect(log.className).toContain('whitespace-pre')
    expect(log.className).not.toContain('whitespace-pre-wrap')
  })
})
