import { describe, it, expect, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { server } from '../../test/msw/server'
import { renderWithProviders } from '../../test/utils'
import { ProductForm } from './ProductForm'
import type { ProductFormValues } from './productSchema'

const VALID: ProductFormValues = {
  project: 'Ulysses',
  name: 'demo',
  product_code: 'P-1',
  git_url: 'https://example.com/repo.git',
  git_ref: 'main',
  compile_db_rel: 'build',
  out_tests_rel: 'tests',
  cmake_configure_cmd: 'cmake -S . -B build',
  cmake_build_cmd: 'cmake --build build',
  test_run_cmd: 'ctest',
  test_generation_mode: 'cpp',
  code_path: 'C:/checkout',
  exclude_patterns: '',
  patches: [],
  auto_run: false,
  auto_interval_value: 24,
  auto_interval_unit: 'hours',
  cmake_template: 'set(MODULE_TEST_NAME filename_UnitTest)\n',
}

describe('ProductForm', () => {
  it('shows validation errors and does not submit when empty', async () => {
    const onSubmit = vi.fn()
    renderWithProviders(<ProductForm onSubmit={onSubmit} />)
    await userEvent.click(screen.getByRole('button', { name: '저장' }))
    expect(await screen.findByText('이름을 입력하세요')).toBeInTheDocument()
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('submits valid values including patches', async () => {
    const onSubmit = vi.fn()
    renderWithProviders(
      <ProductForm
        onSubmit={onSubmit}
        defaultValues={{ ...VALID, patches: [{ name: 'p0', content: 'diff0' }] }}
      />,
    )
    await userEvent.click(screen.getByRole('button', { name: '저장' }))
    expect(onSubmit).toHaveBeenCalledTimes(1)
    const values = onSubmit.mock.calls[0][0]
    expect(values.name).toBe('demo')
    expect(values.project).toBe('Ulysses') // 기본 프로젝트
    expect(values.patches).toHaveLength(1)
    expect(values.patches[0].name).toBe('p0')
  })

  it('selects a project and includes it in the submitted values', async () => {
    const onSubmit = vi.fn()
    renderWithProviders(<ProductForm onSubmit={onSubmit} defaultValues={VALID} />)

    await userEvent.selectOptions(screen.getByLabelText('프로젝트'), 'Thetis')
    await userEvent.click(screen.getByRole('button', { name: '저장' }))
    expect(onSubmit).toHaveBeenCalledTimes(1)
    expect(onSubmit.mock.calls[0][0].project).toBe('Thetis')
  })

  it('requires an absolute code_path', async () => {
    const onSubmit = vi.fn()
    renderWithProviders(
      <ProductForm onSubmit={onSubmit} defaultValues={{ ...VALID, code_path: 'repos/foo' }} />,
    )
    await userEvent.click(screen.getByRole('button', { name: '저장' }))
    expect(
      await screen.findByText('코드 저장 경로는 절대 경로로 입력하세요'),
    ).toBeInTheDocument()
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('downloads code into code_path and shows the result next to the button', async () => {
    renderWithProviders(
      <ProductForm onSubmit={vi.fn()} defaultValues={{ ...VALID, code_path: 'C:/checkout' }} />,
    )
    const button = screen.getByRole('button', { name: '다운로드' })
    expect(button).toBeEnabled() // git_url·code_path가 채워져 있으면 활성

    await userEvent.click(button)
    // 기본 MSW 핸들러가 성공(클론 완료)을 반환한다
    expect(await screen.findByText(/다운로드 성공/)).toBeInTheDocument()
    // 공용 로그창에도 다운로드 로그(시작 라인 + 결과 + 최근 커밋)가 남는다
    const consoleEl = screen.getByTestId('form-console')
    expect(consoleEl.textContent).toContain('$ 다운로드:')
    expect(consoleEl.textContent).toContain('클론 완료')
    expect(consoleEl.textContent).toContain('최근 커밋')
  })

  it('runs a cmake command and prints the output in the shared console', async () => {
    renderWithProviders(<ProductForm onSubmit={vi.fn()} defaultValues={VALID} />)
    const runButtons = screen.getAllByRole('button', { name: '실행' })
    expect(runButtons).toHaveLength(2) // CMAKE_CONFIGURE_CMD + CMAKE_BUILD_CMD

    await userEvent.click(runButtons[0])
    const consoleEl = screen.getByTestId('form-console')
    // 명령 에코 + 출력 + exit code가 로그창에 누적된다(기본 MSW: exit 0, 'ok')
    expect(consoleEl.textContent).toContain('$ cmake -S . -B build')
    await waitFor(() => expect(consoleEl.textContent).toContain('ok'))
    expect(consoleEl.textContent).toContain('[exit 0')
  })

  it('shows failing command output with its exit code in the console', async () => {
    server.use(
      http.post('/api/products/run-command', () =>
        HttpResponse.json({ exit_code: 2, output: 'CMake Error: boom', duration_seconds: 0.2 }),
      ),
    )
    renderWithProviders(<ProductForm onSubmit={vi.fn()} defaultValues={VALID} />)
    await userEvent.click(screen.getAllByRole('button', { name: '실행' })[1])
    const consoleEl = screen.getByTestId('form-console')
    await waitFor(() => expect(consoleEl.textContent).toContain('CMake Error: boom'))
    expect(consoleEl.textContent).toContain('[exit 2')
  })

  it('disables run buttons until the code path is absolute and the command is filled', () => {
    renderWithProviders(
      <ProductForm
        onSubmit={vi.fn()}
        defaultValues={{ ...VALID, code_path: 'relative/path', cmake_build_cmd: '' }}
      />,
    )
    for (const button of screen.getAllByRole('button', { name: '실행' })) {
      expect(button).toBeDisabled()
    }
  })

  it('sends the form patches with the download request', async () => {
    let captured: { patches?: unknown } | null = null
    server.use(
      http.post('/api/products/pull-code', async ({ request }) => {
        captured = (await request.json()) as { patches?: unknown }
        return HttpResponse.json({ path: 'C:/checkout', detail: '클론 완료', log: '최근 커밋:\nabc' })
      }),
    )
    renderWithProviders(
      <ProductForm
        onSubmit={vi.fn()}
        defaultValues={{
          ...VALID,
          // 빈 행(내용 없음)은 전송에서 걸러지고, 나머지는 순서대로 order_index가 붙는다
          patches: [
            { name: 'p0', content: 'diff0' },
            { name: 'blank', content: '   ' },
            { name: 'p1', content: 'diff1' },
          ],
        }}
      />,
    )
    await userEvent.click(screen.getByRole('button', { name: '다운로드' }))
    expect(await screen.findByText(/다운로드 성공/)).toBeInTheDocument()
    expect(captured!.patches).toEqual([
      { name: 'p0', content: 'diff0', order_index: 0 },
      { name: 'p1', content: 'diff1', order_index: 1 },
    ])
  })

  it('shows the server detail when the download fails', async () => {
    server.use(
      http.post('/api/products/pull-code', () =>
        HttpResponse.json({ detail: 'git clone failed: repository not found' }, { status: 400 }),
      ),
    )
    renderWithProviders(
      <ProductForm onSubmit={vi.fn()} defaultValues={{ ...VALID, code_path: 'C:/checkout' }} />,
    )
    await userEvent.click(screen.getByRole('button', { name: '다운로드' }))
    // 버튼 옆 인라인 표시와 공용 로그창 모두에 실패 원인이 남는다
    expect(await screen.findByRole('alert')).toHaveTextContent(
      '다운로드 실패: git clone failed: repository not found',
    )
    expect(screen.getByTestId('form-console').textContent).toContain(
      'git clone failed: repository not found',
    )
  })

  it('disables the download button while git_url or code_path is empty', () => {
    renderWithProviders(<ProductForm onSubmit={vi.fn()} />) // 빈 폼
    expect(screen.getByRole('button', { name: '다운로드' })).toBeDisabled()
  })

  it('fetches a gerrit change and appends it as a patch row', async () => {
    let captured: { change?: string } | null = null
    server.use(
      http.post('/api/products/fetch-gerrit-patch', async ({ request }) => {
        captured = (await request.json()) as { change?: string }
        return HttpResponse.json({
          name: 'gerrit-1234-2',
          content: 'diff --git a/x b/x',
          ref: 'refs/changes/34/1234/2',
          subject: 'Fix timer',
        })
      }),
    )
    renderWithProviders(<ProductForm onSubmit={vi.fn()} defaultValues={VALID} />)

    await userEvent.type(screen.getByLabelText('Gerrit change 주소'), '1234')
    await userEvent.click(screen.getByRole('button', { name: '가져오기' }))

    // 패치 행이 name/content 채워진 채 추가된다
    expect(await screen.findByLabelText('패치 1 이름')).toHaveValue('gerrit-1234-2')
    expect(screen.getByLabelText('패치 1 내용')).toHaveValue('diff --git a/x b/x')
    expect(captured).toEqual({
      git_url: VALID.git_url,
      code_path: VALID.code_path,
      change: '1234',
    })
    // 공용 로그창에 ref·제목이 남고 입력칸은 비워진다
    const consoleEl = screen.getByTestId('form-console')
    expect(consoleEl.textContent).toContain('refs/changes/34/1234/2')
    expect(consoleEl.textContent).toContain('Fix timer')
    expect(screen.getByLabelText('Gerrit change 주소')).toHaveValue('')
  })

  it('shows the server detail when the gerrit fetch fails', async () => {
    server.use(
      http.post('/api/products/fetch-gerrit-patch', () =>
        HttpResponse.json(
          { detail: 'change 9999를 원격에서 찾을 수 없다' },
          { status: 400 },
        ),
      ),
    )
    renderWithProviders(<ProductForm onSubmit={vi.fn()} defaultValues={VALID} />)
    await userEvent.type(screen.getByLabelText('Gerrit change 주소'), '9999')
    await userEvent.click(screen.getByRole('button', { name: '가져오기' }))

    const consoleEl = screen.getByTestId('form-console')
    await waitFor(() =>
      expect(consoleEl.textContent).toContain('change 9999를 원격에서 찾을 수 없다'),
    )
    // 실패 시 패치 행은 추가되지 않는다
    expect(screen.queryByLabelText('패치 1 이름')).not.toBeInTheDocument()
  })

  it('disables the gerrit fetch button without input or an absolute code path', async () => {
    renderWithProviders(
      <ProductForm onSubmit={vi.fn()} defaultValues={{ ...VALID, code_path: 'relative/path' }} />,
    )
    const button = screen.getByRole('button', { name: '가져오기' })
    expect(button).toBeDisabled() // 입력 없음 + 상대 경로

    await userEvent.type(screen.getByLabelText('Gerrit change 주소'), '1234')
    expect(button).toBeDisabled() // code_path가 절대 경로가 아니면 여전히 비활성
  })

  it('adds and removes patch rows', async () => {
    renderWithProviders(<ProductForm onSubmit={vi.fn()} />)
    await userEvent.click(screen.getByRole('button', { name: '패치 추가' }))
    expect(screen.getByLabelText('패치 1 이름')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '삭제' }))
    expect(screen.queryByLabelText('패치 1 이름')).not.toBeInTheDocument()
  })

  it('auto mode reveals interval/template, lists target files, and requires auto prefix', async () => {
    server.use(
      http.post('/api/products/target-files', () =>
        HttpResponse.json({
          files: [
            { path: 'src/aaa.c', excluded_by_pattern: false },
            { path: 'src/bbb.c', excluded_by_pattern: true },
          ],
        }),
      ),
    )
    const onSubmit = vi.fn()
    renderWithProviders(
      <ProductForm
        onSubmit={onSubmit}
        defaultValues={{ ...VALID, code_path: '/x', compile_db_rel: 'build' }}
      />,
    )

    await userEvent.click(screen.getByRole('checkbox'))
    // 주기 입력 + 템플릿 편집기 노출
    expect(screen.getByLabelText('자동 수행 주기')).toBeInTheDocument()
    expect(screen.getByLabelText(/CMakeLists.txt 양식/)).toBeInTheDocument()

    // 디바운스 후 미리보기 목록(패턴 제외 표시 포함)
    expect(await screen.findByText('src/aaa.c', {}, { timeout: 3000 })).toBeInTheDocument()
    expect(screen.getByText('src/bbb.c')).toBeInTheDocument()
    expect(screen.getByText(/제외됨 \(패턴\)/)).toBeInTheDocument()

    // product_code가 auto로 시작하지 않으면 저장 차단
    await userEvent.click(screen.getByRole('button', { name: '저장' }))
    expect(
      await screen.findByText("자동 실행 모드의 ID는 'auto'로 시작해야 합니다"),
    ).toBeInTheDocument()
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('hides the CMakeLists template editor in auto mode when the test mode is kunit', async () => {
    renderWithProviders(<ProductForm onSubmit={vi.fn()} defaultValues={VALID} />)

    await userEvent.click(screen.getByRole('checkbox'))
    // cpp(기본) → 양식창 노출
    expect(screen.getByLabelText(/CMakeLists.txt 양식/)).toBeInTheDocument()

    // kunit으로 바꾸면 양식창이 사라지고, 되돌리면 다시 나타난다
    await userEvent.selectOptions(screen.getByLabelText(/테스트 모드/), 'kunit')
    expect(screen.queryByLabelText(/CMakeLists.txt 양식/)).not.toBeInTheDocument()
    await userEvent.selectOptions(screen.getByLabelText(/테스트 모드/), 'cpp')
    expect(screen.getByLabelText(/CMakeLists.txt 양식/)).toBeInTheDocument()
  })
})
