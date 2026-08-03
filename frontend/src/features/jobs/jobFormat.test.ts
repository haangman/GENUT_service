import { describe, it, expect, vi } from 'vitest'
import { formatDuration, jobTargetLabel } from './jobFormat'

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

describe('jobTargetLabel', () => {
  it('함수가 지정된 job은 파일명 :: 함수명으로 보여준다', () => {
    const target = jobTargetLabel({ file_list: ['src/parser.c'], function_name: 'parse_line' })
    expect(target.text).toBe('parser.c :: parse_line')
    expect(target.params).toBeUndefined()
    // 툴팁에는 잘리지 않은 전체 상대경로가 남는다(동명 파일 구분용)
    expect(target.title).toBe('src/parser.c')
  })

  it('파일 전체 job(함수 미지정)은 파일명만 보여준다', () => {
    const target = jobTargetLabel({ file_list: ['src/math/vector2d.cpp'], function_name: null })
    expect(target.text).toBe('vector2d.cpp')
    expect(target.title).toBe('src/math/vector2d.cpp')
  })

  it('파일이 여러 개면 첫 파일 + 나머지 개수로 요약한다', () => {
    const target = jobTargetLabel({
      file_list: ['src/main.c', 'src/a.c', 'src/b.c', 'src/c.c'],
      function_name: null,
    })
    expect(target.text).toBe('{name} 외 {count}개{func}')
    expect(target.params).toEqual({ name: 'main.c', count: 3, func: '' })
    // 툴팁은 전체 목록(줄바꿈)
    expect(target.title).toBe('src/main.c\nsrc/a.c\nsrc/b.c\nsrc/c.c')
  })

  it('다중 파일에 함수까지 지정되면 함수명을 뒤에 붙인다', () => {
    const target = jobTargetLabel({
      file_list: ['src/main.c', 'src/a.c'],
      function_name: 'do_work',
    })
    expect(target.params).toEqual({ name: 'main.c', count: 1, func: ' :: do_work' })
  })

  it('대상 파일이 없는 준비 job(스캔/변경 감지)은 -', () => {
    const target = jobTargetLabel({ file_list: [], function_name: null })
    expect(target.text).toBe('-')
    expect(target.title).toBe('')
  })
})
