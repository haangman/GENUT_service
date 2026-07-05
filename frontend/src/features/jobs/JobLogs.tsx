import { memo, useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { getJobLogs, rerunJob } from '../../api/jobs'
import { TERMINAL, formatStamp } from './jobFormat'

// 로그 패널에 표시하는 최대 줄 수. 수만 줄을 한 텍스트 노드로 올리면 스크롤할 때마다
// 거대한 블록의 레이아웃/페인트가 반복되어 페이지 전체가 버벅인다 — 최근 줄만 표시하고
// 전체는 '로그 저장'으로 받는다(저장은 누적 전체를 담는다).
const MAX_RENDER_LINES = 2000

// 증분 폴링: 마지막으로 받은 이벤트 id 이후(`?since=`)만 받아 누적한다.
// 작업이 종료(done/failed)되면 마지막 한 번만 더 받아오고 폴링을 멈춘다.
// memo: 부모 테이블이 폴링으로 리렌더돼도 props(jobId/status)가 같으면 다시 그리지 않는다.
export const JobLogs = memo(function JobLogs({
  jobId,
  status,
  pollMs = 1500,
}: {
  jobId: number
  status: string
  pollMs?: number
}) {
  // 전체 줄은 ref에 누적(저장용), 렌더는 version 증가로만 트리거해 최근 줄만 그린다.
  const linesRef = useRef<string[]>([])
  const [version, setVersion] = useState(0)
  const cursorRef = useRef(0)
  const preRef = useRef<HTMLPreElement>(null)
  // 사용자가 바닥 근처에 있을 때만 자동 스크롤한다 — 위로 올려 읽는 중에
  // 매 폴링마다 바닥으로 끌어내리면 스크롤이 계속 튄다.
  const stickToBottomRef = useRef(true)
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
    linesRef.current = []
    cursorRef.current = 0
    stickToBottomRef.current = true
    setVersion((v) => v + 1)
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
          for (const event of batch) {
            linesRef.current.push(`[${event.phase ?? '-'}] ${event.message}`)
          }
          setVersion((v) => v + 1)
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

  // 표시 텍스트: 최근 MAX_RENDER_LINES줄만. version이 바뀔 때만 다시 만든다
  // (부모 리렌더마다 전체 join을 반복하지 않는다).
  const { text, hiddenCount } = useMemo(() => {
    const lines = linesRef.current
    const hidden = Math.max(0, lines.length - MAX_RENDER_LINES)
    return {
      text: (hidden > 0 ? lines.slice(hidden) : lines).join('\n'),
      hiddenCount: hidden,
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [version])

  // 새 로그가 들어오면, 사용자가 바닥 근처에 있을 때만 맨 아래로 스크롤
  useEffect(() => {
    const pre = preRef.current
    if (pre && stickToBottomRef.current) pre.scrollTop = pre.scrollHeight
  }, [text])

  const handleScroll = () => {
    const pre = preRef.current
    if (!pre) return
    stickToBottomRef.current = pre.scrollHeight - pre.scrollTop - pre.clientHeight < 40
  }

  // 누적 전체 로그(표시 생략분 포함)를 파일로 저장. 출력 중에도 동작.
  const handleSave = () => {
    const blob = new Blob([linesRef.current.join('\n')], { type: 'text/plain;charset=utf-8' })
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
      {/* 버튼은 제목 바로 옆(왼쪽 정렬)에 둔다 — 우측 정렬이면 테이블이 화면보다 넓을 때
          좌우 스크롤 밖으로 밀려 보이지 않는다 */}
      <div className="mb-2 flex flex-wrap items-center gap-2 text-xs text-muted">
        <span className="font-medium">
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
        {hiddenCount > 0 ? (
          <span className="text-subtle">
            이전 {hiddenCount.toLocaleString()}줄 표시 생략 — 전체는 로그 저장으로 받으세요
          </span>
        ) : null}
      </div>
      <pre
        ref={preRef}
        onScroll={handleScroll}
        data-testid="job-log"
        // 로그는 줄바꿈하지 않고(whitespace-pre) 박스 안에서 상하·좌우로 스크롤한다.
        // 테이블은 table-fixed라 이 긴 로그가 데이터 컬럼 폭을 밀지 않는다.
        // contain: 스크롤러 내부 레이아웃/페인트를 격리해 스크롤 비용을 줄인다.
        className="max-h-64 overflow-auto whitespace-pre rounded-lg p-3 font-mono text-xs leading-relaxed"
        style={{ background: 'var(--code-bg)', color: 'var(--code-fg)', contain: 'content' }}
      >
        {text || '로그 없음'}
      </pre>
    </div>
  )
})
