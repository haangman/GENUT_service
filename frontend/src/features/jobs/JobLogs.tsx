import { useEffect, useRef, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { getJobLogs, rerunJob } from '../../api/jobs'
import type { JobEvent } from '../../types/api'
import { TERMINAL, formatStamp } from './jobFormat'

// 증분 폴링: 마지막으로 받은 이벤트 id 이후(`?since=`)만 받아 누적한다.
// 작업이 종료(done/failed)되면 마지막 한 번만 더 받아오고 폴링을 멈춘다.
export function JobLogs({
  jobId,
  status,
  pollMs = 1500,
}: {
  jobId: number
  status: string
  pollMs?: number
}) {
  const [events, setEvents] = useState<JobEvent[]>([])
  const cursorRef = useRef(0)
  const preRef = useRef<HTMLPreElement>(null)
  const terminal = TERMINAL.has(status)

  // 재수행: 동일 입력의 새 job을 큐에 추가한다(완료된 job에서만 가능).
  const queryClient = useQueryClient()
  const rerunMut = useMutation({
    mutationFn: () => rerunJob(jobId),
    onSuccess: (job) => {
      // ['jobs'] prefix 무효화: 모니터링(['jobs','history',…])·auto 이력(['jobs','auto',…]) 모두 갱신
      queryClient.invalidateQueries({ queryKey: ['jobs'] })
      queryClient.invalidateQueries({ queryKey: ['queue'] })
      window.alert(`재수행 요청 완료 (새 job #${job.id})`)
    },
    onError: () => window.alert('재수행 요청에 실패했습니다.'),
  })

  // 선택한 job이 바뀌면 누적 로그와 커서를 초기화
  useEffect(() => {
    setEvents([])
    cursorRef.current = 0
  }, [jobId])

  // 폴링 루프 (terminal이 true가 되면 마지막 1회만 받고 재예약하지 않음)
  useEffect(() => {
    let active = true
    let timer: ReturnType<typeof setTimeout> | undefined
    const poll = async () => {
      try {
        const batch = await getJobLogs(jobId, cursorRef.current)
        if (!active) return
        if (batch.length > 0) {
          cursorRef.current = batch[batch.length - 1].id
          setEvents((prev) => [...prev, ...batch])
        }
      } catch {
        /* 일시 오류는 무시하고 다음 tick에서 재시도 */
      }
      if (active && !terminal) {
        timer = setTimeout(poll, pollMs)
      }
    }
    poll()
    return () => {
      active = false
      if (timer) clearTimeout(timer)
    }
  }, [jobId, terminal, pollMs])

  // 새 로그가 들어오면 맨 아래로 스크롤
  useEffect(() => {
    if (preRef.current) preRef.current.scrollTop = preRef.current.scrollHeight
  }, [events])

  // 현재 화면에 쌓인(=그 순간까지의) 로그를 파일로 저장. 출력 중에도 동작.
  const handleSave = () => {
    const text = events.map((event) => `[${event.phase ?? '-'}] ${event.message}`).join('\n')
    const blob = new Blob([text], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `job_${jobId}_${formatStamp(new Date())}.log`
    document.body.appendChild(anchor)
    anchor.click()
    anchor.remove()
    URL.revokeObjectURL(url)
  }

  return (
    <div>
      <div className="mb-2 flex items-center gap-2 text-xs text-muted">
        <span className="mr-auto font-medium">
          job #{jobId} 로그 {terminal ? '(완료)' : '· 실행 중…'}
        </span>
        <button type="button" onClick={handleSave} className="btn btn-sm">
          로그 저장
        </button>
        {terminal ? (
          <button
            type="button"
            onClick={() => rerunMut.mutate()}
            disabled={rerunMut.isPending}
            className="btn btn-sm"
          >
            {rerunMut.isPending ? '재수행 중…' : '재수행'}
          </button>
        ) : null}
      </div>
      <pre
        ref={preRef}
        data-testid="job-log"
        // 로그는 줄바꿈하지 않고(whitespace-pre) 박스 안에서 상하·좌우로 스크롤한다.
        // 테이블은 table-fixed라 이 긴 로그가 데이터 컬럼 폭을 밀지 않는다.
        className="max-h-64 overflow-auto whitespace-pre rounded-lg p-3 font-mono text-xs leading-relaxed"
        style={{ background: 'var(--code-bg)', color: 'var(--code-fg)' }}
      >
        {events.map((event) => `[${event.phase ?? '-'}] ${event.message}`).join('\n') ||
          '로그 없음'}
      </pre>
    </div>
  )
}
