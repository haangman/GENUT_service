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
  const termRef = useRef<Terminal | null>(null)
  const fitRef = useRef<FitAddon | null>(null)
  const wsRef = useRef<WebSocket | null>(null)

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
    termRef.current = term
    fitRef.current = fit
    wsRef.current = null
    term.loadAddon(fit)
    term.open(container)

    const ws = new WebSocket(terminalWsUrl())
    ws.binaryType = 'arraybuffer'
    wsRef.current = ws

    // 컨테이너에 맞춰 크기를 재계산하고, 열려 있으면 서버 PTY에도 알린다.
    // vim 등 전체화면 앱은 정확한 크기를 모르면 화면·커서가 어긋나 입력이 안 먹는
    // 것처럼 보이므로, 크기 동기화가 핵심이다.
    const syncSize = () => {
      try {
        fit.fit()
      } catch {
        return // 컨테이너가 아직 레이아웃 전(크기 0)이면 다음 기회에 맞춘다
      }
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'resize', cols: term.cols, rows: term.rows }))
      }
    }

    ws.onopen = () => {
      term.focus()
      // 레이아웃이 확정된 다음 프레임에 크기를 맞춰 정확한 값이 서버로 가도록 한다
      requestAnimationFrame(syncSize)
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
    const observer = new ResizeObserver(() => syncSize())
    observer.observe(container)

    return () => {
      observer.disconnect()
      dataSub.dispose()
      ws.close()
      term.dispose()
      termRef.current = null
      fitRef.current = null
      wsRef.current = null
    }
  }, [t])

  // 탭이 다시 보이면: 레이아웃 확정 후 크기를 다시 맞추고(vim이 SIGWINCH로 다시 그림)
  // 포커스를 되돌린다(숨김 동안 크기 변화를 놓쳤거나 포커스를 잃었을 수 있다).
  useEffect(() => {
    if (hidden) return
    const id = requestAnimationFrame(() => {
      const term = termRef.current
      const fit = fitRef.current
      const ws = wsRef.current
      if (!term || !fit) return
      try {
        fit.fit()
      } catch {
        return
      }
      term.focus()
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'resize', cols: term.cols, rows: term.rows }))
      }
    })
    return () => cancelAnimationFrame(id)
  }, [hidden])

  return (
    <div
      ref={containerRef}
      // 클릭 시 입력 포커스를 확실히 잡는다(전체화면 앱 진입 후 포커스 유실 방지)
      onMouseDown={() => termRef.current?.focus()}
      className="h-[70vh] w-full overflow-hidden rounded-lg border border-border bg-[#0b0f17] p-2"
      style={{ display: hidden ? 'none' : 'block' }}
    />
  )
}
