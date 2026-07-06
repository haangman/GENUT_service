import { describe, it, expect } from 'vitest'
import { translate } from './i18n'

describe('translate', () => {
  it('한국어는 키를 그대로 반환한다', () => {
    expect(translate('ko', '저장')).toBe('저장')
  })

  it('영어는 사전의 번역을 반환한다', () => {
    expect(translate('en', '저장')).toBe('Save')
    expect(translate('en', '프로덕트 등록')).toBe('Product Registration')
  })

  it('사전에 없는 키는 영어에서도 한국어 원문으로 폴백한다', () => {
    expect(translate('en', '사전에 없는 문구')).toBe('사전에 없는 문구')
  })

  it('{name} 플레이스홀더를 치환한다', () => {
    expect(translate('ko', '전체 {total}건', { total: 12 })).toBe('전체 12건')
    expect(translate('en', '전체 {total}건', { total: 12 })).toBe('12 total')
    expect(translate('en', '더 보기 ({visible}/{total})', { visible: '200', total: '1,000' })).toBe(
      'Show more (200/1,000)',
    )
  })

  it('params에 없는 플레이스홀더는 그대로 남긴다', () => {
    expect(translate('ko', '전체 {total}건', {})).toBe('전체 {total}건')
  })

  it('서버 데이터(사전 미등록)는 params 없이 그대로 통과한다', () => {
    // jobKindLabel이 반환하는 GENUT 인스턴스 이름 등
    expect(translate('en', 'GENUT1')).toBe('GENUT1')
  })
})
