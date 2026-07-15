import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render } from '@testing-library/react'
import { LangProvider } from '../../lib/i18n'

// xterm/addon-fit/CSS를 가볍게 모킹한다(실제 렌더/캔버스 없이 연동 로직만 검증)
const onDataCbs: Array<(data: string) => void> = []
vi.mock('@xterm/xterm', () => ({
  Terminal: class {
    cols = 80
    rows = 24
    loadAddon() {}
    open() {}
    focus() {}
    write() {}
    onData(cb: (data: string) => void) {
      onDataCbs.push(cb)
      return { dispose() {} }
    }
    dispose() {}
  },
}))
vi.mock('@xterm/addon-fit', () => ({ FitAddon: class { fit() {} } }))
vi.mock('@xterm/xterm/css/xterm.css', () => ({}))

class MockWebSocket {
  static OPEN = 1
  static instances: MockWebSocket[] = []
  readyState = MockWebSocket.OPEN
  binaryType = ''
  sent: string[] = []
  closed = false
  onopen: (() => void) | null = null
  onmessage: ((e: unknown) => void) | null = null
  onclose: (() => void) | null = null
  constructor(public url: string) {
    MockWebSocket.instances.push(this)
  }
  send(data: string) {
    this.sent.push(data)
  }
  close() {
    this.closed = true
  }
}

import { TerminalTab } from './TerminalTab'

function renderTab(hidden = false) {
  return render(
    <LangProvider>
      <TerminalTab hidden={hidden} />
    </LangProvider>,
  )
}

describe('TerminalTab', () => {
  beforeEach(() => {
    onDataCbs.length = 0
    MockWebSocket.instances = []
    vi.stubGlobal('WebSocket', MockWebSocket)
    vi.stubGlobal(
      'ResizeObserver',
      class {
        observe() {}
        disconnect() {}
      },
    )
  })
  afterEach(() => vi.unstubAllGlobals())

  it('opens a WebSocket to the terminal endpoint and sends resize on open', async () => {
    renderTab()
    expect(MockWebSocket.instances).toHaveLength(1)
    const ws = MockWebSocket.instances[0]
    expect(ws.url).toContain('/api/terminal/ws')
    expect(ws.binaryType).toBe('arraybuffer')

    ws.onopen?.()
    // 크기 동기화는 레이아웃 확정 후(다음 애니메이션 프레임) 이뤄진다
    await new Promise((resolve) => requestAnimationFrame(() => resolve(null)))
    const resize = ws.sent.map((s) => JSON.parse(s)).find((m) => m.type === 'resize')
    expect(resize).toMatchObject({ type: 'resize', cols: 80, rows: 24 })
  })

  it('forwards terminal input to the WebSocket as JSON', () => {
    renderTab()
    const ws = MockWebSocket.instances[0]
    // xterm onData 콜백을 통해 사용자가 'ls' 입력한 상황을 흉내낸다
    onDataCbs[0]?.('ls\r')
    const input = ws.sent.map((s) => JSON.parse(s)).find((m) => m.type === 'input')
    expect(input).toEqual({ type: 'input', data: 'ls\r' })
  })

  it('closes the WebSocket on unmount', () => {
    const { unmount } = renderTab()
    const ws = MockWebSocket.instances[0]
    unmount()
    expect(ws.closed).toBe(true)
  })
})
