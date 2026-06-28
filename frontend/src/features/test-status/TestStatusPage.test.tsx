import { describe, it, expect } from 'vitest'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { server } from '../../test/msw/server'
import { renderWithProviders } from '../../test/utils'
import { TestStatusPage } from './TestStatusPage'

describe('TestStatusPage', () => {
  it('groups by name, then drills name → target files → test files with product ids', async () => {
    server.use(
      // 같은 이름 'AA'의 두 변이가 1행으로 합산됨
      http.get('/api/test-status', () =>
        HttpResponse.json([
          {
            name: 'AA',
            product_codes: ['AA-1', 'AA-2'],
            test_generation_mode: 'cpp',
            target_file_count: 1,
            total_test_count: 2,
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
              { name: 'calc_Test_0.cpp', path: 't/calc_Test_0.cpp', product_codes: ['AA-1'] },
              { name: 'calc_Test_1.cpp', path: 't/calc_Test_1.cpp', product_codes: ['AA-2'] },
            ],
          },
        ])
      }),
    )

    renderWithProviders(<TestStatusPage />)

    // L1: 이름 1행 + 등록 ID(두 변이) + 총 테스트 2
    expect(await screen.findByText('AA')).toBeInTheDocument()
    expect(screen.getByText('AA-1, AA-2')).toBeInTheDocument()

    // L2: 이름 클릭 → 대상 파일 + 프로덕트 ID(AA-1, AA-2) + 합계
    await userEvent.click(screen.getByText('AA'))
    expect(await screen.findByText('calc.c')).toBeInTheDocument()
    expect(screen.getByText('총 테스트 2')).toBeInTheDocument()
    expect(screen.getByText('AA-1, AA-2')).toBeInTheDocument()

    // L3: 파일 클릭 → 테스트 파일별 출처(AA-1 / AA-2)
    await userEvent.click(screen.getByText('calc.c'))
    expect(await screen.findByText('calc_Test_0.cpp')).toBeInTheDocument()
    expect(screen.getByText('AA-1')).toBeInTheDocument()
    expect(screen.getByText('AA-2')).toBeInTheDocument()
  })
})
