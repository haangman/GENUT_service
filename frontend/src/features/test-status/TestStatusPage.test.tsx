import { describe, it, expect } from 'vitest'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { server } from '../../test/msw/server'
import { renderWithProviders } from '../../test/utils'
import { TestStatusPage } from './TestStatusPage'

describe('TestStatusPage', () => {
  it('drills name → target files → success/failed test files with fail counts and viewer links', async () => {
    server.use(
      // 같은 이름 'AA'의 두 변이가 1행으로 합산됨(총 테스트 2, 실패 1)
      http.get('/api/test-status', () =>
        HttpResponse.json([
          {
            name: 'AA',
            product_codes: ['AA-1', 'AA-2'],
            test_generation_mode: 'cpp',
            target_file_count: 1,
            total_test_count: 2,
            total_fail_count: 1,
          },
        ]),
      ),
      http.get('/api/test-status/detail', ({ request }) => {
        const name = new URL(request.url).searchParams.get('name')
        if (name !== 'AA') return HttpResponse.json([])
        return HttpResponse.json([
          {
            name: 'calc.c',
            path: 'src/calc.c',
            product_codes: ['AA-1', 'AA-2'],
            test_count: 2,
            test_files: [
              {
                name: 'calc_Test_0.cpp',
                path: 'out/calc/calc_Test_0.cpp',
                product_codes: ['AA-1'],
                log_path: 'out_debug_log/calc/calc_Test_0.log',
              },
              {
                name: 'calc_Test_1.cpp',
                path: 'out/calc/calc_Test_1.cpp',
                product_codes: ['AA-2'],
                log_path: null,
              },
            ],
            fail_count: 1,
            failed_test_files: [
              {
                name: 'calc_Test_2.cpp',
                path: 'out_Fail/calc/calc_Test_2.cpp',
                product_codes: ['AA-1'],
                log_path: 'out_debug_log/calc/calc_Test_2.log',
              },
            ],
          },
        ])
      }),
    )

    renderWithProviders(<TestStatusPage />)

    // L1: 이름 1행 + 등록 ID(두 변이)
    expect(await screen.findByText('AA')).toBeInTheDocument()
    expect(screen.getByText('AA-1, AA-2')).toBeInTheDocument()

    // L2: 이름 클릭 → 대상 파일 + 합계(총 테스트/총 실패)
    await userEvent.click(screen.getByText('AA'))
    expect(await screen.findByText('calc.c')).toBeInTheDocument()
    expect(screen.getByText('총 테스트 2')).toBeInTheDocument()
    expect(screen.getByText('총 실패 1')).toBeInTheDocument()

    // L3: 파일 클릭 → 성공/실패 분리 표
    await userEvent.click(screen.getByText('calc.c'))
    expect(await screen.findByText('생성 성공')).toBeInTheDocument()
    expect(screen.getByText('생성 실패')).toBeInTheDocument()
    expect(screen.getByText('calc_Test_0.cpp')).toBeInTheDocument()
    expect(screen.getByText('calc_Test_1.cpp')).toBeInTheDocument()
    expect(screen.getByText('calc_Test_2.cpp')).toBeInTheDocument()

    // 코드 링크는 모든 테스트 파일에(성공 2 + 실패 1 = 3개), 뷰어 라우트로 연결된다
    const codeLinks = screen.getAllByRole('link', { name: '코드' })
    expect(codeLinks).toHaveLength(3)
    expect(codeLinks[0]).toHaveAttribute('href', expect.stringContaining('/test-status/view?'))
    expect(codeLinks[0].getAttribute('href')).toContain('tab=code')
    expect(codeLinks[0].getAttribute('href')).toContain('code=AA-1')

    // 로그 링크는 log_path가 있는 파일(test_0, test_2)에만, 없는 파일(test_1)은 비활성 버튼
    const logLinks = screen.getAllByRole('link', { name: '로그' })
    expect(logLinks).toHaveLength(2)
    expect(logLinks[0].getAttribute('href')).toContain('tab=log')
    expect(screen.getByRole('button', { name: '로그' })).toBeDisabled()
  })
})
