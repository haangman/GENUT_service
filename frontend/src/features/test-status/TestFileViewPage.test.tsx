import { describe, it, expect } from 'vitest'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { server } from '../../test/msw/server'
import { renderWithProviders } from '../../test/utils'
import { TestFileViewPage } from './TestFileViewPage'

describe('TestFileViewPage', () => {
  it('shows code content and switches to log on tab click', async () => {
    server.use(
      http.get('/api/test-status/file', ({ request }) => {
        const path = new URL(request.url).searchParams.get('path')
        if (path === 'out/calc/calc_Test_0.cpp')
          return HttpResponse.json({ path, content: 'CODE_BODY' })
        if (path === 'out_debug_log/calc/calc_Test_0.log')
          return HttpResponse.json({ path, content: 'LOG_BODY' })
        return HttpResponse.json({ path, content: '' })
      }),
    )

    renderWithProviders(<TestFileViewPage />, {
      route:
        '/test-status/view?code=AA-1&codePath=out/calc/calc_Test_0.cpp' +
        '&logPath=out_debug_log/calc/calc_Test_0.log&name=calc_Test_0.cpp&tab=code',
    })

    expect(await screen.findByText('CODE_BODY')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: '로그' }))
    expect(await screen.findByText('LOG_BODY')).toBeInTheDocument()
  })

  it('disables the log tab when there is no log path', () => {
    renderWithProviders(<TestFileViewPage />, {
      route: '/test-status/view?code=AA-1&codePath=out/calc/x.cpp&name=x.cpp&tab=code',
    })
    expect(screen.getByRole('button', { name: '로그' })).toBeDisabled()
  })
})
