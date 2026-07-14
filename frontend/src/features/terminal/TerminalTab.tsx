import { useEffect, useRef } from 'react'
import { Terminal } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import '@xterm/xterm/css/xterm.css'
import { terminalWsUrl } from '../../api/terminal'
import { useLang } from '../../lib/i18n'

// 탭 1개 = xterm 인스턴스 1개 + WebSocket 1개(= 셸 프로세스 1개).
// hidden 탭도 언마운트하지 않고 숨겨 세션/스크롤백을 보존한다.
export function TerminalTab({ hidden }: { hidden: boolean }) {
  const { t } = useLang()
  const containerRef = useRef<HTMLDivElement>(null)
  const fitRef = useRef<FitAddon | null>(null)

  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    const term = new Terminal({
      convertEol: false,
      cursorBlink: true,
      fontFamily: 'JetBrains Mono, ui-monospace, monospace',
      fontSize: 13,
      theme: { background: '#0b0f17' },
    })
    const fit = new FitAddon()
    fitRef.current = fit
    term.loadAddon(fit)
    term.open(container)
    try {
      fit.fit()
    } catch {
      // 컨테이너가 아직 레이아웃 전이면 무시(ResizeObserver가 곧 다시 맞춘다)
    }

    const ws = new WebSocket(terminalWsUrl())
    ws.binaryType = 'arraybuffer'

    const sendResize = () => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'resize', cols: term.cols, rows: term.rows }))
      }
    }

    ws.onopen = () => {
      term.focus()
      sendResize()
    }
    ws.onmessage = (event) => {
      // 서버는 PTY 원시 바이트를 보낸다 — xterm이 UTF-8 디코딩을 처리
      if (event.data instanceof ArrayBuffer) {
        term.write(new Uint8Array(event.data))
      } else {
        term.write(String(event.data))
      }
    }
    ws.onclose = () => term.write(t('\r\n[연결이 종료되었습니다]\r\n'))

    const dataSub = term.onData((data) => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'input', data }))
      }
    })

    // 컨테이너 크기 변화 → 맞춤 + 서버에 열/행 전달
    const observer = new ResizeObserver(() => {
      try {
        fit.fit()
        sendResize()
      } catch {
        // 숨김 상태 등으로 크기가 0이면 무시
      }
    })
    observer.observe(container)

    return () => {
      observer.disconnect()
      dataSub.dispose()
      ws.close()
      term.dispose()
      fitRef.current = null
    }
  }, [t])

  // 탭이 다시 보이면 크기를 다시 맞춘다(숨김 동안 리사이즈를 놓쳤을 수 있음)
  useEffect(() => {
    if (!hidden && fitRef.current) {
      try {
        fitRef.current.fit()
      } catch {
        // no-op
      }
    }
  }, [hidden])

  return (
    <div
      ref={containerRef}
      className="h-[70vh] w-full overflow-hidden rounded-lg border border-border bg-[#0b0f17] p-2"
      style={{ display: hidden ? 'none' : 'block' }}
    />
  )
}
