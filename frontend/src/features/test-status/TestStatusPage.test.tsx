import { describe, it, expect } from 'vitest'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { server } from '../../test/msw/server'
import { renderWithProviders } from '../../test/utils'
import { TestStatusPage } from './TestStatusPage'

function productsPage(items: Array<{ id: number; name: string }>) {
  return {
    items: items.map((p) => ({
      id: p.id,
      name: p.name,
      product_code: `${p.name}-1`,
      git_url: 'u',
      git_ref: 'main',
      compile_db_rel: 'build',
      out_tests_rel: 'tests/generated',
      cmake_configure_cmd: 'c',
      cmake_build_cmd: 'b',
      test_run_cmd: 'r',
      test_generation_mode: 'cpp',
      active: true,
      code_path: null,
      exclude_globs: [],
      patches: [],
    })),
    total: items.length,
    page: 1,
    page_size: 50,
  }
}

describe('TestStatusPage', () => {
  it('drills products → target files → test files', async () => {
    server.use(
      http.get('/api/products', () => HttpResponse.json(productsPage([{ id: 1, name: 'AA' }]))),
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
          { name: 'util.c', path: 'src/util.c', test_count: 0, test_files: [] },
        ]),
      ),
    )

    renderWithProviders(<TestStatusPage />)

    // L1: 프로덕트 선택
    await userEvent.click(await screen.findByText('AA'))

    // L2: 대상 파일과 테스트 개수
    expect(await screen.findByText('calc.c')).toBeInTheDocument()
    expect(screen.getByText('src/calc.c')).toBeInTheDocument()
    expect(screen.getByText('util.c')).toBeInTheDocument()

    // calc.c 파일 선택 → L3: 테스트 파일 목록
    await userEvent.click(screen.getByText('calc.c'))
    expect(await screen.findByText('calc_Test_0.cpp')).toBeInTheDocument()
    expect(screen.getByText('calc_Test_1.cpp')).toBeInTheDocument()
  })
})
