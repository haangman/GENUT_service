import { describe, it, expect } from 'vitest'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { server } from '../../test/msw/server'
import { renderWithProviders } from '../../test/utils'
import { TestStatusPage } from './TestStatusPage'

describe('TestStatusPage', () => {
  it('shows per-product counts then drills products → target files → test files', async () => {
    server.use(
      http.get('/api/test-status', () =>
        HttpResponse.json([
          {
            product_id: 1,
            name: 'AA',
            product_code: 'AA-1',
            test_generation_mode: 'cpp',
            code_path: null,
            target_file_count: 2,
            total_test_count: 3,
          },
        ]),
      ),
      http.get('/api/products/1/test-status', () =>
        HttpResponse.json([
          {
            name: 'calc.c',
            path: 'src/calc.c',
            test_count: 2,
            test_files: [
              { name: 'calc_Test_0.cpp', path: 'tests/generated/S1/calc/calc_Test_0.cpp' },
              { name: 'calc_Test_1.cpp', path: 'tests/generated/S1/calc/calc_Test_1.cpp' },
            ],
          },
          { name: 'util.c', path: 'src/util.c', test_count: 1, test_files: [
            { name: 'util_Test_0.cpp', path: 'tests/generated/S1/util/util_Test_0.cpp' },
          ] },
        ]),
      ),
    )

    renderWithProviders(<TestStatusPage />)

    // L1: 프로덕트 행에 대상 파일 수(2)·총 테스트 수(3)가 보인다
    expect(await screen.findByText('AA')).toBeInTheDocument()
    expect(screen.getByText('2')).toBeInTheDocument()
    expect(screen.getByText('3')).toBeInTheDocument()

    // L2: 프로덕트 선택 → 대상 파일 + 합계(총 테스트 3)
    await userEvent.click(screen.getByText('AA'))
    expect(await screen.findByText('calc.c')).toBeInTheDocument()
    expect(screen.getByText('src/calc.c')).toBeInTheDocument()
    expect(screen.getByText('총 테스트 3')).toBeInTheDocument()

    // L3: calc.c 선택 → 테스트 파일 목록
    await userEvent.click(screen.getByText('calc.c'))
    expect(await screen.findByText('calc_Test_0.cpp')).toBeInTheDocument()
  })
})
