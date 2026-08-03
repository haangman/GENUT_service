import type { TranslateParams } from '../../lib/i18n'
import type { Job } from '../../types/api'

// 종료(terminal) 상태 집합 — 로그 폴링 중단/재수행 가능 판정에 사용
export const TERMINAL = new Set(['done', 'failed', 'canceled', 'interrupted'])

// 파일명용 타임스탬프: YYYYMMDD-HHMMSS
export function formatStamp(date: Date): string {
  const p = (n: number) => String(n).padStart(2, '0')
  return (
    `${date.getFullYear()}${p(date.getMonth() + 1)}${p(date.getDate())}` +
    `-${p(date.getHours())}${p(date.getMinutes())}${p(date.getSeconds())}`
  )
}

// 로컬 시각 표시: YYYY-MM-DD HH:MM:SS (없으면 '-')
export function formatDateTime(iso: string | null): string {
  if (!iso) return '-'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '-'
  const p = (n: number) => String(n).padStart(2, '0')
  return (
    `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ` +
    `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
  )
}

// 총 수행 시간(시작~종료). 종료 전이면 현재까지 경과 + '(진행 중)', 미시작이면 '-'.
// runningLabel: 진행 중 표시 문구(i18n — 호출부가 번역된 문구를 넘길 수 있다).
export function formatDuration(
  startIso: string | null,
  endIso: string | null,
  runningLabel = '진행 중',
): string {
  if (!startIso) return '-'
  const start = new Date(startIso).getTime()
  const end = endIso ? new Date(endIso).getTime() : Date.now()
  if (Number.isNaN(start) || Number.isNaN(end) || end < start) return '-'
  const totalSec = Math.floor((end - start) / 1000)
  const h = Math.floor(totalSec / 3600)
  const m = Math.floor((totalSec % 3600) / 60)
  const s = totalSec % 60
  const p = (n: number) => String(n).padStart(2, '0')
  const base = h > 0 ? `${h}:${p(m)}:${p(s)}` : `${m}:${p(s)}`
  return endIso ? base : `${base} (${runningLabel})`
}

// 결과 컬럼 표시: 짧은 요약만 보여준다. 긴 에러 로그(job.error)는 컬럼에 넣지 않고
// 상태 기반의 간단한 설명으로 대체한다(원문 로그는 행을 펼친 로그 뷰어/다운로드에서 확인).
export function jobResultLabel(job: Job): string {
  if (job.result_summary) return job.result_summary
  switch (job.status) {
    case 'done':
      return '완료'
    case 'failed':
      return '실패로 실행이 중단됨.'
    case 'interrupted':
      return '서버 재시작으로 실행이 중단됨.'
    case 'canceled':
      return '강제 종료됨'
    default:
      return ''
  }
}

// 대상 컬럼 표시값. text는 i18n 키(다중 파일이면 플레이스홀더 포함)라 호출부가
// `t(text, params)`로 번역한다. title은 잘린 이름의 전체 경로를 담는 툴팁이다.
export interface JobTarget {
  text: string
  params?: TranslateParams
  title: string
}

// 경로 구분자는 서버에서 '/'로 정규화되지만, 구 데이터의 '\'도 방어적으로 처리한다.
function baseName(rel: string): string {
  const parts = rel.split(/[\\/]/)
  return parts[parts.length - 1] || rel
}

// job이 어떤 파일의 어떤 함수를 대상으로 하는지 한 줄로 요약한다.
// 로그를 펼치지 않아도 이력 표에서 바로 확인할 수 있게 하는 것이 목적이다.
// - 파일 1개 + 함수 지정 → `parser.c :: parse_line`
// - 파일 1개, 파일 전체   → `parser.c`
// - 파일 여러 개          → `main.c 외 3개`
// - 대상 파일 없음(스캔/변경 감지 준비 job) → `-`
export function jobTargetLabel(job: Pick<Job, 'file_list' | 'function_name'>): JobTarget {
  const files = job.file_list ?? []
  if (files.length === 0) return { text: '-', title: '' }

  const func = job.function_name ? ` :: ${job.function_name}` : ''
  if (files.length === 1) {
    return { text: `${baseName(files[0])}${func}`, title: files[0] }
  }
  // 첫 파일만 이름으로 보여주고 나머지는 개수로 접는다. 전체 목록은 툴팁에서 본다.
  return {
    text: '{name} 외 {count}개{func}',
    params: { name: baseName(files[0]), count: files.length - 1, func },
    title: files.join('\n'),
  }
}

// job 종류 badge: GENUT 실행 vs 준비 작업(스캔/변경 감지).
// GENUT 실행 job은 배정된 인스턴스 이름(예: GENUT1)을 보여준다(미배정이면 'GENUT').
export function jobKindLabel(job: Pick<Job, 'kind'> & { genut_name?: string | null }): string {
  switch (job.kind) {
    case 'auto_scan':
      return '스캔'
    case 'auto_diff':
      return '변경 감지'
    default:
      return job.genut_name ?? 'GENUT' // kind가 없는 구 데이터도 GENUT으로 본다
  }
}

export function jobKindBadgeClass(kind: string | undefined): string {
  switch (kind) {
    case 'auto_scan':
    case 'auto_diff':
      return 'badge badge-neutral'
    default:
      return 'badge badge-primary'
  }
}

export function jobBadgeClass(status: string): string {
  switch (status) {
    case 'done':
      return 'badge badge-success'
    case 'running':
      return 'badge badge-primary'
    case 'failed':
    case 'canceled':
      return 'badge badge-danger'
    case 'interrupted':
      return 'badge badge-warn'
    default:
      return 'badge badge-neutral'
  }
}
