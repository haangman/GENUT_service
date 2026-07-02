import { describe, it, expect, vi } from 'vitest'
import { formatDuration } from './jobFormat'

describe('formatDuration', () => {
  it('완료된 job은 시작~종료 차이를 고정 표시한다', () => {
    expect(formatDuration('2026-06-15T00:00:00Z', '2026-06-15T00:01:30Z')).toBe('1:30')
  })

  it('실행 중 job은 현재 시각까지의 경과를 (진행 중)으로 표시한다', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-06-15T00:00:45Z'))
    // 종료 전(endIso=null)이면 now-start 경과 → 실시간 갱신의 근거
    expect(formatDuration('2026-06-15T00:00:00Z', null)).toBe('0:45 (진행 중)')
    vi.setSystemTime(new Date('2026-06-15T00:01:07Z'))
    expect(formatDuration('2026-06-15T00:00:00Z', null)).toBe('1:07 (진행 중)')
    vi.useRealTimers()
  })

  it('미시작(시작 시각 없음) job은 -', () => {
    expect(formatDuration(null, null)).toBe('-')
  })
})
