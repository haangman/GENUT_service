import { describe, it, expect, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { server } from '../../test/msw/server'
import { renderWithProviders } from '../../test/utils'
import { TerminalPage } from './TerminalPage'

// 페이지 로직(탭 추가/닫기, 미지원 안내)에 집중 — xterm/WebSocket을 쓰는 TerminalTab은
// 더미로 대체하고 렌더된 탭 수만 확인한다(연동은 TerminalTab.test.tsx에서 검증).
vi.mock('./TerminalTab', () => ({
  TerminalTab: ({ hidden }: { hidden: boolean }) => (
    <div data-testid="terminal-tab" data-hidden={hidden} />
  ),
}))

describe('TerminalPage', () => {
  it('shows a notice when the terminal is unavailable', async () => {
    server.use(
      http.get('/api/terminal/info', () =>
        HttpResponse.json({ available: false, reason: '터미널은 Linux/WSL·Docker 환경에서만 지원된다' }),
      ),
    )
    renderWithProviders(<TerminalPage />)
    expect(await screen.findByText('터미널을 사용할 수 없습니다.')).toBeInTheDocument()
    expect(screen.getByText(/Linux\/WSL·Docker 환경에서만/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '+ 새 터미널' })).not.toBeInTheDocument()
  })

  it('opens a tab automatically when available and adds more on demand', async () => {
    renderWithProviders(<TerminalPage />)
    // 사용 가능하면 첫 탭이 자동으로 열린다
    await waitFor(() => expect(screen.getAllByTestId('terminal-tab')).toHaveLength(1))

    await userEvent.click(screen.getByRole('button', { name: '+ 새 터미널' }))
    expect(screen.getAllByTestId('terminal-tab')).toHaveLength(2)
    // 활성 탭 하나만 보이고 나머지는 hidden
    const visible = screen.getAllByTestId('terminal-tab').filter((el) => el.dataset.hidden === 'false')
    expect(visible).toHaveLength(1)
  })

  it('closes a tab', async () => {
    renderWithProviders(<TerminalPage />)
    await waitFor(() => expect(screen.getAllByTestId('terminal-tab')).toHaveLength(1))
    await userEvent.click(screen.getByRole('button', { name: '+ 새 터미널' }))
    expect(screen.getAllByTestId('terminal-tab')).toHaveLength(2)

    // 첫 탭 닫기 → 1개 남는다
    await userEvent.click(screen.getByRole('button', { name: /탭 닫기 터미널 1/ }))
    expect(screen.getAllByTestId('terminal-tab')).toHaveLength(1)
  })
})
