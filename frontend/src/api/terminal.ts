import { apiFetch } from '../lib/apiClient'

export interface TerminalInfo {
  available: boolean
  reason: string
}

// 터미널 사용 가능 여부(플랫폼/설정) 조회
export function getTerminalInfo(): Promise<TerminalInfo> {
  return apiFetch<TerminalInfo>('/terminal/info')
}

// 터미널 WebSocket URL — 현재 오리진 기준(dev는 vite 프록시가 8000으로 넘긴다)
export function terminalWsUrl(): string {
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${proto}//${window.location.host}/api/terminal/ws`
}
