import { describe, it, expect } from 'vitest'
import { fireEvent, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '../../test/msw/server'
import { renderWithProviders } from '../../test/utils'
import type { Job } from '../../types/api'
import { AutoJobsPage } from './AutoJobsPage'

let nextId = 100

function makeJob(overrides: Partial<Job> = {}): Job {
  nextId += 1
  return {
    id: nextId,
    product_id: 1,
    genut_instance_id: null,
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
    result_summary: null,
    error: null,
    ...overrides,
  }
}

function group(overrides: Record<string, unknown> = {}) {
  return {
    product_id: 1,
    product_name: 'auto-demo',
    product_code: 'auto-p1',
    auto_interval_seconds: 600,
    total: 0,
    jobs: [],
    ...overrides,
  }
}

describe('AutoJobsPage', () => {
  it('auto 프로덕트별 그룹과 최근 job·종류 badge를 보여준다', async () => {
    const jobs = [
      makeJob({ id: 30, kind: 'genut', result_summary: 'status=success total=4' }),
      makeJob({ id: 29, kind: 'auto_scan', result_summary: '파일 1개 스캔: job 1개 생성' }),
      makeJob({ id: 28, kind: 'auto_diff', result_summary: '변경 없음 (abc123)' }),
    ]
    server.use(
      http.get('/api/jobs/auto-history', () =>
        HttpResponse.json([
          group({ total: 10, jobs }),
          group({ product_id: 2, product_name: 'auto-idle', product_code: 'auto-p2' }),
        ]),
      ),
    )

    renderWithProviders(<AutoJobsPage />)

    // 그룹 헤더: 프로덕트명 + 전체 건수(접힘 시 "외 N건 보기")
    expect(await screen.findByText('auto-demo')).toBeInTheDocument()
    expect(screen.getByText(/전체 10건/)).toBeInTheDocument()
    expect(screen.getByText(/외 7건 보기/)).toBeInTheDocument()
    // 최근 3개 행
    expect(screen.getByText('30')).toBeInTheDocument()
    expect(screen.getByText('29')).toBeInTheDocument()
    expect(screen.getByText('28')).toBeInTheDocument()
    // 종류 badge: GENUT 실행 / JJ 스캔(누락 테스트) / 변경 감지
    expect(screen.getByText('GENUT')).toBeInTheDocument()
    expect(screen.getByText('JJ 스캔')).toBeInTheDocument()
    expect(screen.getByText('변경 감지')).toBeInTheDocument()

    // 이력 없는 auto 프로덕트도 빈 그룹으로 보인다
    expect(screen.getByText('auto-idle')).toBeInTheDocument()
    expect(screen.getByText('실행 이력이 없습니다.')).toBeInTheDocument()
  })

  it('그룹 헤더를 클릭하면 전체 이력을 조회하고, 다시 클릭하면 최근 3개로 돌아온다', async () => {
    const recent = [makeJob({ id: 55 }), makeJob({ id: 54 }), makeJob({ id: 53 })]
    const full = [...recent, makeJob({ id: 52 }), makeJob({ id: 51 })]
    const paramsSeen: string[] = []
    server.use(
      http.get('/api/jobs/auto-history', () =>
        HttpResponse.json([group({ total: 5, jobs: recent })]),
      ),
      http.get('/api/jobs', ({ request }) => {
        paramsSeen.push(new URL(request.url).search)
        return HttpResponse.json({ items: full, total: 5, page: 1, page_size: 50 })
      }),
    )

    renderWithProviders(<AutoJobsPage />)
    expect(await screen.findByText('55')).toBeInTheDocument()
    expect(screen.queryByText('51')).toBeNull() // 접힘: 최근 3개만

    // 확장 → 해당 프로덕트의 auto job 전체 조회
    fireEvent.click(screen.getByRole('button', { name: /auto-demo/ }))
    expect(await screen.findByText('51')).toBeInTheDocument()
    expect(paramsSeen.length).toBeGreaterThan(0)
    const query = new URLSearchParams(paramsSeen[0])
    expect(query.get('product_id')).toBe('1')
    expect(query.get('origin')).toBe('auto')

    // 다시 클릭 → 접힘(최근 3개)
    fireEvent.click(screen.getByRole('button', { name: /auto-demo/ }))
    await waitFor(() => expect(screen.queryByText('51')).toBeNull())
    expect(screen.getByText('55')).toBeInTheDocument()
  })

  it('행 클릭 시 로그 패널이 열리고, 실행 중 준비 job은 강제 종료를 호출한다', async () => {
    let canceled = false
    const runningScan = makeJob({
      id: 70,
      kind: 'auto_scan',
      status: 'running',
      started_at: '2026-06-15T00:00:00Z',
      finished_at: null,
    })
    const doneDiff = makeJob({ id: 69, kind: 'auto_diff', result_summary: '변경 없음' })
    server.use(
      http.get('/api/jobs/auto-history', () =>
        HttpResponse.json([group({ total: 2, jobs: [runningScan, doneDiff] })]),
      ),
      http.get('/api/jobs/69/logs', () =>
        HttpResponse.json([
          {
            id: 1,
            job_id: 69,
            ts: '2026-06-15T00:00:00Z',
            level: 'info',
            phase: 'diff',
            message: '변경 없음 (abc123)',
          },
        ]),
      ),
      http.post('/api/jobs/70/cancel', () => {
        canceled = true
        return HttpResponse.json(runningScan)
      }),
    )

    renderWithProviders(<AutoJobsPage />)

    // 완료된 준비 job 행 클릭 → 기존과 동일한 로그 패널(저장/재수행 포함)이 열린다
    fireEvent.click(await screen.findByText('변경 없음'))
    expect(await screen.findByText(/job #69 로그/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '로그 저장' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '재수행' })).toBeInTheDocument()

    // 실행 중 준비 job에는 강제 종료 버튼이 있고, 클릭 시 cancel을 호출한다
    fireEvent.click(screen.getByRole('button', { name: '강제 종료' }))
    await waitFor(() => expect(canceled).toBe(true))
  })

  it('auto 프로덕트가 없으면 빈 상태 안내를 보여준다', async () => {
    renderWithProviders(<AutoJobsPage />)
    expect(await screen.findByText('자동 실행 프로덕트가 없습니다.')).toBeInTheDocument()
  })
})
