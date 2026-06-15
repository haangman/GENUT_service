import type { TestGenerationMode } from '../../types/api'

// 모드별 소스 파일 확장자 allowlist (폴더 가져오기에서 사용).
// 과소 수집보다 과다 수집이 낫다 — 최종 판정은 compile-check가 한다.
const SOURCE_EXTS: Record<TestGenerationMode, string[]> = {
  c: ['.c', '.h'],
  cpp: ['.cpp', '.cc', '.cxx', '.c', '.hpp', '.hh', '.h'],
  kunit: ['.c', '.h'],
}

export function makeIsSourceFile(mode: TestGenerationMode): (name: string) => boolean {
  const exts = SOURCE_EXTS[mode]
  return (name: string) => exts.some((ext) => name.toLowerCase().endsWith(ext))
}
